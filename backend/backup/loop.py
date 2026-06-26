"""Async backup loop. Mirrors backend/locks/sweep.py pattern.

Started from backend/main.py lifespan, cancelled on shutdown. Single-process,
safe with WAL mode. Each iteration re-reads backup.interval_seconds from
site_settings so admin tuning takes effect on the next cycle.
"""
import asyncio
import logging
import sqlite3
from typing import Optional

from backend import config
from backend.backup.service import run_backup_cycle
from backend.shared import settings as S
from backend.shared.db import connect


log = logging.getLogger(__name__)
DEFAULT_INTERVAL_SECONDS = 86400  # 24h
STARTUP_DELAY_SECONDS = 300


def _read_interval(db: sqlite3.Connection) -> int:
    return S.get_int(
        db,
        "backup.interval_seconds",
        default=DEFAULT_INTERVAL_SECONDS,
    )


async def backup_once() -> dict:
    """Run a single backup cycle. Exposed for tests so the cycle can be
    triggered without the loop's sleep."""
    def _do() -> dict:
        conn = connect(config.DB_PATH)
        try:
            return run_backup_cycle(conn)
        finally:
            conn.close()
    return await asyncio.to_thread(_do)


async def backup_loop() -> None:
    """Async loop. Cancel via task.cancel().

    On boot:
      1. Sleep for STARTUP_DELAY_SECONDS (to let Neon sync and boot work settle).
      2. Run the initial backup cycle.

    Each subsequent iteration:
      1. Re-read backup.interval_seconds (live admin tuning).
      2. Sleep `interval_seconds`.
      3. Run one backup cycle inside asyncio.to_thread.
      4. Swallow any non-Cancelled exception; log + continue.
    """
    try:
        await asyncio.sleep(STARTUP_DELAY_SECONDS)
        await backup_once()
    except asyncio.CancelledError:
        return
    except Exception:
        log.exception("initial backup cycle failed")

    while True:
        try:
            conn = connect(config.DB_PATH)
            try:
                interval = _read_interval(conn)
            finally:
                conn.close()
        except Exception:
            log.exception("backup loop: failed to read interval; using default 86400")
            interval = DEFAULT_INTERVAL_SECONDS

        try:
            await asyncio.sleep(interval)
            await backup_once()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("backup cycle iteration failed")


_task: Optional[asyncio.Task] = None


def start() -> asyncio.Task:
    """Start the backup task; returns the task handle for shutdown cancellation."""
    global _task
    _task = asyncio.create_task(backup_loop())
    return _task


def stop() -> None:
    """Cancel the running backup task (no-op if not started)."""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
    _task = None
