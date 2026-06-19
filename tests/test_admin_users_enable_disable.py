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


def test_disable_broadcast_failure_does_not_rollback_account_state(
    client,
    bootstrap_admin,
    monkeypatch,
):
    bootstrap_admin()
    target_id = _register_target_user(client)
    from backend.shared.sse import broker as sse_broker
    from backend.shared.db import connect
    from backend import config

    db = connect(config.DB_PATH)
    try:
        db.execute(
            """
            INSERT INTO documents_meta(
                document_id, file_path, pdf_text, word_count, sentence_count,
                text_density, estimated_difficulty, created_at
            ) VALUES (
                'disable-route-doc', 'path', 'text', 1, 1, 1, 'Kolay',
                datetime('now')
            )
            """
        )
        db.execute(
            """
            INSERT INTO document_locks(
                document_id, user_id, acquired_at, last_heartbeat, expires_at
            ) VALUES (
                'disable-route-doc', ?, datetime('now'), datetime('now'),
                datetime('now', '+5 minutes')
            )
            """,
            (target_id,),
        )
    finally:
        db.close()

    async def fail_publish(*_args, **_kwargs):
        raise RuntimeError("SSE unavailable")

    monkeypatch.setattr(sse_broker, "publish_broadcast", fail_publish)
    response = client.post(f"/api/admin/users/{target_id}/disable")

    assert response.status_code == 200
    db = connect(config.DB_PATH)
    try:
        user = db.execute(
            "SELECT is_active FROM users WHERE id=?",
            (target_id,),
        ).fetchone()
        assert user["is_active"] == 0
        assert db.execute(
            "SELECT 1 FROM document_locks WHERE user_id=?",
            (target_id,),
        ).fetchone() is None
    finally:
        db.close()
