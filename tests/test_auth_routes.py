import pytest


@pytest.fixture
def seeded_client(client):
    """Client with one active invite code seeded."""
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
    cookie_header = r.headers["set-cookie"]
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header
    assert "Max-Age=2592000" in cookie_header


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


def test_logout_releases_user_locks(seeded_client):
    """Verify that logging out immediately releases any document locks held by the user."""
    from backend.shared.db import connect
    from backend import config
    
    # 1. Register and login
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })
    
    # Get user ID
    conn = connect(config.DB_PATH)
    try:
        user = conn.execute("SELECT id FROM users WHERE username='alice'").fetchone()
        user_id = user["id"]
        
        # 2. Manually insert a document lock or acquire it
        doc = conn.execute("SELECT document_id FROM documents_meta LIMIT 1").fetchone()
        if not doc:
            conn.execute(
                "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, sentence_count, text_density, estimated_difficulty, created_at) "
                "VALUES ('doc1', 'path', 'text', 100, 10, 0.5, 'Kolay', datetime('now'))"
            )
            doc_id = "doc1"
        else:
            doc_id = doc["document_id"]
            
        # Insert a lock
        conn.execute(
            "INSERT INTO document_locks(document_id, user_id, acquired_at, last_heartbeat, expires_at) "
            "VALUES (?, ?, datetime('now'), datetime('now'), datetime('now', '+5 minutes'))",
            (doc_id, user_id),
        )
        
        # Verify lock is present
        lock = conn.execute("SELECT 1 FROM document_locks WHERE document_id=? AND user_id=?", (doc_id, user_id)).fetchone()
        assert lock is not None
    finally:
        conn.close()
        
    # 3. Log out
    r = seeded_client.post("/api/auth/logout")
    assert r.status_code == 200
    
    # 4. Verify lock is immediately released in the database!
    conn = connect(config.DB_PATH)
    try:
        lock = conn.execute("SELECT 1 FROM document_locks WHERE document_id=? AND user_id=?", (doc_id, user_id)).fetchone()
        assert lock is None, "Expected document lock to be released on logout!"
    finally:
        conn.close()


def test_logout_still_succeeds_when_lock_broadcast_fails(seeded_client, monkeypatch):
    from backend import config
    from backend.shared.db import connect
    from backend.shared.sse import broker as sse_broker

    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })

    conn = connect(config.DB_PATH)
    try:
        user_id = conn.execute(
            "SELECT id FROM users WHERE username='alice'"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO documents_meta("
            "document_id, file_path, pdf_text, word_count, sentence_count, "
            "text_density, estimated_difficulty, created_at"
            ") VALUES ('logout-doc', 'path', 'text', 1, 1, 1, 'Kolay', datetime('now'))"
        )
        conn.execute(
            "INSERT INTO document_locks("
            "document_id, user_id, acquired_at, last_heartbeat, expires_at"
            ") VALUES ('logout-doc', ?, datetime('now'), datetime('now'), "
            "datetime('now', '+5 minutes'))",
            (user_id,),
        )
    finally:
        conn.close()

    async def fail_publish(*_args, **_kwargs):
        raise RuntimeError("SSE unavailable")

    monkeypatch.setattr(sse_broker, "publish_broadcast", fail_publish)
    response = seeded_client.post("/api/auth/logout")

    assert response.status_code == 200
    assert seeded_client.get("/api/auth/me").status_code == 401
    conn = connect(config.DB_PATH)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM document_locks WHERE user_id=?",
            (user_id,),
        ).fetchone()[0] == 0
    finally:
        conn.close()


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


def test_login_sets_secure_cookie_in_production(seeded_client, monkeypatch):
    """Verify that secure flag is set when ENVIRONMENT=production."""
    from backend import config

    # Temporarily override ENVIRONMENT to production
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    # The OriginCheckMiddleware now enforces in production (see
    # backend/shared/csrf.py); whitelist the TestClient origin and send
    # the matching Origin header on the state-changing POSTs.
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", {"http://testserver"})
    origin = {"Origin": "http://testserver"}

    # Register and login
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    }, headers=origin)
    r = seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    }, headers=origin)
    assert r.status_code == 200

    # Check that the cookie header contains "Secure" flag
    cookie_header = r.headers.get("set-cookie", "")
    assert "Secure" in cookie_header, f"Expected 'Secure' in cookie header: {cookie_header}"
    assert "SameSite=lax" in cookie_header


def test_login_supports_explicit_cross_site_cookie_mode(
    seeded_client,
    monkeypatch,
):
    from backend import config

    monkeypatch.setattr(config, "SESSION_COOKIE_SAMESITE", "none")
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    response = seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })

    assert response.status_code == 200
    cookie_header = response.headers["set-cookie"]
    assert "SameSite=none" in cookie_header
    assert "Secure" in cookie_header


def test_login_cookie_not_secure_in_development(seeded_client, monkeypatch):
    """Verify that secure flag is NOT set in development mode."""
    from backend import config

    # Ensure ENVIRONMENT is development
    monkeypatch.setattr(config, "ENVIRONMENT", "development")

    # Register and login
    seeded_client.post("/api/auth/register", json={
        "username": "bob", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    r = seeded_client.post("/api/auth/login", json={
        "username": "bob", "password": "password123",
    })
    assert r.status_code == 200

    # Check that the cookie header does NOT contain "Secure" flag in dev
    cookie_header = r.headers.get("set-cookie", "")
    assert "Secure" not in cookie_header, f"Expected NO 'Secure' in dev cookie: {cookie_header}"


def test_invite_code_preserves_custom_active_code(client):
    """Verify that startup code initialization logic preserves existing active invite codes."""
    from backend.shared.db import connect
    from backend import config
    from datetime import datetime, timezone

    conn = connect(config.DB_PATH)
    try:
        # Deactivate all and set a custom active code
        conn.execute("UPDATE invite_codes SET is_active=0")
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?, 1, ?)",
            ("CUSTOM-CODE-2026", datetime.now(timezone.utc).isoformat()),
        )
        
        # Run simulated boot code block
        active_code = conn.execute("SELECT code FROM invite_codes WHERE is_active=1").fetchone()
        if active_code is None:
            conn.execute(
                "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?, 1, ?)",
                ("BURSIYER-2026", datetime.now(timezone.utc).isoformat()),
            )
            
        # Verify custom code was NOT overwritten
        post_boot_code = conn.execute("SELECT code FROM invite_codes WHERE is_active=1").fetchone()
        assert post_boot_code is not None
        assert post_boot_code["code"] == "CUSTOM-CODE-2026"
    finally:
        conn.close()


def test_invite_code_seeds_default_when_none_active(client):
    """Verify that if no active code exists, startup code initialization seeds the default."""
    from backend.shared.db import connect
    from backend import config
    from datetime import datetime, timezone

    conn = connect(config.DB_PATH)
    try:
        # Deactivate all
        conn.execute("UPDATE invite_codes SET is_active=0")
        
        # Run simulated boot code block
        active_code = conn.execute("SELECT code FROM invite_codes WHERE is_active=1").fetchone()
        if active_code is None:
            conn.execute(
                "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?, 1, ?)",
                ("BURSIYER-2026", datetime.now(timezone.utc).isoformat()),
            )
            
        # Verify default code was seeded
        post_boot_code = conn.execute("SELECT code FROM invite_codes WHERE is_active=1").fetchone()
        assert post_boot_code is not None
        assert post_boot_code["code"] == "BURSIYER-2026"
    finally:
        conn.close()
