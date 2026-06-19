"""HTTP-level tests for /api/training/* endpoints."""
from backend.shared.db import connect
from backend import config


def _seen_manual_user(client, username="u_train"):
    """Register + login a user with has_seen_manual=1, has_passed_training=0."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE invite_codes SET is_active=0 WHERE is_active=1")
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            (f"INV-{username}",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": username, "password": "password123",
        "invite_code": f"INV-{username}",
    })
    assert r.status_code == 201
    user = r.json()
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET has_seen_manual=1, has_passed_training=0 WHERE id=?",
            (user["id"],),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/login", json={
        "username": username, "password": "password123",
    })
    assert r.status_code == 200
    return user


def test_start_requires_auth(client):
    r = client.post("/api/training/start")
    assert r.status_code == 401


def test_start_get_is_not_a_state_changing_alias(client):
    r = client.get("/api/training/start")
    assert r.status_code == 405


def test_start_pre_manual_user_409(client):
    """User who hasn't seen manual yet gets 409 (manual_not_seen)."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("INV-PRE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "u_pre", "password": "password123", "invite_code": "INV-PRE",
    })
    client.post("/api/auth/login", json={"username": "u_pre", "password": "password123"})
    r = client.post("/api/training/start")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "manual_not_seen"


def test_start_returns_5_questions_and_3_gold_docs(client):
    _seen_manual_user(client, "u_start1")
    r = client.post("/api/training/start")
    assert r.status_code == 200
    data = r.json()
    assert "attempt_id" in data
    assert len(data["questions"]) == 5
    assert len(data["gold_docs"]) == 3
    # No leaks on quiz answers
    for q in data["questions"]:
        assert "correct_choice_idx" not in q
    for g in data["gold_docs"]:
        assert set(g.keys()) == {"gold_id", "content"}


def test_start_409_when_already_passed(client):
    user = _seen_manual_user(client, "u_done")
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE users SET has_passed_training=1 WHERE id=?", (user["id"],))
    finally:
        conn.close()
    r = client.post("/api/training/start")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "already_passed"


def test_start_403_when_locked_out(client):
    user = _seen_manual_user(client, "u_locked")
    conn = connect(config.DB_PATH)
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        for n in range(1, 4):
            conn.execute(
                "INSERT INTO training_attempts(user_id, attempt_number, quiz_score, "
                "quiz_total, annotation_pass_count, annotation_total, passed, started_at, "
                "finished_at) VALUES (?, ?, 0, 5, 0, 3, 0, ?, ?)",
                (user["id"], n, now, now),
            )
    finally:
        conn.close()
    r = client.post("/api/training/start")
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "max_attempts_reached"


def test_start_503_when_training_content_is_incomplete(client):
    user = _seen_manual_user(client, "u_incomplete")
    conn = connect(config.DB_PATH)
    try:
        for qid in ("q01", "q02", "q03", "q04"):
            conn.execute(
                """
                INSERT INTO training_quiz_overrides(
                    question_id, is_deleted, source, created_at, updated_at
                ) VALUES (?, 1, 'override', datetime('now'), datetime('now'))
                """,
                (qid,),
            )
    finally:
        conn.close()

    r = client.post("/api/training/start")
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "training_content_unavailable"

    conn = connect(config.DB_PATH)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM training_attempts WHERE user_id=?",
            (user["id"],),
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 0


def test_quiz_submit_unknown_attempt_404(client):
    _seen_manual_user(client, "u_qs1")
    r = client.post("/api/training/quiz/submit", json={
        "attempt_id": 9999, "answers": {},
    })
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "attempt_not_found"


def test_quiz_submit_wrong_user_403(client):
    _seen_manual_user(client, "u_qa")
    r = client.post("/api/training/start")
    aid = r.json()["attempt_id"]
    # Switch to a different user
    client.cookies.clear()
    _seen_manual_user(client, "u_qb")
    r = client.post("/api/training/quiz/submit", json={
        "attempt_id": aid, "answers": {},
    })
    assert r.status_code == 403


def test_quiz_submit_idempotent_409(client):
    _seen_manual_user(client, "u_qid")
    r = client.post("/api/training/start")
    aid = r.json()["attempt_id"]
    r = client.post("/api/training/quiz/submit", json={
        "attempt_id": aid, "answers": {},
    })
    assert r.status_code == 200
    r = client.post("/api/training/quiz/submit", json={
        "attempt_id": aid, "answers": {},
    })
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "quiz_already_submitted"


def test_annotate_submit_unknown_gold_id_404(client):
    _seen_manual_user(client, "u_an1")
    r = client.post("/api/training/start")
    aid = r.json()["attempt_id"]
    r = client.post("/api/training/annotate/submit", json={
        "attempt_id": aid, "gold_id": "not_in_attempt", "references": [],
    })
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "gold_doc_not_in_attempt"


def test_annotate_submit_resubmit_409(client):
    _seen_manual_user(client, "u_an2")
    r = client.post("/api/training/start")
    aid = r.json()["attempt_id"]
    gid = r.json()["gold_docs"][0]["gold_id"]
    r = client.post("/api/training/annotate/submit", json={
        "attempt_id": aid, "gold_id": gid, "references": [],
    })
    assert r.status_code == 200
    r = client.post("/api/training/annotate/submit", json={
        "attempt_id": aid, "gold_id": gid, "references": [],
    })
    assert r.status_code == 409


def test_start_response_does_not_expose_gold_answers(passed_user, db_conn):
    me_id = passed_user["user"]["id"]
    db_conn.execute(
        "DELETE FROM training_attempts WHERE user_id=?", (me_id,),
    )
    db_conn.execute(
        "UPDATE users SET has_passed_training=0 WHERE id=?", (me_id,),
    )
    db_conn.commit()

    res = passed_user["client"].post("/api/training/start")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "gold_docs" in body
    assert len(body["gold_docs"]) >= 1
    for doc in body["gold_docs"]:
        assert set(doc) == {"gold_id", "content"}


def test_skip_training_requires_auth(client):
    res = client.post("/api/training/skip")
    assert res.status_code == 401


def test_skip_training_allowed_in_production(passed_user, monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "SPACE_ID", None)
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", {"*"})

    res = passed_user["client"].post(
        "/api/training/skip",
    )
    assert res.status_code == 200


def test_skip_training_sets_flag_and_writes_activity_log(passed_user, db_conn):
    """Fresh user (has_passed_training=0): POST /skip → 200 + ok=True,
    has_passed_training becomes 1, activity_events has one
    'training_skipped' row for this user with extra={"actor":"self"}."""
    me_id = passed_user["user"]["id"]
    # Reset to has_passed_training=0 for this test
    db_conn.execute(
        "UPDATE users SET has_passed_training=0 WHERE id=?", (me_id,),
    )
    db_conn.execute(
        "DELETE FROM activity_events WHERE user_id=? AND event_type='training_skipped'",
        (me_id,),
    )
    db_conn.commit()

    res = passed_user["client"].post("/api/training/skip")
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    row = db_conn.execute(
        "SELECT has_passed_training FROM users WHERE id=?", (me_id,),
    ).fetchone()
    assert row["has_passed_training"] == 1

    activity = db_conn.execute(
        "SELECT event_type, extra_json FROM activity_events "
        "WHERE user_id=? AND event_type='training_skipped'",
        (me_id,),
    ).fetchall()
    assert len(activity) == 1
    import json as _json
    assert _json.loads(activity[0]["extra_json"]) == {"actor": "self"}


def test_skip_training_is_idempotent(passed_user, db_conn):
    """Re-calling skip on an already-passed user is a no-op
    (returns 200, does NOT write a second activity_events row)."""
    me_id = passed_user["user"]["id"]
    db_conn.execute(
        "UPDATE users SET has_passed_training=0 WHERE id=?", (me_id,),
    )
    db_conn.execute(
        "DELETE FROM activity_events WHERE user_id=? AND event_type='training_skipped'",
        (me_id,),
    )
    db_conn.commit()

    res1 = passed_user["client"].post("/api/training/skip")
    assert res1.status_code == 200

    res2 = passed_user["client"].post("/api/training/skip")
    assert res2.status_code == 200
    assert res2.json() == {"ok": True}

    count = db_conn.execute(
        "SELECT COUNT(*) AS c FROM activity_events "
        "WHERE user_id=? AND event_type='training_skipped'",
        (me_id,),
    ).fetchone()["c"]
    assert count == 1
