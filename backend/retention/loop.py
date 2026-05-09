"""Async retention loop. Mirrors backend/backup/loop.py: lifespan-driven
asyncio task, sleep-first ordering, settings live-tuned interval, never
dies on per-cycle exceptions.

Single-process; safe with WAL mode (concurrent readers OK, BEGIN
IMMEDIATE serializes against backup_loop's writer via busy_timeout).
"""
import asyncio
import logging
from typing import Optional

from backend import config
from backend.retention.service import run_purge
from backend.shared import settings as settings_mod
from backend.shared.db import connect


log = logging.getLogger(__name__)


DEFAULT_INTERVAL_SECONDS = 86400  # 24h


def _read_interval() -> int:
    """Re-read site_settings.retention.interval_seconds each cycle.
    Falls back to DEFAULT_INTERVAL_SECONDS if missing or unparseable.
    Uses its own short-lived connection (called from async context)."""
    try:
        conn = connect(config.DB_PATH)
        try:
            return settings_mod.get_int(
                conn,
                "retention.interval_seconds",
                default=DEFAULT_INTERVAL_SECONDS,
            )
        finally:
            conn.close()
    except Exception:
        log.exception("retention: failed to read interval, using default")
        return DEFAULT_INTERVAL_SECONDS


def _run_purge_blocking() -> None:
    """Open a connection, call run_purge, close. Synchronous wrapper for
    asyncio.to_thread — keeps blocking SQLite work off the event loop."""
    conn = connect(config.DB_PATH)
    try:
        run_purge(conn)
    finally:
        conn.close()


async def retention_once() -> None:
    """Run one retention cycle in a worker thread. Exposed for tests so
    they can call a single cycle without driving the loop."""
    await asyncio.to_thread(_run_purge_blocking)


async def retention_loop() -> None:
    """Async loop. Cancel via task.cancel().
    Sleep-first ordering: first cycle fires `interval` seconds AFTER start,
    matching backup_loop and locks_sweep so concurrent first-fire does not
    happen at boot.
    """
    while True:
        try:
            interval = _read_interval()
            await asyncio.sleep(interval)
            await retention_once()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("retention cycle failed")


_task: Optional[asyncio.Task] = None


def start() -> asyncio.Task:
    """Start the retention task; returns the handle for shutdown cancellation."""
    global _task
    _task = asyncio.create_task(retention_loop())
    return _task


def stop() -> None:
    """Cancel the running retention task (no-op if not started)."""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
    _task = None
