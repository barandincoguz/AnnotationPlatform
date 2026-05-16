"""v0004 — add trace_id column + partial index to admin_audit_log and system_events.

Allows correlating admin-triggered chains (audit row + the system_events rows
emitted by the same operation) via a single key. Background-loop and lifespan
events are emitted with NULL trace_id by design.

ALTER TABLE ADD COLUMN is O(1) in SQLite; partial indexes (3.8+) keep the
index compact since most rows will have NULL trace_id (legacy + loop-origin).
"""
import sqlite3


SQL = """
ALTER TABLE admin_audit_log ADD COLUMN trace_id TEXT;
ALTER TABLE system_events   ADD COLUMN trace_id TEXT;

CREATE INDEX idx_audit_trace
  ON admin_audit_log(trace_id)
  WHERE trace_id IS NOT NULL;

CREATE INDEX idx_sys_trace
  ON system_events(trace_id)
  WHERE trace_id IS NOT NULL;
"""


def up(conn: sqlite3.Connection) -> None:
    for stmt in (s.strip() for s in SQL.split(";")):
        if stmt:
            conn.execute(stmt)
