import pytest


@pytest.fixture
def seeded_client(client):
    """Client with one active invite code seeded."""
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("BURSIYER-2026",),
        )
    finally:
        conn.close()
    return client


def test_app_imports_users_router(client):
    """Smoke: app boots after mounting users router."""
    r = client.get("/api/health")
    assert r.status_code == 200


def test_register_creates_user(seeded_client):
    r = seeded_client.post("/api/auth/register", json={
        "username": "alice",
        "password": "password123",
        "invite_code": "BURSIYER-2026",
        "email": "alice@example.com",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["username"] == "alice"
    assert body["role"] == "user"


def test_register_invalid_invite_code_returns_403(seeded_client):
    r = seeded_client.post("/api/auth/register", json={
        "username": "alice",
        "password": "password123",
        "invite_code": "WRONG",
    })
    assert r.status_code == 403


def test_register_short_password_returns_422(seeded_client):
    r = seeded_client.post("/api/auth/register", json={
        "username": "alice",
        "password": "short",
        "invite_code": "BURSIYER-2026",
    })
    assert r.status_code == 422  # Pydantic validation


def test_register_duplicate_username_returns_409(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    r = seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "different123",
        "invite_code": "BURSIYER-2026",
    })
    assert r.status_code == 409


def test_login_sets_session_cookie(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    r = seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })
    assert r.status_code == 200
    assert "anotasyon_session" in r.cookies


def test_login_wrong_password_returns_401(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    r = seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "WRONG",
    })
    assert r.status_code == 401


def test_me_returns_current_user(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })
    r = seeded_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_me_unauthenticated_returns_401(seeded_client):
    r = seeded_client.get("/api/auth/me")
    assert r.status_code == 401


def test_logout_clears_session(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })
    r = seeded_client.post("/api/auth/logout")
    assert r.status_code == 200
    # Session should now be invalid
    r2 = seeded_client.get("/api/auth/me")
    assert r2.status_code == 401


def test_seen_manual_endpoint_sets_flag(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })
    r = seeded_client.post("/api/me/seen-manual")
    assert r.status_code == 200

    me = seeded_client.get("/api/auth/me").json()
    assert me["has_seen_manual"] is True


def test_seen_manual_unauthenticated_returns_401(seeded_client):
    r = seeded_client.post("/api/me/seen-manual")
    assert r.status_code == 401
