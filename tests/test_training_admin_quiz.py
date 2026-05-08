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
    r = client.get("/api/training/start")
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


def test_insufficient_quiz_pool_logs_warning(client, caplog, bootstrap_admin, seen_manual_user):
    """Tombstoning enough baseline questions so the active pool drops below 5
    should produce a warning log when start_attempt fires."""
    import logging
    bootstrap_admin()
    # Tombstone 4 baseline questions, leaving only 4 active (8 - 4 = 4)
    for qid in ("q01", "q02", "q03", "q04"):
        client.delete(f"/api/admin/training/quiz/{qid}")

    client.cookies.clear()
    seen_manual_user("bursiyer1", "INVITE-2026")
    with caplog.at_level(logging.WARNING, logger="backend.training.service"):
        r = client.get("/api/training/start")
    assert r.status_code == 200
    # Should be only 4 questions
    assert len(r.json()["questions"]) == 4
    assert any(
        "quiz pool has only" in record.message
        for record in caplog.records if record.levelno == logging.WARNING
    )
