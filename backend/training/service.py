"""Training gate service.

Public API (filled progressively across Paket 10 tasks):
  get_active_gold_docs(db) -> list[dict]                       # Task 4
  start_attempt(db, *, user_id) -> dict                        # Task 5
  submit_quiz(db, *, attempt_id, user_id, answers) -> dict     # Task 5
  submit_annotation(db, *, attempt_id, user_id, gold_id,       # Task 5
                    references) -> dict
  finalize_if_complete(db, *, attempt_id, user_id) -> dict     # Task 5
  is_locked_out(db, *, user_id) -> bool                        # Task 5

The resolver merges the code baseline (`backend.training.gold_docs.GOLD_DOCS`)
with rows in the `training_gold_doc_overrides` table per spec §"Q5 hibrit
modeli" (spec lines 1007-1034).
"""
import json
import logging
import sqlite3

from backend.training import gold_docs as code_gold


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hybrid gold-doc resolver
# ---------------------------------------------------------------------------

def get_active_gold_docs(db: sqlite3.Connection) -> list[dict]:
    """Return the resolved list of gold docs available for the training
    challenge. Code baseline + DB overrides per spec lines 1007-1034.

    Resolution rules:
      - For every code-baseline entry:
          * If override row exists with is_deleted=1 → exclude.
          * If override row exists → merge: override fields win over code
            (NULL/missing in override means fall back to code).
          * Otherwise → use code entry as-is.
      - For every override row with source='custom' AND is_deleted=0 AND
        gold_id NOT in code baseline → append.
    """
    rows = db.execute(
        "SELECT gold_id, is_deleted, content, expected_concepts, "
        "min_concept_count, source FROM training_gold_doc_overrides"
    ).fetchall()
    overrides = {r["gold_id"]: r for r in rows}

    out: list[dict] = []
    seen: set[str] = set()
    for code in code_gold.GOLD_DOCS:
        gid = code["gold_id"]
        ov = overrides.get(gid)
        if ov is not None and ov["is_deleted"]:
            continue
        if ov is not None:
            content = ov["content"] if ov["content"] is not None else code["content"]
            ec_blob = ov["expected_concepts"]
            expected = json.loads(ec_blob) if ec_blob is not None else code["expected_concepts"]
            mcc = ov["min_concept_count"] if ov["min_concept_count"] is not None else code["min_concept_count"]
            out.append({
                "gold_id": gid,
                "content": content,
                "expected_concepts": expected,
                "min_concept_count": mcc,
            })
        else:
            out.append(dict(code))
        seen.add(gid)

    for gid, ov in overrides.items():
        if ov["source"] == "custom" and not ov["is_deleted"] and gid not in seen:
            out.append({
                "gold_id": gid,
                "content": ov["content"],
                "expected_concepts": json.loads(ov["expected_concepts"]) if ov["expected_concepts"] else [],
                "min_concept_count": ov["min_concept_count"] if ov["min_concept_count"] is not None else 1,
            })

    return out


# ---------------------------------------------------------------------------
# Attempt lifecycle — service exceptions
# ---------------------------------------------------------------------------

class TrainingServiceError(Exception):
    """Base for all training service exceptions."""


class AlreadyPassedError(TrainingServiceError):
    """User already has has_passed_training=1; can't retake."""


class LockedOutError(TrainingServiceError):
    """User has reached max_attempts without passing. Admin reset required."""


class AttemptNotOwnedError(TrainingServiceError):
    """The given attempt_id doesn't belong to the calling user."""


class AttemptNotFoundError(TrainingServiceError):
    """No training_attempts row for this id."""


class QuizAlreadySubmittedError(TrainingServiceError):
    """Quiz already submitted for this attempt — idempotency guard."""


class GoldDocNotInAttemptError(TrainingServiceError):
    """The supplied gold_id wasn't selected for this attempt."""


class GoldDocAlreadySubmittedError(TrainingServiceError):
    """This gold_id was already annotated within this attempt."""


# ---------------------------------------------------------------------------
# Deterministic selection (attempt_id is the seed)
# ---------------------------------------------------------------------------

import random
from datetime import datetime, timezone
from typing import Optional

from backend.shared import settings as S
from backend.shared import audit
from backend.training import quiz_data
from backend.training import matching
from backend.gamification import service as gamification_service
from backend.notifications import service as notif_service


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _select_questions_for_attempt(db: sqlite3.Connection, attempt_id: int) -> list[dict]:
    """Pick 5 deterministic questions seeded by attempt_id, drawn from the
    resolved active pool (code baseline + DB overrides). Migrated from
    direct QUIZ_QUESTIONS import in Paket 11 T6 so admin overrides take
    effect on next attempt without code changes."""
    pool = quiz_data.get_active_quiz_questions(db)
    if len(pool) < 5:
        # Defensive: if admin tombstoned too many baseline questions, fall
        # back to whatever is available so the attempt can still proceed.
        log.warning(
            "quiz pool has only %d questions (expected >=5); "
            "training quiz size degraded; consider restoring a tombstoned question or adding custom ones",
            len(pool),
        )
        return pool
    rng = random.Random(attempt_id)
    return rng.sample(pool, 5)


def _select_gold_docs_for_attempt(db: sqlite3.Connection, attempt_id: int) -> list[dict]:
    """Pick 3 deterministic gold docs seeded by attempt_id, drawn from the
    resolved active pool (code baseline + DB overrides)."""
    pool = get_active_gold_docs(db)
    if len(pool) < 3:
        # In production, the user's CLI-imported docs + 3 placeholders
        # always satisfies this. Defensive: fall back to whatever is available.
        return pool
    rng = random.Random(attempt_id)
    return rng.sample(pool, 3)


def _strip_correct_answers(questions: list[dict]) -> list[dict]:
    return [
        {"id": q["id"], "text": q["text"], "choices": q["choices"]}
        for q in questions
    ]


def _strip_gold_answers(docs: list[dict]) -> list[dict]:
    """Project the resolver gold-doc dicts down to the wire shape.

    Per 16c.1: expected_concepts and min_concept_count are preserved
    (not stripped) so the AnnotateStep reveal panel can render them.
    The "strip" name is kept for git-history continuity even though
    we no longer strip those two fields.
    """
    return [
        {
            "gold_id": d["gold_id"],
            "content": d["content"],
            "expected_concepts": d["expected_concepts"],
            "min_concept_count": d["min_concept_count"],
        }
        for d in docs
    ]


# ---------------------------------------------------------------------------
# Attempt lifecycle
# ---------------------------------------------------------------------------

def is_locked_out(db: sqlite3.Connection, *, user_id: int) -> bool:
    """True iff user has used >= max_attempts AND none passed."""
    max_attempts = S.get_int(db, "training.max_attempts", default=3)
    rows = db.execute(
        "SELECT passed FROM training_attempts WHERE user_id=?", (user_id,),
    ).fetchall()
    if not rows:
        return False
    if any(r["passed"] == 1 for r in rows):
        return False
    return len(rows) >= max_attempts


def _user_passed(db: sqlite3.Connection, user_id: int) -> bool:
    row = db.execute(
        "SELECT has_passed_training FROM users WHERE id=?", (user_id,),
    ).fetchone()
    return bool(row and row["has_passed_training"])


def _attempt_row(db: sqlite3.Connection, attempt_id: int) -> Optional[dict]:
    row = db.execute(
        "SELECT * FROM training_attempts WHERE id=?", (attempt_id,),
    ).fetchone()
    return dict(row) if row else None


def _verify_owner(db: sqlite3.Connection, attempt_id: int, user_id: int) -> dict:
    """Return attempt row dict; raise AttemptNotOwnedError or AttemptNotFoundError."""
    row = _attempt_row(db, attempt_id)
    if row is None:
        raise AttemptNotFoundError(attempt_id)
    if row["user_id"] != user_id:
        raise AttemptNotOwnedError(attempt_id)
    return row


def start_attempt(db: sqlite3.Connection, *, user_id: int) -> dict:
    """Begin a new training attempt for the user.

    Raises:
      AlreadyPassedError — user.has_passed_training already 1
      LockedOutError    — user has used max_attempts without passing
    """
    if _user_passed(db, user_id):
        raise AlreadyPassedError(user_id)
    if is_locked_out(db, user_id=user_id):
        raise LockedOutError(user_id)

    # Compute next attempt_number
    row = db.execute(
        "SELECT COUNT(*) AS c FROM training_attempts WHERE user_id=?", (user_id,),
    ).fetchone()
    attempt_number = row["c"] + 1
    now = _now_utc_iso()

    cur = db.execute(
        """
        INSERT INTO training_attempts(
            user_id, attempt_number, quiz_score, quiz_total,
            annotation_pass_count, annotation_total, annotation_details_json,
            passed, started_at, finished_at
        ) VALUES (?, ?, 0, 5, 0, 3, NULL, 0, ?, ?)
        """,
        (user_id, attempt_number, now, now),
    )
    attempt_id = cur.lastrowid
    assert attempt_id is not None  # SQLite always returns an id on successful INSERT

    questions = _select_questions_for_attempt(db, attempt_id)
    docs = _select_gold_docs_for_attempt(db, attempt_id)

    audit.log_activity(
        db, user_id=user_id, event_type="training_start",
        extra={"attempt_id": attempt_id, "attempt_number": attempt_number},
    )
    return {
        "attempt_id": attempt_id,
        "attempt_number": attempt_number,
        "questions": _strip_correct_answers(questions),
        "gold_docs": _strip_gold_answers(docs),
    }


def submit_quiz(
    db: sqlite3.Connection,
    *,
    attempt_id: int,
    user_id: int,
    answers: dict[str, int],
) -> dict:
    """Score the quiz portion. Idempotent: re-submit raises QuizAlreadySubmittedError."""
    row = _verify_owner(db, attempt_id, user_id)
    # Idempotency: we use a marker in annotation_details_json — but quiz also has
    # a "submitted" flag. Since the schema lacks a dedicated column, we encode
    # it as: a non-null annotation_details_json with `_quiz_submitted` key.
    details = json.loads(row["annotation_details_json"]) if row["annotation_details_json"] else {}
    if details.get("_quiz_submitted"):
        raise QuizAlreadySubmittedError(attempt_id)

    questions = _select_questions_for_attempt(db, attempt_id)
    score = matching.score_quiz(questions, answers)

    details["_quiz_submitted"] = True
    details["_quiz_score"] = score
    db.execute(
        "UPDATE training_attempts SET quiz_score=?, annotation_details_json=? WHERE id=?",
        (score, json.dumps(details), attempt_id),
    )
    finalize_if_complete(db, attempt_id=attempt_id, user_id=user_id)
    return {"score": score, "total": 5}


def submit_annotation(
    db: sqlite3.Connection,
    *,
    attempt_id: int,
    user_id: int,
    gold_id: str,
    references: list[dict],
) -> dict:
    """Score one gold doc. Idempotent: re-submit same gold_id raises
    GoldDocAlreadySubmittedError. Auto-finalizes when 3rd distinct doc lands."""
    row = _verify_owner(db, attempt_id, user_id)
    selected_docs = _select_gold_docs_for_attempt(db, attempt_id)
    by_id = {d["gold_id"]: d for d in selected_docs}
    if gold_id not in by_id:
        raise GoldDocNotInAttemptError(gold_id)

    details = json.loads(row["annotation_details_json"]) if row["annotation_details_json"] else {}
    if gold_id in details and isinstance(details[gold_id], dict):
        raise GoldDocAlreadySubmittedError(gold_id)

    doc = by_id[gold_id]
    summary = matching.match_gold_doc(doc["expected_concepts"], references)
    passed = matching.is_doc_pass(summary, min_concept_count=doc["min_concept_count"])
    details[gold_id] = {
        "passed": passed,
        "matched_count": summary["matched_count"],
        "expected_count": summary["expected_count"],
    }

    # Recompute annotation_pass_count from details
    pass_count = sum(
        1 for k, v in details.items()
        if not k.startswith("_") and isinstance(v, dict) and v.get("passed")
    )

    db.execute(
        "UPDATE training_attempts SET annotation_pass_count=?, annotation_details_json=? WHERE id=?",
        (pass_count, json.dumps(details), attempt_id),
    )
    finalize_if_complete(db, attempt_id=attempt_id, user_id=user_id)
    return {
        "passed": passed,
        "matched_count": summary["matched_count"],
        "expected_count": summary["expected_count"],
        "min_concept_count": doc["min_concept_count"],
    }


def finalize_if_complete(
    db: sqlite3.Connection, *, attempt_id: int, user_id: int,
) -> Optional[dict]:
    """Check if both quiz + 3 docs submitted; if so, compute pass and apply
    user/gamification/notification side-effects. Returns the finalize summary
    or None if not yet complete. Idempotent — finalize is a no-op if attempt
    is already passed=1 or fail-final."""
    row = _attempt_row(db, attempt_id)
    if row is None:
        return None
    if row["passed"] == 1:
        return None  # already finalized as pass

    details = json.loads(row["annotation_details_json"]) if row["annotation_details_json"] else {}
    if not details.get("_quiz_submitted"):
        return None
    doc_keys = [k for k in details if not k.startswith("_") and isinstance(details[k], dict)]
    if len(doc_keys) < 3:
        return None
    if details.get("_finalized"):
        return None  # already finalized as fail

    quiz_threshold = S.get_int(db, "training.quiz_pass_threshold", default=4)
    anno_threshold = S.get_int(db, "training.annotation_pass_threshold", default=2)
    quiz_pass = row["quiz_score"] >= quiz_threshold
    anno_pass = row["annotation_pass_count"] >= anno_threshold
    overall_pass = quiz_pass and anno_pass

    now = _now_utc_iso()
    details["_finalized"] = True
    db.execute(
        "UPDATE training_attempts SET passed=?, finished_at=?, annotation_details_json=? WHERE id=?",
        (1 if overall_pass else 0, now, json.dumps(details), attempt_id),
    )

    if overall_pass:
        xp_delta = S.get_int(db, "gamification.xp_training_pass", default=50)
        try:
            db.execute("UPDATE users SET has_passed_training=1 WHERE id=?", (user_id,))
        except Exception:
            log.exception("flip has_passed_training failed for user %s", user_id)
        try:
            gamification_service.award_xp(
                db, user_id=user_id, delta_xp=xp_delta,
                reason="training_pass", related_doc_id=None,
            )
        except Exception:
            log.exception("training_pass xp award failed for user %s", user_id)
        try:
            notif_service.create(
                db, user_id=user_id, kind="training_passed",
                title="Tebrikler! Eğitimi geçtin",
                body=f"Bursiyer eğitimini başarıyla tamamladın. +{xp_delta} XP kazandın.",
                data={"attempt_id": attempt_id},
            )
        except Exception:
            log.exception("training_pass notification create failed")
        try:
            audit.log_activity(
                db, user_id=user_id, event_type="training_pass",
                extra={"attempt_id": attempt_id},
            )
        except Exception:
            log.exception("training_pass audit log failed")
    else:
        try:
            audit.log_activity(
                db, user_id=user_id, event_type="training_fail",
                extra={
                    "attempt_id": attempt_id,
                    "quiz_score": row["quiz_score"],
                    "annotation_pass_count": row["annotation_pass_count"],
                },
            )
        except Exception:
            log.exception("training_fail audit log failed")

    return {
        "passed": overall_pass,
        "quiz_score": row["quiz_score"],
        "quiz_total": 5,
        "annotation_pass_count": row["annotation_pass_count"],
        "annotation_total": 3,
    }


def reset_user_training(
    db: sqlite3.Connection, *, user_id: int, admin_id: int,
    trace_id: Optional[str] = None,
) -> bool:
    """Soft reset: delete training_attempts rows, flip has_passed_training=0,
    create training_reset notification, write admin audit row.

    Returns True if user existed (operation completed), False if user not found.
    Idempotent: running on an already-reset user is a no-op success.

    Per-step fault isolation pattern from Paket 9: notification + audit
    failures are logged and swallowed; the core state change (DELETE +
    UPDATE) is the source of truth.
    """
    user_row = db.execute(
        "SELECT id, username FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if user_row is None:
        return False

    # Atomic transaction wraps DELETE + UPDATE so concurrent readers cannot
    # observe a torn state where attempts are gone but has_passed_training=1.
    # The two mutations target different tables, so SQLite's autocommit
    # semantics aren't sufficient. Notification + audit are intentionally
    # outside this transaction (best-effort side effects).
    db.execute("BEGIN")
    try:
        db.execute("DELETE FROM training_attempts WHERE user_id=?", (user_id,))
        db.execute("UPDATE users SET has_passed_training=0 WHERE id=?", (user_id,))
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    try:
        notif_service.create(
            db,
            user_id=user_id,
            kind="training_reset",
            title="Eğitiminiz sıfırlandı",
            body="Bir admin eğitim ilerlemenizi sıfırladı. Yeniden başlayabilirsiniz.",
            data={"admin_id": admin_id},
        )
    except Exception:
        log.exception("create training_reset notification failed for user_id=%s", user_id)

    try:
        audit.log_admin_action(
            db, admin_user_id=admin_id, action_type="reset_training",
            target_kind="user", target_id=str(user_id),
            metadata={"username": user_row["username"]},
            trace_id=trace_id,
        )
    except Exception:
        log.exception("log_admin_action reset_training failed for user_id=%s", user_id)

    return True


# ---------------------------------------------------------------------------
# Gold-doc admin CRUD helpers (Paket 11 Task 5)
# ---------------------------------------------------------------------------

def upsert_gold_doc_override(
    db: sqlite3.Connection, *, gold_id: str, content: str,
    expected_concepts: list[dict], min_concept_count: int, admin_id: int,
) -> None:
    """Upsert a gold-doc override row. source='override' if gold_id exists in
    code baseline, else 'custom'.

    On INSERT: created_by_admin_id is set to the calling admin.
    On UPDATE: created_by_admin_id is preserved from the original row so that
    the original author attribution is not overwritten by a subsequent editor.
    """
    baseline_ids = {d["gold_id"] for d in code_gold.GOLD_DOCS}
    source = "override" if gold_id in baseline_ids else "custom"
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT INTO training_gold_doc_overrides(
            gold_id, is_deleted, content, expected_concepts,
            min_concept_count, source, created_by_admin_id,
            created_at, updated_at
        ) VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(gold_id) DO UPDATE SET
            is_deleted = excluded.is_deleted,
            content = excluded.content,
            expected_concepts = excluded.expected_concepts,
            min_concept_count = excluded.min_concept_count,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (
            gold_id, content, json.dumps(expected_concepts),
            min_concept_count, source, admin_id, now, now,
        ),
    )


def soft_delete_gold_doc(
    db: sqlite3.Connection, *, gold_id: str, admin_id: int,
) -> None:
    """Tombstone via is_deleted=1. Idempotent. Preserves created_at and
    created_by_admin_id from the original row if any (those columns are
    absent from the ON CONFLICT DO UPDATE SET clause)."""
    baseline_ids = {d["gold_id"] for d in code_gold.GOLD_DOCS}
    source = "override" if gold_id in baseline_ids else "custom"
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT INTO training_gold_doc_overrides(
            gold_id, is_deleted, content, expected_concepts,
            min_concept_count, source, created_by_admin_id,
            created_at, updated_at
        ) VALUES (?, 1, NULL, NULL, NULL, ?, ?, ?, ?)
        ON CONFLICT(gold_id) DO UPDATE SET
            is_deleted = 1,
            content = NULL,
            expected_concepts = NULL,
            min_concept_count = NULL,
            updated_at = excluded.updated_at
        """,
        (gold_id, source, admin_id, now, now),
    )


# ---------------------------------------------------------------------------
# Quiz admin CRUD helpers (Paket 11 Task 6)
# ---------------------------------------------------------------------------

def upsert_quiz_override(
    db: sqlite3.Connection, *, question_id: str, text: str,
    choices: list[str], correct_choice_idx: int, admin_id: int,
) -> None:
    """Upsert a quiz override row. source='override' if question_id is in
    code baseline (QUIZ_QUESTIONS), else 'custom'.
    Uses ON CONFLICT DO UPDATE to preserve created_at across edits.

    On INSERT: created_by_admin_id is set to the calling admin.
    On UPDATE: created_by_admin_id is preserved from the original row so that
    the original author attribution is not overwritten by a subsequent editor.
    """
    baseline_ids = {q["id"] for q in quiz_data.QUIZ_QUESTIONS}
    source = "override" if question_id in baseline_ids else "custom"
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT INTO training_quiz_overrides(
            question_id, is_deleted, text, choices_json, correct_choice_idx,
            source, created_by_admin_id, created_at, updated_at
        ) VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(question_id) DO UPDATE SET
            is_deleted = excluded.is_deleted,
            text = excluded.text,
            choices_json = excluded.choices_json,
            correct_choice_idx = excluded.correct_choice_idx,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (
            question_id, text, json.dumps(choices), correct_choice_idx,
            source, admin_id, now, now,
        ),
    )


def soft_delete_quiz_override(
    db: sqlite3.Connection, *, question_id: str, admin_id: int,
) -> None:
    """Tombstone via is_deleted=1. Preserves created_at, source,
    created_by_admin_id from the original row if any."""
    baseline_ids = {q["id"] for q in quiz_data.QUIZ_QUESTIONS}
    source = "override" if question_id in baseline_ids else "custom"
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT INTO training_quiz_overrides(
            question_id, is_deleted, text, choices_json, correct_choice_idx,
            source, created_by_admin_id, created_at, updated_at
        ) VALUES (?, 1, NULL, NULL, NULL, ?, ?, ?, ?)
        ON CONFLICT(question_id) DO UPDATE SET
            is_deleted = 1,
            text = NULL,
            choices_json = NULL,
            correct_choice_idx = NULL,
            updated_at = excluded.updated_at
        """,
        (question_id, source, admin_id, now, now),
    )


# ---------------------------------------------------------------------------
# Skip training escape hatch (Paket 16c.1 Task 3)
# ---------------------------------------------------------------------------

def skip_training(db: sqlite3.Connection, *, user_id: int) -> None:
    """Bypass the training gate: set has_passed_training=1 and log an
    activity_events row. Idempotent: if has_passed_training is already
    1, return without writing.

    Used by the user-facing POST /api/training/skip endpoint. The
    activity log uses event_type='training_skipped' with extra={'actor':
    'self'} so admins (Paket 16e) can audit who self-bypassed.
    """
    row = db.execute(
        "SELECT has_passed_training FROM users WHERE id=?", (user_id,),
    ).fetchone()
    if row is None:
        # Caller of /skip is always authenticated, so a missing row is
        # a server-side bug, not a normal API failure.
        raise ValueError(f"user {user_id} not found")
    if row["has_passed_training"]:
        return
    db.execute(
        "UPDATE users SET has_passed_training=1, updated_at=datetime('now') "
        "WHERE id=?",
        (user_id,),
    )
    audit.log_activity(
        db, user_id, "training_skipped", extra={"actor": "self"},
    )
    db.commit()
