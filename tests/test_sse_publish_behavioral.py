"""Verify behavioral detectors publish personal SSE events to the saving
user only — never as broadcast. Covers the same ground as the integration
tests but pins the personal-vs-broadcast invariant explicitly so a future
refactor that switches to publish_broadcast would be caught here."""
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
        "fikra": "1", "bent": "a", "source_text": "kısa",
    }
    base.update(overrides)
    return base


def test_speed_warning_only_to_saving_user(second_passed_user, ingest_doc):
    """Bob is online; alice trips the speed_warning. Bob must NOT see it."""
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_publ_speed")
    alice_id = ctx["alice"]["id"]
    bob_id = ctx["bob"]["id"]

    # Plant 5 prior saves for alice
    conn = connect(config.DB_PATH)
    try:
        now = datetime.now(timezone.utc)
        for i in range(5):
            conn.execute(
                "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
                (alice_id, "annotation_save", (now - timedelta(seconds=10 * (i + 1))).isoformat()),
            )
    finally:
        conn.close()

    bob_q = sse_broker.subscribe(user_id=bob_id)
    alice_q = sse_broker.subscribe(user_id=alice_id)

    ctx["login"]("alice")
    r = c.post("/api/annotations", json={
        "document_id": "doc_publ_speed", "references": [_ref()],
    })
    assert r.status_code == 200

    # alice receives speed_warning (plus annotation_saved broadcast). bob only sees broadcast.
    async def _drain(q, n, timeout=2.0):
        out = []
        for _ in range(n):
            out.append(await asyncio.wait_for(q.get(), timeout=timeout))
        return out

    # alice's queue: 2 events expected (annotation_saved + speed_warning)
    alice_events = asyncio.run(_drain(alice_q, 2))
    types = sorted(e.event_type for e in alice_events)
    assert types == ["annotation_saved", "speed_warning"]

    # bob's queue: 1 event expected (annotation_saved only)
    bob_events = asyncio.run(_drain(bob_q, 1))
    assert bob_events[0].event_type == "annotation_saved"

    # bob's queue must be empty now (no extra speed_warning leaked)
    async def _empty():
        return await asyncio.wait_for(bob_q.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_empty())


def test_char_limit_warning_only_to_saving_user(second_passed_user, ingest_doc):
    """Long source_text → char_limit_warning to alice only."""
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_publ_chars")
    alice_id = ctx["alice"]["id"]
    bob_id = ctx["bob"]["id"]

    bob_q = sse_broker.subscribe(user_id=bob_id)
    alice_q = sse_broker.subscribe(user_id=alice_id)

    ctx["login"]("alice")
    r = c.post("/api/annotations", json={
        "document_id": "doc_publ_chars",
        "references": [_ref(source_text="x" * 700)],
    })
    assert r.status_code == 200

    async def _drain(q, n, timeout=2.0):
        out = []
        for _ in range(n):
            out.append(await asyncio.wait_for(q.get(), timeout=timeout))
        return out

    alice_events = asyncio.run(_drain(alice_q, 2))
    types = sorted(e.event_type for e in alice_events)
    assert types == ["annotation_saved", "char_limit_warning"]

    bob_events = asyncio.run(_drain(bob_q, 1))
    assert bob_events[0].event_type == "annotation_saved"

    async def _empty():
        return await asyncio.wait_for(bob_q.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_empty())
