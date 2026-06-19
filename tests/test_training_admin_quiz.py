"""Admin quiz CRUD + resolver integration in start_attempt."""


def test_list_quiz_returns_resolved_and_overrides(client, bootstrap_admin):
    bootstrap_admin()
    r = client.get("/api/admin/training/quiz")
    assert r.status_code == 200
    body = r.json()
    assert "resolved" in body
    assert "overrides" in body
    # Baseline has 8 placeholder questions
    assert len(body["resolved"]) == 8
    assert body["overrides"] == []


def test_upsert_baseline_id_writes_source_override(client, bootstrap_admin):
    admin_id = bootstrap_admin()
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


def test_upsert_new_id_writes_source_custom(client, bootstrap_admin):
    bootstrap_admin()
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


def test_delete_writes_tombstone(client, bootstrap_admin):
    bootstrap_admin()
    r = client.delete("/api/admin/training/quiz/q01")
    assert r.status_code == 200

    r = client.get("/api/admin/training/quiz")
    resolved_ids = [q["id"] for q in r.json()["resolved"]]
    assert "q01" not in resolved_ids


def test_start_attempt_uses_resolver_with_admin_override(client, bootstrap_admin, seen_manual_user):
    """Regression — start_attempt now reads from resolver, not direct import."""
    admin_id = bootstrap_admin()
    # Override q01 with new text BEFORE bursiyer starts
    client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "Override question text", "choices": ["A", "B", "C", "D"], "correct_choice_idx": 0},
    )

    # Switch to bursiyer to start training
    client.cookies.clear()
    user_id = seen_manual_user("bursiyer1", "INVITE-2026")
    r = client.post("/api/training/start")
    assert r.status_code == 200
    questions = r.json()["questions"]
    # If q01 is among the 5 sampled, it should have the override text
    q01 = next((q for q in questions if q["id"] == "q01"), None)
    if q01 is not None:
        assert q01["text"] == "Override question text"


def test_quiz_endpoints_require_admin(client, seen_manual_user):
    seen_manual_user("bursiyer1", "INVITE-2026")
    assert client.get("/api/admin/training/quiz").status_code == 404
    assert client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "X", "choices": ["a", "b", "c", "d"], "correct_choice_idx": 0},
    ).status_code == 404
    assert client.delete("/api/admin/training/quiz/q01").status_code == 404


def test_upsert_writes_audit_row(client, bootstrap_admin):
    bootstrap_admin()
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


def test_upsert_quiz_audit_carries_trace_id(client, bootstrap_admin):
    """Group B audit-only: upsert_quiz_question audit row carries a non-NULL 16-char trace_id."""
    bootstrap_admin()
    r = client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "Trace test question?", "choices": ["A", "B", "C", "D"], "correct_choice_idx": 0},
    )
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    try:
        row = db.execute(
            "SELECT trace_id FROM admin_audit_log "
            "WHERE action_type='upsert_quiz_question' AND target_id='q01' "
            "ORDER BY id DESC LIMIT 1",
        ).fetchone()
        assert row is not None
        assert isinstance(row["trace_id"], str), f"trace_id={row['trace_id']!r}"
        assert len(row["trace_id"]) == 16
    finally:
        db.close()


def test_delete_quiz_audit_carries_trace_id(client, bootstrap_admin):
    """Group B audit-only: delete_quiz_question audit row carries a non-NULL 16-char trace_id."""
    bootstrap_admin()
    r = client.delete("/api/admin/training/quiz/q01")
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    try:
        row = db.execute(
            "SELECT trace_id FROM admin_audit_log "
            "WHERE action_type='delete_quiz_question' AND target_id='q01' "
            "ORDER BY id DESC LIMIT 1",
        ).fetchone()
        assert row is not None
        assert isinstance(row["trace_id"], str), f"trace_id={row['trace_id']!r}"
        assert len(row["trace_id"]) == 16
    finally:
        db.close()


def test_delete_cannot_reduce_quiz_pool_below_five(
    client, bootstrap_admin, seen_manual_user,
):
    bootstrap_admin()
    for qid in ("q01", "q02", "q03"):
        assert client.delete(f"/api/admin/training/quiz/{qid}").status_code == 200
    rejected = client.delete("/api/admin/training/quiz/q04")
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["error"] == "training_pool_minimum"

    client.cookies.clear()
    seen_manual_user("bursiyer1", "INVITE-2026")
    r = client.post("/api/training/start")
    assert r.status_code == 200
    assert len(r.json()["questions"]) == 5
