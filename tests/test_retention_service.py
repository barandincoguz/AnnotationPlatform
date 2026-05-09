"""Tests for backend/retention/service.py — compute_cutoffs (Task 2),
purge_single_table (Task 3), run_purge (Task 4)."""
import sqlite3
from datetime import datetime, timedelta, timezone
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


# ---------------- compute_cutoffs ----------------


def test_compute_cutoffs_uses_code_default_when_no_db_override(fresh_db):
    """If site_settings has no retention.<table>.days override, the
    PolicyEntry's default_days is used."""
    from backend.retention.service import compute_cutoffs, PURGE_POLICY

    # Wipe defaults inserted by v0003 so the resolver falls through to code.
    fresh_db.execute("DELETE FROM site_settings WHERE key LIKE 'retention.%'")
    fresh_db.commit()

    cutoffs = compute_cutoffs(fresh_db)
    now = datetime.now(timezone.utc)
    for entry in PURGE_POLICY:
        expected = now - timedelta(days=entry.default_days)
        actual = cutoffs[entry.table]
        # Allow 5-second wiggle for clock skew between compute and assertion.
        assert abs((actual - expected).total_seconds()) < 5, (
            f"cutoff for {entry.table}: expected {expected}, got {actual}"
        )


def test_compute_cutoffs_prefers_db_override(fresh_db):
    """If site_settings has retention.<table>.days, that value wins over default."""
    from backend.retention.service import compute_cutoffs

    # v0003 sets 30 by default; override to 60.
    fresh_db.execute(
        "UPDATE site_settings SET value=? WHERE key=?",
        ("60", "retention.behavioral_events.days"),
    )
    fresh_db.commit()

    cutoffs = compute_cutoffs(fresh_db)
    now = datetime.now(timezone.utc)
    expected = now - timedelta(days=60)
    assert abs((cutoffs["behavioral_events"] - expected).total_seconds()) < 5


def test_compute_cutoffs_treats_zero_days_as_kill_switch(fresh_db):
    """retention.<table>.days = 0 → entry is omitted from the cutoff dict
    entirely. Caller must skip the table for this cycle."""
    from backend.retention.service import compute_cutoffs

    fresh_db.execute(
        "UPDATE site_settings SET value='0' WHERE key='retention.drafts.days'"
    )
    fresh_db.commit()

    cutoffs = compute_cutoffs(fresh_db)
    assert "drafts" not in cutoffs


def test_compute_cutoffs_raises_on_negative_days(fresh_db):
    """Negative days is operator error; raise ValueError so the cycle fails
    fast and the system_events row records the misconfiguration."""
    from backend.retention.service import compute_cutoffs

    fresh_db.execute(
        "UPDATE site_settings SET value='-1' WHERE key='retention.notifications.days'"
    )
    fresh_db.commit()

    with pytest.raises(ValueError) as exc:
        compute_cutoffs(fresh_db)
    assert "negative" in str(exc.value).lower() or "-1" in str(exc.value)


def test_compute_cutoffs_raises_on_non_numeric_value(fresh_db):
    """Non-JSON-numeric value (e.g. 'abc') yields a ValueError carrying the
    key name, so the eventual retention_failed audit log is actionable
    rather than a raw json.JSONDecodeError fragment."""
    from backend.retention.service import compute_cutoffs

    fresh_db.execute(
        "UPDATE site_settings SET value='abc' WHERE key='retention.drafts.days'"
    )
    fresh_db.commit()

    with pytest.raises(ValueError) as exc:
        compute_cutoffs(fresh_db)
    assert "retention.drafts.days" in str(exc.value)
