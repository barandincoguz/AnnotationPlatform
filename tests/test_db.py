import sqlite3
from backend.shared.db import connect


def test_connect_returns_connection(db_path):
    conn = connect(db_path)
    try:
        assert isinstance(conn, sqlite3.Connection)
    finally:
        conn.close()


def test_connect_enables_wal_mode(db_path):
    conn = connect(db_path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        conn.close()


def test_connect_enables_foreign_keys(db_path):
    conn = connect(db_path)
    try:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
    finally:
        conn.close()


def test_connect_uses_row_factory(db_path):
    conn = connect(db_path)
    try:
        conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'hi')")
        row = conn.execute("SELECT * FROM t").fetchone()
        assert row["a"] == 1
        assert row["b"] == "hi"
    finally:
        conn.close()


def test_connect_sets_busy_timeout(db_path):
    """connect() must set PRAGMA busy_timeout so concurrent BEGIN IMMEDIATE
    writes (retention loop, backup loop, locks sweep) wait for the lock
    instead of failing immediately. Without this, the docstrings in
    loop.py modules that claim 'serializes via busy_timeout' would be
    false, and a future task firing more frequently could see
    'database is locked' on the first contended cycle."""
    conn = connect(db_path)
    try:
        timeout_ms = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        # 5000 ms is the project default; assert >= 1000 to allow tuning later
        # without silently regressing to 0.
        assert timeout_ms >= 1000, f"busy_timeout too low: {timeout_ms}ms"
    finally:
        conn.close()
