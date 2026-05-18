"""Tests for the Phase 4 trigger generator (Task 4).

Covers per-table trigger SQL shape, the full 69-trigger count,
end-to-end install + capture behavior, and the pk_columns_manifest export.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.migrations.helpers.schema_introspect import introspect_table
from backend.migrations.helpers.trigger_generator import (
    build_all_triggers,
    build_pk_columns_manifest,
    build_triggers_for_table,
)


def _migrated_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    apply_migrations(conn, discover_migrations())
    return conn


def test_users_triggers_have_expected_names_and_columns():
    conn = _migrated_conn()
    s = introspect_table(conn, "users")
    triggers = build_triggers_for_table(s)
    assert len(triggers) == 3
    joined = " ;; ".join(triggers)
    assert "_outbox_users_ins" in joined
    assert "_outbox_users_upd" in joined
    assert "_outbox_users_del" in joined
    # INSERT trigger body uses NEW.id and enumerates all users columns
    insert_sql = triggers[0]
    assert "AFTER INSERT ON users" in insert_sql
    assert "CAST(NEW.id AS TEXT)" in insert_sql
    # Every users column must appear in the json_object payload.
    for col in ("id", "username", "email", "password_hash", "role",
                "is_active", "has_passed_training", "has_seen_manual",
                "avatar_color", "created_at", "updated_at"):
        assert f"'{col}', NEW.{col}" in insert_sql, f"missing column {col}"
    conn.close()


def test_annotations_pk_is_text_uses_cast():
    """`annotations.document_id` is TEXT PRIMARY KEY → CAST(NEW.document_id AS TEXT)."""
    conn = _migrated_conn()
    s = introspect_table(conn, "annotations")
    triggers = build_triggers_for_table(s)
    insert_sql = triggers[0]
    assert "CAST(NEW.document_id AS TEXT)" in insert_sql
    conn.close()


def test_delete_trigger_uses_old_row():
    conn = _migrated_conn()
    s = introspect_table(conn, "users")
    triggers = build_triggers_for_table(s)
    delete_sql = triggers[2]
    assert "AFTER DELETE ON users" in delete_sql
    assert "OLD.id" in delete_sql
    assert "NEW.id" not in delete_sql  # NEW is undefined on DELETE
    conn.close()


def test_drafts_composite_pk_concat():
    """`drafts (document_id, user_id)` DELETE → `OLD.document_id || '::' || OLD.user_id`."""
    conn = _migrated_conn()
    s = introspect_table(conn, "drafts")
    triggers = build_triggers_for_table(s)
    delete_sql = triggers[2]
    assert "AFTER DELETE ON drafts" in delete_sql
    assert "CAST(OLD.document_id AS TEXT) || '::' || CAST(OLD.user_id AS TEXT)" in delete_sql, delete_sql
    conn.close()


def test_build_all_triggers_returns_69_statements():
    conn = _migrated_conn()
    all_t = build_all_triggers(conn)
    assert len(all_t) == 69, f"expected 69 triggers, got {len(all_t)}"
    conn.close()


def test_install_all_triggers_produces_69_in_sqlite_master():
    """Run the generated trigger SQL against a freshly migrated DB and confirm 69 rows."""
    conn = _migrated_conn()
    triggers = build_all_triggers(conn)
    # Wrap in explicit BEGIN IMMEDIATE / COMMIT to mirror the runner.
    conn.execute("BEGIN IMMEDIATE")
    try:
        for stmt in triggers:
            conn.execute(stmt)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    row = conn.execute(
        "SELECT count(*) AS c FROM sqlite_master WHERE type='trigger' AND name LIKE '_outbox_%'"
    ).fetchone()
    assert row["c"] == 69, f"expected 69 triggers, got {row['c']}"
    conn.close()


def test_trigger_sql_has_no_line_comments():
    """`-- ...` comments are stripped by the runner's _split_sql; verify generated SQL has none."""
    conn = _migrated_conn()
    triggers = build_all_triggers(conn)
    for stmt in triggers:
        assert "--" not in stmt, f"trigger contains line comment:\n{stmt}"
    conn.close()


def test_pk_columns_manifest_has_23_keys_with_expected_pks():
    conn = _migrated_conn()
    manifest = build_pk_columns_manifest(conn)
    assert len(manifest) == 23, f"expected 23 manifest entries, got {len(manifest)}"
    assert manifest["users"] == ["id"]
    assert manifest["drafts"] == ["document_id", "user_id"]
    assert manifest["annotations"] == ["document_id"]
    assert manifest["site_settings"] == ["key"]
    # Composite PK from badges_earned
    assert manifest["badges_earned"] == ["user_id", "badge_id"]
    # Excluded operational tables must not appear.
    assert "_outbox" not in manifest
    assert "schema_migrations" not in manifest
    conn.close()
