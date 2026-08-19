"""Pre-submit quality audit endpoint. Read-only: writes nothing, logs nothing.

The audit decision is recorded by /complete (inside its transaction), never
here — a manual "compare me" look must not pollute the audit trail.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.quality import service
from backend.quality.models import PreAuditRequest, PreAuditResponse
from backend.users.deps import get_db, require_passed_training

router = APIRouter(prefix="/api", tags=["quality"])


@router.post(
    "/annotations/{document_id}/pre-audit",
    response_model=PreAuditResponse,
)
def pre_audit(
    document_id: str,
    payload: PreAuditRequest,
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(require_passed_training),
):
    """Compare the caller's current references against the cached G0 prediction."""
    try:
        report = service.build_report(
            db,
            document_id=document_id,
            references=[r.model_dump() for r in payload.references],
        )
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    return report.to_response()
