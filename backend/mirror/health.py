"""Operator-facing health surface for the Neon mirror.

Pure functions only — no I/O beyond the supplied SQLite connection.
`backend/admin/routes.py` wraps `collect_health()` in a route at
`GET /api/admin/mirror/health` (admin auth via existing dependency).

The two boolean fields (`dispatcher_alive`, `neon_reachable`) are
operational ergonomics, not strictly required by D-18 — included
because surfacing the task liveness in the same payload lets the
operator distinguish "queue empty because dispatcher is healthy"
from "queue empty because dispatcher crashed silently." They cost
~5 lines of code total and add zero new auth surface.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.mirror import config as mirror_config
from backend.mirror import dispatcher as mirror_dispatcher


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _seconds_since(iso_value: Optional[str]) -> Optional[float]:
    parsed = _parse_iso(iso_value)
    if parsed is None:
        return None
    return (_utc_now() - parsed).total_seconds()


def collect_health(conn: sqlite3.Connection) -> dict:
    """Return the mirror health snapshot.

    Dead-letter rows (`retry_count >= MAX_RETRIES`) are NOT counted
    in `queue_depth` — they're terminal until an operator resets
    `retry_count` + `error`. Counting them in queue_depth would
    make the queue-depth metric monotonically grow under failure
    even after the dispatcher gave up.
    """
    max_retries = mirror_config.MAX_RETRIES

    queue_depth = conn.execute(
        "SELECT COUNT(*) AS c FROM _outbox "
        "WHERE delivered_at IS NULL AND retry_count < ?",
        (max_retries,),
    ).fetchone()["c"]

    dead_letter_count = conn.execute(
        "SELECT COUNT(*) AS c FROM _outbox "
        "WHERE delivered_at IS NULL AND retry_count >= ?",
        (max_retries,),
    ).fetchone()["c"]

    oldest_row = conn.execute(
        "SELECT MIN(created_at) AS oldest FROM _outbox "
        "WHERE delivered_at IS NULL AND retry_count < ?",
        (max_retries,),
    ).fetchone()
    oldest_undelivered_age_seconds = _seconds_since(
        oldest_row["oldest"] if oldest_row else None
    )

    last_delivered_at: Optional[str] = mirror_dispatcher.last_delivered_at
    if last_delivered_at is None:
        row = conn.execute(
            "SELECT MAX(delivered_at) AS lda FROM _outbox WHERE delivered_at IS NOT NULL"
        ).fetchone()
        last_delivered_at = row["lda"] if row else None

    # Ergonomic extras — see module docstring for the rationale.
    dispatcher_alive = mirror_dispatcher.is_alive()
    last_status = mirror_dispatcher.last_status
    # `last_status` is None until the first apply attempt fires; we treat
    # that as "unknown / not yet reached" rather than asserting reachability
    # either way.
    if last_status is None:
        neon_reachable: Optional[bool] = None
    else:
        neon_reachable = bool(last_status)

    return {
        "queue_depth": int(queue_depth),
        "dead_letter_count": int(dead_letter_count),
        "oldest_undelivered_age_seconds": oldest_undelivered_age_seconds,
        "last_delivered_at": last_delivered_at,
        "dispatcher_alive": dispatcher_alive,
        "neon_reachable": neon_reachable,
    }
