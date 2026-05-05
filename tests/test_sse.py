import asyncio
import pytest
from backend.shared.sse import SSEBroker


@pytest.mark.asyncio
async def test_subscriber_receives_personal_event():
    broker = SSEBroker()
    queue = broker.subscribe(user_id=1)
    await broker.publish_to([1], "badge_unlocked", {"badge_id": "first_annotation"})
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event.event_type == "badge_unlocked"
    assert event.data == {"badge_id": "first_annotation"}


@pytest.mark.asyncio
async def test_other_user_does_not_receive_personal_event():
    broker = SSEBroker()
    q1 = broker.subscribe(user_id=1)
    q2 = broker.subscribe(user_id=2)
    await broker.publish_to([1], "badge_unlocked", {"x": 1})
    await asyncio.wait_for(q1.get(), timeout=1.0)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q2.get(), timeout=0.2)


@pytest.mark.asyncio
async def test_broadcast_reaches_all_users():
    broker = SSEBroker()
    q1 = broker.subscribe(user_id=1)
    q2 = broker.subscribe(user_id=2)
    await broker.publish_broadcast("lock_acquired", {"document_id": "doc_1"})
    e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert e1.event_type == "lock_acquired"
    assert e2.event_type == "lock_acquired"


@pytest.mark.asyncio
async def test_user_can_have_multiple_queues_one_per_tab():
    broker = SSEBroker()
    q_tab1 = broker.subscribe(user_id=1)
    q_tab2 = broker.subscribe(user_id=1)
    await broker.publish_to([1], "speed_warning", {"msg": "slow"})
    e1 = await asyncio.wait_for(q_tab1.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q_tab2.get(), timeout=1.0)
    assert e1.data == {"msg": "slow"}
    assert e2.data == {"msg": "slow"}


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    broker = SSEBroker()
    queue = broker.subscribe(user_id=1)
    broker.unsubscribe(user_id=1, queue=queue)
    await broker.publish_to([1], "x", {})
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.2)


@pytest.mark.asyncio
async def test_online_users_returns_user_ids_with_subscribers():
    broker = SSEBroker()
    broker.subscribe(user_id=1)
    broker.subscribe(user_id=2)
    broker.subscribe(user_id=2)  # second tab
    assert broker.online_user_ids() == {1, 2}


@pytest.mark.asyncio
async def test_unsubscribe_last_queue_removes_user_from_online():
    broker = SSEBroker()
    queue = broker.subscribe(user_id=1)
    assert 1 in broker.online_user_ids()
    broker.unsubscribe(1, queue)
    assert 1 not in broker.online_user_ids()
