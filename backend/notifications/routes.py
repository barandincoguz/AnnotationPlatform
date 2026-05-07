"""HTTP endpoints for the notifications inbox.

Auth: get_current_user (NOT require_passed_training — even pre-training
users may receive admin announcements).
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.notifications import service
from backend.notifications.models import (
    NotificationListResponse, OkResponse,
)
from backend.users.deps import get_current_user, get_db


router = APIRouter(prefix="/api/me/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(get_current_user),
    unread_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
):
    items = service.list_for_user(
        db, user_id=user["id"], unread_only=unread_only, limit=limit,
    )
    return {"items": items}


@router.post("/{notification_id}/read", response_model=OkResponse)
def mark_read(
    notification_id: int,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(get_current_user),
):
    try:
        service.mark_read(db, notification_id=notification_id, user_id=user["id"])
    except service.NotificationNotFound:
        raise HTTPException(status_code=404, detail="notification not found")
    return {"ok": True}
