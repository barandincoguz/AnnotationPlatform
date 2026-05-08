"""Admin reset endpoint: soft reset (clear attempts + has_passed_training=0)."""


def test_reset_clears_attempts_and_flips_passed(client, bootstrap_admin, seen_manual_user):
    admin_id = bootstrap_admin()
    user_id = seen_manual_user("bursiyer1", "INVITE-2026")
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


def test_reset_writes_audit_row(client, bootstrap_admin, seen_manual_user):
    admin_id = bootstrap_admin()
    user_id = seen_manual_user("bursiyer1", "INVITE-2026")
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


def test_reset_creates_notification(client, bootstrap_admin, seen_manual_user):
    admin_id = bootstrap_admin()
    user_id = seen_manual_user("bursiyer1", "INVITE-2026")
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


def test_reset_unknown_user_returns_404(client, bootstrap_admin):
    bootstrap_admin()
    r = client.post("/api/admin/training/users/9999/reset")
    assert r.status_code == 404


def test_reset_is_idempotent(client, bootstrap_admin, seen_manual_user):
    bootstrap_admin()
    user_id = seen_manual_user("bursiyer1", "INVITE-2026")
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    r1 = client.post(f"/api/admin/training/users/{user_id}/reset")
    r2 = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r1.status_code == 200
    assert r2.status_code == 200


def test_reset_requires_admin(client, seen_manual_user):
    user_id = seen_manual_user("bursiyer1", "INVITE-2026")
    # bursiyer1 is logged in (not admin)
    r = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r.status_code == 404  # existence-hide
