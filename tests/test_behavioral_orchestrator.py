"""Unit tests for behavioral.service.run_after_save orchestrator.

Verifies that both detectors are evaluated, hits are logged to
behavioral_events with full context, and personal SSE events are published.
A failure in one detector must not block the other.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from backend.shared.db import connect
from backend.shared.sse import broker as sse_broker
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.behavioral import service as behavioral


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
    yield conn
    conn.close()


def _ref(**overrides):
    base = {
        "kanun_no": "5520", "kanun_ad": "KVK", "madde": "5",
        "fikra": "1", "bent": "a", "source_text": "kısa",
    }
    base.update(overrides)
    return base


def test_no_hits_no_events_no_logs(db):
    """Quiet save with short refs → no SSE events, no behavioral rows."""
    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice", references=[_ref()],
    ))
    rows = db.execute("SELECT * FROM behavioral_events").fetchall()
    assert rows == []
    # No events delivered
    async def _wait():
        return await asyncio.wait_for(queue.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_wait())


def test_speed_warning_logs_and_publishes(db):
    """6 saves in 5min → speed_warning logged + SSE personal event."""
    now = datetime.now(timezone.utc)
    for i in range(6):
        db.execute(
            "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
            (1, "annotation_save", (now - timedelta(seconds=10 * i)).isoformat()),
        )

    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice", references=[_ref()],
    ))

    rows = db.execute(
        "SELECT detector, threshold_value, actual_value, context_json FROM behavioral_events"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["detector"] == "speed_warning"
    assert rows[0]["threshold_value"] == 5
    assert rows[0]["actual_value"] == 6
    ctx = json.loads(rows[0]["context_json"])
    assert ctx["recent_save_count"] == 6

    async def _wait():
        return await asyncio.wait_for(queue.get(), timeout=2.0)
    event = asyncio.run(_wait())
    assert event.event_type == "speed_warning"
    assert event.data["recent_save_count"] == 6
    assert event.data["window_seconds"] == 300
    assert "message" in event.data


def test_char_limit_warning_logs_and_publishes(db):
    """Long source_text → char_limit_warning logged + SSE personal event."""
    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice",
        references=[_ref(source_text="x" * 700)],
    ))

    rows = db.execute(
        "SELECT detector, actual_value FROM behavioral_events WHERE detector='char_limit_warning'"
    ).fetchall()
    assert len(rows) == 1
    # actual_value carries the worst length seen
    assert rows[0]["actual_value"] == 700

    async def _wait():
        return await asyncio.wait_for(queue.get(), timeout=2.0)
    event = asyncio.run(_wait())
    assert event.event_type == "char_limit_warning"
    assert event.data["level"] == "alert"
    assert event.data["warn_threshold"] == 300
    assert event.data["alert_threshold"] == 600


def test_both_detectors_fire_independently(db):
    """If both fire, both rows logged + both SSE events delivered."""
    now = datetime.now(timezone.utc)
    for i in range(7):
        db.execute(
            "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
            (1, "annotation_save", (now - timedelta(seconds=10 * i)).isoformat()),
        )

    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice",
        references=[_ref(source_text="y" * 400)],
    ))

    detectors = sorted(
        r["detector"] for r in db.execute(
            "SELECT detector FROM behavioral_events ORDER BY id"
        ).fetchall()
    )
    assert detectors == ["char_limit_warning", "speed_warning"]

    received = []
    async def _drain():
        for _ in range(2):
            received.append(await asyncio.wait_for(queue.get(), timeout=2.0))
    asyncio.run(_drain())
    types = sorted(e.event_type for e in received)
    assert types == ["char_limit_warning", "speed_warning"]


def test_only_publishes_to_saving_user_not_broadcast(db, monkeypatch):
    """Personal events: bob (online) must NOT see alice's speed_warning."""
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (2, 'bob', 'x', 'user', ?, ?)",
        (now.isoformat(), now.isoformat()),
    )
    for i in range(7):
        db.execute(
            "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
            (1, "annotation_save", (now - timedelta(seconds=10 * i)).isoformat()),
        )

    alice_q = sse_broker.subscribe(user_id=1)
    bob_q = sse_broker.subscribe(user_id=2)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice", references=[_ref()],
    ))

    # alice receives
    async def _alice():
        return await asyncio.wait_for(alice_q.get(), timeout=2.0)
    ev = asyncio.run(_alice())
    assert ev.event_type == "speed_warning"

    # bob does not
    async def _bob():
        return await asyncio.wait_for(bob_q.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_bob())


def test_speed_detector_failure_does_not_block_char_limit(db, monkeypatch):
    """If speed detector raises, char_limit still fires."""
    def boom(*a, **kw):
        raise RuntimeError("speed detector exploded")
    monkeypatch.setattr(behavioral, "detect_speed_warning", boom)

    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice",
        references=[_ref(source_text="z" * 400)],
    ))

    detectors = [r["detector"] for r in db.execute(
        "SELECT detector FROM behavioral_events"
    ).fetchall()]
    assert detectors == ["char_limit_warning"]
