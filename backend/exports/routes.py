"""Admin HTTP endpoint for streaming the annotation dataset export."""
import logging
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse

from backend import config
from backend.exports.models import ExportFilters
from backend.exports.service import (
    build_query, stream_csv_rows, stream_jsonl_objects,
)
from backend.shared import audit
from backend.shared.db import connect
from backend.users.deps import require_admin


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/export", tags=["admin-export"])


def _utc_filename_stamp() -> str:
    """YYYYMMDD-HHMM in UTC; matches backup snapshot naming convention."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")


def _filters_for_audit(filters: ExportFilters) -> dict:
    """Render filters as a JSON-serializable dict for admin_audit_log."""
    return {
        "format": filters.format,
        "status": filters.status,
        "from_date": filters.from_date.isoformat() if filters.from_date else None,
        "to_date": filters.to_date.isoformat() if filters.to_date else None,
        "document_id": filters.document_id,
        "user_id": filters.user_id,
    }


@router.get("")
def admin_export_dataset(
    background: BackgroundTasks,
    filters: ExportFilters = Depends(),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Stream the annotation dataset matching `filters` as CSV or JSONL.

    We open a dedicated connection here (not via get_db) because
    StreamingResponse consumes the body iterator lazily — after the route
    handler returns — so a get_db-yielded connection would already be closed
    by the time the first chunk is generated. The dedicated connection is
    closed by the background task once both the stream and the audit write
    are done.
    """
    stream_conn = connect(config.DB_PATH)
    sql, params = build_query(filters)
    cursor = stream_conn.execute(sql, params)

    # Counter is mutable so the background task can read the post-stream value.
    counter = [0]

    if filters.format == "csv":
        def _count_rows_csv(cursor_inner):
            for row in cursor_inner:
                counter[0] += 1
                yield row
        body_iter = stream_csv_rows(_count_rows_csv(cursor))
        media_type = "text/csv; charset=utf-8"
        ext = "csv"
    else:  # jsonl
        # JSONL counts annotations (= unique document_ids), not cursor rows.
        def _count_annotations(cursor_inner):
            """Count unique document_ids in the cursor stream. Relies on
            row[0] being document_id per _BASE_SELECT column order; if
            that ordering ever changes, this counter silently miscounts.
            (CSV_COLUMNS[0] == 'document_id' is the source-of-truth
            contract — keep _BASE_SELECT and CSV_COLUMNS in sync.)
            """
            seen = None
            for row in cursor_inner:
                doc_id = row[0]
                if doc_id != seen:
                    counter[0] += 1
                    seen = doc_id
                yield row
        body_iter = stream_jsonl_objects(_count_annotations(cursor))
        media_type = "application/x-ndjson; charset=utf-8"
        ext = "jsonl"

    filename = f"annotations-export-{_utc_filename_stamp()}.{ext}"

    def _record_audit_and_close():
        try:
            audit.log_admin_action(
                stream_conn, admin_user_id=admin["id"],
                action_type="export_dataset",
                target_kind="export", target_id=filename,
                metadata={
                    "format": filters.format,
                    "filters": _filters_for_audit(filters),
                    "exported_count": counter[0],
                },
            )
            # No explicit commit needed — connect() uses isolation_level=None
            # (autocommit), so log_admin_action's INSERT is durable on
            # statement execution. Kept the close() in finally so the
            # connection is released even if log_admin_action raises.
        except Exception:
            log.exception("audit export_dataset failed")
        finally:
            stream_conn.close()

    background.add_task(_record_audit_and_close)

    return StreamingResponse(
        body_iter,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        background=background,
    )
