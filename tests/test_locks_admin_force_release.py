"""Admin force-release endpoint + SSE reason='admin_force' field."""
import json


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
    AND has_passed_training=1 so they pass require_passed_training (which is
    the gate for /api/locks/*/acquire).
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


_SAMPLE_DOC = {
    "evrakOid": "doc_test",
    "sayi": 1,
    "tarih": "20260101",
    "konu": "Test özelge",
    "pdfText": "Bu bir test dokümanıdır. Kanun atıfları içerir.",
    "kanunBilgileri": [],
    "bkkTebligSirkuBilgileri": [],
}


def _ingest(document_id: str) -> None:
    """Ingest a doc into the active config DB so /api/locks/{id}/acquire passes."""
    from backend.shared.db import connect
    from backend.documents import service as doc_service
    from backend import config

    payload = {**_SAMPLE_DOC, "evrakOid": document_id}
    path = config.DOCUMENTS_DIR / f"{document_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    conn = connect(config.DB_PATH)
    try:
        doc_service.ingest_file(conn, path)
    finally:
        conn.close()


def test_force_release_deletes_lock(client):
    admin_id = _bootstrap_admin(client)
    other_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    _ingest("doc-A")
    # bursiyer1 acquires a lock first
    r = client.post("/api/locks/doc-A/acquire")
    assert r.status_code == 200, r.text
    # Switch to admin
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})
    r = client.post("/api/locks/doc-A/admin/force-release")
    assert r.status_code == 200, r.text

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute("SELECT * FROM document_locks WHERE document_id='doc-A'").fetchone()
    assert row is None
    db.close()


def test_force_release_writes_audit(client):
    admin_id = _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    _ingest("doc-B")
    client.post("/api/locks/doc-B/acquire")
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    r = client.post("/api/locks/doc-B/admin/force-release")
    assert r.status_code == 200, r.text

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='lock_force_release' AND target_id='doc-B'"
    ).fetchone()
    assert row is not None
    assert row["admin_user_id"] == admin_id
    db.close()


def test_force_release_no_lock_returns_404(client):
    _bootstrap_admin(client)
    r = client.post("/api/locks/doc-doesnotexist/admin/force-release")
    assert r.status_code == 404


def test_force_release_publishes_lock_released_with_reason(client):
    """Direct SSE event capture by patching the broker."""
    admin_id = _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    _ingest("doc-C")
    client.post("/api/locks/doc-C/acquire")
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    captured = []
    from backend.shared.sse import broker as sse_broker
    orig_publish = sse_broker.publish_broadcast

    async def capture(event_type: str, data: dict):
        captured.append((event_type, data))
        await orig_publish(event_type, data)

    sse_broker.publish_broadcast = capture
    try:
        r = client.post("/api/locks/doc-C/admin/force-release")
        assert r.status_code == 200, r.text
    finally:
        sse_broker.publish_broadcast = orig_publish

    released = [(t, d) for t, d in captured if t == "lock_released"]
    assert len(released) == 1
    assert released[0][1]["reason"] == "admin_force"
    assert released[0][1]["document_id"] == "doc-C"


def test_force_release_requires_admin(client):
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    # bursiyer1 is logged in (not admin)
    r = client.post("/api/locks/doc-X/admin/force-release")
    assert r.status_code == 404  # existence-hide


def test_user_release_publishes_reason_user_release(client):
    """Regression: existing user-driven release now carries reason='user_release'."""
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    _ingest("doc-D")
    client.post("/api/locks/doc-D/acquire")

    captured = []
    from backend.shared.sse import broker as sse_broker
    orig_publish = sse_broker.publish_broadcast

    async def capture(event_type, data):
        captured.append((event_type, data))
        await orig_publish(event_type, data)

    sse_broker.publish_broadcast = capture
    try:
        r = client.post("/api/locks/doc-D/release")
        assert r.status_code == 200
    finally:
        sse_broker.publish_broadcast = orig_publish

    released = [(t, d) for t, d in captured if t == "lock_released"]
    assert len(released) == 1
    assert released[0][1]["reason"] == "user_release"
