"""Help content endpoint."""
import sqlite3

from fastapi import APIRouter, Depends

from backend.users.deps import get_current_user
from backend.docs_help.service import list_help_sections, list_law_abbreviations

router = APIRouter(prefix="/api", tags=["help"])


@router.get("/help")
def get_help(
    _user: sqlite3.Row = Depends(get_current_user),
):
    """Return all help sections in order. Auth required, has_seen_manual NOT required."""
    return {"sections": list_help_sections()}


@router.get("/law-abbreviations")
def get_law_abbreviations(
    _user: sqlite3.Row = Depends(get_current_user),
):
    """Law abbreviation → full name (+ number) reference for annotators.

    Auth required, has_seen_manual NOT required. Sourced from the canonical
    normalization tables so it stays consistent with backend behavior.
    """
    return {"laws": list_law_abbreviations()}
