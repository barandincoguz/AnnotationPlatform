"""HTTP endpoints for the training gate. Auth: require_seen_manual.

The user is taking training right now — using require_passed_training would
be circular. Pre-manual users (has_seen_manual=0) still must read /help first."""
import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.training import service
from backend.training.models import (
    StartResponse, QuizSubmitRequest, QuizSubmitResponse,
    AnnotateSubmitRequest, AnnotateSubmitResponse,
    OkResponse,
    GoldDocUpsertRequest, GoldDocsListResponse,
    QuizUpsertRequest, QuizListResponse,
)
from backend.training.quiz_data import get_active_quiz_questions
from backend.shared import audit
from backend.users.deps import get_db, get_current_user, require_seen_manual, require_admin


log = logging.getLogger(__name__)


router = APIRouter(prefix="/api/training", tags=["training"])
admin_router = APIRouter(prefix="/api/admin/training", tags=["admin-training"])


@router.get("/start", response_model=StartResponse)
def start(
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_seen_manual),
):
    """Begin a new training attempt. 409 if user already passed; 403 if locked out."""
    try:
        return service.start_attempt(db, user_id=user["id"])
    except service.AlreadyPassedError:
        raise HTTPException(
            status_code=409,
            detail={"error": "already_passed", "message": "user already passed training"},
        )
    except service.LockedOutError:
        raise HTTPException(
            status_code=403,
            detail={"error": "max_attempts_reached", "message": "max attempts used; admin reset required"},
        )


@router.post("/quiz/submit", response_model=QuizSubmitResponse)
def submit_quiz(
    payload: QuizSubmitRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_seen_manual),
):
    try:
        return service.submit_quiz(
            db, attempt_id=payload.attempt_id, user_id=user["id"],
            answers=payload.answers,
        )
    except service.AttemptNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "attempt_not_found"})
    except service.AttemptNotOwnedError:
        raise HTTPException(status_code=403, detail={"error": "attempt_not_owned"})
    except service.QuizAlreadySubmittedError:
        raise HTTPException(status_code=409, detail={"error": "quiz_already_submitted"})


@router.post("/annotate/submit", response_model=AnnotateSubmitResponse)
def submit_annotation(
    payload: AnnotateSubmitRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_seen_manual),
):
    try:
        return service.submit_annotation(
            db, attempt_id=payload.attempt_id, user_id=user["id"],
            gold_id=payload.gold_id, references=payload.references,
        )
    except service.AttemptNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "attempt_not_found"})
    except service.AttemptNotOwnedError:
        raise HTTPException(status_code=403, detail={"error": "attempt_not_owned"})
    except service.GoldDocNotInAttemptError:
        raise HTTPException(status_code=404, detail={"error": "gold_doc_not_in_attempt"})
    except service.GoldDocAlreadySubmittedError:
        raise HTTPException(status_code=409, detail={"error": "gold_doc_already_submitted"})


@router.post("/skip", response_model=OkResponse)
def skip_training_route(
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(get_current_user),
):
    """Bypass the training gate. Auth required; user must already be
    logged in (pre-training users CAN call this — it's the whole
    point). Idempotent: re-calling on an already-passed user returns
    ok without side effects."""
    service.skip_training(db, user_id=user["id"])
    return {"ok": True}


@admin_router.post("/users/{user_id}/reset", response_model=OkResponse)
def admin_reset_user_training(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Admin endpoint — soft reset of a user's training. Clears attempts,
    sets has_passed_training=0, creates training_reset notification,
    writes audit row. Idempotent."""
    trace_id = audit.gen_trace_id()
    ok = service.reset_user_training(
        db, user_id=user_id, admin_id=admin["id"], trace_id=trace_id,
    )
    if not ok:
        # Match the project-wide error-shape convention used by other
        # admin endpoints (backend/users/routes.py emits
        # `{"error": "...", "message": "..."}`). Bare-string `detail`
        # forced consumers to special-case this one route.
        raise HTTPException(
            status_code=404,
            detail={
                "error": "user_not_found",
                "message": f"User {user_id} not found",
            },
        )
    return {"ok": True}


@admin_router.get("/gold-docs", response_model=GoldDocsListResponse)
def admin_list_gold_docs(
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    resolved = service.get_active_gold_docs(db)
    rows = db.execute(
        "SELECT gold_id, is_deleted, content, expected_concepts, "
        "min_concept_count, source, created_by_admin_id, created_at, updated_at "
        "FROM training_gold_doc_overrides ORDER BY gold_id"
    ).fetchall()
    overrides = [dict(r) for r in rows]
    return {"resolved": resolved, "overrides": overrides}


@admin_router.put("/gold-docs/{gold_id}", response_model=OkResponse)
def admin_upsert_gold_doc(
    gold_id: str,
    payload: GoldDocUpsertRequest,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()
    concepts = [c.model_dump(exclude_none=True) for c in payload.expected_concepts]
    service.upsert_gold_doc_override(
        db, gold_id=gold_id, content=payload.content,
        expected_concepts=concepts,
        min_concept_count=payload.min_concept_count,
        admin_id=admin["id"],
    )
    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="upsert_gold_doc",
            target_kind="gold_doc", target_id=gold_id,
            metadata={"min_concept_count": payload.min_concept_count, "concept_count": len(concepts)},
            trace_id=trace_id,
        )
    except Exception:
        log.exception("audit upsert_gold_doc failed for %s", gold_id)
    return {"ok": True}


@admin_router.delete("/gold-docs/{gold_id}", response_model=OkResponse)
def admin_delete_gold_doc(
    gold_id: str,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()
    service.soft_delete_gold_doc(db, gold_id=gold_id, admin_id=admin["id"])
    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="delete_gold_doc",
            target_kind="gold_doc", target_id=gold_id,
            trace_id=trace_id,
        )
    except Exception:
        log.exception("audit delete_gold_doc failed for %s", gold_id)
    return {"ok": True}


@admin_router.get("/quiz", response_model=QuizListResponse)
def admin_list_quiz(
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    resolved = get_active_quiz_questions(db)
    rows = db.execute(
        "SELECT question_id, is_deleted, text, choices_json, correct_choice_idx, "
        "source, created_by_admin_id, created_at, updated_at "
        "FROM training_quiz_overrides ORDER BY question_id"
    ).fetchall()
    overrides = [dict(r) for r in rows]
    return {"resolved": resolved, "overrides": overrides}


@admin_router.put("/quiz/{question_id}", response_model=OkResponse)
def admin_upsert_quiz(
    question_id: str,
    payload: QuizUpsertRequest,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()
    service.upsert_quiz_override(
        db, question_id=question_id, text=payload.text,
        choices=payload.choices, correct_choice_idx=payload.correct_choice_idx,
        admin_id=admin["id"],
    )
    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="upsert_quiz_question",
            target_kind="quiz_question", target_id=question_id,
            trace_id=trace_id,
        )
    except Exception:
        log.exception("audit upsert_quiz_question failed for %s", question_id)
    return {"ok": True}


@admin_router.delete("/quiz/{question_id}", response_model=OkResponse)
def admin_delete_quiz(
    question_id: str,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()
    service.soft_delete_quiz_override(db, question_id=question_id, admin_id=admin["id"])
    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="delete_quiz_question",
            target_kind="quiz_question", target_id=question_id,
            trace_id=trace_id,
        )
    except Exception:
        log.exception("audit delete_quiz_question failed for %s", question_id)
    return {"ok": True}
