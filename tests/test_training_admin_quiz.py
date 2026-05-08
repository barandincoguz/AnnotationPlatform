"""Admin quiz CRUD + resolver integration in start_attempt."""


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
    """Register a new user, mark has_seen_manual=1, login. Returns user_id (int)."""
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


def test_list_quiz_returns_resolved_and_overrides(client):
    _bootstrap_admin(client)
    r = client.get("/api/admin/training/quiz")
    assert r.status_code == 200
    body = r.json()
    assert "resolved" in body
    assert "overrides" in body
    # Baseline has 8 placeholder questions
    assert len(body["resolved"]) == 8
    assert body["overrides"] == []


def test_upsert_baseline_id_writes_source_override(client):
    admin_id = _bootstrap_admin(client)
    payload = {
        "text": "Yeni soru?",
        "choices": ["A", "B", "C", "D"],
        "correct_choice_idx": 2,
    }
    r = client.put("/api/admin/training/quiz/q01", json=payload)
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM training_quiz_overrides WHERE question_id='q01'"
    ).fetchone()
    assert row["source"] == "override"
    assert row["text"] == "Yeni soru?"
    assert row["correct_choice_idx"] == 2
    db.close()


def test_upsert_new_id_writes_source_custom(client):
    _bootstrap_admin(client)
    r = client.put(
        "/api/admin/training/quiz/custom_q99",
        json={"text": "X", "choices": ["a", "b", "c", "d"], "correct_choice_idx": 0},
    )
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT source FROM training_quiz_overrides WHERE question_id='custom_q99'"
    ).fetchone()
    assert row["source"] == "custom"
    db.close()


def test_delete_writes_tombstone(client):
    _bootstrap_admin(client)
    r = client.delete("/api/admin/training/quiz/q01")
    assert r.status_code == 200

    r = client.get("/api/admin/training/quiz")
    resolved_ids = [q["id"] for q in r.json()["resolved"]]
    assert "q01" not in resolved_ids


def test_start_attempt_uses_resolver_with_admin_override(client):
    """Regression — start_attempt now reads from resolver, not direct import."""
    admin_id = _bootstrap_admin(client)
    # Override q01 with new text BEFORE bursiyer starts
    client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "Override question text", "choices": ["A", "B", "C", "D"], "correct_choice_idx": 0},
    )

    # Switch to bursiyer to start training
    client.cookies.clear()
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    r = client.get("/api/training/start")
    assert r.status_code == 200
    questions = r.json()["questions"]
    # If q01 is among the 5 sampled, it should have the override text
    q01 = next((q for q in questions if q["id"] == "q01"), None)
    if q01 is not None:
        assert q01["text"] == "Override question text"


def test_quiz_endpoints_require_admin(client):
    _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    assert client.get("/api/admin/training/quiz").status_code == 404
    assert client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "X", "choices": ["a", "b", "c", "d"], "correct_choice_idx": 0},
    ).status_code == 404
    assert client.delete("/api/admin/training/quiz/q01").status_code == 404


def test_upsert_writes_audit_row(client):
    _bootstrap_admin(client)
    client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "X", "choices": ["a", "b", "c", "d"], "correct_choice_idx": 0},
    )
    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='upsert_quiz_question' AND target_id='q01'"
    ).fetchone()
    assert row is not None
    db.close()
