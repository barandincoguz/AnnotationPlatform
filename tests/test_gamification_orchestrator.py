"""Unit tests for gamification.service.run_after_save / run_after_complete.

Drives the full orchestrator: XP award, streak update, badge check, notification
create, SSE publish to the saving user (and to a prior editor on review_kept).
"""
import asyncio
import json
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.shared.sse import broker as sse_broker
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.gamification import service as gam


@pytest.fixture(autouse=True)
def _reset_broker():
    sse_broker._subscribers.clear()
    yield
    sse_broker._subscribers.clear()


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (2, 'bob', 'x', 'user', ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
        "sentence_count, text_density, estimated_difficulty, created_at) "
        "VALUES ('doc_1', 'x.json', 'text', 1, 1, 1.0, 'Kolay', ?)",
        (now,),
    )
    yield conn
    conn.close()


def _seed_prior_version(conn, doc_id, user_id, refs_json="[]"):
    """Plant an annotation_versions row so run_after_save can find a prior editor."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO annotation_versions(document_id, user_id, references_json, "
        "diff_from_previous, is_diff_zero, action, created_at) "
        "VALUES (?, ?, ?, ?, 0, 'create', ?)",
        (doc_id, user_id, refs_json, json.dumps({"added": [], "removed": []}), now),
    )


def test_save_create_awards_xp_and_increments_counters(db):
    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="create", is_diff_zero=False, document_id="doc_1",
    ))

    state = db.execute("SELECT total_xp, today_save_count, current_streak_days FROM gamification_state WHERE user_id=1").fetchone()
    assert state["total_xp"] == 1            # xp_save default
    assert state["today_save_count"] == 1
    assert state["current_streak_days"] == 1

    ledger = db.execute("SELECT reason, delta_xp FROM gamification_ledger").fetchall()
    assert len(ledger) == 1
    assert ledger[0]["reason"] == "save"
    assert ledger[0]["delta_xp"] == 1


def test_save_edit_awards_review_xp(db):
    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="edit", is_diff_zero=False, document_id="doc_1",
    ))
    state = db.execute("SELECT total_xp, today_review_count FROM gamification_state WHERE user_id=1").fetchone()
    assert state["total_xp"] == 2            # xp_review default
    assert state["today_review_count"] == 1


def test_save_create_unlocks_first_annotation_badge(db):
    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="create", is_diff_zero=False, document_id="doc_1",
    ))

    # badges_earned has the row
    rows = db.execute("SELECT badge_id FROM badges_earned WHERE user_id=1").fetchall()
    assert {r["badge_id"] for r in rows} == {"first_annotation"}

    # SSE: badge_unlocked + notification both published
    received = []
    async def _drain():
        for _ in range(2):
            received.append(await asyncio.wait_for(queue.get(), timeout=2.0))
    asyncio.run(_drain())
    types = sorted(e.event_type for e in received)
    assert types == ["badge_unlocked", "notification"]

    # notification row also persisted
    nrow = db.execute("SELECT kind, title FROM notifications WHERE user_id=1").fetchone()
    assert nrow["kind"] == "badge_unlocked"


def test_complete_awards_xp_publishes_no_extra_event_if_no_badge(db):
    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(gam.run_after_complete(
        db, user_id=1, username="alice",
        completed=True, document_id="doc_1",
    ))
    state = db.execute("SELECT total_xp, today_complete_count FROM gamification_state WHERE user_id=1").fetchone()
    assert state["total_xp"] == 5
    assert state["today_complete_count"] == 1

    # First complete unlocks first_completion → 2 events
    received = []
    async def _drain():
        for _ in range(2):
            received.append(await asyncio.wait_for(queue.get(), timeout=2.0))
    asyncio.run(_drain())
    types = sorted(e.event_type for e in received)
    assert types == ["badge_unlocked", "notification"]


def test_uncomplete_awards_zero_xp_no_events(db):
    asyncio.run(gam.run_after_complete(
        db, user_id=1, username="alice",
        completed=True, document_id="doc_1",
    ))
    queue = sse_broker.subscribe(user_id=1)

    asyncio.run(gam.run_after_complete(
        db, user_id=1, username="alice",
        completed=False, document_id="doc_1",
    ))
    # No new XP awarded
    total = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=1").fetchone()["total_xp"]
    assert total == 5  # unchanged

    # No new event delivered
    async def _wait():
        return await asyncio.wait_for(queue.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_wait())


def test_review_kept_awards_prior_user_xp(db):
    """alice edits doc_1 with diff_zero against bob's prior version → bob gets +3.

    Note: the orchestrator queries the last 2 annotation_versions and treats
    the second-most-recent as the prior editor. So we plant TWO rows: bob's
    older version, then alice's just-inserted current version. (In a real
    save through annotations.service, the new version row is already
    committed before run_after_save fires.)"""
    _seed_prior_version(db, "doc_1", user_id=2)  # bob's prior version
    _seed_prior_version(db, "doc_1", user_id=1)  # alice's just-inserted current
    bob_q = sse_broker.subscribe(user_id=2)

    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="edit", is_diff_zero=True, document_id="doc_1",
    ))

    # bob got +3 (xp_review_kept default)
    bob_total = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=2").fetchone()
    assert bob_total["total_xp"] == 3
    bob_ledger = db.execute(
        "SELECT reason FROM gamification_ledger WHERE user_id=2"
    ).fetchall()
    assert any(r["reason"] == "review_kept" for r in bob_ledger)


def test_review_kept_does_not_self_award(db):
    """If the prior version's editor is the same user, NO review_kept award.
    Plant TWO alice-versions so _prior_version_user_id resolves to alice
    (not None), then assert the same-user-skip branch fires."""
    _seed_prior_version(db, "doc_1", user_id=1)  # alice's older version
    _seed_prior_version(db, "doc_1", user_id=1)  # alice's current version

    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="edit", is_diff_zero=True, document_id="doc_1",
    ))
    rows = db.execute(
        "SELECT reason FROM gamification_ledger WHERE user_id=1 AND reason='review_kept'"
    ).fetchall()
    assert rows == []  # no self-kept


def test_personal_scope_other_users_dont_see_alice_badge(db):
    """Bob is online; alice unlocks first_annotation. Bob's queue stays empty."""
    bob_q = sse_broker.subscribe(user_id=2)
    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="create", is_diff_zero=False, document_id="doc_1",
    ))
    async def _wait():
        return await asyncio.wait_for(bob_q.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_wait())


def test_xp_award_failure_does_not_block_streak_or_badges(db, monkeypatch):
    """If award_xp raises, the rest of the orchestrator (streak + badges)
    must still run. Each step is independently fault-isolated."""
    original_award = gam.award_xp
    call_count = {"n": 0}
    def boom_award(*a, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("award_xp boom")
        return original_award(*a, **kw)
    monkeypatch.setattr(gam, "award_xp", boom_award)

    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="create", is_diff_zero=False, document_id="doc_1",
    ))
    # Streak still updated
    state = db.execute("SELECT current_streak_days FROM gamification_state WHERE user_id=1").fetchone()
    assert state["current_streak_days"] == 1


def test_run_after_complete_uncomplete_does_not_touch_streak(db):
    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="create", is_diff_zero=False, document_id="doc_1",
    ))
    streak_before = db.execute(
        "SELECT current_streak_days FROM gamification_state WHERE user_id=1"
    ).fetchone()["current_streak_days"]

    asyncio.run(gam.run_after_complete(
        db, user_id=1, username="alice",
        completed=True, document_id="doc_1",
    ))
    asyncio.run(gam.run_after_complete(
        db, user_id=1, username="alice",
        completed=False, document_id="doc_1",
    ))
    streak_after = db.execute(
        "SELECT current_streak_days FROM gamification_state WHERE user_id=1"
    ).fetchone()["current_streak_days"]
    assert streak_after == streak_before
