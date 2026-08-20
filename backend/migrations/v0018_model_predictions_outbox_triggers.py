"""v0018 — install outbox triggers on model_predictions so predictions mirror to NeonDB."""
import sqlite3

from backend.migrations.helpers.schema_introspect import introspect_table
from backend.migrations.helpers.trigger_generator import build_triggers_for_table


def up(conn: sqlite3.Connection) -> None:
    schema = introspect_table(conn, "model_predictions")
    for stmt in build_triggers_for_table(schema):
        conn.execute(stmt)
