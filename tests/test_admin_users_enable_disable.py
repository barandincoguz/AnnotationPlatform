"""B4: enable_user / disable_user must 404 for non-existent target users."""


def _register_target_user(client):
    """Helper: admin already logged in; registers a plain target user, returns user_id."""
    client.post("/api/auth/register", json={
        "username": "target_user", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    r = client.get("/api/admin/users")
    target = next(u for u in r.json()["users"] if u["username"] == "target_user")
    return target["id"]


# ── enable_user ──────────────────────────────────────────────────────────────

def test_enable_user_returns_404_for_nonexistent(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.post("/api/admin/users/999999/enable")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "user_not_found"


def test_enable_user_returns_404_includes_message(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.post("/api/admin/users/999999/enable")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "999999" in detail["message"]


def test_enable_existing_user_succeeds(client, bootstrap_admin):
    bootstrap_admin()
    target_id = _register_target_user(client)
    # Disable first, then re-enable
    client.post(f"/api/admin/users/{target_id}/disable")
    resp = client.post(f"/api/admin/users/{target_id}/enable")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_enable_nonexistent_does_not_write_audit_log(client, bootstrap_admin):
    bootstrap_admin()
    from backend.shared.db import connect
    from backend import config

    db = connect(config.DB_PATH)
    try:
        before = db.execute(
            "SELECT COUNT(*) AS c FROM admin_audit_log WHERE action_type='enable_user'"
        ).fetchone()["c"]
    finally:
        db.close()

    client.post("/api/admin/users/999999/enable")

    db = connect(config.DB_PATH)
    try:
        after = db.execute(
            "SELECT COUNT(*) AS c FROM admin_audit_log WHERE action_type='enable_user'"
        ).fetchone()["c"]
    finally:
        db.close()

    assert after == before, "phantom audit log row written for non-existent user"


# ── disable_user ─────────────────────────────────────────────────────────────

def test_disable_user_returns_404_for_nonexistent(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.post("/api/admin/users/999999/disable")
    assert resp.status_code == 404


def test_disable_nonexistent_does_not_write_audit_log(client, bootstrap_admin):
    bootstrap_admin()
    from backend.shared.db import connect
    from backend import config

    db = connect(config.DB_PATH)
    try:
        before = db.execute(
            "SELECT COUNT(*) AS c FROM admin_audit_log WHERE action_type='disable_user'"
        ).fetchone()["c"]
    finally:
        db.close()

    client.post("/api/admin/users/999999/disable")

    db = connect(config.DB_PATH)
    try:
        after = db.execute(
            "SELECT COUNT(*) AS c FROM admin_audit_log WHERE action_type='disable_user'"
        ).fetchone()["c"]
    finally:
        db.close()

    assert after == before, "phantom audit log row written for non-existent user"


def test_disable_existing_user_succeeds(client, bootstrap_admin):
    bootstrap_admin()
    target_id = _register_target_user(client)
    resp = client.post(f"/api/admin/users/{target_id}/disable")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
