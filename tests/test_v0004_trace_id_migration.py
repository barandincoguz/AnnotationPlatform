"""Tests for v0004 — trace_id column + partial indexes."""
from pathlib import Path

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def _columns(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _index_names(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA index_list({table})").fetchall()}


def test_v0004_adds_trace_id_to_admin_audit_log(fresh_db):
    assert "trace_id" in _columns(fresh_db, "admin_audit_log")


def test_v0004_adds_trace_id_to_system_events(fresh_db):
    assert "trace_id" in _columns(fresh_db, "system_events")


def test_v0004_creates_partial_index_on_admin_audit_log(fresh_db):
    assert "idx_audit_trace" in _index_names(fresh_db, "admin_audit_log")


def test_v0004_creates_partial_index_on_system_events(fresh_db):
    assert "idx_sys_trace" in _index_names(fresh_db, "system_events")


def test_v0004_up_raises_on_direct_reapplication(fresh_db):
    """Calling up() a second time on an already-migrated DB must raise.
    The migration relies on the schema_migrations runner gate for
    idempotency — up() itself is intentionally non-reentrant
    (ALTER TABLE ADD COLUMN errors on duplicate column). This test
    pins the contract: anyone wrapping up() outside the runner must
    handle the raise."""
    from backend.migrations.v0004_trace_id import up
    with pytest.raises(Exception):
        up(fresh_db)
