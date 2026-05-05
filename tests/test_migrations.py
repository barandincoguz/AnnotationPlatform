import sqlite3
from backend.shared.db import connect
from backend.migrations.runner import (
    Migration, ensure_migrations_table, applied_versions, apply_migrations
)


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def test_ensure_migrations_table_creates_it(db_path):
    conn = connect(db_path)
    try:
        ensure_migrations_table(conn)
        assert _has_table(conn, "schema_migrations")
    finally:
        conn.close()


def test_applied_versions_empty_initially(db_path):
    conn = connect(db_path)
    try:
        ensure_migrations_table(conn)
        assert applied_versions(conn) == set()
    finally:
        conn.close()


def test_apply_migrations_runs_pending(db_path):
    conn = connect(db_path)
    try:
        def m1(c): c.execute("CREATE TABLE m1 (x INT)")
        def m2(c): c.execute("CREATE TABLE m2 (x INT)")
        migs = [Migration("v0001", "first", m1), Migration("v0002", "second", m2)]
        applied = apply_migrations(conn, migs)
        assert applied == ["v0001", "v0002"]
        assert _has_table(conn, "m1")
        assert _has_table(conn, "m2")
        assert applied_versions(conn) == {"v0001", "v0002"}
    finally:
        conn.close()


def test_apply_migrations_idempotent(db_path):
    conn = connect(db_path)
    try:
        def m1(c): c.execute("CREATE TABLE m1 (x INT)")
        migs = [Migration("v0001", "first", m1)]
        first = apply_migrations(conn, migs)
        second = apply_migrations(conn, migs)
        assert first == ["v0001"]
        assert second == []
    finally:
        conn.close()


def test_apply_migrations_skips_already_applied(db_path):
    conn = connect(db_path)
    try:
        def m1(c): c.execute("CREATE TABLE m1 (x INT)")
        def m2(c): c.execute("CREATE TABLE m2 (x INT)")
        apply_migrations(conn, [Migration("v0001", "first", m1)])
        applied = apply_migrations(conn, [
            Migration("v0001", "first", m1),
            Migration("v0002", "second", m2),
        ])
        assert applied == ["v0002"]
    finally:
        conn.close()
