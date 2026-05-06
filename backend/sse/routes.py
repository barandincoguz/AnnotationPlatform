"""GET /api/events — Server-Sent Events stream for live updates.

Each request gets its own asyncio.Queue subscribed to the broker. The
generator yields formatted SSE messages until the client disconnects or
the queue raises (broker shutdown). A `: ping\n\n` comment is sent
every 30s to keep the connection open through proxies/load balancers.

Cleanup: the queue is unsubscribed in `finally:` so disconnects don't
leak subscribers.
"""
import asyncio
import json
import logging
import sqlite3
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.shared.sse import broker
from backend.users.deps import require_passed_training


router = APIRouter(prefix="/api", tags=["sse"])
log = logging.getLogger(__name__)

KEEPALIVE_INTERVAL_SECONDS = 30.0


def format_sse_message(*, event_type: Optional[str], data: dict) -> str:
    """Format one event per the SSE wire protocol.

    If event_type is None, only the data line is emitted (default
    'message' event listener handles it). Otherwise an `event: TYPE`
    line precedes the data.
    """
    payload = json.dumps(data)
    if event_type is None:
        return f"data: {payload}\n\n"
    return f"event: {event_type}\ndata: {payload}\n\n"


async def _stream_for_user(user_id: int) -> AsyncIterator[str]:
    """Subscribe to broker; yield SSE messages until cancelled."""
    queue = broker.subscribe(user_id)
    try:
        # Emit an immediate comment so response headers flush before the
        # first real event. Without this, StreamingResponse buffers the
        # 200 response until the first yield — which can be up to 30s
        # (the keepalive timeout) for an idle subscriber.
        yield ": ready\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL_SECONDS)
                yield format_sse_message(event_type=event.event_type, data=event.data)
            except asyncio.TimeoutError:
                # Idle keepalive — comments are ignored by EventSource clients.
                yield ": ping\n\n"
    except asyncio.CancelledError:
        # Client disconnected; let the finally block clean up.
        raise
    except Exception:
        log.exception("SSE stream errored for user_id=%s", user_id)
        raise
    finally:
        broker.unsubscribe(user_id, queue)


@router.get("/events")
async def events(
    user: sqlite3.Row = Depends(require_passed_training),
):
    return StreamingResponse(
        _stream_for_user(user["id"]),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if behind proxy
        },
    )
