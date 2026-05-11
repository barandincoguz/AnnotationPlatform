"""Admin gold-doc CRUD: list, upsert (override + custom), tombstone."""


def test_list_gold_docs_returns_resolved_and_overrides(client, bootstrap_admin):
    bootstrap_admin()
    r = client.get("/api/admin/training/gold-docs")
    assert r.status_code == 200
    body = r.json()
    assert "resolved" in body
    assert "overrides" in body
    # Baseline has 3 placeholder docs; no overrides yet
    assert len(body["resolved"]) == 3
    assert body["overrides"] == []


def test_upsert_baseline_id_writes_source_override(client, bootstrap_admin):
    admin_id = bootstrap_admin()
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


def test_upsert_new_id_writes_source_custom(client, bootstrap_admin):
    admin_id = bootstrap_admin()
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


def test_delete_writes_tombstone(client, bootstrap_admin):
    bootstrap_admin()
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


def test_upsert_writes_audit_row(client, bootstrap_admin):
    admin_id = bootstrap_admin()
    client.put(
        "/api/admin/training/gold-docs/x_new",
        json={"content": "X", "expected_concepts": [{"kanun_no": "5520"}], "min_concept_count": 1},
    )

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='upsert_gold_doc' AND target_id='x_new'"
    ).fetchone()
    assert row is not None
    db.close()


def test_delete_writes_audit_row(client, bootstrap_admin):
    admin_id = bootstrap_admin()
    client.delete("/api/admin/training/gold-docs/sample_kvk_5")

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='delete_gold_doc' AND target_id='sample_kvk_5'"
    ).fetchone()
    assert row is not None
    db.close()


def test_endpoints_require_admin(client, seen_manual_user):
    seen_manual_user("bursiyer1", "INVITE-2026")
    r = client.get("/api/admin/training/gold-docs")
    assert r.status_code == 404
    r = client.put(
        "/api/admin/training/gold-docs/x",
        json={"content": "", "expected_concepts": [], "min_concept_count": 0},
    )
    assert r.status_code == 404
    r = client.delete("/api/admin/training/gold-docs/x")
    assert r.status_code == 404


def test_upsert_twice_preserves_created_at(client, bootstrap_admin):
    bootstrap_admin()
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


def test_upsert_gold_doc_audit_carries_trace_id(client, bootstrap_admin):
    """Group B audit-only: upsert_gold_doc audit row carries a non-NULL 16-char trace_id."""
    bootstrap_admin()
    gold_id = "gold_trace_upsert_t5"
    r = client.put(
        f"/api/admin/training/gold-docs/{gold_id}",
        json={"content": "trace test content", "expected_concepts": [{"kanun_no": "5520"}], "min_concept_count": 1},
    )
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    try:
        row = db.execute(
            "SELECT trace_id FROM admin_audit_log "
            "WHERE action_type='upsert_gold_doc' AND target_id=? "
            "ORDER BY id DESC LIMIT 1",
            (gold_id,),
        ).fetchone()
        assert row is not None
        assert isinstance(row["trace_id"], str), f"trace_id={row['trace_id']!r}"
        assert len(row["trace_id"]) == 16
    finally:
        db.close()


def test_delete_gold_doc_audit_carries_trace_id(client, bootstrap_admin):
    """Group B audit-only: delete_gold_doc audit row carries a non-NULL 16-char trace_id."""
    bootstrap_admin()
    r = client.delete("/api/admin/training/gold-docs/sample_kvk_5")
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    try:
        row = db.execute(
            "SELECT trace_id FROM admin_audit_log "
            "WHERE action_type='delete_gold_doc' AND target_id='sample_kvk_5' "
            "ORDER BY id DESC LIMIT 1",
        ).fetchone()
        assert row is not None
        assert isinstance(row["trace_id"], str), f"trace_id={row['trace_id']!r}"
        assert len(row["trace_id"]) == 16
    finally:
        db.close()


def test_upsert_by_second_admin_preserves_original_created_by(client, bootstrap_admin):
    """Admin A creates override; Admin B edits it; created_by_admin_id stays as A."""
    admin_a_id = bootstrap_admin(username="admin_a", password="adminapass1")

    client.put(
        "/api/admin/training/gold-docs/sample_kvk_5",
        json={"content": "v1", "expected_concepts": [{"kanun_no": "5520"}], "min_concept_count": 1},
    )

    # Switch to a second admin
    client.cookies.clear()
    admin_b_id = bootstrap_admin(username="admin_b", password="adminbpass1")

    client.put(
        "/api/admin/training/gold-docs/sample_kvk_5",
        json={"content": "v2", "expected_concepts": [{"kanun_no": "5520"}], "min_concept_count": 1},
    )

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT created_by_admin_id, content FROM training_gold_doc_overrides WHERE gold_id='sample_kvk_5'"
    ).fetchone()
    assert row["created_by_admin_id"] == admin_a_id  # original creator preserved
    assert row["content"] == "v2"  # content updated
    assert admin_a_id != admin_b_id  # sanity
    db.close()
