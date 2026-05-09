"""Admin-only HTTP endpoints. Currently: site_settings read/write."""
import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.admin import service as admin_service
from backend.admin.models import SettingUpdateRequest, SettingUpdateResponse
from backend.shared import audit, settings as S
from backend.users.deps import get_db, require_admin


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/settings")
def list_settings(
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    """Return the full key→value map of site_settings."""
    return S.get_all(db)


def _python_type_label(value) -> str:
    """Human-readable type label for type-mismatch errors."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def _types_compatible(old, new) -> bool:
    """int↔int, str↔str, dict↔dict, list↔list, bool↔bool, float↔float.
    int and float are NOT considered compatible (the typed accessors are strict
    and the seeded values are integers throughout — silent truncation would be
    a footgun)."""
    return _python_type_label(old) == _python_type_label(new)


@router.put("/settings/{key}", response_model=SettingUpdateResponse)
def update_setting(
    key: str,
    payload: SettingUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Update an existing site_settings entry. Allowlist: 404 if the key isn't
    already in the table (use migrations to add new keys). Type guard: 422 if
    the new value's Python type does not match the existing value's type.
    Successful writes are audited."""
    all_settings = S.get_all(db)
    if key not in all_settings:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_setting_key", "key": key},
        )
    old_value = all_settings[key]
    new_value = payload.value
    if not _types_compatible(old_value, new_value):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "type_mismatch",
                "expected": _python_type_label(old_value),
                "got": _python_type_label(new_value),
            },
        )

    trace_id = audit.gen_trace_id()
    S.set_value(db, key, new_value, updated_by_user_id=admin["id"])
    audit.log_admin_action(
        db, admin_user_id=admin["id"], action_type="settings_update",
        target_kind="setting", target_id=key,
        metadata={"old_value": old_value, "new_value": new_value},
        trace_id=trace_id,
    )
    return {"key": key, "value": new_value}


@router.get("/audit-log")
def admin_audit_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_id: Optional[int] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    """Paginated + filtered admin audit log."""
    return admin_service.list_admin_audit(
        db, limit=limit, offset=offset,
        admin_id=admin_id, action=action,
        date_from=date_from, date_to=date_to,
    )


@router.get("/system-events")
def admin_system_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    date_from: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    """Paginated + filtered system events log."""
    return admin_service.list_system_events(
        db, limit=limit, offset=offset,
        event_type=event_type, severity=severity,
        date_from=date_from, date_to=date_to,
    )
