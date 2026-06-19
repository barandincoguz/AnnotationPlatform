"""v0013 - stop mirroring runtime locks and local system telemetry."""
import sqlite3


EXCLUDED_TABLES = ("document_locks", "system_events")


def up(conn: sqlite3.Connection) -> None:
    for table in EXCLUDED_TABLES:
        for suffix in ("ins", "upd", "del"):
            conn.execute(
                f"DROP TRIGGER IF EXISTS _outbox_{table}_{suffix}"
            )

    placeholders = ",".join("?" for _ in EXCLUDED_TABLES)
    conn.execute(
        f"DELETE FROM _outbox WHERE table_name IN ({placeholders})",
        EXCLUDED_TABLES,
    )
