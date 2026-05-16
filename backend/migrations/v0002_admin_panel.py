"""v0002 — Admin Panel: training_quiz_overrides table.

Adds a single new table symmetric with training_gold_doc_overrides (v0001).
Quiz override storage allows admins (Paket 11) to edit, replace, or
soft-delete training quiz questions without code changes. NULL fields
fall back to baseline `quiz_data.QUIZ_QUESTIONS` per the hybrid resolver.
"""
import sqlite3


SCHEMA_SQL = """
CREATE TABLE training_quiz_overrides (
    question_id         TEXT PRIMARY KEY,
    is_deleted          INTEGER NOT NULL DEFAULT 0,
    text                TEXT,
    choices_json        TEXT,
    correct_choice_idx  INTEGER,
    source              TEXT NOT NULL CHECK(source IN ('override','custom')),
    created_by_admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);

CREATE INDEX idx_quiz_overrides_active
    ON training_quiz_overrides(question_id) WHERE is_deleted=0;
"""


def up(conn: sqlite3.Connection) -> None:
    for stmt in (s.strip() for s in SCHEMA_SQL.split(";")):
        if stmt:
            conn.execute(stmt)
