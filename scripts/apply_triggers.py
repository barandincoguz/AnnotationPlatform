import sqlite3
from backend.migrations.helpers.schema_introspect import introspect_table
from backend.migrations.helpers.trigger_generator import build_triggers_for_table

conn = sqlite3.connect("data/db/annotations.db")
conn.row_factory = sqlite3.Row
schema = introspect_table(conn, "model_predictions")
for stmt in build_triggers_for_table(schema):
    conn.execute(stmt)
conn.commit()
print("Triggers applied to local SQLite!")
