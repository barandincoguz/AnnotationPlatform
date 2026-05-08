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
)
from backend.shared import audit
from backend.users.deps import get_db, require_seen_manual, require_admin


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


@admin_router.post("/users/{user_id}/reset", response_model=OkResponse)
def admin_reset_user_training(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Admin endpoint — soft reset of a user's training. Clears attempts,
    sets has_passed_training=0, creates training_reset notification,
    writes audit row. Idempotent."""
    ok = service.reset_user_training(
        db, user_id=user_id, admin_id=admin["id"],
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"user {user_id} not found")
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
    service.soft_delete_gold_doc(db, gold_id=gold_id, admin_id=admin["id"])
    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="delete_gold_doc",
            target_kind="gold_doc", target_id=gold_id,
        )
    except Exception:
        log.exception("audit delete_gold_doc failed for %s", gold_id)
    return {"ok": True}
