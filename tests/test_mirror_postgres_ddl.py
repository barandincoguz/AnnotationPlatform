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
from backend.migrations.helpers.postgres_ddl import (
    build_all_pg_ddl,
    build_pg_ddl_for_table,
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
    """Operational tables and bearer credentials are excluded from the mirror."""
    conn = _migrated_conn()
    tables = list_project_tables(conn)
    assert "_outbox" not in tables, "_outbox must be excluded"
    assert "schema_migrations" not in tables, "schema_migrations must be excluded"
    assert "sqlite_sequence" not in tables, "sqlite_sequence must be excluded"
    assert "user_sessions" not in tables, "bearer sessions must be excluded"
    assert len(tables) == 23, f"expected 23 in-scope tables, got {len(tables)}: {tables}"
    # A few sentinel checks
    assert "users" in tables
    assert "user_feedback" in tables
    assert "annotations" in tables
    assert "drafts" in tables
    conn.close()


def test_introspect_system_events_check_clause_with_nested_parens():
    """`system_events.severity` CHECK has nested parens — parser must handle it."""
    conn = _migrated_conn()
    s = introspect_table(conn, "system_events")
    assert any("severity" in c.lower() and "info" in c.lower() for c in s.checks), s.checks
    conn.close()


# === Task 3: Postgres DDL generator ===


def _full_ddl(conn) -> str:
    return build_all_pg_ddl(conn)


def test_pg_ddl_users_bigserial_primary_key():
    conn = _migrated_conn()
    stmts = build_pg_ddl_for_table(introspect_table(conn, "users"))
    sql = "\n".join(stmts)
    assert "CREATE TABLE IF NOT EXISTS baran_users" in sql
    # `id` is the AUTOINCREMENT PK → bigserial PRIMARY KEY
    assert "id bigserial PRIMARY KEY" in sql, sql
    conn.close()


def test_pg_ddl_annotations_text_primary_key_preserved():
    """`annotations.document_id TEXT PRIMARY KEY` must NOT be rewritten to bigserial."""
    conn = _migrated_conn()
    stmts = build_pg_ddl_for_table(introspect_table(conn, "annotations"))
    sql = "\n".join(stmts)
    # Must contain `document_id text PRIMARY KEY` (or with the inline REFERENCES)
    assert "document_id text PRIMARY KEY" in sql, sql
    # Must NOT contain `document_id bigserial`
    assert "document_id bigserial" not in sql, sql
    conn.close()


def test_pg_ddl_drafts_composite_pk_with_mixed_types():
    """`drafts` composite PK (document_id TEXT, user_id INTEGER)."""
    conn = _migrated_conn()
    stmts = build_pg_ddl_for_table(introspect_table(conn, "drafts"))
    sql = "\n".join(stmts)
    # Each column line with its mapped type (no inline PRIMARY KEY).
    assert "document_id text" in sql
    assert "user_id bigint" in sql
    # Trailing composite PK clause.
    assert "PRIMARY KEY (document_id, user_id)" in sql, sql
    # Composite PK columns must NOT carry inline PRIMARY KEY tokens
    # ("document_id text PRIMARY KEY" would be wrong here).
    assert "document_id text PRIMARY KEY" not in sql
    assert "user_id bigint PRIMARY KEY" not in sql
    conn.close()


def test_pg_ddl_fk_rewrites_to_baran():
    """`REFERENCES users(id) ON DELETE SET NULL` → `REFERENCES baran_users(id) ON DELETE SET NULL`."""
    conn = _migrated_conn()
    stmts = build_pg_ddl_for_table(introspect_table(conn, "annotations"))
    sql = "\n".join(stmts)
    assert "REFERENCES baran_users(id) ON DELETE SET NULL" in sql, sql
    # And no un-rewritten REFERENCES to bare project tables
    assert "REFERENCES users(id)" not in sql
    assert "REFERENCES documents_meta(document_id)" not in sql
    conn.close()


def test_pg_ddl_drafts_references_json_maps_to_jsonb():
    conn = _migrated_conn()
    stmts = build_pg_ddl_for_table(introspect_table(conn, "drafts"))
    sql = "\n".join(stmts)
    assert "references_json jsonb" in sql, sql
    conn.close()


def test_pg_ddl_system_events_check_copied_verbatim():
    conn = _migrated_conn()
    stmts = build_pg_ddl_for_table(introspect_table(conn, "system_events"))
    sql = "\n".join(stmts)
    # CHECK body contains the literal severity-in-list expression.
    assert "CHECK (" in sql
    assert "severity IN ('info','warn','error')" in sql, sql
    conn.close()


def test_pg_ddl_topological_order_users_before_annotations():
    conn = _migrated_conn()
    full = build_all_pg_ddl(conn)
    pos_users = full.find("CREATE TABLE IF NOT EXISTS baran_users")
    pos_anno = full.find("CREATE TABLE IF NOT EXISTS baran_annotations")
    assert pos_users != -1 and pos_anno != -1
    assert pos_users < pos_anno, "users must come before annotations (FK target)"
    # documents_meta is also a parent of annotations
    pos_meta = full.find("CREATE TABLE IF NOT EXISTS baran_documents_meta")
    assert pos_meta < pos_anno
    conn.close()


def test_pg_ddl_excludes_outbox_and_schema_migrations():
    conn = _migrated_conn()
    full = build_all_pg_ddl(conn)
    assert "baran__outbox" not in full
    assert "baran_schema_migrations" not in full
    assert "baran_user_sessions" not in full
    conn.close()


def test_pg_ddl_every_create_table_is_idempotent():
    conn = _migrated_conn()
    full = build_all_pg_ddl(conn)
    create_count = full.count("CREATE TABLE ")
    idempotent_count = full.count("CREATE TABLE IF NOT EXISTS ")
    assert create_count == idempotent_count == 23, (create_count, idempotent_count)
    conn.close()


def test_pg_ddl_every_underscore_json_column_maps_to_jsonb():
    """Heuristic guard: every column ending in `_json` across all in-scope
    tables must surface as `jsonb` in the generated DDL.
    """
    conn = _migrated_conn()
    full = build_all_pg_ddl(conn)
    json_columns: list[tuple[str, str]] = []
    for t in list_project_tables(conn):
        s = introspect_table(conn, t)
        for c in s.columns:
            if c.name.endswith("_json"):
                json_columns.append((t, c.name))
    assert json_columns, "expected at least one *_json column in the project schema"
    for table, col in json_columns:
        # The `col jsonb` token must appear within the `baran_<table>` block.
        block_start = full.find(f"CREATE TABLE IF NOT EXISTS baran_{table}")
        assert block_start != -1, f"missing baran_{table} block"
        block_end = full.find("CREATE TABLE IF NOT EXISTS", block_start + 1)
        if block_end == -1:
            block_end = len(full)
        block = full[block_start:block_end]
        assert f"{col} jsonb" in block, (
            f"baran_{table}.{col} did not map to jsonb in:\n{block}"
        )
    conn.close()


def test_pg_ddl_full_script_contains_23_create_table_statements():
    conn = _migrated_conn()
    full = build_all_pg_ddl(conn)
    count = full.count("CREATE TABLE IF NOT EXISTS baran_")
    assert count == 23, count
    conn.close()


def test_pg_ddl_omits_fk_to_local_only_session_table():
    conn = _migrated_conn()
    sql = "\n".join(
        build_pg_ddl_for_table(introspect_table(conn, "activity_events"))
    )
    assert "session_id bigint" in sql
    assert "baran_user_sessions" not in sql
    conn.close()


def test_committed_neon_ddl_matches_regen():
    """Phase 6 P6-6 schema drift guard.

    Asserts the committed `migrations/postgres/001-baran-init.sql` is
    byte-identical to what `build_all_pg_ddl` emits against a freshly-migrated
    SQLite schema. If this fails, the operator must regenerate the committed
    file via `python -m scripts.regen_neon_ddl` and commit the result.
    """
    from pathlib import Path

    # Walk up from this test file to the repo root (marker: pyproject.toml).
    repo_root = None
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            repo_root = parent
            break
    assert repo_root is not None, "could not locate repo root (pyproject.toml marker)"

    committed_path = repo_root / "migrations" / "postgres" / "001-baran-init.sql"
    assert committed_path.is_file(), f"missing committed DDL at {committed_path}"

    conn = _migrated_conn()
    try:
        generated = build_all_pg_ddl(conn)
    finally:
        conn.close()

    committed = committed_path.read_text(encoding="utf-8")

    assert generated == committed, (
        "Postgres DDL drift detected: the committed "
        "`migrations/postgres/001-baran-init.sql` no longer matches the "
        "live SQLite schema. Regenerate and re-commit:\n"
        "    python -m scripts.regen_neon_ddl\n"
        "then `git add migrations/postgres/001-baran-init.sql` and commit."
    )
