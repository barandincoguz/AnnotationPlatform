"""Tests for backend.users.service.seed_bootstrap_admin.

Behaviour:
  - Idempotent: only seeds when no active admin exists.
  - Fails on username conflict with existing non-admin user.
  - Fails when password set is None / empty while username set.
  - Audit-logs the seed via admin_audit_log.
"""
import pytest

from backend.shared.db import connect
from backend.shared import auth
from backend.users import service
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "bootstrap.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def test_seed_creates_admin_when_no_admin(db):
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    row = db.execute(
        "SELECT username, role, is_active, has_passed_training, has_seen_manual "
        "FROM users WHERE username=?",
        ("rootadmin",),
    ).fetchone()
    assert row is not None
    assert row["role"] == "admin"
    assert row["is_active"] == 1
    assert row["has_passed_training"] == 1
    assert row["has_seen_manual"] == 1


def test_seed_idempotent(db):
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    count = db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE username=?", ("rootadmin",)
    ).fetchone()["c"]
    assert count == 1


def test_seed_skipped_when_admin_exists(db):
    db.execute(
        "INSERT INTO users(username, password_hash, role, is_active, "
        "avatar_color, created_at, updated_at) "
        "VALUES (?, ?, 'admin', 1, '#000', datetime('now'), datetime('now'))",
        ("existing_admin", auth.hash_password("anypass1234")),
    )
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    row = db.execute("SELECT 1 FROM users WHERE username=?", ("rootadmin",)).fetchone()
    assert row is None  # no new admin seeded


def test_seed_fails_if_username_taken_by_user(db):
    db.execute(
        "INSERT INTO users(username, password_hash, role, is_active, "
        "avatar_color, created_at, updated_at) "
        "VALUES (?, ?, 'user', 1, '#000', datetime('now'), datetime('now'))",
        ("rootadmin", auth.hash_password("userpass1234")),
    )
    with pytest.raises(RuntimeError) as exc:
        service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    assert "conflicts with existing non-admin user" in str(exc.value)


def test_seed_skipped_when_env_missing(db):
    service.seed_bootstrap_admin(db, username="", password="strongpass1234")
    count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    assert count == 0
    service.seed_bootstrap_admin(db, username="rootadmin", password="")
    count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    assert count == 0


def test_seed_writes_audit_log(db):
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    row = db.execute(
        "SELECT action_type, target_kind, metadata_json "
        "FROM admin_audit_log WHERE action_type=?",
        ("bootstrap_admin_seed",),
    ).fetchone()
    assert row is not None
    assert row["target_kind"] == "user"
    assert "lifespan" in (row["metadata_json"] or "")


def test_seed_password_hashed_correctly(db):
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    row = db.execute(
        "SELECT password_hash FROM users WHERE username=?", ("rootadmin",)
    ).fetchone()
    assert row["password_hash"] != "strongpass1234"
    assert auth.verify_password("strongpass1234", row["password_hash"]) is True


def test_seed_admin_can_login(client, monkeypatch):
    """End-to-end: seed then login via HTTP. Uses TestClient fixture from conftest."""
    from backend.shared.db import connect
    from backend import config

    conn = connect(config.DB_PATH)
    try:
        service.seed_bootstrap_admin(conn, username="rootadmin", password="strongpass1234")
    finally:
        conn.close()

    r = client.post("/api/auth/login", json={
        "username": "rootadmin",
        "password": "strongpass1234",
    })
    assert r.status_code == 200, r.text
    r2 = client.get("/api/auth/me")
    assert r2.status_code == 200
    assert r2.json()["role"] == "admin"
