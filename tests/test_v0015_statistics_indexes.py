from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


def _index_columns(conn, index_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA index_info({index_name})").fetchall()
    return [row["name"] for row in rows]


def test_v0015_adds_statistics_rollup_indexes(db_path):
    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        names = {row["name"] for row in rows}

        assert "idx_ver_created_user" in names
        assert "idx_act_created_user_type" in names
        assert "idx_ledger_created_user" in names

        assert _index_columns(conn, "idx_ver_created_user") == ["created_at", "user_id"]
        assert _index_columns(conn, "idx_act_created_user_type") == [
            "created_at",
            "user_id",
            "event_type",
        ]
        assert _index_columns(conn, "idx_ledger_created_user") == ["created_at", "user_id"]
    finally:
        conn.close()
