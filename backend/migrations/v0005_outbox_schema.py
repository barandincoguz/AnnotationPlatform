"""v0005 — add _outbox table for the Neon dual-write mirror (Phase 4, D-04, D-05).

Every committed INSERT/UPDATE/DELETE on a project table will fire a trigger
(installed in v0006) that appends one _outbox row inside the same transaction.
The async dispatcher (backend/mirror/dispatcher.py) drains this queue and
applies each row to the partner Neon Postgres database under baran_* tables.

_outbox is local operational state only; it is NEVER itself mirrored (D-06).
"""
import sqlite3


SQL = """
CREATE TABLE IF NOT EXISTS _outbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name      TEXT NOT NULL,
    op              TEXT NOT NULL CHECK(op IN ('INSERT','UPDATE','DELETE')),
    pk_value        TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    delivered_at    TEXT,
    error           TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_outbox_delivered_at ON _outbox(delivered_at);
CREATE INDEX IF NOT EXISTS idx_outbox_created_at   ON _outbox(created_at);
"""


def up(conn: sqlite3.Connection) -> None:
    for stmt in (s.strip() for s in SQL.split(";")):
        if stmt:
            conn.execute(stmt)
