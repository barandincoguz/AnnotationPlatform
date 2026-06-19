"""v0011 - distinguish active training attempts from completed attempts."""
import sqlite3

from backend.migrations.helpers.schema_introspect import introspect_table
from backend.migrations.helpers.trigger_generator import build_triggers_for_table


def up(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(training_attempts)").fetchall()
    }
    finished_at = columns.get("finished_at")
    if finished_at is None or finished_at["notnull"] == 0:
        return

    conn.execute(
        """
        CREATE TABLE training_attempts_v0011 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            attempt_number INTEGER NOT NULL,
            quiz_score INTEGER NOT NULL,
            quiz_total INTEGER NOT NULL,
            annotation_pass_count INTEGER NOT NULL,
            annotation_total INTEGER NOT NULL,
            annotation_details_json TEXT,
            passed INTEGER NOT NULL,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO training_attempts_v0011(
            id, user_id, attempt_number, quiz_score, quiz_total,
            annotation_pass_count, annotation_total, annotation_details_json,
            passed, started_at, finished_at
        )
        SELECT
            id, user_id, attempt_number, quiz_score, quiz_total,
            annotation_pass_count, annotation_total, annotation_details_json,
            passed, started_at, finished_at
        FROM training_attempts
        """
    )
    conn.execute("DROP TABLE training_attempts")
    conn.execute(
        "ALTER TABLE training_attempts_v0011 RENAME TO training_attempts"
    )
    # Earlier code stamped finished_at at start because the column was
    # NOT NULL. Clear that placeholder only for attempts that have not
    # actually finalized; passed attempts and finalized failures keep
    # their historical completion timestamp.
    conn.execute(
        """
        UPDATE training_attempts
        SET finished_at = NULL
        WHERE passed = 0
          AND (
            annotation_details_json IS NULL
            OR COALESCE(
                CASE
                    WHEN json_valid(annotation_details_json)
                    THEN json_extract(
                        annotation_details_json,
                        '$._finalized'
                    )
                    ELSE 0
                END,
                0
            ) != 1
          )
        """
    )
    conn.execute(
        "CREATE INDEX idx_train_user ON training_attempts(user_id)"
    )

    schema = introspect_table(conn, "training_attempts")
    for statement in build_triggers_for_table(schema):
        conn.execute(statement)
