"""Tests for v0003 — retention default settings migration."""
import sqlite3
from pathlib import Path

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


EXPECTED_KEYS = {
    "retention.interval_seconds":        "86400",
    "retention.behavioral_events.days": "30",
    "retention.activity_events.days":   "90",
    "retention.system_events.days":     "180",
    "retention.user_sessions.days":     "30",
    "retention.notifications.days":     "30",
    "retention.drafts.days":            "14",
}


def test_v0003_inserts_default_retention_keys(fresh_db):
    rows = fresh_db.execute(
        "SELECT key, value FROM site_settings WHERE key LIKE 'retention.%'"
    ).fetchall()
    actual = {r["key"]: r["value"] for r in rows}
    assert actual == EXPECTED_KEYS


def test_v0003_is_idempotent_via_insert_or_ignore(fresh_db):
    """Operator-tuned override survives re-running v0003. Simulates the
    re-apply path that happens after a restore (operator may have set
    retention.system_events.days=60 before backup; restore must not clobber)."""
    fresh_db.execute(
        "UPDATE site_settings SET value=? WHERE key=?",
        ("60", "retention.system_events.days"),
    )
    fresh_db.commit()

    # Re-run v0003 specifically
    from backend.migrations.v0003_retention_settings import up
    up(fresh_db)

    row = fresh_db.execute(
        "SELECT value FROM site_settings WHERE key=?",
        ("retention.system_events.days",),
    ).fetchone()
    assert row["value"] == "60"  # operator override preserved
