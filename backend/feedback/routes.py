"""Feedback HTTP endpoints."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.feedback import service
from backend.feedback.models import FeedbackCreateRequest, FeedbackRow, FeedbackType
from backend.users.deps import get_db, get_current_user, require_admin


router = APIRouter(prefix="/api", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackRow, status_code=201)
def submit_feedback(
    payload: FeedbackCreateRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(get_current_user),
):
    """Submit a complaint or suggestion. Authenticated users only."""
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail="message cannot be empty")
    row_id = service.submit_feedback(
        db, user_id=user["id"], type=payload.type, message=payload.message.strip()
    )
    # Fetch back to return full row with username
    row = db.execute(
        """
        SELECT uf.id, uf.user_id, u.username, uf.type, uf.message, uf.created_at
        FROM user_feedback uf
        JOIN users u ON u.id = uf.user_id
        WHERE uf.id = ?
        """,
        (row_id,),
    ).fetchone()
    return dict(row)


@router.get("/admin/feedback", response_model=list[FeedbackRow])
def list_feedback(
    type_filter: FeedbackType | None = None,
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    """List all feedback, optionally filtered by type. Admin only."""
    return service.list_feedback(db, type_filter=type_filter)
