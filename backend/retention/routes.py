"""Admin HTTP endpoints for retention purge and dry-run preview."""
import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.retention.models import (
    RetentionPreviewResponse,
    RetentionRunNowResponse,
)
from backend.retention.service import preview_purge, run_purge
from backend.shared import audit
from backend.users.deps import get_db, require_admin


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/retention", tags=["admin-retention"])


@router.post("/run-now", response_model=RetentionRunNowResponse)
def admin_retention_run_now(
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Trigger a retention cycle synchronously. Blocks until commit/rollback.
    Returns 500 on any failure (system_events row already written by run_purge).
    A trace_id is generated at entry and threaded through the cycle + audit."""
    trace_id = audit.gen_trace_id()
    try:
        result = run_purge(db, trace_id=trace_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "retention_failed", "message": str(e), "trace_id": trace_id},
        )

    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="retention_run_now",
            target_kind="retention", target_id=None,
            metadata={
                "total": result["total"],
                "by_table": result["purged"],
            },
            trace_id=trace_id,
        )
    except Exception:
        log.exception("audit retention_run_now failed")

    return {**result, "trace_id": trace_id}


@router.get("/preview", response_model=RetentionPreviewResponse)
def admin_retention_preview(
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Read-only dry-run. Returns per-table count of rows that would be
    purged plus the active policy snapshot."""
    return preview_purge(db)
