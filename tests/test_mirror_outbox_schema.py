"""Tests for v0005_outbox_schema migration (Phase 4 — MIRROR-01)."""
import sqlite3

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.migrations.v0005_outbox_schema import up as outbox_up


def _fresh_conn() -> sqlite3.Connection:
    """In-memory SQLite connection with the same PRAGMAs as the request path."""
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrated_conn() -> sqlite3.Connection:
    """Fresh in-memory DB with all migrations applied (v0001..v0005)."""
    conn = _fresh_conn()
    apply_migrations(conn, discover_migrations())
    return conn


def test_outbox_table_exists_after_migration():
    conn = _migrated_conn()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='_outbox'"
    ).fetchone()
    assert row is not None, "_outbox table should exist after v0005"
    conn.close()


def test_outbox_has_expected_columns():
    conn = _migrated_conn()
    cols = conn.execute("PRAGMA table_info('_outbox')").fetchall()
    by_name = {c["name"]: c for c in cols}
    expected = {
        "id":             ("INTEGER", 0, None, 1),
        "table_name":     ("TEXT",    1, None, 0),
        "op":             ("TEXT",    1, None, 0),
        "pk_value":       ("TEXT",    1, None, 0),
        "payload_json":   ("TEXT",    1, None, 0),
        "created_at":     ("TEXT",    1, None, 0),
        "delivered_at":   ("TEXT",    0, None, 0),
        "error":          ("TEXT",    0, None, 0),
        "retry_count":    ("INTEGER", 1, "0",  0),
    }
    assert set(by_name.keys()) == set(expected.keys()), f"got {set(by_name.keys())}"
    for name, (typ, notnull, dflt, pk) in expected.items():
        c = by_name[name]
        assert c["type"].upper() == typ, f"{name} type {c['type']!r} != {typ!r}"
        assert c["notnull"] == notnull, f"{name} notnull mismatch"
        assert c["pk"] == pk, f"{name} pk flag mismatch"
        if dflt is not None:
            assert c["dflt_value"] == dflt, f"{name} default {c['dflt_value']!r} != {dflt!r}"
    conn.close()


def test_outbox_has_both_indexes():
    conn = _migrated_conn()
    idx = conn.execute("PRAGMA index_list('_outbox')").fetchall()
    names = {i["name"] for i in idx}
    assert "idx_outbox_delivered_at" in names
    assert "idx_outbox_created_at" in names
    conn.close()


def test_outbox_migration_is_idempotent():
    """Re-running up(conn) against the same DB does not raise."""
    conn = _migrated_conn()
    # Apply again directly — should be a silent no-op (CREATE TABLE IF NOT EXISTS).
    outbox_up(conn)
    outbox_up(conn)  # twice for good measure
    conn.close()


def test_outbox_op_check_constraint():
    """op = 'FOO' must raise IntegrityError (CHECK constraint)."""
    conn = _migrated_conn()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO _outbox(table_name, op, pk_value, payload_json, created_at) "
            "VALUES (?,?,?,?,?)",
            ("users", "FOO", "1", "{}", "2026-05-18T00:00:00Z"),
        )
    # Sanity: valid ops are accepted
    for op in ("INSERT", "UPDATE", "DELETE"):
        conn.execute(
            "INSERT INTO _outbox(table_name, op, pk_value, payload_json, created_at) "
            "VALUES (?,?,?,?,?)",
            ("users", op, "1", "{}", "2026-05-18T00:00:00Z"),
        )
    conn.close()
