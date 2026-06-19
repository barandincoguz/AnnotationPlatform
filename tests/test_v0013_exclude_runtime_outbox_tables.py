from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


def test_runtime_triggers_and_queued_rows_are_removed(db_path):
    conn = connect(db_path)
    try:
        migrations = discover_migrations()
        apply_migrations(
            conn,
            [migration for migration in migrations if migration.version <= "v0012"],
        )
        conn.execute(
            """
            INSERT INTO _outbox(
                table_name, op, pk_value, payload_json, created_at
            ) VALUES
                ('system_events', 'INSERT', '1', '{}', datetime('now')),
                ('document_locks', 'INSERT', 'doc', '{}', datetime('now')),
                ('users', 'INSERT', '1', '{}', datetime('now'))
            """
        )

        apply_migrations(
            conn,
            [migration for migration in migrations if migration.version == "v0013"],
        )

        triggers = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='trigger' AND name LIKE '_outbox_%'"
            ).fetchall()
        }
        assert not any("system_events" in name for name in triggers)
        assert not any("document_locks" in name for name in triggers)
        queued_tables = [
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM _outbox ORDER BY id"
            ).fetchall()
        ]
        assert queued_tables == ["users"]
    finally:
        conn.close()
