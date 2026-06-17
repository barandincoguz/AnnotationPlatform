"""v0009 - stop mirroring bearer session tokens and purge queued copies."""
import sqlite3


SESSION_TRIGGER_NAMES = (
    "_outbox_user_sessions_ins",
    "_outbox_user_sessions_upd",
    "_outbox_user_sessions_del",
)


def up(conn: sqlite3.Connection) -> None:
    for trigger_name in SESSION_TRIGGER_NAMES:
        conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")

    # Purge delivered rows too: payload_json contains the plaintext bearer
    # token, so retaining historical rows would preserve the credential.
    conn.execute("DELETE FROM _outbox WHERE table_name='user_sessions'")
