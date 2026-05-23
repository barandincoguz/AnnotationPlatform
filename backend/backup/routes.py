"""Admin HTTP endpoint for manual backup trigger."""
import json
import logging
import pathlib
import sqlite3
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend import config
from backend.backup.models import BackupRestoreResponse, BackupRunNowResponse
from backend.backup.restore import restore_from_snapshot
from backend.backup.service import is_wal_busy, run_backup_cycle
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
    by the cycle's per-step error logging).

    A trace_id is generated at entry and threaded through the cycle and
    the audit row so an operator can reconstruct the chain via trace_id.
    """
    trace_id = audit.gen_trace_id()
    try:
        result = run_backup_cycle(db, trace_id=trace_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "backup_failed", "message": str(e), "trace_id": trace_id},
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
            trace_id=trace_id,
        )
    except Exception:
        log.exception("audit backup_run_now failed")

    return {
        "ok": True,
        "snapshot_path": result["snapshot_path"],
        "committed_sha": result["committed_sha"],
        "pushed": result["pushed"],
        "rotated_count": result["rotated_count"],
        "trace_id": trace_id,
    }


@router.post("/restore", response_model=BackupRestoreResponse)
async def admin_backup_restore(
    snapshot: UploadFile = File(...),
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Restore DB state from an uploaded snapshot JSON.

    Refuses with 409 db_busy if WAL has uncommitted frames from another
    writer. Wraps restore_from_snapshot and writes an admin_audit_log row
    on success.
    """
    trace_id = audit.gen_trace_id()

    if is_wal_busy(db):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "db_busy",
                "message": "WAL has uncommitted frames from another writer; retry after the writer finishes.",
                "trace_id": trace_id,
            },
        )

    raw = await snapshot.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_json", "message": str(e), "trace_id": trace_id},
        )

    # Persist to a temp file inside DATA_DIR so restore_from_snapshot's
    # Path-based signature is preserved without further refactor.
    with tempfile.NamedTemporaryFile(
        delete=False, mode="w", dir=str(config.DATA_DIR), suffix=".restore.json"
    ) as f:
        json.dump(payload, f)
        snap_path = pathlib.Path(f.name)

    try:
        result = restore_from_snapshot(db, snap_path)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "restore_invalid_columns", "message": str(e), "trace_id": trace_id},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "restore_failed", "message": str(e), "trace_id": trace_id},
        )
    finally:
        try:
            snap_path.unlink()
        except OSError:
            pass

    # Capture admin_user_id before restore because restore_from_snapshot
    # DELETEs and re-inserts the users table. If the restored snapshot does
    # not include the acting admin row, a post-restore FK lookup would fail.
    # admin_audit_log.admin_user_id is nullable (ON DELETE SET NULL), so
    # passing None is valid; trace_id carries attribution for the audit trail.
    admin_user_id: int = admin["id"]
    try:
        audit.log_admin_action(
            db, admin_user_id=None, action_type="backup_restore",
            target_kind="backup", target_id=None,
            metadata={
                "admin_user_id_at_request": admin_user_id,
                "total_rows": result["total_rows"],
                "tables": result["tables"],
                "skipped_tables": result["skipped_tables"],
            },
            trace_id=trace_id,
        )
    except Exception:
        log.exception("audit backup_restore failed")

    return {"ok": True, **result, "trace_id": trace_id}
