"""Tests for the Phase 4 schema introspection helper (Task 2) and
Postgres DDL generator (Task 3 — extended in a follow-up commit).

Uses a fresh in-memory SQLite DB seeded by the same migration runner
the production app uses, so the introspection results match the live
schema bit-for-bit.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.migrations.helpers.schema_introspect import (
    introspect_table,
    list_project_tables,
)


def _migrated_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    apply_migrations(conn, discover_migrations())
    return conn


# === Task 2: introspection ===


def test_introspect_users_columns():
    """`users` has the expected column shape including `created_at TIMESTAMP`."""
    conn = _migrated_conn()
    s = introspect_table(conn, "users")
    by_name = {c.name: c for c in s.columns}
    # PK column
    assert "id" in by_name
    assert by_name["id"].is_pk is True
    assert by_name["id"].sqlite_type.upper() == "INTEGER"
    assert by_name["id"].is_autoincrement is True  # INTEGER PRIMARY KEY AUTOINCREMENT
    # TIMESTAMP columns preserved as declared (D-11 maps to text on PG side)
    assert by_name["created_at"].sqlite_type.upper() == "TIMESTAMP"
    assert by_name["updated_at"].sqlite_type.upper() == "TIMESTAMP"
    # NOT NULL flags
    assert by_name["username"].notnull is True
    assert by_name["email"].notnull is False
    # Role default + CHECK constraint
    assert s.checks  # at least one CHECK present (role IN ('user','admin'))
    assert any("role" in c.lower() for c in s.checks)
    conn.close()


def test_introspect_drafts_composite_pk():
    """`drafts` has composite PK (document_id, user_id)."""
    conn = _migrated_conn()
    s = introspect_table(conn, "drafts")
    assert s.primary_key == ["document_id", "user_id"], s.primary_key
    # Neither participates in AUTOINCREMENT (composite PK can't be AUTOINCREMENT)
    by_name = {c.name: c for c in s.columns}
    assert by_name["document_id"].is_autoincrement is False
    assert by_name["user_id"].is_autoincrement is False
    conn.close()


def test_introspect_annotations_foreign_keys():
    """`annotations` has FKs to documents_meta (PK) and users (editor / completer)."""
    conn = _migrated_conn()
    s = introspect_table(conn, "annotations")
    fk_targets = {(fk.column, fk.ref_table) for fk in s.foreign_keys}
    assert ("last_editor_user_id", "users") in fk_targets
    assert ("completed_by_user_id", "users") in fk_targets
    # document_id is itself the PK + a FK to documents_meta
    assert ("document_id", "documents_meta") in fk_targets
    # The PK is a single TEXT column (NOT autoincrement)
    assert s.primary_key == ["document_id"]
    by_name = {c.name: c for c in s.columns}
    assert by_name["document_id"].sqlite_type.upper() == "TEXT"
    assert by_name["document_id"].is_autoincrement is False
    conn.close()


def test_list_project_tables_count_and_exclusions():
    """`list_project_tables` returns the 23 in-scope tables (no _outbox, no schema_migrations)."""
    conn = _migrated_conn()
    tables = list_project_tables(conn)
    assert "_outbox" not in tables, "_outbox must be excluded"
    assert "schema_migrations" not in tables, "schema_migrations must be excluded"
    assert "sqlite_sequence" not in tables, "sqlite_sequence must be excluded"
    assert len(tables) == 23, f"expected 23 in-scope tables, got {len(tables)}: {tables}"
    # A few sentinel checks
    assert "users" in tables
    assert "annotations" in tables
    assert "drafts" in tables
    conn.close()


def test_introspect_system_events_check_clause_with_nested_parens():
    """`system_events.severity` CHECK has nested parens — parser must handle it."""
    conn = _migrated_conn()
    s = introspect_table(conn, "system_events")
    assert any("severity" in c.lower() and "info" in c.lower() for c in s.checks), s.checks
    conn.close()
