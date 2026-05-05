"""Help content endpoint."""
import sqlite3

from fastapi import APIRouter, Depends

from backend.users.deps import get_current_user
from backend.docs_help.service import list_help_sections

router = APIRouter(prefix="/api", tags=["help"])


@router.get("/help")
def get_help(
    _user: sqlite3.Row = Depends(get_current_user),
):
    """Return all help sections in order. Auth required, has_seen_manual NOT required."""
    return {"sections": list_help_sections()}
