"""Tests for restore_from_snapshot."""
import json
import sqlite3
from pathlib import Path

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def _write_snapshot(tmp_path: Path, payload: dict) -> Path:
    snap = tmp_path / "test_snapshot.json"
    snap.write_text(json.dumps(payload, ensure_ascii=False))
    return snap


def test_restore_populates_tables(fresh_db, tmp_path):
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "invite_codes": [
            {"id": 1, "code": "RESTORED", "is_active": 1, "created_at": "2026-05-09T00:00:00+00:00"},
        ],
        "users": [],
    }
    snap = _write_snapshot(tmp_path, payload)
    out = restore_from_snapshot(fresh_db, snap)
    assert out["tables"]["invite_codes"] == 1
    row = fresh_db.execute("SELECT code FROM invite_codes WHERE id=1").fetchone()
    assert row["code"] == "RESTORED"


def test_restore_does_not_touch_schema_migrations(fresh_db, tmp_path):
    """schema_migrations should NOT be in the snapshot or restored."""
    from backend.backup.restore import restore_from_snapshot
    pre_migrations = fresh_db.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    pre_versions = [r["version"] for r in pre_migrations]

    payload = {"users": []}
    snap = _write_snapshot(tmp_path, payload)
    restore_from_snapshot(fresh_db, snap)

    post_migrations = fresh_db.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [r["version"] for r in post_migrations] == pre_versions


def test_restore_clears_existing_rows_first(fresh_db, tmp_path):
    fresh_db.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,?)",
        ("OLD", "2026-05-01T00:00:00+00:00"),
    )
    fresh_db.commit()
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "invite_codes": [
            {"id": 1, "code": "NEW", "is_active": 1, "created_at": "2026-05-09T00:00:00+00:00"},
        ],
    }
    snap = _write_snapshot(tmp_path, payload)
    restore_from_snapshot(fresh_db, snap)
    rows = fresh_db.execute("SELECT code FROM invite_codes").fetchall()
    codes = [r["code"] for r in rows]
    assert "OLD" not in codes
    assert "NEW" in codes


def test_restore_returns_total_row_count(fresh_db, tmp_path):
    from backend.backup.restore import restore_from_snapshot
    # Note: idx_invite_active is a partial unique index allowing only one
    # is_active=1 row, so the second row is inactive. The test verifies
    # row counting, not active-invite semantics.
    payload = {
        "invite_codes": [
            {"id": 1, "code": "A", "is_active": 1, "created_at": "2026-05-09T00:00:00+00:00"},
            {"id": 2, "code": "B", "is_active": 0, "created_at": "2026-05-09T00:00:00+00:00"},
        ],
    }
    snap = _write_snapshot(tmp_path, payload)
    out = restore_from_snapshot(fresh_db, snap)
    assert out["total_rows"] == 2
    assert out["tables"]["invite_codes"] == 2


def test_restore_rolls_back_on_failure(fresh_db, tmp_path):
    """If a single INSERT fails (e.g. unknown column), nothing is committed."""
    fresh_db.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,?)",
        ("PRE_EXISTING", "2026-05-01T00:00:00+00:00"),
    )
    fresh_db.commit()
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "invite_codes": [{"this_column_does_not_exist": "x"}],
    }
    snap = _write_snapshot(tmp_path, payload)
    with pytest.raises(Exception):
        restore_from_snapshot(fresh_db, snap)
    row = fresh_db.execute(
        "SELECT code FROM invite_codes WHERE code='PRE_EXISTING'"
    ).fetchone()
    assert row is not None


def test_restore_skips_unknown_table(fresh_db, tmp_path):
    """A table in the snapshot that doesn't exist in the current schema should
    be skipped silently rather than crashing — forward-compatible."""
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "future_table_does_not_exist_yet": [{"id": 1, "x": "y"}],
        "invite_codes": [
            {"id": 1, "code": "A", "is_active": 1, "created_at": "2026-05-09T00:00:00+00:00"},
        ],
    }
    snap = _write_snapshot(tmp_path, payload)
    out = restore_from_snapshot(fresh_db, snap)
    assert out["tables"]["invite_codes"] == 1
    assert "future_table_does_not_exist_yet" not in out["tables"]
