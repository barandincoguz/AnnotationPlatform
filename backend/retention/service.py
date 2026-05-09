"""Retention purge — core service layer.

Architecture mirrors backend/backup/service.py: a pure-function layer
the loop and HTTP routes both call into. No async, no SQLite session
state; callers manage connections.

The PURGE_POLICY list is the source of truth for which tables get
retention applied. site_settings provides per-deployment overrides.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import json
import sqlite3

from backend.shared import audit, settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PurgePolicyEntry:
    table: str
    cutoff_column: str
    default_days: int
    extra_where: Optional[str]


PURGE_POLICY: list[PurgePolicyEntry] = [
    PurgePolicyEntry("behavioral_events", "created_at", 30,  None),
    PurgePolicyEntry("activity_events",   "created_at", 90,  None),
    PurgePolicyEntry("system_events",     "created_at", 180, None),
    PurgePolicyEntry("user_sessions",     "ended_at",   30,  "ended_at IS NOT NULL"),
    PurgePolicyEntry("notifications",     "created_at", 30,  "is_read=1"),
    PurgePolicyEntry("drafts",            "updated_at", 14,  None),
]


def _resolve_days(db: sqlite3.Connection, entry: PurgePolicyEntry) -> int:
    """Return effective retention days for `entry`. Reads
    site_settings retention.<table>.days; falls back to entry.default_days
    if missing. Raises ValueError on:
      - negative value (operator error)
      - non-numeric value (e.g. someone wrote 'abc' via raw SQL UPDATE)
    so the eventual retention_failed audit row carries the key name."""
    key = f"retention.{entry.table}.days"
    try:
        days = settings.get_int(db, key, default=entry.default_days)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(
            f"site_settings {key} is not a valid integer: {e}"
        ) from e
    if days < 0:
        raise ValueError(
            f"site_settings {key}={days} is negative; retention windows "
            f"must be >= 0 (0 = kill switch, table not purged)"
        )
    return days


def compute_cutoffs(db: sqlite3.Connection) -> dict[str, datetime]:
    """For each PURGE_POLICY entry, compute cutoff = now() - days(N).
    Skips entries whose effective days is 0 (kill switch) — the result
    dict will not contain those tables, signaling to the caller that
    they must be omitted from this cycle.

    Raises ValueError if any entry has negative days configured.
    """
    now = datetime.now(timezone.utc)
    cutoffs: dict[str, datetime] = {}
    for entry in PURGE_POLICY:
        days = _resolve_days(db, entry)
        if days == 0:
            continue  # kill switch
        cutoffs[entry.table] = now - timedelta(days=days)
    return cutoffs


def purge_single_table(
    db: sqlite3.Connection,
    entry: PurgePolicyEntry,
    cutoff: datetime,
) -> int:
    """Delete rows where entry.cutoff_column < cutoff (and extra_where if any).
    Caller manages the transaction (typically a multi-table BEGIN IMMEDIATE).
    Returns the rowcount of the DELETE statement.

    The cutoff is bound as an ISO timestamp string; SQLite's text-comparison
    on ISO-8601 produces correct chronological ordering."""
    cutoff_iso = cutoff.isoformat()
    sql = f"DELETE FROM {entry.table} WHERE {entry.cutoff_column} < ?"
    if entry.extra_where:
        sql += f" AND {entry.extra_where}"
    cur = db.execute(sql, (cutoff_iso,))
    return cur.rowcount


def run_purge(db: sqlite3.Connection) -> dict:
    """Run a single retention cycle. Resolves cutoffs, opens a
    BEGIN IMMEDIATE transaction, runs purge_single_table for each
    PURGE_POLICY entry that has a cutoff (kill-switched entries are
    omitted from the dict). On any failure rolls back, records a
    retention_failed system_event, and re-raises. On success commits
    and records retention_success.

    Returns {ok: True, purged: {table: count}, total: N}.
    """
    cutoffs = compute_cutoffs(db)

    db.execute("BEGIN IMMEDIATE")
    try:
        purged: dict[str, int] = {}
        for entry in PURGE_POLICY:
            if entry.table not in cutoffs:
                purged[entry.table] = 0  # kill switch — report 0, not absent
                continue
            count = purge_single_table(db, entry, cutoffs[entry.table])
            purged[entry.table] = count
        db.execute("COMMIT")
    except Exception as e:
        db.execute("ROLLBACK")
        audit.log_system_event(
            db, "retention_failed", "error",
            message="retention cycle failed",
            extra={"step": "purge", "error": str(e)},
        )
        raise

    total = sum(purged.values())
    audit.log_system_event(
        db, "retention_success", "info",
        message=f"purged {total} rows across {len(purged)} tables",
        extra={"purged": purged},
    )
    return {"ok": True, "purged": purged, "total": total}
