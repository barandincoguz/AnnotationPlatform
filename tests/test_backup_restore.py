"""Tests for restore_from_snapshot."""
import gzip
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


def _write_gzip_snapshot(tmp_path: Path, payload: dict) -> Path:
    snap = tmp_path / "test_snapshot.json.gz"
    snap.write_bytes(gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8")))
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


def test_restore_populates_tables_from_gzip_snapshot(fresh_db, tmp_path):
    from backend.backup.restore import restore_from_snapshot

    payload = {
        "invite_codes": [
            {"id": 1, "code": "RESTORED-GZ", "is_active": 1, "created_at": "2026-05-09T00:00:00+00:00"},
        ],
        "users": [],
    }

    out = restore_from_snapshot(fresh_db, _write_gzip_snapshot(tmp_path, payload))

    assert out["tables"]["invite_codes"] == 1
    row = fresh_db.execute("SELECT code FROM invite_codes WHERE id=1").fetchone()
    assert row["code"] == "RESTORED-GZ"


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


def test_restore_raises_on_unknown_column(fresh_db, tmp_path):
    """Snapshot row with a column that doesn't exist in the current schema
    raises a ValueError with a clear message; transaction is rolled back."""
    fresh_db.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,?)",
        ("PRESERVED", "2026-05-01T00:00:00+00:00"),
    )
    fresh_db.commit()

    from backend.backup.restore import restore_from_snapshot
    payload = {
        "invite_codes": [
            {"id": 1, "code": "X", "is_active": 0,
             "created_at": "2026-05-09T00:00:00+00:00",
             "future_column_added_in_v0099": "uh oh"},
        ],
    }
    snap = _write_snapshot(tmp_path, payload)
    with pytest.raises(ValueError) as exc:
        restore_from_snapshot(fresh_db, snap)
    assert "future_column_added_in_v0099" in str(exc.value)

    # Pre-existing row preserved by rollback
    row = fresh_db.execute(
        "SELECT code FROM invite_codes WHERE code='PRESERVED'"
    ).fetchone()
    assert row is not None


def test_restore_silently_skips_format_version_metadata(fresh_db, tmp_path):
    """__format_version is payload-level metadata, not a table. Restore must
    not log it as 'unknown table' or surface it in skipped_tables (which is
    reserved for forward-compat unknown table names operators may want to
    investigate)."""
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "__format_version": 1,
        "invite_codes": [
            {"id": 1, "code": "VERSIONED", "is_active": 1,
             "created_at": "2026-05-09T00:00:00+00:00"},
        ],
    }
    snap = _write_snapshot(tmp_path, payload)
    out = restore_from_snapshot(fresh_db, snap)
    assert out["tables"]["invite_codes"] == 1
    assert "__format_version" not in out["tables"]
    assert "__format_version" not in out["skipped_tables"]


def test_restore_handles_cross_table_fk_regardless_of_iteration_order(fresh_db, tmp_path):
    """Snapshot iteration order is alphabetical (admin_audit_log before users),
    but admin_audit_log.admin_user_id is a FK to users.id. Restore must succeed
    by deferring FK checks until COMMIT — otherwise real-world snapshots fail
    with 'FOREIGN KEY constraint failed' on the first INSERT."""
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "admin_audit_log": [
            {"id": 1, "admin_user_id": 42, "action_type": "test",
             "target_kind": "x", "target_id": "y",
             "metadata_json": "{}", "created_at": "2026-05-09T00:00:00+00:00"},
        ],
        "users": [
            {"id": 42, "username": "admin", "email": None, "password_hash": "x",
             "role": "admin", "is_active": 1,
             "has_passed_training": 1, "has_seen_manual": 1,
             "avatar_color": "#000000",
             "created_at": "2026-05-09T00:00:00+00:00",
             "updated_at": "2026-05-09T00:00:00+00:00"},
        ],
    }
    snap = _write_snapshot(tmp_path, payload)
    out = restore_from_snapshot(fresh_db, snap)
    assert out["tables"]["admin_audit_log"] == 1
    assert out["tables"]["users"] == 1
    row = fresh_db.execute(
        "SELECT admin_user_id FROM admin_audit_log WHERE id=1"
    ).fetchone()
    assert row["admin_user_id"] == 42


def test_restore_returns_skipped_tables_list(fresh_db, tmp_path):
    """Skipped tables are returned in the result dict so callers (CLI) can
    display them to the operator without scraping logs."""
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "future_table_a": [{"x": "y"}],
        "future_table_b": [],
        "invite_codes": [
            {"id": 1, "code": "A", "is_active": 1,
             "created_at": "2026-05-09T00:00:00+00:00"},
        ],
    }
    snap = _write_snapshot(tmp_path, payload)
    out = restore_from_snapshot(fresh_db, snap)
    assert "skipped_tables" in out
    assert sorted(out["skipped_tables"]) == ["future_table_a", "future_table_b"]
    assert out["tables"]["invite_codes"] == 1


def test_restore_ignores_runtime_tables_and_clears_live_runtime_state(
    fresh_db,
    tmp_path,
):
    from backend.backup.restore import restore_from_snapshot

    fresh_db.execute(
        """
        INSERT INTO users(
            id, username, password_hash, role, created_at, updated_at
        ) VALUES (1, 'live-user', 'hash', 'user', datetime('now'), datetime('now'))
        """
    )
    fresh_db.execute(
        """
        INSERT INTO documents_meta(
            document_id, file_path, pdf_text, word_count, sentence_count,
            text_density, estimated_difficulty, created_at
        ) VALUES ('live-doc', 'path', 'text', 1, 1, 1, 'Kolay', datetime('now'))
        """
    )
    fresh_db.execute(
        """
        INSERT INTO user_sessions(
            user_id, session_token, started_at, last_activity_at
        ) VALUES (1, 'live-session', datetime('now'), datetime('now'))
        """
    )
    fresh_db.execute(
        """
        INSERT INTO document_locks(
            document_id, user_id, acquired_at, last_heartbeat, expires_at
        ) VALUES (
            'live-doc', 1, datetime('now'), datetime('now'),
            datetime('now', '+5 minutes')
        )
        """
    )
    fresh_db.execute(
        """
        INSERT INTO _outbox(
            table_name, op, pk_value, payload_json, created_at
        ) VALUES ('users', 'UPDATE', '1', '{}', datetime('now'))
        """
    )
    payload = {
        "user_sessions": [{
            "id": 99,
            "user_id": 1,
            "session_token": "stale-snapshot-session",
            "ip_hash": None,
            "user_agent": None,
            "started_at": "2020-01-01T00:00:00+00:00",
            "ended_at": None,
            "last_activity_at": "2020-01-01T00:00:00+00:00",
        }],
        "document_locks": [{
            "document_id": "live-doc",
            "user_id": 1,
            "acquired_at": "2020-01-01T00:00:00+00:00",
            "last_heartbeat": "2020-01-01T00:00:00+00:00",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }],
        "_outbox": [{
            "id": 999,
            "table_name": "users",
            "op": "UPDATE",
            "pk_value": "1",
            "payload_json": "{}",
            "created_at": "2020-01-01T00:00:00+00:00",
            "delivered_at": None,
            "retry_count": 0,
            "error": None,
        }],
    }

    out = restore_from_snapshot(
        fresh_db,
        _write_snapshot(tmp_path, payload),
    )

    assert "user_sessions" not in out["tables"]
    assert "document_locks" not in out["tables"]
    assert "_outbox" not in out["tables"]
    assert fresh_db.execute(
        "SELECT COUNT(*) FROM user_sessions"
    ).fetchone()[0] == 0
    assert fresh_db.execute(
        "SELECT COUNT(*) FROM document_locks"
    ).fetchone()[0] == 0
    assert fresh_db.execute(
        "SELECT COUNT(*) FROM _outbox WHERE id=999"
    ).fetchone()[0] == 0


def test_restore_streams_rows_larger_than_reader_chunk(fresh_db, tmp_path):
    from backend.backup.restore import restore_from_snapshot

    large_value = "x" * (1024 * 1024 + 17)
    payload = {
        "invite_codes": [{
            "id": 1,
            "code": large_value,
            "is_active": 0,
            "created_at": "2026-05-09T00:00:00+00:00",
        }],
    }

    out = restore_from_snapshot(
        fresh_db,
        _write_snapshot(tmp_path, payload),
    )

    assert out["tables"]["invite_codes"] == 1
    assert fresh_db.execute(
        "SELECT length(code) FROM invite_codes WHERE id=1"
    ).fetchone()[0] == len(large_value)
