from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


EXPECTED_TABLES = {
    # Core
    "users", "invite_codes", "site_settings", "documents_meta",
    "annotations", "annotation_versions", "drafts", "document_locks",
    # Event logs
    "user_sessions", "activity_events", "behavioral_events",
    "admin_audit_log", "system_events",
    # Auxiliary
    "gamification_state", "gamification_ledger", "badges_earned",
    "training_attempts", "notifications",
    # Hybrid override (Q5)
    "training_gold_doc_overrides",
    # Migration tracking (created by runner)
    "schema_migrations",
}


def _all_tables(conn) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r["name"] for r in rows}


def test_v0001_creates_all_19_tables(db_path):
    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())
        tables = _all_tables(conn)
        missing = EXPECTED_TABLES - tables
        assert not missing, f"Missing tables: {missing}"
    finally:
        conn.close()


def test_v0001_creates_indices(db_path):
    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        index_names = {r["name"] for r in rows}
        for expected in [
            "idx_users_active", "idx_ver_doc_time", "idx_act_user_time",
            "idx_audit_admin_time", "idx_ledger_user_time",
        ]:
            assert expected in index_names, f"missing index: {expected}"
    finally:
        conn.close()


def test_v0001_seeds_default_settings(db_path):
    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())
        rows = conn.execute("SELECT key FROM site_settings").fetchall()
        keys = {r["key"] for r in rows}
        for k in [
            "speed_warning.window_seconds",
            "char_limit.warn_threshold",
            "lock.expires_seconds",
            "backup.interval_seconds",
            "training.quiz_pass_threshold",
            "gamification.daily_target_docs",
            "gamification.xp_save",
        ]:
            assert k in keys, f"missing default setting: {k}"
    finally:
        conn.close()


def test_v0001_idempotent(db_path):
    conn = connect(db_path)
    try:
        first = apply_migrations(conn, discover_migrations())
        second = apply_migrations(conn, discover_migrations())
        assert first == ["v0001"]
        assert second == []
    finally:
        conn.close()
