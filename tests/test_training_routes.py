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
    r = client.get("/api/training/start")
    assert r.status_code == 401


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
    r = client.get("/api/training/start")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "manual_not_seen"


def test_start_returns_5_questions_and_3_gold_docs(client):
    _seen_manual_user(client, "u_start1")
    r = client.get("/api/training/start")
    assert r.status_code == 200
    data = r.json()
    assert "attempt_id" in data
    assert len(data["questions"]) == 5
    assert len(data["gold_docs"]) == 3
    # No leaks on quiz answers
    for q in data["questions"]:
        assert "correct_choice_idx" not in q
    # Per 16c.1: gold doc expected_concepts ARE exposed (reveal panel, no penalty)
    for g in data["gold_docs"]:
        assert set(g.keys()) == {"gold_id", "content", "expected_concepts", "min_concept_count"}


def test_start_409_when_already_passed(client):
    user = _seen_manual_user(client, "u_done")
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE users SET has_passed_training=1 WHERE id=?", (user["id"],))
    finally:
        conn.close()
    r = client.get("/api/training/start")
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
    r = client.get("/api/training/start")
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "max_attempts_reached"


def test_quiz_submit_unknown_attempt_404(client):
    _seen_manual_user(client, "u_qs1")
    r = client.post("/api/training/quiz/submit", json={
        "attempt_id": 9999, "answers": {},
    })
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "attempt_not_found"


def test_quiz_submit_wrong_user_403(client):
    _seen_manual_user(client, "u_qa")
    r = client.get("/api/training/start")
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
    r = client.get("/api/training/start")
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
    r = client.get("/api/training/start")
    aid = r.json()["attempt_id"]
    r = client.post("/api/training/annotate/submit", json={
        "attempt_id": aid, "gold_id": "not_in_attempt", "references": [],
    })
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "gold_doc_not_in_attempt"


def test_annotate_submit_resubmit_409(client):
    _seen_manual_user(client, "u_an2")
    r = client.get("/api/training/start")
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


def test_start_response_includes_expected_concepts(passed_user, db_conn):
    """Per Paket 16c.1: the start payload exposes expected_concepts and
    min_concept_count per gold doc so the reveal panel can render them.

    NOTE: this leaks answers to the client. Acceptable in 16c.1
    because the design decision was 'reveal panel, no penalty'.
    """
    me_id = passed_user["user"]["id"]
    db_conn.execute(
        "DELETE FROM training_attempts WHERE user_id=?", (me_id,),
    )
    db_conn.execute(
        "UPDATE users SET has_passed_training=0 WHERE id=?", (me_id,),
    )
    db_conn.commit()

    res = passed_user["client"].get("/api/training/start")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "gold_docs" in body
    assert len(body["gold_docs"]) >= 1
    for doc in body["gold_docs"]:
        assert "expected_concepts" in doc, doc
        assert isinstance(doc["expected_concepts"], list)
        assert "min_concept_count" in doc
        assert isinstance(doc["min_concept_count"], int)
