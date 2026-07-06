"""Migration: add user_feedback table (complaints/suggestions)."""
import sqlite3


SCHEMA_SQL = """
CREATE TABLE user_feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       TEXT NOT NULL CHECK(type IN ('complaint', 'suggestion')),
    message    TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_fb_user_time ON user_feedback(user_id, created_at DESC);
CREATE INDEX idx_fb_type ON user_feedback(type);
"""


def up(conn: sqlite3.Connection) -> None:
    for raw in SCHEMA_SQL.split(";"):
        stmt = raw.strip()
        if stmt:
            conn.execute(stmt)
