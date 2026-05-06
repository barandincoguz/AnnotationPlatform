"""Background sweep — periodically clears expired locks.

Runs every `interval_seconds` (default 60). Started from main.py lifespan,
cancelled on shutdown. Single-process; safe with WAL mode.

Publishes one lock_released SSE event per released doc (by_user_id=None
since the sweep doesn't surface the original holder to consumers).
"""
import asyncio
import logging
from typing import Optional

from backend import config
from backend.shared.db import connect
from backend.shared.sse import broker as sse_broker
from backend.locks import service

log = logging.getLogger(__name__)


async def sweep_once_and_publish() -> list[str]:
    """Run one sweep iteration and broadcast lock_released for each released doc.

    Exposed for tests so a single sweep can be triggered without the loop's
    sleep. Returns the list of released document_ids.
    """
    conn = connect(config.DB_PATH)
    try:
        released = service.sweep_expired(conn)
    finally:
        conn.close()

    for document_id in released:
        try:
            await sse_broker.publish_broadcast(
                "lock_released",
                {"document_id": document_id, "by_user_id": None},
            )
        except Exception:
            log.exception("publish lock_released failed for %s", document_id)
    if released:
        log.info("Lock sweep released %d locks: %s", len(released), released)
    return released


async def sweep_loop(interval_seconds: int = 60) -> None:
    """Async loop. Cancel via task.cancel()."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await sweep_once_and_publish()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("Lock sweep iteration failed")


_task: Optional[asyncio.Task] = None


def start(interval_seconds: int = 60) -> asyncio.Task:
    """Start the sweep task; returns the task handle for shutdown cancellation."""
    global _task
    _task = asyncio.create_task(sweep_loop(interval_seconds))
    return _task


def stop() -> None:
    """Cancel the running sweep task (no-op if not started)."""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
    _task = None
