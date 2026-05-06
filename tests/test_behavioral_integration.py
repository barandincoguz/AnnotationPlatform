"""Integration tests: behavioral detectors fire through POST /api/annotations.

Drives the full HTTP path so a regression in routes.py wiring is caught.
"""
import asyncio
from datetime import datetime, timedelta, timezone

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
        "fikra": "1", "bent": "a", "source_text": "kısa atıf",
    }
    base.update(overrides)
    return base


def test_save_triggers_speed_warning_after_threshold(passed_user, ingest_doc):
    """5 prior saves planted, 6th save through HTTP triggers speed_warning."""
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_speed_x")

    # Plant 5 prior annotation_save activity_events (just under threshold)
    conn = connect(config.DB_PATH)
    try:
        now = datetime.now(timezone.utc)
        for i in range(5):
            conn.execute(
                "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
                (user_id, "annotation_save", (now - timedelta(seconds=10 * (i + 1))).isoformat()),
            )
    finally:
        conn.close()

    queue = sse_broker.subscribe(user_id=user_id)

    r = c.post("/api/annotations", json={
        "document_id": "doc_speed_x", "references": [_ref()],
    })
    assert r.status_code == 200

    # We should see TWO events on the queue: annotation_saved (broadcast) + speed_warning (personal).
    received_types = []
    async def _drain():
        for _ in range(2):
            received_types.append(
                (await asyncio.wait_for(queue.get(), timeout=2.0)).event_type
            )
    asyncio.run(_drain())
    assert "speed_warning" in received_types

    # And the behavioral row exists
    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT detector, actual_value FROM behavioral_events WHERE user_id=?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    assert any(r["detector"] == "speed_warning" for r in rows)


def test_save_with_long_source_text_triggers_char_limit(passed_user, ingest_doc):
    """Single save with source_text > alert threshold triggers char_limit_warning."""
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_chars_x")

    queue = sse_broker.subscribe(user_id=user_id)

    r = c.post("/api/annotations", json={
        "document_id": "doc_chars_x",
        "references": [_ref(source_text="x" * 700)],
    })
    assert r.status_code == 200

    received_types = []
    async def _drain():
        for _ in range(2):
            received_types.append(
                (await asyncio.wait_for(queue.get(), timeout=2.0)).event_type
            )
    asyncio.run(_drain())
    assert "char_limit_warning" in received_types

    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT detector FROM behavioral_events WHERE user_id=?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    assert any(r["detector"] == "char_limit_warning" for r in rows)


def test_save_with_short_payload_no_behavioral_events(passed_user, ingest_doc):
    """Quiet save → no behavioral rows, no personal SSE events (annotation_saved still
    broadcasts but that's separate)."""
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_quiet_x")

    r = c.post("/api/annotations", json={
        "document_id": "doc_quiet_x", "references": [_ref()],
    })
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute("SELECT * FROM behavioral_events WHERE user_id=?", (user_id,)).fetchall()
    finally:
        conn.close()
    assert rows == []


def test_detector_failure_does_not_500_the_save(passed_user, ingest_doc, monkeypatch):
    """If run_after_save explodes, the save still returns 200 — detectors are best-effort."""
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_isolate_x")

    async def boom(*args, **kwargs):
        raise RuntimeError("orchestrator exploded")
    monkeypatch.setattr(
        "backend.annotations.routes.behavioral_service.run_after_save", boom
    )

    r = c.post("/api/annotations", json={
        "document_id": "doc_isolate_x", "references": [_ref()],
    })
    assert r.status_code == 200

    # And the actual annotation row is persisted
    conn = connect(config.DB_PATH)
    try:
        row = conn.execute(
            "SELECT 1 FROM annotations WHERE document_id=?", ("doc_isolate_x",)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
