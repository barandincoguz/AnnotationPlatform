import sqlite3

import pytest

from backend.main import (
    MIRROR_RESTORE_TABLES,
    _local_annotation_state_empty,
    _mirror_annotation_state_available,
    _restore_mirrored_state,
)
from backend.migrations import discover_migrations
from backend.migrations.helpers.schema_introspect import list_project_tables
from backend.migrations.runner import apply_migrations


class _Cursor:
    def __init__(self, rows_by_table, fail_table=None):
        self.rows_by_table = rows_by_table
        self.fail_table = fail_table
        self.table = None

    def execute(self, sql):
        self.table = sql.removeprefix("SELECT * FROM baran_")
        if self.table == self.fail_table:
            raise RuntimeError("mirror read failed")

    def fetchall(self):
        return self.rows_by_table.get(self.table, [])

    def close(self):
        pass


class _PgConnection:
    def __init__(self, rows_by_table=None, fail_table=None):
        self.rows_by_table = rows_by_table or {}
        self.fail_table = fail_table

    def cursor(self):
        return _Cursor(self.rows_by_table, self.fail_table)


class _CountCursor:
    def __init__(self, counts):
        self.counts = counts
        self.table = None

    def execute(self, sql):
        self.table = sql.removeprefix("SELECT COUNT(*) FROM baran_")

    def fetchone(self):
        return (self.counts.get(self.table, 0),)

    def close(self):
        pass


class _CountPgConnection:
    def __init__(self, counts):
        self.counts = counts

    def cursor(self):
        return _CountCursor(self.counts)


def _conn():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    apply_migrations(conn, discover_migrations())
    return conn


def test_restore_scope_excludes_runtime_credentials_and_locks():
    assert "user_sessions" not in MIRROR_RESTORE_TABLES
    assert "document_locks" not in MIRROR_RESTORE_TABLES


def test_restore_scope_covers_every_durable_non_document_mirror_table():
    conn = _conn()
    document_sync_tables = {
        "documents_meta",
        "document_kanun_refs",
        "document_bkk_refs",
    }
    expected = set(list_project_tables(conn)) - document_sync_tables - {
        "document_locks",
        "user_sessions",
        "system_events",
    }
    assert set(MIRROR_RESTORE_TABLES) == expected
    conn.close()


def test_local_annotation_state_empty_detects_empty_and_non_empty_state():
    conn = _conn()
    try:
        assert _local_annotation_state_empty(conn) is True
        conn.execute(
            """
            INSERT INTO users(id, username, password_hash, role, created_at, updated_at)
            VALUES (1, 'alice', 'hash', 'user', 'now', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO documents_meta(
                document_id, file_path, pdf_text, word_count, sentence_count,
                text_density, estimated_difficulty, created_at
            ) VALUES ('doc_1', 'doc.json', 'body', 1, 1, 1, 'Kolay', 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO drafts(document_id, user_id, references_json, updated_at)
            VALUES ('doc_1', 1, '[]', 'now')
            """
        )
        assert _local_annotation_state_empty(conn) is False
    finally:
        conn.close()


def test_mirror_annotation_state_available_checks_annotations_and_drafts():
    assert _mirror_annotation_state_available(
        _CountPgConnection({"annotations": 0, "drafts": 0})
    ) is False
    assert _mirror_annotation_state_available(
        _CountPgConnection({"annotations": 0, "drafts": 3})
    ) is True
    assert _mirror_annotation_state_available(
        _CountPgConnection({"annotation_versions": 1})
    ) is True


def test_restore_invalidates_sessions_and_nulls_legacy_session_references():
    conn = _conn()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, is_active, "
        "has_passed_training, has_seen_manual, created_at, updated_at) "
        "VALUES (1, 'old', 'hash', 'user', 1, 0, 0, 'old', 'old')"
    )
    conn.execute(
        "INSERT INTO user_sessions("
        "id, user_id, session_token, started_at, last_activity_at"
        ") VALUES (1, 1, 'old-token', 'old', 'old')"
    )

    rows = {
        "users": [{
            "id": 2,
            "username": "restored",
            "email": None,
            "password_hash": "hash",
            "role": "user",
            "is_active": 1,
            "has_passed_training": 1,
            "has_seen_manual": 1,
            "avatar_color": None,
            "created_at": "new",
            "updated_at": "new",
        }],
        "activity_events": [{
            "id": 7,
            "user_id": 2,
            "session_id": 999,
            "event_type": "login",
            "document_id": None,
            "duration_ms": None,
            "extra_json": None,
            "created_at": "new",
        }],
    }

    counts = _restore_mirrored_state(conn, _PgConnection(rows))

    assert counts["users"] == 1
    assert conn.execute("SELECT COUNT(*) FROM user_sessions").fetchone()[0] == 0
    event = conn.execute(
        "SELECT user_id, session_id FROM activity_events WHERE id=7"
    ).fetchone()
    assert dict(event) == {"user_id": 2, "session_id": None}
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_restore_rolls_back_every_table_when_required_remote_table_fails():
    conn = _conn()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, is_active, "
        "has_passed_training, has_seen_manual, created_at, updated_at) "
        "VALUES (1, 'original', 'hash', 'user', 1, 0, 0, 'old', 'old')"
    )
    conn.execute(
        "INSERT INTO user_sessions("
        "id, user_id, session_token, started_at, last_activity_at"
        ") VALUES (1, 1, 'must-survive-rollback', 'old', 'old')"
    )
    rows = {
        "users": [{
            "id": 2,
            "username": "partial",
            "email": None,
            "password_hash": "hash",
            "role": "user",
            "is_active": 1,
            "has_passed_training": 0,
            "has_seen_manual": 0,
            "avatar_color": None,
            "created_at": "new",
            "updated_at": "new",
        }],
    }

    with pytest.raises(RuntimeError, match="baran_site_settings"):
        _restore_mirrored_state(
            conn,
            _PgConnection(rows, fail_table="site_settings"),
        )

    assert conn.execute("SELECT username FROM users").fetchone()[0] == "original"
    assert conn.execute("SELECT session_token FROM user_sessions").fetchone()[0] == (
        "must-survive-rollback"
    )
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()
