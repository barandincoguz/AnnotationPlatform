"""Tests for broker QueueFull hardening (Codex BROKEN, Pass 3).

When publish_to hits QueueFull on a slow consumer, the existing code
silently drops the event — but the dead queue stays in self._subscribers,
making online_user_ids() report a ghost user forever.

After the fix:
1. The dead queue is removed via unsubscribe().
2. If that was the user's last queue, a user_offline broadcast fires.
3. online_user_ids() no longer includes the dropped user.
"""
import pytest

from backend.shared.sse import SSEBroker


@pytest.mark.asyncio
async def test_queue_full_cleans_dead_queue():
    broker = SSEBroker()
    # Subscribe a user whose queue is filled to capacity (maxsize=100).
    q = broker.subscribe(42)
    for _ in range(100):
        q.put_nowait("filler")

    # Publishing one more event hits QueueFull. The broker must drop
    # the queue and remove the user from online set.
    await broker.publish_to([42], "any_event", {"k": "v"})
    assert 42 not in broker.online_user_ids()


@pytest.mark.asyncio
async def test_queue_full_emits_user_offline_to_remaining_subscribers():
    """When the dropped queue was the user's last, broker broadcasts
    user_offline so other clients refetch /api/users/online."""
    broker = SSEBroker()
    # Subscribe a slow consumer for user 42 + a healthy listener for user 7.
    slow_q = broker.subscribe(42)
    for _ in range(100):
        slow_q.put_nowait("filler")
    listener_q = broker.subscribe(7)

    await broker.publish_to([42], "any_event", {"k": "v"})

    seen_offline = False
    while not listener_q.empty():
        evt = listener_q.get_nowait()
        if evt.event_type == "user_offline" and evt.data == {"id": 42}:
            seen_offline = True
            break
    assert seen_offline, "user_offline event was not emitted on QueueFull cleanup"


@pytest.mark.asyncio
async def test_queue_full_when_user_has_other_open_queues_no_offline():
    """If the user has OTHER open queues (e.g. second browser tab), the
    cleanup does NOT emit user_offline — the user is still online."""
    broker = SSEBroker()
    # User 42 has two tabs.
    slow_q = broker.subscribe(42)
    healthy_q = broker.subscribe(42)  # noqa: F841 — kept open intentionally
    listener_q = broker.subscribe(7)
    for _ in range(100):
        slow_q.put_nowait("filler")

    await broker.publish_to([42], "any_event", {"k": "v"})

    # 42 must still be online (other tab healthy)
    assert 42 in broker.online_user_ids()
    # Listener should NOT have user_offline event for 42.
    saw_offline_for_42 = False
    while not listener_q.empty():
        evt = listener_q.get_nowait()
        if evt.event_type == "user_offline" and evt.data.get("id") == 42:
            saw_offline_for_42 = True
    assert not saw_offline_for_42
