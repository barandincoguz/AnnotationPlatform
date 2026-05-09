def test_admin_can_list_users(client, bootstrap_admin):
    bootstrap_admin()
    r = client.get("/api/admin/users")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1


def test_non_admin_gets_404_on_admin_routes(client, bootstrap_admin):
    bootstrap_admin()
    # Logout, register new normal user
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    r = client.get("/api/admin/users")
    assert r.status_code == 404  # spec hides existence


def test_admin_promotes_user(client, bootstrap_admin):
    bootstrap_admin()
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


def test_admin_cannot_demote_last_admin(client, bootstrap_admin):
    bootstrap_admin()
    r = client.get("/api/admin/users")
    me = next(u for u in r.json()["users"] if u["username"] == "root")
    demote = client.post(f"/api/admin/users/{me['id']}/demote")
    assert demote.status_code == 400


def test_admin_disable_user(client, bootstrap_admin):
    bootstrap_admin()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "BURSIYER-2026",
    })
    r = client.get("/api/admin/users")
    alice = next(u for u in r.json()["users"] if u["username"] == "alice")
    dis = client.post(f"/api/admin/users/{alice['id']}/disable")
    assert dis.status_code == 200


def test_admin_rotate_invite_code(client, bootstrap_admin):
    bootstrap_admin()
    r = client.post("/api/admin/invite/rotate", json={"new_code": "NEW-CODE-2026"})
    assert r.status_code == 200
    body = r.json()
    assert body["new_code"] == "NEW-CODE-2026"


def test_admin_audit_log_endpoint_returns_actions(client, bootstrap_admin):
    bootstrap_admin()
    client.post("/api/admin/invite/rotate", json={"new_code": "X-2026"})
    r = client.get("/api/admin/audit-log")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "has_more" in body
    assert any(e["action_type"] == "rotate_invite_code" for e in body["items"])


def test_bootstrap_admin_fixture_is_idempotent(client, bootstrap_admin):
    """The fixture uses INSERT OR IGNORE on the BURSIYER-2026 invite code so
    it can be called multiple times in a single test (e.g. to seed two admins)
    without IntegrityError on the second insert. Without OR IGNORE, the second
    call would crash before the second register, masking real test failures."""
    admin1 = bootstrap_admin(username="root1", password="rootpass1")
    admin2 = bootstrap_admin(username="root2", password="rootpass2")
    assert admin1 != admin2
    # Sanity-check both admins exist
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT username, role FROM users WHERE id IN (?, ?)",
            (admin1, admin2),
        ).fetchall()
    finally:
        conn.close()
    assert {r["username"] for r in rows} == {"root1", "root2"}
    assert all(r["role"] == "admin" for r in rows)
