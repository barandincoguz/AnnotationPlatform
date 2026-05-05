"""Lock HTTP endpoints. Auth: require_passed_training on all."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.locks import service
from backend.locks.models import LockInfo, OkResponse
from backend.users.deps import get_db, require_passed_training


router = APIRouter(prefix="/api/locks", tags=["locks"])


def _strip_dup_keys(info: dict) -> dict:
    """Service returns both user_id and by_user_id (same value); keep the response shape clean."""
    return {k: v for k, v in info.items() if k != "by_user_id"}


@router.post("/{document_id}/acquire", response_model=LockInfo)
def acquire(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        info = service.acquire(db, document_id=document_id, user_id=user["id"])
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    except service.LockHeldByOther as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "lock_held_by_other",
                "by_user_id": e.info["by_user_id"],
                "by_username": e.info["by_username"],
                "acquired_at": e.info["acquired_at"],
                "expires_at": e.info["expires_at"],
            },
        )
    return _strip_dup_keys(info)


@router.post("/{document_id}/heartbeat", response_model=LockInfo)
def heartbeat(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        info = service.heartbeat(db, document_id=document_id, user_id=user["id"])
    except service.NotLockHolder:
        raise HTTPException(status_code=404, detail="lock not found or not held by you")
    return _strip_dup_keys(info)


@router.post("/{document_id}/release", response_model=OkResponse)
def release(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        service.release(db, document_id=document_id, user_id=user["id"])
    except service.NotLockHolder:
        raise HTTPException(status_code=404, detail="lock held by another user")
    return {"ok": True}
