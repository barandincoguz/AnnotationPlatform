"""Phase 5 BE-10: dead-letter requeue endpoint.

Three tests:
  1. Happy path — dead-lettered rows get retry_count=0 + error=NULL; response has
     rows_requeued count + trace_id; an audit row is written.
  2. Empty queue — rows_requeued=0 when no dead-lettered rows exist.
  3. Non-admin gets 401/403.

Fixtures follow the `test_mirror_admin_health.py` pattern:
  - `client` + `db_path` from conftest.py
  - `_make_admin()` helper (inline) registers, promotes, and logs in an admin
  - `_make_annotator()` helper registers and logs in a plain user
  - direct DB manipulation via `connect(config.DB_PATH)` for setup/verify
"""
from backend.shared.db import connect
from backend import config


# ---- helpers ----------------------------------------------------------------


def _make_admin(client):
    """Register a user, promote to admin, log them in."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO invite_codes(code, is_active, created_at) "
            "VALUES (?,1,datetime('now'))",
            ("DL-ADMIN-INV",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": "dl_admin", "password": "password123",
        "invite_code": "DL-ADMIN-INV", "email": "dl_admin@example.com",
    })
    assert r.status_code == 201, r.text
    user = r.json()
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET role='admin', has_seen_manual=1, has_passed_training=1 "
            "WHERE id=?",
            (user["id"],),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/login", json={
        "username": "dl_admin", "password": "password123",
    })
    assert r.status_code == 200, r.text


def _make_annotator(client):
    """Register a plain annotator user and log them in."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO invite_codes(code, is_active, created_at) "
            "VALUES (?,1,datetime('now'))",
            ("DL-USER-INV",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": "dl_user", "password": "password123",
        "invite_code": "DL-USER-INV", "email": "dl_user@example.com",
    })
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={
        "username": "dl_user", "password": "password123",
    })
    assert r.status_code == 200, r.text


def _insert_dead_letter(n: int = 1):
    """Insert `n` dead-lettered _outbox rows directly into the app DB."""
    from backend.mirror import config as mirror_config
    conn = connect(config.DB_PATH)
    try:
        for i in range(n):
            conn.execute(
                "INSERT INTO _outbox(table_name, op, pk_value, payload_json, "
                "retry_count, error, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "users", "INSERT", str(i + 1), "{}",
                    mirror_config.MAX_RETRIES,
                    "permanent failure",
                    "2026-01-01T00:00:00Z",
                ),
            )
        conn.commit()
    finally:
        conn.close()


# ---- tests ------------------------------------------------------------------


def test_requeue_resets_dead_letter_rows(client):
    """Happy path: two dead-lettered rows → both reset, response carries count + trace_id,
    and an admin_audit_log row is written."""
    _make_admin(client)
    _insert_dead_letter(2)

    resp = client.post("/api/admin/mirror/dead-letter/requeue")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["rows_requeued"] == 2
    assert "trace_id" in body
    assert isinstance(body["trace_id"], str) and body["trace_id"]

    # Verify DB: the rows we seeded (pk_value 1/2, table users) should be reset
    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT retry_count, error FROM _outbox "
            "WHERE delivered_at IS NULL AND pk_value IN ('1', '2') "
            "  AND table_name = 'users' AND created_at = '2026-01-01T00:00:00Z'"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 2, f"expected 2 seeded rows, got {len(rows)}"
    for r in rows:
        assert r["retry_count"] == 0
        assert r["error"] is None

    # Verify audit row written
    conn = connect(config.DB_PATH)
    try:
        audit_row = conn.execute(
            "SELECT * FROM admin_audit_log "
            "WHERE action_type='mirror_dead_letter_requeue' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert audit_row is not None
    assert audit_row["trace_id"] == body["trace_id"]


def test_requeue_returns_zero_when_no_dead_letter(client):
    """If there are no dead-lettered rows, rows_requeued=0 and 200 OK."""
    _make_admin(client)

    resp = client.post("/api/admin/mirror/dead-letter/requeue")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["rows_requeued"] == 0
    assert "trace_id" in body


def test_requeue_requires_admin(client):
    """Non-admin (annotator role) must get 401 or 403/404."""
    _make_annotator(client)

    resp = client.post("/api/admin/mirror/dead-letter/requeue")
    assert resp.status_code in (401, 403, 404), resp.text
