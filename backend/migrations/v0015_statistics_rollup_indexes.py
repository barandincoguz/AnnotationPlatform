"""v0015 — add created-at-leading indexes for statistics rollups."""
import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ver_created_user "
        "ON annotation_versions(created_at DESC, user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_act_created_user_type "
        "ON activity_events(created_at DESC, user_id, event_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_created_user "
        "ON gamification_ledger(created_at DESC, user_id)"
    )
