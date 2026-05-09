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
