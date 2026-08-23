import sqlite3

import pytest

from backend.mirror import schema_sync


def test_schema_sync_failure_is_fail_closed(monkeypatch):
    def fail_connect(_dsn):
        raise RuntimeError("Neon unavailable")

    monkeypatch.setattr(schema_sync.psycopg, "connect", fail_connect)
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(RuntimeError, match="Neon unavailable"):
            schema_sync.sync_postgres_schema(conn, "postgresql://example.invalid/db")
    finally:
        conn.close()
