"""Unit tests for training.service attempt lifecycle (no HTTP)."""
import json
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.training import service as training_service


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, has_seen_manual, "
        "has_passed_training, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', 1, 0, ?, ?)",
        (now, now),
    )
    yield conn
    conn.close()


def _ref(**kw):
    base = {"kanun_no": "", "kanun_ad": "", "madde": "",
            "fikra": "", "bent": "", "source_text": "x"}
    base.update(kw)
    return base


# ---- start_attempt ----

def test_start_attempt_creates_row_returns_questions_and_docs(db):
    out = training_service.start_attempt(db, user_id=1)
    assert "attempt_id" in out
    assert isinstance(out["attempt_id"], int)
    assert len(out["questions"]) == 5
    # No correct_choice_idx exposed
    assert all("correct_choice_idx" not in q for q in out["questions"])
    assert len(out["gold_docs"]) == 3
    # No expected_concepts / min_concept_count exposed
    assert all("expected_concepts" not in g for g in out["gold_docs"])
    assert all("min_concept_count" not in g for g in out["gold_docs"])


def test_start_attempt_persists_attempt_row(db):
    out = training_service.start_attempt(db, user_id=1)
    row = db.execute(
        "SELECT user_id, attempt_number, quiz_total, annotation_total, passed "
        "FROM training_attempts WHERE id=?", (out["attempt_id"],),
    ).fetchone()
    assert row["user_id"] == 1
    assert row["attempt_number"] == 1
    assert row["quiz_total"] == 5
    assert row["annotation_total"] == 3
    assert row["passed"] == 0


def test_start_attempt_increments_attempt_number(db):
    a1 = training_service.start_attempt(db, user_id=1)
    a2 = training_service.start_attempt(db, user_id=1)
    row1 = db.execute("SELECT attempt_number FROM training_attempts WHERE id=?", (a1["attempt_id"],)).fetchone()
    row2 = db.execute("SELECT attempt_number FROM training_attempts WHERE id=?", (a2["attempt_id"],)).fetchone()
    assert row1["attempt_number"] == 1
    assert row2["attempt_number"] == 2


def test_start_attempt_already_passed_user_409(db):
    db.execute("UPDATE users SET has_passed_training=1 WHERE id=1")
    with pytest.raises(training_service.AlreadyPassedError):
        training_service.start_attempt(db, user_id=1)


def test_start_attempt_lockout_after_max_attempts(db):
    # Plant 3 failed attempts (default max=3)
    now = datetime.now(timezone.utc).isoformat()
    for n in range(1, 4):
        db.execute(
            "INSERT INTO training_attempts(user_id, attempt_number, quiz_score, "
            "quiz_total, annotation_pass_count, annotation_total, passed, started_at, "
            "finished_at) VALUES (1, ?, 0, 5, 0, 3, 0, ?, ?)",
            (n, now, now),
        )
    with pytest.raises(training_service.LockedOutError):
        training_service.start_attempt(db, user_id=1)


def test_start_attempt_seed_is_deterministic(db):
    """Same attempt_id → same questions and gold doc selection."""
    out = training_service.start_attempt(db, user_id=1)
    questions_a = training_service._select_questions_for_attempt(out["attempt_id"])
    questions_b = training_service._select_questions_for_attempt(out["attempt_id"])
    assert [q["id"] for q in questions_a] == [q["id"] for q in questions_b]


# ---- submit_quiz ----

def test_submit_quiz_scores_and_persists(db):
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    # Answer all correctly
    answers = {q["id"]: q["correct_choice_idx"] for q in selected}
    result = training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1, answers=answers,
    )
    assert result["score"] == 5
    assert result["total"] == 5
    row = db.execute(
        "SELECT quiz_score FROM training_attempts WHERE id=?", (out["attempt_id"],),
    ).fetchone()
    assert row["quiz_score"] == 5


def test_submit_quiz_partial_score(db):
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    answers = {q["id"]: (q["correct_choice_idx"] + 1) % 4 for q in selected}  # all wrong
    result = training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1, answers=answers,
    )
    assert result["score"] == 0


def test_submit_quiz_idempotent_409_on_resubmit(db):
    """Re-submitting quiz for the same attempt is a 409 conflict."""
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    answers = {q["id"]: q["correct_choice_idx"] for q in selected}
    training_service.submit_quiz(db, attempt_id=out["attempt_id"], user_id=1, answers=answers)
    with pytest.raises(training_service.QuizAlreadySubmittedError):
        training_service.submit_quiz(db, attempt_id=out["attempt_id"], user_id=1, answers=answers)


def test_submit_quiz_zero_score_can_still_submit_once(db):
    """Zero score is the legitimate first submission — must NOT trigger the
    idempotency guard. Guard logic must use a separate marker, not quiz_score>0."""
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    bad_answers = {q["id"]: (q["correct_choice_idx"] + 1) % 4 for q in selected}
    result = training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1, answers=bad_answers,
    )
    assert result["score"] == 0


def test_submit_quiz_wrong_user_403(db):
    """Submitting another user's attempt is a 403/AccessDenied."""
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO users(id, username, password_hash, role, has_seen_manual, "
        "has_passed_training, created_at, updated_at) "
        "VALUES (2, 'bob', 'x', 'user', 1, 0, ?, ?)",
        (now, now),
    )
    out = training_service.start_attempt(db, user_id=1)
    with pytest.raises(training_service.AttemptNotOwnedError):
        training_service.submit_quiz(
            db, attempt_id=out["attempt_id"], user_id=2, answers={},
        )


# ---- submit_annotation ----

def test_submit_annotation_first_doc_persists(db):
    out = training_service.start_attempt(db, user_id=1)
    docs = training_service._select_gold_docs_for_attempt(db, out["attempt_id"])
    gid = docs[0]["gold_id"]
    refs = [_ref(kanun_no="5520", madde="5", source_text="x")]
    result = training_service.submit_annotation(
        db, attempt_id=out["attempt_id"], user_id=1, gold_id=gid, references=refs,
    )
    assert "passed" in result
    assert "matched_count" in result
    row = db.execute(
        "SELECT annotation_details_json FROM training_attempts WHERE id=?",
        (out["attempt_id"],),
    ).fetchone()
    details = json.loads(row["annotation_details_json"])
    assert gid in details


def test_submit_annotation_unknown_gold_id_404(db):
    out = training_service.start_attempt(db, user_id=1)
    with pytest.raises(training_service.GoldDocNotInAttemptError):
        training_service.submit_annotation(
            db, attempt_id=out["attempt_id"], user_id=1,
            gold_id="not_in_this_attempt", references=[],
        )


def test_submit_annotation_resubmit_same_doc_409(db):
    out = training_service.start_attempt(db, user_id=1)
    docs = training_service._select_gold_docs_for_attempt(db, out["attempt_id"])
    gid = docs[0]["gold_id"]
    training_service.submit_annotation(
        db, attempt_id=out["attempt_id"], user_id=1, gold_id=gid, references=[],
    )
    with pytest.raises(training_service.GoldDocAlreadySubmittedError):
        training_service.submit_annotation(
            db, attempt_id=out["attempt_id"], user_id=1, gold_id=gid, references=[],
        )


# ---- finalize_if_complete ----

def test_finalize_does_nothing_when_quiz_or_docs_missing(db):
    out = training_service.start_attempt(db, user_id=1)
    final = training_service.finalize_if_complete(db, attempt_id=out["attempt_id"], user_id=1)
    assert final is None  # not yet complete
    user = db.execute("SELECT has_passed_training FROM users WHERE id=1").fetchone()
    assert user["has_passed_training"] == 0


def test_finalize_marks_passed_when_all_thresholds_met(db):
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    docs = training_service._select_gold_docs_for_attempt(db, out["attempt_id"])

    # Quiz: all correct
    training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1,
        answers={q["id"]: q["correct_choice_idx"] for q in selected},
    )
    # Annotate: pass 2 of 3 (one with a real concept hit, one with a real concept hit, one empty)
    for i, doc in enumerate(docs):
        ref = _ref(
            kanun_no=doc["expected_concepts"][0].get("kanun_no", ""),
            madde=doc["expected_concepts"][0].get("madde", ""),
            source_text="x",
        ) if i < 2 else _ref()
        training_service.submit_annotation(
            db, attempt_id=out["attempt_id"], user_id=1,
            gold_id=doc["gold_id"], references=[ref] if i < 2 else [],
        )
    # 3rd submission should auto-finalize
    user = db.execute("SELECT has_passed_training FROM users WHERE id=1").fetchone()
    assert user["has_passed_training"] == 1
    row = db.execute(
        "SELECT passed, annotation_pass_count FROM training_attempts WHERE id=?",
        (out["attempt_id"],),
    ).fetchone()
    assert row["passed"] == 1
    assert row["annotation_pass_count"] == 2


def test_finalize_awards_xp_and_notification(db):
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    docs = training_service._select_gold_docs_for_attempt(db, out["attempt_id"])

    training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1,
        answers={q["id"]: q["correct_choice_idx"] for q in selected},
    )
    for i, doc in enumerate(docs):
        ref = _ref(
            kanun_no=doc["expected_concepts"][0].get("kanun_no", ""),
            madde=doc["expected_concepts"][0].get("madde", ""),
        ) if i < 2 else _ref()
        training_service.submit_annotation(
            db, attempt_id=out["attempt_id"], user_id=1,
            gold_id=doc["gold_id"], references=[ref] if i < 2 else [],
        )
    # Gamification ledger gained a +50 row with reason='training_pass'
    ledger = db.execute(
        "SELECT delta_xp, reason FROM gamification_ledger WHERE user_id=1 "
        "AND reason='training_pass'",
    ).fetchall()
    assert len(ledger) == 1
    assert ledger[0]["delta_xp"] == 50

    # Notification persisted
    notifs = db.execute(
        "SELECT kind, title FROM notifications WHERE user_id=1 AND kind='training_passed'"
    ).fetchall()
    assert len(notifs) == 1
    assert "Tebrikler" in notifs[0]["title"]


def test_finalize_fail_does_not_award_xp_or_pass_user(db):
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    docs = training_service._select_gold_docs_for_attempt(db, out["attempt_id"])

    # Quiz: all wrong → score 0, below threshold 4
    training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1,
        answers={q["id"]: (q["correct_choice_idx"] + 1) % 4 for q in selected},
    )
    for doc in docs:
        training_service.submit_annotation(
            db, attempt_id=out["attempt_id"], user_id=1,
            gold_id=doc["gold_id"], references=[],
        )
    user = db.execute("SELECT has_passed_training FROM users WHERE id=1").fetchone()
    assert user["has_passed_training"] == 0
    row = db.execute(
        "SELECT passed FROM training_attempts WHERE id=?", (out["attempt_id"],),
    ).fetchone()
    assert row["passed"] == 0
    # No training_pass XP
    ledger = db.execute(
        "SELECT COUNT(*) AS c FROM gamification_ledger WHERE reason='training_pass'"
    ).fetchone()
    assert ledger["c"] == 0


# ---- is_locked_out ----

def test_is_locked_out_below_max_attempts(db):
    now = datetime.now(timezone.utc).isoformat()
    for n in range(1, 3):  # 2 attempts (under 3-default-max)
        db.execute(
            "INSERT INTO training_attempts(user_id, attempt_number, quiz_score, "
            "quiz_total, annotation_pass_count, annotation_total, passed, started_at, "
            "finished_at) VALUES (1, ?, 0, 5, 0, 3, 0, ?, ?)",
            (n, now, now),
        )
    assert training_service.is_locked_out(db, user_id=1) is False


def test_is_locked_out_at_max_attempts_no_pass(db):
    now = datetime.now(timezone.utc).isoformat()
    for n in range(1, 4):
        db.execute(
            "INSERT INTO training_attempts(user_id, attempt_number, quiz_score, "
            "quiz_total, annotation_pass_count, annotation_total, passed, started_at, "
            "finished_at) VALUES (1, ?, 0, 5, 0, 3, 0, ?, ?)",
            (n, now, now),
        )
    assert training_service.is_locked_out(db, user_id=1) is True


def test_is_locked_out_passed_user_not_locked(db):
    """A user who already passed isn't 'locked out' — they're done. Lockout
    only matters if user hasn't passed AND has exhausted attempts."""
    now = datetime.now(timezone.utc).isoformat()
    for n in range(1, 4):
        passed = 1 if n == 3 else 0
        db.execute(
            "INSERT INTO training_attempts(user_id, attempt_number, quiz_score, "
            "quiz_total, annotation_pass_count, annotation_total, passed, started_at, "
            "finished_at) VALUES (1, ?, 0, 5, 0, 3, ?, ?, ?)",
            (n, passed, now, now),
        )
    assert training_service.is_locked_out(db, user_id=1) is False
