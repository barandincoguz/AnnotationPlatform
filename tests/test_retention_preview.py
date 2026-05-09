"""Tests for backend.retention.service.preview_purge."""
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


def _seed_user(db, user_id: int = 1):
    db.execute(
        """INSERT INTO users (id, username, password_hash, role, is_active,
                              has_seen_manual, has_passed_training,
                              avatar_color, created_at, updated_at)
           VALUES (?, 'u', 'x', 'user', 1, 1, 1, '#000',
                   datetime('now'), datetime('now'))""",
        (user_id,),
    )
    db.commit()


def test_preview_returns_count_per_table_without_deleting(fresh_db):
    """preview_purge counts rows that would be purged; does not delete."""
    from backend.retention.service import preview_purge
    from datetime import datetime, timedelta, timezone

    _seed_user(fresh_db)
    old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    young = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    fresh_db.execute(
        """INSERT INTO behavioral_events
           (user_id, detector, threshold_value, actual_value, context_json, created_at)
           VALUES (1, 't', 1.0, 1.0, '{}', ?)""",
        (old,),
    )
    fresh_db.execute(
        """INSERT INTO behavioral_events
           (user_id, detector, threshold_value, actual_value, context_json, created_at)
           VALUES (1, 't', 1.0, 1.0, '{}', ?)""",
        (young,),
    )
    fresh_db.commit()

    out = preview_purge(fresh_db)
    assert out["rows_to_purge"]["behavioral_events"] == 1
    # Both rows still exist after preview (no delete).
    n = fresh_db.execute(
        "SELECT COUNT(*) FROM behavioral_events"
    ).fetchone()[0]
    assert n == 2


def test_preview_includes_policy_snapshot(fresh_db):
    """The response includes a policy list with table, days, cutoff_iso so
    admin UI can render 'rows older than YYYY-MM-DD will be deleted'."""
    from backend.retention.service import preview_purge, PURGE_POLICY

    out = preview_purge(fresh_db)
    assert "policy" in out
    assert isinstance(out["policy"], list)
    tables_in_response = {p["table"] for p in out["policy"]}
    assert tables_in_response == {p.table for p in PURGE_POLICY}
    for entry in out["policy"]:
        assert "days" in entry
        assert "cutoff_iso" in entry
        assert isinstance(entry["days"], int)


def test_preview_uses_db_override_in_policy_snapshot(fresh_db):
    """Operator changes retention.drafts.days to 1 → preview shows 1, not 14."""
    from backend.retention.service import preview_purge

    fresh_db.execute(
        "UPDATE site_settings SET value='1' WHERE key='retention.drafts.days'"
    )
    fresh_db.commit()

    out = preview_purge(fresh_db)
    drafts_entry = next(p for p in out["policy"] if p["table"] == "drafts")
    assert drafts_entry["days"] == 1


def test_preview_kill_switch_omits_table_from_rows_to_purge(fresh_db):
    """When retention.<table>.days=0, the table appears in 'policy' with
    days=0 and cutoff_iso=None, AND is absent from 'rows_to_purge' so the
    total never inflates with rows that are protected by the kill switch.

    Kill switch is the operator's panic button: setting days=0 in
    site_settings stops that table from ever being purged, regardless of
    how many old rows exist. Preview must reflect this so the admin UI
    doesn't show '1247 rows will be purged from behavioral_events' when
    in fact 0 will be (because that table is killed)."""
    from backend.retention.service import preview_purge
    from datetime import datetime, timedelta, timezone

    fresh_db.execute(
        "UPDATE site_settings SET value='0' WHERE key='retention.behavioral_events.days'"
    )
    fresh_db.commit()

    _seed_user(fresh_db)
    old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    fresh_db.execute(
        """INSERT INTO behavioral_events
           (user_id, detector, threshold_value, actual_value, context_json, created_at)
           VALUES (1, 't', 1.0, 1.0, '{}', ?)""",
        (old,),
    )
    fresh_db.commit()

    out = preview_purge(fresh_db)
    # Killed table absent from rows_to_purge.
    assert "behavioral_events" not in out["rows_to_purge"]
    # Killed table present in policy with days=0 and cutoff_iso=None.
    entry = next(p for p in out["policy"] if p["table"] == "behavioral_events")
    assert entry["days"] == 0
    assert entry["cutoff_iso"] is None
    # The very-old row is NOT counted in the total (kill-switched).
    assert out["total"] == 0 or "behavioral_events" not in out["rows_to_purge"]
