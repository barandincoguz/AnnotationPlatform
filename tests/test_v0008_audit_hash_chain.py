# tests/test_v0008_audit_hash_chain.py
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


def test_v0008_migration_adds_columns(db_path):
    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())
        
        # Verify columns exist in admin_audit_log
        cursor = conn.execute("PRAGMA table_info(admin_audit_log)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "hash" in columns
        assert "prev_hash" in columns
    finally:
        conn.close()
