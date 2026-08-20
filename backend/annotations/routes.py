"""Annotation HTTP endpoints. Auth: require_passed_training on all."""
import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.annotations import drafts as drafts_service
from backend.annotations import service
from backend.annotations.diff import (
    DuplicateReference, InvalidReference,
)
from backend.annotations.models import (
    SaveAnnotationRequest, SaveAnnotationResponse,
    AnnotationWithChain,
    CompleteRequest, OkResponse,
)
from backend.behavioral import service as behavioral_service
from backend.gamification import service as gamification_service
from backend.quality import service as quality_service
from backend.shared.sse import broker as sse_broker
from backend.users.deps import get_db, require_passed_training


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["annotations"])


@router.post(
    "/annotations",
    response_model=SaveAnnotationResponse,
)
async def save(
    payload: SaveAnnotationRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    """Save reference list (atomic version + denorm rebuild). Broadcasts
    annotation_saved on success, then runs behavioral detectors which may
    publish personal speed_warning / char_limit_warning events back to the
    saving user, then runs the gamification orchestrator (XP, streak,
    badges, post-hoc review_kept). 422 on duplicate/invalid refs; 404 on
    unknown document. Publish, detector, and orchestrator errors are logged
    and swallowed."""
    refs = [r.model_dump() for r in payload.references]
    try:
        result = service.save_annotation(
            db,
            document_id=payload.document_id,
            user_id=user["id"],
            references=refs,
        )
    except service.LockOwnedByOther:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "lock_owned_by_other",
                "message": "Bu doküman başka bir kullanıcı tarafından kilitli.",
            },
        )
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {payload.document_id} not found")
    except (DuplicateReference, InvalidReference) as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        action = "create" if result["is_new"] else "edit"
        await sse_broker.publish_broadcast(
            "annotation_saved",
            {
                "document_id": payload.document_id,
                "user_id": user["id"],
                "username": user["username"],
                "action": action,
                "is_diff_zero": result["is_diff_zero"],
                "ref_count": len(result["current_references"]),
            },
        )
    except Exception:
        log.exception("publish annotation_saved failed for %s", payload.document_id)

    try:
        await behavioral_service.run_after_save(
            db,
            user_id=user["id"],
            username=user["username"],
            references=result["current_references"],
            model_quotes=quality_service.model_quotes(db, payload.document_id),
        )
    except Exception:
        log.exception("run_after_save failed for %s", payload.document_id)

    try:
        action = "create" if result["is_new"] else "edit"
        await gamification_service.run_after_save(
            db,
            user_id=user["id"],
            username=user["username"],
            action=action,
            is_diff_zero=result["is_diff_zero"],
            document_id=payload.document_id,
        )
    except Exception:
        log.exception("gamification.run_after_save failed for %s", payload.document_id)
    return result


@router.post(
    "/annotations/{document_id}/skip",
    response_model=OkResponse,
)
def skip(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    """Log a skip activity event and release the caller's lock, then bump
    gamification today_skip_count (no XP). Stays sync; intentionally does
    NOT broadcast (skip is private to the user). Orchestrator errors are
    logged and swallowed."""
    try:
        service.skip_annotation(db, document_id=document_id, user_id=user["id"])
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")

    try:
        gamification_service.record_skip(db, user_id=user["id"])
    except Exception:
        log.exception("gamification.record_skip failed for %s", document_id)
    return {"ok": True}


@router.post(
    "/annotations/{document_id}/complete",
    response_model=OkResponse,
)
async def complete(
    document_id: str,
    payload: CompleteRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    """Toggle is_completed on the annotation, optionally saving refs atomically.

    Side effects driven from the service's transaction-committed result:
      * `did_save` (atomic path persisted refs) → broadcast annotation_saved,
        run behavioral detectors + gamification.run_after_save (XP, streak,
        badges) — same surface as the dedicated /annotations save route.
      * `changed` (flag transitioned this call) → broadcast annotation_completed,
        run gamification.run_after_complete (XP + first_completion on True;
        uncomplete is a clamp — no decrement).

    Pre-Phase-2 the route read `service.get_annotation` BEFORE calling
    `set_complete` to derive a `will_change` flag. That left first-time
    atomic completes (annotation didn't exist yet) firing zero side
    effects because `prior is None`. The service now returns committed
    facts and the route stops second-guessing them. 404 if no annotation
    row AND no refs to create one. Publish, detector, and orchestrator
    errors are logged and swallowed.
    """
    # Pass refs through when the caller is doing an atomic save+complete
    # (Phase 2). Convert Pydantic ReferenceItem → dicts to match the
    # service's plain-dict contract. `None` preserves the legacy
    # flag-flip-only path.
    refs_payload: Optional[list[dict]] = (
        [r.model_dump() for r in payload.references]
        if payload.references is not None
        else None
    )

    try:
        result = service.set_complete(
            db, document_id=document_id, user_id=user["id"],
            completed=payload.completed,
            references=refs_payload,
            audit_ack=(
                payload.audit_ack.prediction_fingerprint
                if payload.audit_ack is not None
                else None
            ),
        )
    except quality_service.AuditAckRequired as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "audit_required",
                "message": (
                    "Model karşılaştırmasında farklılık var. Lütfen kalite "
                    "denetimini görüntüleyip onaylayın."
                ),
                "bucket": exc.bucket,
                "prediction_fingerprint": exc.prediction_fingerprint,
            },
        )
    except quality_service.AuditAckStale as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "audit_stale",
                "message": (
                    "Yeni model tahmini alındı, lütfen son kez teyit edip "
                    "Tamamla'ya basınız."
                ),
                "prediction_fingerprint": exc.prediction_fingerprint,
            },
        )
    except service.LockOwnedByOther:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "lock_owned_by_other",
                "message": "Bu doküman başka bir kullanıcı tarafından kilitli.",
            },
        )
    except service.AnnotationNotFound:
        raise HTTPException(status_code=404, detail=f"no annotation for {document_id}")
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    except (DuplicateReference, InvalidReference) as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Save-side effects: fire whenever refs were committed in this call.
    if result["did_save"]:
        try:
            await sse_broker.publish_broadcast(
                "annotation_saved",
                {
                    "document_id": document_id,
                    "user_id": user["id"],
                    "username": user["username"],
                    "action": result["save_action"],
                    "is_diff_zero": result["save_is_diff_zero"],
                    "ref_count": result["save_ref_count"],
                },
            )
        except Exception:
            log.exception("publish annotation_saved failed for %s", document_id)
        try:
            # behavioral.run_after_save reads the final refs out of the
            # DB; pass refs_payload so it doesn't have to re-query.
            # `refs_payload` is non-None here because did_save implies
            # references were passed in.
            await behavioral_service.run_after_save(
                db,
                user_id=user["id"],
                username=user["username"],
                references=refs_payload or [],
                model_quotes=quality_service.model_quotes(db, document_id),
            )
        except Exception:
            log.exception("behavioral.run_after_save failed for %s", document_id)
        try:
            await gamification_service.run_after_save(
                db,
                user_id=user["id"],
                username=user["username"],
                action=result["save_action"] or "edit",
                is_diff_zero=bool(result["save_is_diff_zero"]),
                document_id=document_id,
            )
        except Exception:
            log.exception("gamification.run_after_save failed for %s", document_id)

    # Complete-side effects: fire only on real flag transitions
    # (committed-state truth from the service).
    if result["changed"]:
        try:
            await sse_broker.publish_broadcast(
                "annotation_completed",
                {
                    "document_id": document_id,
                    "user_id": user["id"],
                    "username": user["username"],
                    "completed": payload.completed,
                },
            )
        except Exception:
            log.exception("publish annotation_completed failed for %s", document_id)

        try:
            await gamification_service.run_after_complete(
                db,
                user_id=user["id"],
                username=user["username"],
                completed=payload.completed,
                document_id=document_id,
            )
        except Exception:
            log.exception("gamification.run_after_complete failed for %s", document_id)
    return {"ok": True}


@router.get(
    "/documents/{document_id}/annotation",
    response_model=AnnotationWithChain,
)
def get_annotation_with_chain(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(require_passed_training),
):
    """Returns current annotation + version chain. Caller uses this for chain review."""
    ann = service.get_annotation(db, document_id)
    chain = service.get_chain(db, document_id)
    if ann is None and not chain:
        # confirm doc exists, otherwise 404 (not all-empty for a missing doc)
        row = db.execute(
            "SELECT 1 FROM documents_meta WHERE document_id=?", (document_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    return {"annotation": ann, "chain": chain}


class _DraftPutRequest(BaseModel):
    # Raw — frontend may send incomplete rows. Cap matches the committed
    # SaveAnnotationRequest list cap (200) so a draft cannot exceed the
    # ceiling of a finalized annotation. Without a cap, an authenticated
    # user could PUT multi-MB blobs into their draft and bloat the DB.
    references: list[dict] = Field(max_length=200)


@router.put("/drafts/{document_id}", response_model=OkResponse)
def put_draft(
    document_id: str,
    payload: _DraftPutRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        drafts_service.set_draft(
            db, document_id=document_id, user_id=user["id"],
            references=payload.references,
        )
    except drafts_service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    return {"ok": True}


@router.get("/drafts/{document_id}")
def get_draft(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    out = drafts_service.get_draft(db, document_id=document_id, user_id=user["id"])
    if out is None:
        raise HTTPException(status_code=404, detail="no draft")
    return out


@router.delete("/drafts/{document_id}", response_model=OkResponse)
def delete_draft(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    drafts_service.clear_draft(db, document_id=document_id, user_id=user["id"])
    return {"ok": True}
