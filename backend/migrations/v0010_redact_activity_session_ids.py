"""v0010 - keep local session references out of mirrored activity events."""
import sqlite3

from backend.migrations.helpers.schema_introspect import introspect_table
from backend.migrations.helpers.trigger_generator import build_triggers_for_table


TRIGGER_NAMES = (
    "_outbox_activity_events_ins",
    "_outbox_activity_events_upd",
    "_outbox_activity_events_del",
)


def up(conn: sqlite3.Connection) -> None:
    for trigger_name in TRIGGER_NAMES:
        conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")

    schema = introspect_table(conn, "activity_events")
    for statement in build_triggers_for_table(schema):
        conn.execute(statement)

    # Existing queued rows may target a legacy Neon FK. Preserve the event,
    # but remove its local-only session reference before dispatch.
    conn.execute(
        "UPDATE _outbox "
        "SET payload_json=json_set(payload_json, '$.session_id', NULL) "
        "WHERE table_name='activity_events' AND json_valid(payload_json)"
    )
