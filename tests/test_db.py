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
