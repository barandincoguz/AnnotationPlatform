"""Admin reset endpoint: soft reset (clear attempts + has_passed_training=0)."""


def _bootstrap_admin(client, username="root", password="rootpass1"):
    """Register a user, promote to admin via direct DB, login.
    Returns: admin user_id (int)."""
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


def _seen_manual_user(client, username, invite_code, password="password123"):
    """Register a new user with the given invite code; mark has_seen_manual=1
    so they pass the require_seen_manual gate. Logs them in.
    Returns: user_id (int).
    Note: deactivates the existing active invite first to avoid
    idx_invite_active uniqueness conflict."""
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


def test_reset_clears_attempts_and_flips_passed(client):
    admin_id = _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    # Re-login as admin (helper logged in as bursiyer1 last)
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    # Simulate: user has passed training
    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    db.execute(
        "INSERT INTO training_attempts(id, user_id, attempt_number, started_at, finished_at, quiz_score, quiz_total, annotation_pass_count, annotation_total, passed) VALUES (1, ?, 1, '2026-05-01T00:00:00+00:00', '2026-05-01T00:01:00+00:00', 5, 5, 3, 3, 1)",
        (user_id,),
    )
    db.execute("UPDATE users SET has_passed_training=1 WHERE id=?", (user_id,))
    db.commit()
    db.close()

    r = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    db = connect(DB_PATH)
    rows = db.execute("SELECT id FROM training_attempts WHERE user_id=?", (user_id,)).fetchall()
    assert rows == []
    user = db.execute("SELECT has_passed_training FROM users WHERE id=?", (user_id,)).fetchone()
    assert user["has_passed_training"] == 0
    db.close()


def test_reset_writes_audit_row(client):
    admin_id = _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    r = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='reset_training' AND target_id=?",
        (str(user_id),),
    ).fetchone()
    assert row is not None
    assert row["admin_user_id"] == admin_id
    db.close()


def test_reset_creates_notification(client):
    admin_id = _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    r = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM notifications WHERE user_id=? AND kind='training_reset'", (user_id,),
    ).fetchone()
    assert row is not None
    db.close()


def test_reset_unknown_user_returns_404(client):
    _bootstrap_admin(client)
    r = client.post("/api/admin/training/users/9999/reset")
    assert r.status_code == 404


def test_reset_is_idempotent(client):
    _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    r1 = client.post(f"/api/admin/training/users/{user_id}/reset")
    r2 = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r1.status_code == 200
    assert r2.status_code == 200


def test_reset_requires_admin(client):
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    # bursiyer1 is logged in (not admin)
    r = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r.status_code == 404  # existence-hide
