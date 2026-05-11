"""Tests for SSE user_online / user_offline lifecycle events."""
import asyncio
import pytest

from backend.shared.sse import broker
from backend.sse.routes import _stream_for_user


@pytest.mark.asyncio
async def test_subscribe_broadcasts_user_online_to_others(db_conn, seed_extra_user, passed_user):
    """When a user opens an SSE connection, all OTHER online users receive
    a user_online event (publish_to_others — no self-echo)."""
    broker._subscribers.clear()
    me_id = passed_user["user"]["id"]
    other_id = seed_extra_user(username="watcher_online_t6", avatar_color="#22c55e")
    listener_q = broker.subscribe(other_id)
    try:
        gen = _stream_for_user(user_id=me_id, db=db_conn)
        first = await gen.__anext__()
        assert ": ready" in first

        seen = False
        for _ in range(5):
            try:
                evt = await asyncio.wait_for(listener_q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                break
            if evt.event_type == "user_online" and evt.data.get("id") == me_id:
                seen = True
                break
        assert seen, "user_online was not broadcast to other subscribers"

        await gen.aclose()
    finally:
        broker.unsubscribe(other_id, listener_q)


@pytest.mark.asyncio
async def test_user_online_payload_shape(db_conn, passed_user, seed_extra_user):
    """The user_online event payload is {id, username, avatar_color}."""
    broker._subscribers.clear()
    me_id = passed_user["user"]["id"]
    other_id = seed_extra_user(username="watcher_shape_t6")
    listener_q = broker.subscribe(other_id)
    try:
        gen = _stream_for_user(user_id=me_id, db=db_conn)
        await gen.__anext__()
        for _ in range(5):
            try:
                evt = await asyncio.wait_for(listener_q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                pytest.fail("no user_online event arrived")
            if evt.event_type == "user_online":
                assert set(evt.data.keys()) == {"id", "username", "avatar_color"}
                assert evt.data["id"] == me_id
                break
        await gen.aclose()
    finally:
        broker.unsubscribe(other_id, listener_q)


@pytest.mark.asyncio
async def test_unsubscribe_broadcasts_user_offline(db_conn, seed_extra_user, passed_user):
    """When a user's last queue is unsubscribed, all remaining subscribers
    receive a user_offline event."""
    broker._subscribers.clear()
    me_id = passed_user["user"]["id"]
    other_id = seed_extra_user(username="watcher_offline_t6", avatar_color="#ef4444")
    listener_q = broker.subscribe(other_id)
    try:
        gen = _stream_for_user(user_id=me_id, db=db_conn)
        await gen.__anext__()
        # Drain any pending online events from listener queue
        while not listener_q.empty():
            listener_q.get_nowait()
        # Close the generator — triggers finally: which unsubscribes + emits user_offline
        await gen.aclose()
        seen_offline = False
        for _ in range(5):
            try:
                evt = await asyncio.wait_for(listener_q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                break
            if evt.event_type == "user_offline" and evt.data == {"id": me_id}:
                seen_offline = True
                break
        assert seen_offline, "user_offline event not seen"
    finally:
        broker.unsubscribe(other_id, listener_q)
