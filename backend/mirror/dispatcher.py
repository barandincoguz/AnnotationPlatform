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
import sqlite3
from typing import Awaitable, Callable, Optional

from backend import config
from backend.mirror import config as mirror_config
from backend.mirror.neon_client import NeonClient, NeonPermanent, NeonTransient
from backend.shared import audit
from backend.shared.db import connect

log = logging.getLogger(__name__)


# ----- module-level handles (Task 10 + Task 12 read these) -----

_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None
_neon_client: Optional[NeonClient] = None
_cold_start_emitted: bool = False  # so we only log "neon_mirror_connected" once

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
) -> asyncio.Task:
    """Schedule the dispatcher coroutine. Returns the task handle for stop().

    Mirrors backend/locks/sweep.py and backend/backup/loop.py — same
    start/stop shape so the lifespan code (Task 10) stays consistent.
    """
    global _task, _stop_event, _neon_client, _cold_start_emitted, last_status, last_delivered_at
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
    global _task, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _task is not None and not _task.done():
        _task.cancel()
    # Closing the Neon client happens after the task is awaited by the caller.


def is_alive() -> bool:
    """Used by the admin health endpoint (Task 12)."""
    return _task is not None and not _task.done()


def get_neon_client() -> Optional[NeonClient]:
    return _neon_client
