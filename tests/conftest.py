# IMPORTANT: this env-set MUST stay above every backend import in this
# module (and every test module that imports backend.main). The SPA
# fallback routes in backend/main.py are registered at module import
# time, so an autouse fixture cannot suppress them retroactively. The
# `setdefault` is non-destructive — production / CI overrides win.
import os
os.environ.setdefault("DISABLE_SPA_MOUNT", "1")
os.environ.setdefault("ENVIRONMENT", "test")

import json
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Tests rapidly fire /api/auth/login and /api/auth/register from a
    single TestClient (one client IP). Without resetting the in-memory
    sliding-window limiter between tests, later tests in the same module
    inherit hits from earlier tests and trip 429 unrelated to what they
    are exercising. The CSRF-style dedicated tests
    (`tests/test_rate_limit.py`) exercise the limiter directly."""
    from backend.shared.rate_limit import reset_for_tests
    reset_for_tests()
    yield


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """FastAPI TestClient with isolated DATA_DIR / DB."""
    from fastapi.testclient import TestClient
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("backend.config.DB_DIR", tmp_path / "db")
    monkeypatch.setattr("backend.config.DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr("backend.config.DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr("backend.config.BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr("backend.config.EXPORTS_DIR", tmp_path / "exports")
    from backend.main import app
    with TestClient(app) as c:
        yield c


# === Paket 5 helpers ===

_SAMPLE_DOC = {
    "evrakOid": "doc_test",
    "sayi": 1,
    "tarih": "20260101",
    "konu": "Test özelge",
    "pdfText": "Bu bir test dokümanıdır. Kanun atıfları içerir.",
    "kanunBilgileri": [],
    "bkkTebligSirkuBilgileri": [],
}


@pytest.fixture
def ingest_doc(client):
    """Ingest a single document into the test DB. Returns document_id."""
    from backend.shared.db import connect
    from backend.documents import service as doc_service
    from backend import config

    def _ingest(document_id: str = "doc_test", **overrides) -> str:
        payload = {**_SAMPLE_DOC, "evrakOid": document_id, **overrides}
        path = config.DOCUMENTS_DIR / f"{document_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        conn = connect(config.DB_PATH)
        try:
            doc_service.ingest_file(conn, path)
        finally:
            conn.close()
        return document_id
    return _ingest


@pytest.fixture
def passed_user(client):
    """Register a user, mark gating flags True, return logged-in client + user dict.

    Returns dict: {"client": TestClient, "user": {...}}.
    The client carries the session cookie.
    """
    from backend.shared.db import connect
    from backend import config

    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE invite_codes SET is_active=0")
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("BURSIYER-2026",),
        )
    finally:
        conn.close()

    r = client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026", "email": "alice@example.com",
    })
    assert r.status_code == 201, r.text
    user = r.json()

    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET has_seen_manual=1, has_passed_training=1 WHERE id=?",
            (user["id"],),
        )
    finally:
        conn.close()

    r = client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })
    assert r.status_code == 200, r.text
    return {"client": client, "user": user}


@pytest.fixture
def second_passed_user(client, passed_user):
    """Adds a second user (bob) sharing the same client/cookie jar via logout/login.

    Returns helper dict with login(name) function so tests can switch users:
      ctx = second_passed_user
      ctx["login"]("alice")  # switches cookie to alice
      ctx["login"]("bob")    # switches to bob
    """
    from backend.shared.db import connect
    from backend import config

    r = client.post("/api/auth/register", json={
        "username": "bob", "password": "password123",
        "invite_code": "BURSIYER-2026", "email": "bob@example.com",
    })
    assert r.status_code == 201, r.text
    bob = r.json()

    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET has_seen_manual=1, has_passed_training=1 WHERE id=?",
            (bob["id"],),
        )
    finally:
        conn.close()

    def login(username: str) -> None:
        client.cookies.clear()
        r = client.post("/api/auth/login", json={
            "username": username, "password": "password123",
        })
        assert r.status_code == 200, r.text

    return {"alice": passed_user["user"], "bob": bob, "login": login, "client": client}


# === Paket 11 admin helpers ===


@pytest.fixture
def bootstrap_admin(client):
    """Register a user, promote to admin via direct DB, login. Returns admin_id."""
    def _do(username="root", password="rootpass1"):
        from backend.shared.db import connect
        from backend import config
        conn = connect(config.DB_PATH)
        try:
            conn.execute("UPDATE invite_codes SET is_active=0")
            conn.execute(
                "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
                ("BURSIYER-2026",),
            )
        finally:
            conn.close()
        client.post("/api/auth/register", json={
            "username": username, "password": password, "invite_code": "BURSIYER-2026",
        })
        conn = connect(config.DB_PATH)
        try:
            conn.execute("UPDATE users SET role='admin' WHERE username=?", (username,))
            row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            admin_id = row["id"]
        finally:
            conn.close()
        client.post("/api/auth/login", json={"username": username, "password": password})
        return admin_id
    return _do


@pytest.fixture
def seen_manual_user(client):
    """Register a new user, mark has_seen_manual=1, login. Returns user_id (int).
    Deactivates existing active invites first to avoid idx_invite_active conflict."""
    def _do(username, invite_code, password="password123"):
        from backend.shared.db import connect
        from backend import config
        conn = connect(config.DB_PATH)
        try:
            conn.execute("UPDATE invite_codes SET is_active=0")
            conn.execute(
                "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
                (invite_code,),
            )
        finally:
            conn.close()
        client.post("/api/auth/register", json={
            "username": username, "password": password, "invite_code": invite_code,
        })
        conn = connect(config.DB_PATH)
        try:
            conn.execute("UPDATE users SET has_seen_manual=1 WHERE username=?", (username,))
            row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            user_id = row["id"]
        finally:
            conn.close()
        client.post("/api/auth/login", json={"username": username, "password": password})
        return user_id
    return _do


@pytest.fixture
def seen_manual_passed_user(client):
    """Like seen_manual_user, but ALSO sets has_passed_training=1.
    Used by tests where the user must pass require_passed_training (e.g. lock acquire)."""
    def _do(username, invite_code, password="password123"):
        from backend.shared.db import connect
        from backend import config
        conn = connect(config.DB_PATH)
        try:
            conn.execute("UPDATE invite_codes SET is_active=0")
            conn.execute(
                "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
                (invite_code,),
            )
        finally:
            conn.close()
        client.post("/api/auth/register", json={
            "username": username, "password": password, "invite_code": invite_code,
        })
        conn = connect(config.DB_PATH)
        try:
            conn.execute(
                "UPDATE users SET has_seen_manual=1, has_passed_training=1 WHERE username=?",
                (username,),
            )
            row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            user_id = row["id"]
        finally:
            conn.close()
        client.post("/api/auth/login", json={"username": username, "password": password})
        return user_id
    return _do


# === Paket 16d helpers ===


@pytest.fixture
def db_conn(client):
    """Direct database connection for test setup. Uses the same DB as client."""
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    yield conn
    conn.close()


@pytest.fixture
def seed_extra_user(db_conn):
    """Insert a user row and return its id. Caller picks username."""
    def _seed(*, username: str = "watcher", avatar_color: str = "#22c55e",
              role: str = "user") -> int:
        cur = db_conn.execute(
            "INSERT INTO users(username, email, password_hash, role, "
            "is_active, has_seen_manual, has_passed_training, avatar_color, "
            "created_at, updated_at) "
            "VALUES (?, NULL, 'pbkdf2_sha256$1$test$x', ?, 1, 1, 1, ?, "
            "datetime('now'), datetime('now'))",
            (username, role, avatar_color),
        )
        db_conn.commit()
        return cur.lastrowid
    return _seed
