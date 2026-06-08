# backend/migrations/v0008_audit_hash_chain.py
"""v0008 — add hash and prev_hash columns to admin_audit_log.

Enables cryptographic tamper-evident hash-chaining of administrative audit logs.
"""
import sqlite3

SQL = """
ALTER TABLE admin_audit_log ADD COLUMN hash TEXT;
ALTER TABLE admin_audit_log ADD COLUMN prev_hash TEXT;

CREATE INDEX idx_audit_hash ON admin_audit_log(hash) WHERE hash IS NOT NULL;
"""


def up(conn: sqlite3.Connection) -> None:
    for stmt in (s.strip() for s in SQL.split(";")):
        if stmt:
            conn.execute(stmt)
