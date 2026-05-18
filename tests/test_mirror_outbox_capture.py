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
