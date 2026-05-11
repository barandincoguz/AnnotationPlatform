"""Tests for GET /api/users/online (auth + presence projection)."""
from backend.shared.sse import broker


def test_users_online_requires_auth(client):
    res = client.get("/api/users/online")
    assert res.status_code == 401


def test_users_online_empty_when_no_subscribers(passed_user):
    """With no SSE subscribers, returns []."""
    broker._subscribers.clear()
    res = passed_user["client"].get("/api/users/online")
    assert res.status_code == 200
    assert res.json() == []


def test_users_online_returns_subscribed_users(passed_user, db_conn, seed_extra_user):
    """When two users have an SSE subscription, both appear ordered by id asc."""
    broker._subscribers.clear()

    me_id = passed_user["user"]["id"]
    other_id = seed_extra_user(username="watcher2", avatar_color="#ef4444")

    q1 = broker.subscribe(me_id)
    q2 = broker.subscribe(other_id)
    try:
        res = passed_user["client"].get("/api/users/online")
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 2
        assert body[0]["id"] < body[1]["id"]
        assert {b["id"] for b in body} == {me_id, other_id}
        for entry in body:
            assert set(entry.keys()) == {"id", "username", "avatar_color"}
    finally:
        broker.unsubscribe(me_id, q1)
        broker.unsubscribe(other_id, q2)


def test_users_online_drops_unknown_user_ids(passed_user):
    """Defensive: a subscriber for a non-existent user_id is filtered out
    (race during disable + still-open SSE)."""
    broker._subscribers.clear()
    q = broker.subscribe(999_999)
    try:
        res = passed_user["client"].get("/api/users/online")
        assert res.status_code == 200
        assert res.json() == []
    finally:
        broker.unsubscribe(999_999, q)
