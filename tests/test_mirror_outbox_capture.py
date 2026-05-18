"""End-to-end capture tests for the Phase 4 outbox triggers (Task 5).

Asserts that committed writes against project tables produce exactly one
`_outbox` row each, with the correct shape (table_name, op, pk_value,
payload_json, delivered_at=NULL, retry_count=0).

Phase 4 Task 13 will append the FastAPI end-to-end smoke test to this file;
Phase 4 Task 7 / Task 8 (config defaults / dispatcher unit) also reuse the
fresh-conn fixture pattern below.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


def _migrated_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    apply_migrations(conn, discover_migrations())
    return conn


def _seed_user(conn: sqlite3.Connection, **overrides) -> int:
    """Insert a minimal users row; returns the new id."""
    fields = {
        "username": "u1",
        "email": None,
        "password_hash": "x",
        "role": "user",
        "is_active": 1,
        "has_passed_training": 0,
        "has_seen_manual": 0,
        "avatar_color": None,
        "created_at": "2026-05-18T00:00:00Z",
        "updated_at": "2026-05-18T00:00:00Z",
    }
    fields.update(overrides)
    cur = conn.execute(
        "INSERT INTO users(username, email, password_hash, role, is_active, "
        "has_passed_training, has_seen_manual, avatar_color, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        tuple(fields[k] for k in (
            "username", "email", "password_hash", "role", "is_active",
            "has_passed_training", "has_seen_manual", "avatar_color",
            "created_at", "updated_at",
        )),
    )
    return cur.lastrowid


# === Task 5: end-to-end trigger capture ===


def test_69_triggers_installed_after_v0006():
    conn = _migrated_conn()
    row = conn.execute(
        "SELECT count(*) AS c FROM sqlite_master "
        "WHERE type='trigger' AND name LIKE '_outbox_%'"
    ).fetchone()
    assert row["c"] == 69
    conn.close()


def test_insert_users_writes_one_outbox_row():
    conn = _migrated_conn()
    user_id = _seed_user(conn, username="alice")
    rows = conn.execute(
        "SELECT * FROM _outbox WHERE table_name='users'"
    ).fetchall()
    assert len(rows) == 1, f"expected exactly 1 outbox row, got {len(rows)}"
    row = rows[0]
    assert row["op"] == "INSERT"
    assert row["pk_value"] == str(user_id)
    assert row["delivered_at"] is None
    assert row["retry_count"] == 0
    payload = json.loads(row["payload_json"])
    assert payload["id"] == user_id
    assert payload["username"] == "alice"
    # Every users column is represented in the payload
    for col in ("password_hash", "role", "is_active", "created_at"):
        assert col in payload
    conn.close()


def test_update_users_writes_outbox_update_row():
    conn = _migrated_conn()
    user_id = _seed_user(conn, username="bob")
    # Clear the INSERT outbox row for isolation.
    conn.execute("DELETE FROM _outbox")
    conn.execute("UPDATE users SET role='admin' WHERE id=?", (user_id,))
    rows = conn.execute("SELECT * FROM _outbox WHERE table_name='users'").fetchall()
    assert len(rows) == 1
    assert rows[0]["op"] == "UPDATE"
    assert rows[0]["pk_value"] == str(user_id)
    payload = json.loads(rows[0]["payload_json"])
    assert payload["role"] == "admin"
    conn.close()


def test_delete_users_writes_outbox_delete_row():
    conn = _migrated_conn()
    user_id = _seed_user(conn, username="carol")
    conn.execute("DELETE FROM _outbox")
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    rows = conn.execute("SELECT * FROM _outbox WHERE table_name='users'").fetchall()
    assert len(rows) == 1
    assert rows[0]["op"] == "DELETE"
    assert rows[0]["pk_value"] == str(user_id)
    # DELETE payload captures the OLD row.
    payload = json.loads(rows[0]["payload_json"])
    assert payload["username"] == "carol"
    conn.close()


def test_composite_pk_capture_for_drafts():
    """`drafts (document_id, user_id)` → pk_value = '<doc_id>::<user_id>'."""
    conn = _migrated_conn()
    # Seed parent rows first (FK constraint).
    user_id = _seed_user(conn, username="dave")
    conn.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
        "sentence_count, text_density, estimated_difficulty, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ("doc-A", "/tmp/a.json", "pdf body", 2, 1, 0.5, "Kolay", "2026-05-18T00:00:00Z"),
    )
    conn.execute("DELETE FROM _outbox")
    conn.execute(
        "INSERT INTO drafts(document_id, user_id, references_json, updated_at) "
        "VALUES (?,?,?,?)",
        ("doc-A", user_id, "[]", "2026-05-18T00:00:00Z"),
    )
    rows = conn.execute("SELECT * FROM _outbox WHERE table_name='drafts'").fetchall()
    assert len(rows) == 1
    assert rows[0]["pk_value"] == f"doc-A::{user_id}", rows[0]["pk_value"]
    conn.close()


def test_migration_v0006_is_idempotent():
    """Re-running v0006 against an already-installed DB does not raise."""
    from backend.migrations.v0006_install_outbox_triggers import up as v0006_up
    conn = _migrated_conn()
    v0006_up(conn)
    v0006_up(conn)
    row = conn.execute(
        "SELECT count(*) AS c FROM sqlite_master "
        "WHERE type='trigger' AND name LIKE '_outbox_%'"
    ).fetchone()
    assert row["c"] == 69
    conn.close()


def test_outbox_table_not_self_mirrored():
    """Inserting into _outbox does not produce a recursive _outbox row.
    (D-06: _outbox itself is never mirrored.)
    """
    conn = _migrated_conn()
    conn.execute(
        "INSERT INTO _outbox(table_name, op, pk_value, payload_json, created_at) "
        "VALUES (?,?,?,?,?)",
        ("ghost", "INSERT", "1", "{}", "2026-05-18T00:00:00Z"),
    )
    rows = conn.execute(
        "SELECT count(*) AS c FROM _outbox WHERE table_name='_outbox'"
    ).fetchone()
    assert rows["c"] == 0  # no recursion
    conn.close()


# === Task 7: mirror config defaults ===


def test_config_defaults(monkeypatch):
    """Config module exposes the documented defaults when no env vars are set."""
    for name in (
        "NEON_MIRROR_URL", "NEON_MIRROR_BATCH_SIZE", "NEON_MIRROR_MAX_RETRIES",
        "NEON_MIRROR_EMPTY_SLEEP", "NEON_MIRROR_BATCH_SLEEP",
    ):
        monkeypatch.delenv(name, raising=False)
    from backend.mirror import config as cfg
    cfg.reload_from_env()
    assert cfg.NEON_MIRROR_URL is None
    assert cfg.NEON_MIRROR_BATCH_SIZE == 100
    assert cfg.MAX_RETRIES == 5
    assert cfg.EMPTY_QUEUE_SLEEP == 5.0
    assert cfg.INTER_BATCH_SLEEP == 0.1
    assert cfg.BACKOFF_SECONDS == (1.0, 2.0, 4.0, 8.0, 16.0)


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("NEON_MIRROR_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("NEON_MIRROR_BATCH_SIZE", "50")
    monkeypatch.setenv("NEON_MIRROR_EMPTY_SLEEP", "2.5")
    from backend.mirror import config as cfg
    cfg.reload_from_env()
    assert cfg.NEON_MIRROR_URL == "postgresql://u:p@h/db"
    assert cfg.NEON_MIRROR_BATCH_SIZE == 50
    assert cfg.EMPTY_QUEUE_SLEEP == 2.5
    # Restore defaults for downstream tests.
    monkeypatch.delenv("NEON_MIRROR_URL", raising=False)
    monkeypatch.delenv("NEON_MIRROR_BATCH_SIZE", raising=False)
    monkeypatch.delenv("NEON_MIRROR_EMPTY_SLEEP", raising=False)
    cfg.reload_from_env()


def test_neon_client_lazy_connect_with_no_dsn():
    """NeonClient(None).connect() returns False; no exception."""
    from backend.mirror.neon_client import NeonClient
    client = NeonClient(None)
    assert client.connect() is False
    assert client._conn is None
    # apply() should raise NeonTransient since connect failed.
    from backend.mirror.neon_client import NeonTransient
    with pytest.raises(NeonTransient):
        client.apply("INSERT", "users", "1", {"id": 1, "username": "x"})


def test_neon_client_upsert_sql_shape():
    """Confirm the upsert builder produces the expected SQL for both single and composite PKs."""
    from backend.mirror.neon_client import _build_upsert
    # Single-column PK (users.id).
    sql, args = _build_upsert("baran_users", ["id"], {"id": 1, "username": "a"})
    assert "INSERT INTO baran_users" in sql
    assert "ON CONFLICT (id) DO UPDATE" in sql
    assert "username = EXCLUDED.username" in sql
    assert args == [1, "a"]
    # Composite PK (drafts).
    sql2, args2 = _build_upsert(
        "baran_drafts", ["document_id", "user_id"],
        {"document_id": "doc1", "user_id": 42, "references_json": "[]"},
    )
    assert "ON CONFLICT (document_id, user_id) DO UPDATE" in sql2
    assert "references_json = EXCLUDED.references_json" in sql2


def test_neon_client_delete_sql_shape():
    from backend.mirror.neon_client import _build_delete
    # Single PK.
    sql, args = _build_delete("baran_users", ["id"], "42")
    assert sql == "DELETE FROM baran_users WHERE id = %s"
    assert args == ["42"]
    # Composite PK split on '::'.
    sql2, args2 = _build_delete("baran_drafts", ["document_id", "user_id"], "doc-1::99")
    assert "WHERE document_id = %s AND user_id = %s" in sql2
    assert args2 == ["doc-1", "99"]
