"""HTTP tests for admin settings endpoints."""
from backend.shared.db import connect
from backend import config


def _make_admin(client):
    """Register a user, promote to admin, log them in, return the user dict."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("ADMIN-INV",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": "boss", "password": "password123",
        "invite_code": "ADMIN-INV", "email": "boss@example.com",
    })
    assert r.status_code == 201
    user = r.json()
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET role='admin', has_seen_manual=1, has_passed_training=1 WHERE id=?",
            (user["id"],),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/login", json={
        "username": "boss", "password": "password123",
    })
    assert r.status_code == 200
    return user


def test_get_settings_requires_auth(client):
    r = client.get("/api/admin/settings")
    assert r.status_code == 401


def test_get_settings_non_admin_404(passed_user):
    r = passed_user["client"].get("/api/admin/settings")
    # require_admin returns 404 to hide existence (per backend/users/deps.py:52)
    assert r.status_code == 404


def test_get_settings_returns_seeded_keys(client):
    _make_admin(client)
    r = client.get("/api/admin/settings")
    assert r.status_code == 200
    data = r.json()
    # Some seeded keys present
    assert "speed_warning.window_seconds" in data
    assert data["speed_warning.window_seconds"] == 300
    assert data["char_limit.warn_threshold"] == 300
    assert data["char_limit.alert_threshold"] == 600
