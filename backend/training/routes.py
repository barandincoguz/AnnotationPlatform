"""HTTP endpoints for the training gate. Auth: require_seen_manual.

The user is taking training right now — using require_passed_training would
be circular. Pre-manual users (has_seen_manual=0) still must read /help first."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.training import service
from backend.training.models import (
    StartResponse, QuizSubmitRequest, QuizSubmitResponse,
    AnnotateSubmitRequest, AnnotateSubmitResponse,
)
from backend.users.deps import get_db, require_seen_manual


router = APIRouter(prefix="/api/training", tags=["training"])


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
