import sqlite3

from backend.migrations.v0009_exclude_user_sessions_from_mirror import up


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE user_sessions (
            id INTEGER PRIMARY KEY,
            session_token TEXT NOT NULL
        );
        CREATE TABLE _outbox (
            id INTEGER PRIMARY KEY,
            table_name TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE TRIGGER _outbox_user_sessions_ins
        AFTER INSERT ON user_sessions
        BEGIN
            INSERT INTO _outbox(table_name, payload_json)
            VALUES ('user_sessions', json_object('session_token', NEW.session_token));
        END;
        CREATE TRIGGER _outbox_user_sessions_upd
        AFTER UPDATE ON user_sessions BEGIN SELECT 1; END;
        CREATE TRIGGER _outbox_user_sessions_del
        AFTER DELETE ON user_sessions BEGIN SELECT 1; END;
        """
    )
    return conn


def test_migration_drops_session_triggers_and_purges_all_queued_tokens():
    conn = _conn()
    conn.execute(
        "INSERT INTO user_sessions(id, session_token) VALUES (1, 'secret-token')"
    )
    conn.execute(
        "INSERT INTO _outbox(table_name, payload_json) VALUES ('users', '{}')"
    )

    up(conn)

    triggers = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='trigger' AND name LIKE '_outbox_user_sessions_%'"
    ).fetchall()
    assert triggers == []
    assert conn.execute(
        "SELECT COUNT(*) FROM _outbox WHERE table_name='user_sessions'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM _outbox WHERE table_name='users'"
    ).fetchone()[0] == 1
    conn.close()


def test_migration_is_idempotent():
    conn = _conn()
    up(conn)
    up(conn)
    conn.close()
