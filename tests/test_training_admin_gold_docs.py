"""Admin gold-doc CRUD: list, upsert (override + custom), tombstone."""


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


def test_list_gold_docs_returns_resolved_and_overrides(client):
    _bootstrap_admin(client)
    r = client.get("/api/admin/training/gold-docs")
    assert r.status_code == 200
    body = r.json()
    assert "resolved" in body
    assert "overrides" in body
    # Baseline has 3 placeholder docs; no overrides yet
    assert len(body["resolved"]) == 3
    assert body["overrides"] == []


def test_upsert_baseline_id_writes_source_override(client):
    admin_id = _bootstrap_admin(client)
    payload = {
        "content": "Modified placeholder content",
        "expected_concepts": [{"kanun_no": "5520", "madde": "5"}],
        "min_concept_count": 1,
    }
    r = client.put("/api/admin/training/gold-docs/sample_kvk_5", json=payload)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM training_gold_doc_overrides WHERE gold_id='sample_kvk_5'"
    ).fetchone()
    assert row is not None
    assert row["source"] == "override"
    assert row["is_deleted"] == 0
    assert row["created_by_admin_id"] == admin_id
    db.close()


def test_upsert_new_id_writes_source_custom(client):
    admin_id = _bootstrap_admin(client)
    payload = {
        "content": "Yeni özelge metni",
        "expected_concepts": [{"kanun_no": "193", "madde": "37"}],
        "min_concept_count": 1,
    }
    r = client.put("/api/admin/training/gold-docs/my_new_gold_001", json=payload)
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM training_gold_doc_overrides WHERE gold_id='my_new_gold_001'"
    ).fetchone()
    assert row["source"] == "custom"
    db.close()


def test_delete_writes_tombstone(client):
    _bootstrap_admin(client)
    r = client.delete("/api/admin/training/gold-docs/sample_kvk_5")
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM training_gold_doc_overrides WHERE gold_id='sample_kvk_5'"
    ).fetchone()
    assert row["is_deleted"] == 1
    db.close()

    # Resolver should now exclude it
    r = client.get("/api/admin/training/gold-docs")
    resolved_ids = [d["gold_id"] for d in r.json()["resolved"]]
    assert "sample_kvk_5" not in resolved_ids


def test_upsert_writes_audit_row(client):
    admin_id = _bootstrap_admin(client)
    client.put(
        "/api/admin/training/gold-docs/x_new",
        json={"content": "X", "expected_concepts": [], "min_concept_count": 0},
    )

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='upsert_gold_doc' AND target_id='x_new'"
    ).fetchone()
    assert row is not None
    db.close()


def test_delete_writes_audit_row(client):
    admin_id = _bootstrap_admin(client)
    client.delete("/api/admin/training/gold-docs/sample_kvk_5")

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='delete_gold_doc' AND target_id='sample_kvk_5'"
    ).fetchone()
    assert row is not None
    db.close()


def test_endpoints_require_admin(client):
    _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    r = client.get("/api/admin/training/gold-docs")
    assert r.status_code == 404
    r = client.put(
        "/api/admin/training/gold-docs/x",
        json={"content": "", "expected_concepts": [], "min_concept_count": 0},
    )
    assert r.status_code == 404
    r = client.delete("/api/admin/training/gold-docs/x")
    assert r.status_code == 404


def test_upsert_twice_preserves_created_at(client):
    _bootstrap_admin(client)
    payload = {
        "content": "v1", "expected_concepts": [{"kanun_no": "5520"}],
        "min_concept_count": 1,
    }
    client.put("/api/admin/training/gold-docs/sample_kvk_5", json=payload)

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    first_created_at = db.execute(
        "SELECT created_at FROM training_gold_doc_overrides WHERE gold_id='sample_kvk_5'"
    ).fetchone()["created_at"]
    db.close()

    # Second upsert with different content
    payload["content"] = "v2"
    client.put("/api/admin/training/gold-docs/sample_kvk_5", json=payload)

    db = connect(DB_PATH)
    row = db.execute(
        "SELECT created_at, updated_at, content FROM training_gold_doc_overrides WHERE gold_id='sample_kvk_5'"
    ).fetchone()
    assert row["created_at"] == first_created_at  # preserved
    assert row["content"] == "v2"  # updated
    # updated_at may be ==first_created_at if both upserts hit the same ISO timestamp
    # under fast test execution; that's acceptable. Just verify content is v2.
    db.close()
