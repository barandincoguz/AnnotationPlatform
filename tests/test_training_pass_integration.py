"""End-to-end pass flow through HTTP.

Drives the full happy path:
  1. start → get attempt_id + 5 questions + 3 gold docs
  2. quiz submit with all-correct answers
  3. annotate submit for each of 3 docs (with refs that hit ≥1 expected concept)
  4. assert: user.has_passed_training=1, +50 XP ledger row, training_passed notification
"""
from backend.shared.db import connect
from backend import config


def _seen_manual_user(client, username="u_e2e"):
    conn = connect(config.DB_PATH)
    try:
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
    user = r.json()
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET has_seen_manual=1, has_passed_training=0 WHERE id=?",
            (user["id"],),
        )
    finally:
        conn.close()
    client.post("/api/auth/login", json={
        "username": username, "password": "password123",
    })
    return user


def _ref(**kw):
    base = {"kanun_no": "", "kanun_ad": "", "madde": "",
            "fikra": "", "bent": "", "source_text": "x"}
    base.update(kw)
    return base


def test_full_pass_flow(client):
    user = _seen_manual_user(client, "u_full")

    # 1. start
    r = client.get("/api/training/start")
    assert r.status_code == 200
    data = r.json()
    aid = data["attempt_id"]

    # 2. Quiz: get the correct answers via the service's helper (test-only access
    #    to the deterministic selection — frontend obviously doesn't have this).
    from backend.training.service import _select_questions_for_attempt
    questions = _select_questions_for_attempt(aid)
    answers = {q["id"]: q["correct_choice_idx"] for q in questions}
    r = client.post("/api/training/quiz/submit", json={
        "attempt_id": aid, "answers": answers,
    })
    assert r.status_code == 200
    assert r.json()["score"] == 5

    # 3. Annotate each doc with a ref hitting first expected concept
    from backend.training.service import _select_gold_docs_for_attempt
    conn = connect(config.DB_PATH)
    try:
        docs = _select_gold_docs_for_attempt(conn, aid)
    finally:
        conn.close()
    for d in docs:
        c = d["expected_concepts"][0]
        ref = _ref(
            kanun_no=c.get("kanun_no", ""),
            madde=c.get("madde", ""),
            fikra=c.get("fikra", ""),
            bent=c.get("bent", ""),
            source_text="dummy text",
        )
        r = client.post("/api/training/annotate/submit", json={
            "attempt_id": aid, "gold_id": d["gold_id"], "references": [ref],
        })
        assert r.status_code == 200
        assert r.json()["passed"] is True

    # 4. Side-effects
    conn = connect(config.DB_PATH)
    try:
        urow = conn.execute(
            "SELECT has_passed_training FROM users WHERE id=?", (user["id"],),
        ).fetchone()
        assert urow["has_passed_training"] == 1

        ledger = conn.execute(
            "SELECT delta_xp FROM gamification_ledger "
            "WHERE user_id=? AND reason='training_pass'", (user["id"],),
        ).fetchall()
        assert len(ledger) == 1
        assert ledger[0]["delta_xp"] == 50

        notif = conn.execute(
            "SELECT title FROM notifications WHERE user_id=? AND kind='training_passed'",
            (user["id"],),
        ).fetchone()
        assert notif is not None
        assert "Tebrikler" in notif["title"]
    finally:
        conn.close()


def test_fail_flow_keeps_user_pre_training(client):
    """All quiz answers wrong → finalize fails → user stays has_passed_training=0."""
    user = _seen_manual_user(client, "u_fail")
    r = client.get("/api/training/start")
    aid = r.json()["attempt_id"]

    from backend.training.service import _select_questions_for_attempt
    questions = _select_questions_for_attempt(aid)
    bad = {q["id"]: (q["correct_choice_idx"] + 1) % 4 for q in questions}
    client.post("/api/training/quiz/submit", json={"attempt_id": aid, "answers": bad})

    for d in r.json()["gold_docs"]:
        client.post("/api/training/annotate/submit", json={
            "attempt_id": aid, "gold_id": d["gold_id"], "references": [],
        })

    conn = connect(config.DB_PATH)
    try:
        urow = conn.execute(
            "SELECT has_passed_training FROM users WHERE id=?", (user["id"],),
        ).fetchone()
    finally:
        conn.close()
    assert urow["has_passed_training"] == 0
