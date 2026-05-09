"""Admin HTTP endpoint for manual backup trigger."""
import logging
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.backup.models import BackupRunNowResponse
from backend.backup.service import run_backup_cycle
from backend.shared import audit
from backend.users.deps import get_db, require_admin


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/backup", tags=["admin-backup"])


@router.post("/run-now", response_model=BackupRunNowResponse)
def admin_backup_run_now(
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Trigger a backup cycle synchronously. Blocks until complete.
    Returns 500 on any cycle failure (system_events row already written
    by the cycle's per-step error logging)."""
    try:
        result = run_backup_cycle(db)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "backup_failed", "message": str(e)},
        )

    try:
        snapshot_filename = Path(result["snapshot_path"]).name
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="backup_run_now",
            target_kind="backup", target_id=snapshot_filename,
            metadata={
                "pushed": result["pushed"],
                "committed_sha": result["committed_sha"],
                "rotated_count": result["rotated_count"],
            },
        )
    except Exception:
        log.exception("audit backup_run_now failed")

    return {
        "ok": True,
        "snapshot_path": result["snapshot_path"],
        "committed_sha": result["committed_sha"],
        "pushed": result["pushed"],
        "rotated_count": result["rotated_count"],
    }
