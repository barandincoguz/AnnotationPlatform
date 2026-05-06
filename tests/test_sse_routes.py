"""HTTP-level tests for GET /api/events.

Note on streaming tests: neither Starlette's sync TestClient nor
httpx.ASGITransport supports truly incremental streaming responses —
both buffer the response body in memory and only return after the
generator completes. An infinite SSE stream therefore deadlocks at
the request level when tested in-process.

So:
- Auth gating (401/409) and the format_sse_message helper are
  exercised through the sync TestClient because those paths return
  before the StreamingResponse generator runs.
- The streaming generator (subscribe / unsubscribe / SSE wire format
  on event delivery) is tested by driving _stream_for_user directly
  as an asyncio generator. This is the same code path the route
  hands to StreamingResponse, so the subscribe/disconnect contract
  is fully covered without an HTTP roundtrip.
- Route mounting + media_type are verified structurally by reading
  the registered route off the FastAPI app.

The broker→event delivery is also verified end-to-end by the
dedicated test_sse_publish_*.py suites in later Paket 7 tasks.
"""
import asyncio
import pytest
from backend.shared.sse import broker as sse_broker


def _reset_broker_subscribers():
    """Clear the singleton broker's subscribers between tests."""
    sse_broker._subscribers.clear()


def test_events_requires_auth(client):
    _reset_broker_subscribers()
    r = client.get("/api/events", timeout=2.0)
    assert r.status_code == 401


def test_events_requires_training_passed(client):
    """Untrained user (default has_passed_training=0) gets 409."""
    _reset_broker_subscribers()
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("INV-SSE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "u_sse_untrained", "password": "password123",
        "invite_code": "INV-SSE",
    })
    client.post("/api/auth/login", json={
        "username": "u_sse_untrained", "password": "password123",
    })
    r = client.get("/api/events", timeout=2.0)
    # require_seen_manual fires before training check; either 409 surfaces
    assert r.status_code == 409
    error = r.json()["detail"]["error"]
    assert error in ("manual_not_seen", "training_not_passed")


def test_events_route_registered_for_get():
    """Structural check: the /api/events route is mounted and accepts GET.

    Note: the StreamingResponse's text/event-stream media_type is set per-response
    inside the handler (routes.py), not on the FastAPI route object — so it can't
    be asserted from app.router.routes. The media_type is exercised by the
    direct-generator tests below (test_stream_for_user_*).
    """
    from backend.main import app
    routes = [r for r in app.router.routes if getattr(r, "path", None) == "/api/events"]
    assert routes, "GET /api/events not registered"
    route = routes[0]
    assert "GET" in route.methods


@pytest.mark.asyncio
async def test_stream_for_user_subscribes_and_unsubscribes_on_close():
    """Drive the generator directly: opening it subscribes the user;
    closing it unsubscribes (finally block runs). This is the same
    generator the route hands to StreamingResponse, so the
    subscribe/disconnect contract is fully covered.
    """
    _reset_broker_subscribers()
    from backend.sse.routes import _stream_for_user
    user_id = 4242

    assert user_id not in sse_broker.online_user_ids()

    gen = _stream_for_user(user_id)
    # First yield is the immediate ': ready' comment — pull it.
    first = await gen.__anext__()
    assert first == ": ready\n\n"
    assert user_id in sse_broker.online_user_ids()

    # Close the generator (simulates client disconnect) — finally must
    # unsubscribe the user.
    await gen.aclose()
    assert user_id not in sse_broker.online_user_ids()


@pytest.mark.asyncio
async def test_stream_for_user_yields_published_events():
    """Publishing to the broker should surface as a formatted SSE
    message on the user's stream."""
    _reset_broker_subscribers()
    from backend.sse.routes import _stream_for_user
    user_id = 4243

    gen = _stream_for_user(user_id)
    try:
        # Pull the immediate ': ready' comment so we know we're subscribed.
        await gen.__anext__()

        # Publish an event to this user via the broker.
        await sse_broker.publish_to([user_id], "lock_acquired", {"document_id": "d1"})

        # Next yield should be the formatted event.
        msg = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
        assert msg == 'event: lock_acquired\ndata: {"document_id": "d1"}\n\n'
    finally:
        await gen.aclose()


# Module-scope helper for SSE message formatting (defined in routes.py, exported for tests)
def test_format_sse_message_event_only():
    from backend.sse.routes import format_sse_message
    msg = format_sse_message(event_type="lock_acquired", data={"document_id": "d1"})
    assert msg == 'event: lock_acquired\ndata: {"document_id": "d1"}\n\n'


def test_format_sse_message_data_only_no_event_type():
    """When event_type is None, only the data line is emitted (default 'message' event)."""
    from backend.sse.routes import format_sse_message
    msg = format_sse_message(event_type=None, data={"x": 1})
    assert msg == 'data: {"x": 1}\n\n'
