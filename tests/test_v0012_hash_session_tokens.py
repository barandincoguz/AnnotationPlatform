from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared import auth
from backend.shared.db import connect
from backend.users import service


def test_existing_raw_session_token_is_hashed_without_invalidating_cookie(db_path):
    conn = connect(db_path)
    try:
        migrations = discover_migrations()
        apply_migrations(
            conn,
            [migration for migration in migrations if migration.version <= "v0011"],
        )
        conn.execute(
            """
            INSERT INTO users(
                id, username, password_hash, role, created_at, updated_at
            ) VALUES (1, 'alice', 'hash', 'user', datetime('now'), datetime('now'))
            """
        )
        raw_token = "existing-browser-cookie-token"
        conn.execute(
            """
            INSERT INTO user_sessions(
                user_id, session_token, started_at, last_activity_at
            ) VALUES (1, ?, datetime('now'), datetime('now'))
            """,
            (raw_token,),
        )

        apply_migrations(
            conn,
            [migration for migration in migrations if migration.version == "v0012"],
        )

        stored = conn.execute(
            "SELECT session_token FROM user_sessions"
        ).fetchone()["session_token"]
        assert stored == auth.hash_session_token(raw_token)
        assert raw_token not in stored
        user = service.get_user_by_session(
            conn,
            session_token=raw_token,
        )
        assert user is not None
        assert user["username"] == "alice"
    finally:
        conn.close()
