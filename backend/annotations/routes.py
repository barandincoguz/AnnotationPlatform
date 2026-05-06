"""Annotation HTTP endpoints. Auth: require_passed_training on all."""
import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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
    refs = [r.model_dump() for r in payload.references]
    try:
        result = service.save_annotation(
            db,
            document_id=payload.document_id,
            user_id=user["id"],
            references=refs,
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
    try:
        service.skip_annotation(db, document_id=document_id, user_id=user["id"])
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
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
    # Read prior state so we know whether this is a real toggle or a no-op
    prior = service.get_annotation(db, document_id)
    will_change = prior is not None and prior["is_completed"] != payload.completed

    try:
        service.set_complete(
            db, document_id=document_id, user_id=user["id"],
            completed=payload.completed,
        )
    except service.AnnotationNotFound:
        raise HTTPException(status_code=404, detail=f"no annotation for {document_id}")

    if will_change:
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
    references: list[dict]  # raw — frontend may send incomplete rows


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
