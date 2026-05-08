"""Lock HTTP endpoints. Auth: require_passed_training on all."""
import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.locks import service
from backend.locks.models import LockInfo, LockConflict, OkResponse
from backend.shared import audit
from backend.shared.sse import broker as sse_broker
from backend.users.deps import get_db, require_admin, require_passed_training


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/locks", tags=["locks"])


def _strip_dup_keys(info: dict) -> dict:
    """Service returns both user_id and by_user_id (same value); keep the response shape clean."""
    return {k: v for k, v in info.items() if k != "by_user_id"}


@router.post(
    "/{document_id}/acquire",
    response_model=LockInfo,
    responses={409: {"model": LockConflict}},
)
async def acquire(
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
    response = _strip_dup_keys(info)
    try:
        await sse_broker.publish_broadcast(
            "lock_acquired",
            {
                "document_id": document_id,
                "by_user_id": info["user_id"],
                "by_username": info["by_username"],
                "expires_at": info["expires_at"],
            },
        )
    except Exception:
        log.exception("publish lock_acquired failed for %s", document_id)
    return response


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
async def release(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    # Read whether the user actually held a lock — service.release is silent on absent.
    # Note: small TOCTOU window vs. background sweep — between this read and the
    # release below, a sweep could clear an already-expired lock. Worst case is a
    # missed lock_released event (the row is gone, nothing to release); never a
    # phantom event or DB corruption. Acceptable tradeoff under autocommit + WAL.
    held = service.get_lock(db, document_id)
    holder_user_id = held["user_id"] if held and held["user_id"] == user["id"] else None

    try:
        service.release(db, document_id=document_id, user_id=user["id"])
    except service.NotLockHolder:
        raise HTTPException(status_code=404, detail="lock held by another user")

    if holder_user_id is not None:
        try:
            await sse_broker.publish_broadcast(
                "lock_released",
                {
                    "document_id": document_id,
                    "by_user_id": holder_user_id,
                    "reason": "user_release",
                },
            )
        except Exception:
            log.exception("publish lock_released failed for %s", document_id)
    return {"ok": True}


@router.post("/{document_id}/admin/force-release", response_model=OkResponse)
async def admin_force_release(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Admin override — unconditional release. 404 if no lock currently held.
    Broadcasts lock_released with reason='admin_force'. Writes admin audit."""
    held = service.get_lock(db, document_id)
    if held is None:
        raise HTTPException(status_code=404, detail=f"no lock on {document_id}")

    prior_user_id = held["user_id"]
    service.force_release(db, document_id=document_id)

    try:
        await sse_broker.publish_broadcast(
            "lock_released",
            {
                "document_id": document_id,
                "by_user_id": prior_user_id,
                "reason": "admin_force",
            },
        )
    except Exception:
        log.exception("publish lock_released admin_force failed for %s", document_id)

    try:
        audit.log_admin_action(
            db,
            admin_user_id=admin["id"],
            action_type="lock_force_release",
            target_kind="document",
            target_id=document_id,
            metadata={"prior_holder_user_id": prior_user_id},
        )
    except Exception:
        log.exception("log_admin_action lock_force_release failed for %s", document_id)

    return {"ok": True}
