import json
import sqlite3

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.migrations.v0010_redact_activity_session_ids import up


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    apply_migrations(conn, discover_migrations())
    return conn


def test_migration_rebuilds_triggers_and_scrubs_queued_session_references():
    conn = _conn()
    conn.execute(
        "INSERT INTO _outbox("
        "table_name, op, pk_value, payload_json, created_at"
        ") VALUES ('activity_events', 'INSERT', '1', ?, 'now')",
        (json.dumps({"id": 1, "session_id": 42}),),
    )

    up(conn)

    trigger_sql = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='trigger' AND name='_outbox_activity_events_ins'"
    ).fetchone()["sql"]
    assert "'session_id', NULL" in trigger_sql
    payload = conn.execute(
        "SELECT payload_json FROM _outbox "
        "WHERE table_name='activity_events' ORDER BY id DESC LIMIT 1"
    ).fetchone()["payload_json"]
    assert json.loads(payload)["session_id"] is None
    conn.close()


def test_migration_is_idempotent():
    conn = _conn()
    up(conn)
    up(conn)
    conn.close()
