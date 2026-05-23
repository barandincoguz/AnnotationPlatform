"""Async outbox dispatcher (Phase 4, D-07 .. D-19).

Coroutine that drains the local `_outbox` queue and pushes each row to the
partner Neon Postgres mirror via `NeonClient.apply`. Runs in the FastAPI
lifespan (Task 10); cancellable via `stop()`.

Failure semantics:
  - NeonTransient -> increment retry_count, leave delivered_at NULL,
                     stamp `error` with the message. The drain query
                     gates re-firing via an exponential clock against
                     `created_at` (Task 9).
  - NeonPermanent -> jump retry_count to MAX_RETRIES (dead-letter),
                     stamp `error`. Dispatcher writes a system_events
                     `neon_mirror_dead_letter` row.
  - Cold-start success -> dispatcher writes a system_events
                          `neon_mirror_connected` row exactly once
                          (Task 9).

Concurrency rules:
  - All blocking SQLite + psycopg calls run via `asyncio.to_thread` so the
    event loop is never starved (MIRROR-07, T-04-03).
  - The dispatcher's long-lived SQLite connection is obtained via the
    canonical `backend.shared.db.connect` helper to inherit the same
    busy_timeout + WAL PRAGMAs as the request path.
  - Each iteration opens-uses-closes its own short transaction; no
    cross-iteration write lock.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from backend import config
from backend.mirror import config as mirror_config
from backend.mirror.neon_client import NeonClient, NeonPermanent, NeonTransient
from backend.shared import audit
from backend.shared.db import connect

log = logging.getLogger(__name__)


# ----- PID-file singleton guard (Phase 5 B-02) -----

def _pid_is_alive(pid: int) -> bool:
    """Return True if the process with *pid* is running on this host."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # PID exists but belongs to a different user; treat as alive.
        return True
    except OSError:
        return False


def _acquire_dispatcher_lock(data_dir: Path) -> bool:
    """Atomic-ish PID-file lock. Returns True if we own the lock.

    Race window: two dispatchers starting within the same OS scheduling
    tick could both pass the liveness check and both overwrite. Acceptable
    — backend.main.lifespan boots dispatcher exactly once per process
    and the workers=1 SQLite constraint means no second backend process
    is supposed to start against the same DATA_DIR. The PID file is a
    second-line defence against accidental dual-boot, not a hard lock.
    """
    pid_file = data_dir / ".mirror-dispatcher.pid"
    if pid_file.exists():
        try:
            existing_pid = int(pid_file.read_text().strip().split()[0])
        except (ValueError, IndexError, OSError):
            existing_pid = -1
        if existing_pid > 0 and _pid_is_alive(existing_pid):
            log.error(
                "mirror dispatcher: refusing to start — another instance "
                "is alive (PID %d) per %s. If this is wrong, remove the "
                "file manually after confirming no other process is "
                "draining the outbox.",
                existing_pid, pid_file,
            )
            return False
        # Stale PID — take over.
        log.warning(
            "mirror dispatcher: stale PID file (PID %d not alive); taking over.",
            existing_pid,
        )
    pid_file.write_text(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n")
    return True


def _release_dispatcher_lock(data_dir: Path) -> None:
    pid_file = data_dir / ".mirror-dispatcher.pid"
    try:
        pid_file.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        log.exception("mirror dispatcher: failed to release PID file")


# ----- module-level handles (Task 10 + Task 12 read these) -----

_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None
_neon_client: Optional[NeonClient] = None
_cold_start_emitted: bool = False  # so we only log "neon_mirror_connected" once
_lock_data_dir: Optional[Path] = None  # set by start(); used by stop() to release PID file

# Operational telemetry consumed by the admin health endpoint (Task 12).
last_status: Optional[bool] = None  # True after a successful apply; False after failure
last_delivered_at: Optional[str] = None


# ----- drain query -----

# Per Task 8 brief: select up to batch_size pending rows in commit order.
# Task 9 will extend the WHERE clause with the exponential-backoff gating.
DRAIN_SQL_BASE = """
SELECT id, table_name, op, pk_value, payload_json, retry_count
FROM _outbox
WHERE delivered_at IS NULL AND retry_count < :max_retries
"""

DRAIN_SQL_WITH_BACKOFF = """
SELECT id, table_name, op, pk_value, payload_json, retry_count
FROM _outbox
WHERE delivered_at IS NULL
  AND retry_count < :max_retries
  AND (
        error IS NULL
        OR datetime(created_at, '+' || (1 << retry_count) || ' seconds') < datetime('now')
      )
ORDER BY id
LIMIT :batch
"""


def _drain_one_batch(conn: sqlite3.Connection, batch_size: int, max_retries: int) -> list[sqlite3.Row]:
    return conn.execute(
        DRAIN_SQL_WITH_BACKOFF,
        {"batch": batch_size, "max_retries": max_retries},
    ).fetchall()


def _mark_delivered(conn: sqlite3.Connection, row_id: int) -> None:
    conn.execute(
        "UPDATE _outbox "
        "SET delivered_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), error = NULL "
        "WHERE id = ?",
        (row_id,),
    )


def _mark_transient_failure(conn: sqlite3.Connection, row_id: int, err: str) -> None:
    conn.execute(
        "UPDATE _outbox SET retry_count = retry_count + 1, error = ? WHERE id = ?",
        (err, row_id),
    )


def _mark_dead_letter(conn: sqlite3.Connection, row_id: int, err: str, max_retries: int) -> None:
    conn.execute(
        "UPDATE _outbox SET retry_count = ?, error = ? WHERE id = ?",
        (max_retries, err, row_id),
    )


# ----- per-row processing -----

def _process_one_row(
    conn: sqlite3.Connection,
    neon: NeonClient,
    row: sqlite3.Row,
    max_retries: int,
) -> tuple[bool, Optional[str]]:
    """Apply one outbox row. Returns (delivered, dead_letter_err)."""
    try:
        payload = json.loads(row["payload_json"])
        neon.apply(row["op"], row["table_name"], row["pk_value"], payload)
    except NeonPermanent as exc:
        _mark_dead_letter(conn, row["id"], str(exc), max_retries)
        return (False, str(exc))
    except NeonTransient as exc:
        new_count = row["retry_count"] + 1
        if new_count >= max_retries:
            # Last retry exhausted — also a dead-letter.
            _mark_dead_letter(conn, row["id"], str(exc), max_retries)
            return (False, str(exc))
        _mark_transient_failure(conn, row["id"], str(exc))
        return (False, None)

    _mark_delivered(conn, row["id"])
    return (True, None)


# ----- core async loop -----

async def run_dispatcher(
    *,
    conn_factory: Callable[[], sqlite3.Connection] | None = None,
    neon_client: NeonClient | None = None,
    batch_size: int | None = None,
    sleep_empty: float | None = None,
    sleep_batch: float | None = None,
    max_retries: int | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Drain `_outbox` until cancelled.

    Knobs default to the values in `backend.mirror.config`. The `conn_factory`
    and `neon_client` overrides are for tests; production calls `start()`
    which wires defaults.
    """
    global _cold_start_emitted, last_status, last_delivered_at
    bsize = batch_size if batch_size is not None else mirror_config.NEON_MIRROR_BATCH_SIZE
    s_empty = sleep_empty if sleep_empty is not None else mirror_config.EMPTY_QUEUE_SLEEP
    s_batch = sleep_batch if sleep_batch is not None else mirror_config.INTER_BATCH_SLEEP
    maxr = max_retries if max_retries is not None else mirror_config.MAX_RETRIES

    if conn_factory is None:
        def _default_factory() -> sqlite3.Connection:
            return connect(config.DB_PATH)
        conn_factory = _default_factory
    if neon_client is None:
        neon_client = NeonClient(mirror_config.NEON_MIRROR_URL)

    while True:
        if stop_event is not None and stop_event.is_set():
            return
        try:
            # One iteration: drain a batch, process each row.
            def _drain_and_process() -> tuple[int, int, list[str]]:
                conn = conn_factory()
                try:
                    rows = _drain_one_batch(conn, bsize, maxr)
                    if not rows:
                        return (0, 0, [])
                    delivered = 0
                    dead_errs: list[str] = []
                    for r in rows:
                        ok, dead_err = _process_one_row(conn, neon_client, r, maxr)
                        if ok:
                            delivered += 1
                        elif dead_err is not None:
                            dead_errs.append(dead_err)
                    return (len(rows), delivered, dead_errs)
                finally:
                    conn.close()

            total, delivered, dead_errs = await asyncio.to_thread(_drain_and_process)

            # Update operational telemetry + cold-start system event.
            if delivered > 0:
                last_status = True
                # cold-start: first successful apply ever in this process
                if not _cold_start_emitted:
                    _cold_start_emitted = True
                    def _emit_connected() -> None:
                        c = conn_factory()
                        try:
                            audit.log_system_event(
                                c, "neon_mirror_connected", "info",
                                message="dispatcher successfully delivered to Neon",
                            )
                        finally:
                            c.close()
                    await asyncio.to_thread(_emit_connected)
            elif total > 0:
                last_status = False

            # Dead-letter audit events (one per dead-lettered row).
            if dead_errs:
                def _emit_dead_letter(errs: list[str]) -> None:
                    c = conn_factory()
                    try:
                        for err in errs:
                            audit.log_system_event(
                                c, "neon_mirror_dead_letter", "error",
                                message=f"row dead-lettered after retries: {err}",
                                extra={"error": err},
                            )
                    finally:
                        c.close()
                await asyncio.to_thread(_emit_dead_letter, dead_errs)

            # Refresh last_delivered_at from disk (cheap query; admin health uses it).
            if delivered > 0:
                def _refresh_lda() -> Optional[str]:
                    c = conn_factory()
                    try:
                        r = c.execute(
                            "SELECT MAX(delivered_at) AS m FROM _outbox WHERE delivered_at IS NOT NULL"
                        ).fetchone()
                        return r["m"] if r else None
                    finally:
                        c.close()
                last_delivered_at = await asyncio.to_thread(_refresh_lda)

            if total == 0:
                await asyncio.sleep(s_empty)
            else:
                await asyncio.sleep(s_batch)
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("dispatcher iteration failed")
            # Brief backoff after an unexpected error so we don't hot-loop on bugs.
            await asyncio.sleep(s_empty)


# ----- public start/stop -----

def start(
    *,
    conn_factory: Callable[[], sqlite3.Connection] | None = None,
    neon_client: NeonClient | None = None,
    batch_size: int | None = None,
    sleep_empty: float | None = None,
    sleep_batch: float | None = None,
    max_retries: int | None = None,
    data_dir: Path | None = None,
) -> asyncio.Task:
    """Schedule the dispatcher coroutine. Returns the task handle for stop().

    Mirrors backend/locks/sweep.py and backend/backup/loop.py — same
    start/stop shape so the lifespan code (Task 10) stays consistent.

    Refuses to start if another dispatcher instance is alive for the same
    DATA_DIR (B-02 singleton guard). On refusal, emits a system_events row
    with severity=error / event_type=mirror_dispatcher_refused_dual_boot and
    returns a no-op already-completed task so the lifespan await is safe.
    """
    global _task, _stop_event, _neon_client, _cold_start_emitted, last_status, last_delivered_at, _lock_data_dir
    _lock_data_dir = data_dir if data_dir is not None else config.DATA_DIR
    if not _acquire_dispatcher_lock(_lock_data_dir):
        # Emit a system_events row recording the refusal.
        _cf = conn_factory if conn_factory is not None else (lambda: connect(config.DB_PATH))
        try:
            c = _cf()
            try:
                audit.log_system_event(
                    c, "mirror_dispatcher_refused_dual_boot", "error",
                    message=(
                        "dispatcher refused to start: another instance is alive "
                        f"per {_lock_data_dir / '.mirror-dispatcher.pid'}"
                    ),
                )
            finally:
                c.close()
        except Exception:
            log.exception("mirror dispatcher: failed to write refused_dual_boot event")
        # Return a no-op completed task so the lifespan `await mirror_task` is safe.
        async def _noop() -> None:
            return
        _task = asyncio.create_task(_noop())
        return _task

    _stop_event = asyncio.Event()
    _cold_start_emitted = False
    last_status = None
    last_delivered_at = None
    if neon_client is None:
        neon_client = NeonClient(mirror_config.NEON_MIRROR_URL)
    _neon_client = neon_client
    _task = asyncio.create_task(
        run_dispatcher(
            conn_factory=conn_factory,
            neon_client=neon_client,
            batch_size=batch_size,
            sleep_empty=sleep_empty,
            sleep_batch=sleep_batch,
            max_retries=max_retries,
            stop_event=_stop_event,
        )
    )
    return _task


def stop() -> None:
    """Signal the dispatcher to exit at the next checkpoint."""
    global _task, _stop_event, _lock_data_dir
    if _stop_event is not None:
        _stop_event.set()
    if _task is not None and not _task.done():
        _task.cancel()
    # Release the PID-file lock so a subsequent start() in the same DATA_DIR
    # (e.g. a process restart) is not refused as a dual-boot.
    if _lock_data_dir is not None:
        _release_dispatcher_lock(_lock_data_dir)
        _lock_data_dir = None
    # Closing the Neon client happens after the task is awaited by the caller.


def is_alive() -> bool:
    """Used by the admin health endpoint (Task 12)."""
    return _task is not None and not _task.done()


def get_neon_client() -> Optional[NeonClient]:
    return _neon_client
