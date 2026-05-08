def _bootstrap_admin(client, username="root", password="rootpass1"):
    """Register a user and promote to admin via direct DB write (simulating CLI)."""
    from backend.shared.db import connect
    from backend import config
    # Seed invite code
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("BURSIYER-2026",),
        )
    finally:
        conn.close()
    # Register
    client.post("/api/auth/register", json={
        "username": username, "password": password, "invite_code": "BURSIYER-2026",
    })
    # Promote via direct DB
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE users SET role='admin' WHERE username=?", (username,))
    finally:
        conn.close()
    # Login
    client.post("/api/auth/login", json={"username": username, "password": password})


def test_admin_can_list_users(client):
    _bootstrap_admin(client)
    r = client.get("/api/admin/users")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1


def test_non_admin_gets_404_on_admin_routes(client):
    _bootstrap_admin(client)
    # Logout, register new normal user
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    r = client.get("/api/admin/users")
    assert r.status_code == 404  # spec hides existence


def test_admin_promotes_user(client):
    _bootstrap_admin(client)
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "BURSIYER-2026",
    })
    # Find alice's id
    r = client.get("/api/admin/users")
    alice = next(u for u in r.json()["users"] if u["username"] == "alice")
    promote = client.post(f"/api/admin/users/{alice['id']}/promote")
    assert promote.status_code == 200
    r2 = client.get("/api/admin/users")
    alice2 = next(u for u in r2.json()["users"] if u["username"] == "alice")
    assert alice2["role"] == "admin"


def test_admin_cannot_demote_last_admin(client):
    _bootstrap_admin(client)
    r = client.get("/api/admin/users")
    me = next(u for u in r.json()["users"] if u["username"] == "root")
    demote = client.post(f"/api/admin/users/{me['id']}/demote")
    assert demote.status_code == 400


def test_admin_disable_user(client):
    _bootstrap_admin(client)
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "BURSIYER-2026",
    })
    r = client.get("/api/admin/users")
    alice = next(u for u in r.json()["users"] if u["username"] == "alice")
    dis = client.post(f"/api/admin/users/{alice['id']}/disable")
    assert dis.status_code == 200


def test_admin_rotate_invite_code(client):
    _bootstrap_admin(client)
    r = client.post("/api/admin/invite/rotate", json={"new_code": "NEW-CODE-2026"})
    assert r.status_code == 200
    body = r.json()
    assert body["new_code"] == "NEW-CODE-2026"


def test_admin_audit_log_endpoint_returns_actions(client):
    _bootstrap_admin(client)
    client.post("/api/admin/invite/rotate", json={"new_code": "X-2026"})
    r = client.get("/api/admin/audit-log")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "has_more" in body
    assert any(e["action_type"] == "rotate_invite_code" for e in body["items"])
