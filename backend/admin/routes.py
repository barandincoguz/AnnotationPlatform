"""Admin-only HTTP endpoints. Currently: site_settings read/write."""
import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.admin.models import SettingUpdateRequest, SettingUpdateResponse, OkResponse
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
