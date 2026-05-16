"""Migration runner — atomicity guarantee.

If a migration raises mid-flight (or the schema_migrations INSERT
fails), the partial changes must roll back. Otherwise the next boot
sees a half-applied schema with no version row, causing the next
boot to retry the migration against a partially-existing schema —
usually fatal since most migrations are not idempotent.
"""
import sqlite3
import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import Migration, apply_migrations
from backend.shared.db import connect


class _BadMigration:
    """A migration that creates a table then raises before completing."""
    version = "v9999_bad"
    name = "bad"

    @staticmethod
    def up(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE bad_test (id INTEGER PRIMARY KEY)")
        raise RuntimeError("simulated migration failure")


def test_migration_rollback_on_failure(tmp_path):
    db_path = tmp_path / "atomic.db"
    conn = connect(db_path)
    try:
        # Bring the schema up to v0004 so schema_migrations table exists.
        apply_migrations(conn, discover_migrations())

        with pytest.raises(RuntimeError, match="simulated migration failure"):
            apply_migrations(conn, [_BadMigration()])

        # bad_test table must NOT exist — DDL was rolled back.
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bad_test'"
        ).fetchone()
        assert row is None, "bad_test table should have been rolled back"

        # v9999_bad must NOT appear in schema_migrations.
        ver = conn.execute(
            "SELECT version FROM schema_migrations WHERE version=?",
            ("v9999_bad",),
        ).fetchone()
        assert ver is None, "version row should not exist after rollback"
    finally:
        conn.close()


def test_migration_version_absent_on_up_error(tmp_path):
    """Even if up() raises after partial DDL, no version row is recorded."""
    db_path = tmp_path / "atomic2.db"
    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())

        call_count = 0

        class _PartialMigration:
            version = "v9998_partial"
            name = "partial"

            @staticmethod
            def up(c: sqlite3.Connection) -> None:
                nonlocal call_count
                call_count += 1
                c.execute("CREATE TABLE partial_test (x TEXT)")
                raise ValueError("partial failure")

        with pytest.raises(ValueError, match="partial failure"):
            apply_migrations(conn, [_PartialMigration()])

        assert call_count == 1
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='partial_test'"
        ).fetchone()
        assert row is None, "partial_test table should have been rolled back"

        ver = conn.execute(
            "SELECT version FROM schema_migrations WHERE version=?",
            ("v9998_partial",),
        ).fetchone()
        assert ver is None
    finally:
        conn.close()


def test_successful_migration_is_versioned(tmp_path):
    """Sanity-check: a clean migration must produce a version row."""
    db_path = tmp_path / "atomic3.db"
    conn = connect(db_path)
    try:
        result = apply_migrations(conn, discover_migrations())
        assert "v0001" in result
        ver = conn.execute(
            "SELECT version FROM schema_migrations WHERE version='v0001'"
        ).fetchone()
        assert ver is not None
        assert ver["version"] == "v0001"
    finally:
        conn.close()
