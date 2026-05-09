"""Retention purge — core service layer.

Architecture mirrors backend/backup/service.py: a pure-function layer
the loop and HTTP routes both call into. No async, no SQLite session
state; callers manage connections.

The PURGE_POLICY list is the source of truth for which tables get
retention applied. site_settings provides per-deployment overrides.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import sqlite3

from backend.shared import settings


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
    if missing. Raises ValueError on negative values (operator error)."""
    key = f"retention.{entry.table}.days"
    days = settings.get_int(db, key, default=entry.default_days)
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
