"""Integration tests: gamification fires through annotation HTTP routes."""
import asyncio
from datetime import datetime, timezone

import pytest
from backend.shared.sse import broker as sse_broker
from backend.shared.db import connect
from backend import config


@pytest.fixture(autouse=True)
def _reset_broker():
    sse_broker._subscribers.clear()
    yield
    sse_broker._subscribers.clear()


def _ref(**overrides):
    base = {
        "kanun_no": "5520", "kanun_ad": "KVK", "madde": "5",
        "fikra": "1", "bent": "a", "source_text": "kısa",
    }
    base.update(overrides)
    return base


def test_first_save_awards_xp_and_unlocks_first_annotation(passed_user, ingest_doc):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_g1")

    queue = sse_broker.subscribe(user_id=user_id)
    r = c.post("/api/annotations", json={
        "document_id": "doc_g1", "references": [_ref()],
    })
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        state = conn.execute(
            "SELECT total_xp, today_save_count, current_streak_days "
            "FROM gamification_state WHERE user_id=?", (user_id,),
        ).fetchone()
        badges = conn.execute(
            "SELECT badge_id FROM badges_earned WHERE user_id=?", (user_id,),
        ).fetchall()
    finally:
        conn.close()
    assert state["total_xp"] == 1
    assert state["today_save_count"] == 1
    assert state["current_streak_days"] == 1
    assert {b["badge_id"] for b in badges} == {"first_annotation"}


def test_skip_increments_skip_count_no_xp(passed_user, ingest_doc):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_g_skip")
    r = c.post("/api/annotations/doc_g_skip/skip")
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        state = conn.execute(
            "SELECT total_xp, today_skip_count FROM gamification_state WHERE user_id=?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    assert state["total_xp"] == 0
    assert state["today_skip_count"] == 1


def test_complete_awards_xp_and_unlocks_first_completion(passed_user, ingest_doc):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_g_complete")
    # Need an annotation row before complete works
    r = c.post("/api/annotations", json={
        "document_id": "doc_g_complete", "references": [_ref()],
    })
    assert r.status_code == 200

    queue = sse_broker.subscribe(user_id=user_id)
    r = c.post("/api/annotations/doc_g_complete/complete", json={"completed": True})
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        total = conn.execute(
            "SELECT total_xp FROM gamification_state WHERE user_id=?", (user_id,),
        ).fetchone()["total_xp"]
        badges = conn.execute(
            "SELECT badge_id FROM badges_earned WHERE user_id=?", (user_id,),
        ).fetchall()
    finally:
        conn.close()
    # 1 (save) + 5 (complete) = 6
    assert total == 6
    assert "first_completion" in {b["badge_id"] for b in badges}


def test_uncomplete_does_not_decrement_xp(passed_user, ingest_doc):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_g_uc")
    c.post("/api/annotations", json={"document_id": "doc_g_uc", "references": [_ref()]})
    c.post("/api/annotations/doc_g_uc/complete", json={"completed": True})
    c.post("/api/annotations/doc_g_uc/complete", json={"completed": False})
    conn = connect(config.DB_PATH)
    try:
        total = conn.execute(
            "SELECT total_xp FROM gamification_state WHERE user_id=?", (user_id,),
        ).fetchone()["total_xp"]
    finally:
        conn.close()
    # 1 (save) + 5 (complete) + 0 (uncomplete) = 6 — no decrement
    assert total == 6


def test_orchestrator_failure_does_not_500_save(passed_user, ingest_doc, monkeypatch):
    """If gamification.run_after_save explodes, the save still returns 200."""
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_g_isolate")

    async def boom(*args, **kwargs):
        raise RuntimeError("orchestrator exploded")
    monkeypatch.setattr(
        "backend.annotations.routes.gamification_service.run_after_save", boom
    )
    r = c.post("/api/annotations", json={
        "document_id": "doc_g_isolate", "references": [_ref()],
    })
    assert r.status_code == 200


def test_review_kept_post_hoc_award_through_http(second_passed_user, ingest_doc):
    """bob saves doc_x → alice edits doc_x with the same references (diff_zero)
    → bob gets +3 xp_review_kept."""
    ctx = second_passed_user
    c = ctx["client"]
    bob_id = ctx["bob"]["id"]
    ingest_doc("doc_g_kept")

    ctx["login"]("bob")
    r = c.post("/api/annotations", json={
        "document_id": "doc_g_kept", "references": [_ref()],
    })
    assert r.status_code == 200

    ctx["login"]("alice")
    r = c.post("/api/annotations", json={
        "document_id": "doc_g_kept", "references": [_ref()],  # identical → diff_zero
    })
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        bob_total = conn.execute(
            "SELECT total_xp FROM gamification_state WHERE user_id=?", (bob_id,),
        ).fetchone()["total_xp"]
    finally:
        conn.close()
    # bob: 1 (save) + 3 (review_kept) = 4
    assert bob_total == 4
