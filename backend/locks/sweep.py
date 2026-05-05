"""Background sweep — periodically clears expired locks.

Runs every `interval_seconds` (default 60). Started from main.py lifespan,
cancelled on shutdown. Single-process; safe with WAL mode.

SSE event emission ('lock_released' broadcast) is added in Paket 7.
"""
import asyncio
import logging
from typing import Optional

from backend import config
from backend.shared.db import connect
from backend.locks import service

log = logging.getLogger(__name__)


async def sweep_loop(interval_seconds: int = 60) -> None:
    """Async loop. Cancel via task.cancel()."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            conn = connect(config.DB_PATH)
            try:
                released = service.sweep_expired(conn)
                if released:
                    log.info("Lock sweep released %d locks: %s", len(released), released)
            finally:
                conn.close()
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
