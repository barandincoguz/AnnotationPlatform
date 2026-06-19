from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


def test_finished_at_becomes_nullable_and_preserves_rows(db_path):
    conn = connect(db_path)
    try:
        migrations = discover_migrations()
        apply_migrations(
            conn,
            [migration for migration in migrations if migration.version <= "v0010"],
        )
        conn.execute(
            """
            INSERT INTO users(
                id, username, password_hash, role, created_at, updated_at
            ) VALUES (1, 'trainer', 'hash', 'user', datetime('now'), datetime('now'))
            """
        )
        conn.execute(
            """
            INSERT INTO training_attempts(
                id, user_id, attempt_number, quiz_score, quiz_total,
                annotation_pass_count, annotation_total, passed,
                started_at, finished_at
            ) VALUES (
                7, 1, 1, 5, 5, 3, 3, 1,
                '2026-06-18T10:00:00+00:00',
                '2026-06-18T10:00:00+00:00'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO training_attempts(
                id, user_id, attempt_number, quiz_score, quiz_total,
                annotation_pass_count, annotation_total, passed,
                started_at, finished_at
            ) VALUES (
                8, 1, 2, 0, 5, 0, 3, 0,
                '2026-06-18T10:05:00+00:00',
                '2026-06-18T10:05:00+00:00'
            )
            """
        )

        apply_migrations(
            conn,
            [migration for migration in migrations if migration.version == "v0011"],
        )

        finished_at = next(
            row for row in conn.execute(
                "PRAGMA table_info(training_attempts)"
            ).fetchall()
            if row["name"] == "finished_at"
        )
        assert finished_at["notnull"] == 0
        assert conn.execute(
            "SELECT id, finished_at FROM training_attempts WHERE id=7"
        ).fetchone()["finished_at"] == "2026-06-18T10:00:00+00:00"
        assert conn.execute(
            "SELECT finished_at FROM training_attempts WHERE id=8"
        ).fetchone()["finished_at"] is None

        conn.execute(
            """
            INSERT INTO training_attempts(
                user_id, attempt_number, quiz_score, quiz_total,
                annotation_pass_count, annotation_total, passed,
                started_at, finished_at
            ) VALUES (1, 2, 0, 5, 0, 3, 0, datetime('now'), NULL)
            """
        )
    finally:
        conn.close()
