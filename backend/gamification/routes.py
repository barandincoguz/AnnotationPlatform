"""Public HTTP endpoints for the gamification module.

Currently exposes only the static badge catalog. The profile endpoint
(`GET /api/me/profile`) lives in `backend/users/routes.py` because it
aggregates user identity + gamification state under the /me/* tree.
"""
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.gamification.badges import BADGE_DEFS
from backend.users.deps import get_current_user


router = APIRouter(prefix="/api/badges", tags=["gamification"])


class BadgeCatalogItem(BaseModel):
    id: str
    name: str
    description: str
    criterion: str


@router.get("/catalog", response_model=list[BadgeCatalogItem])
def get_catalog(
    _user: sqlite3.Row = Depends(get_current_user),
):
    """Return all known badges in insertion order. The frontend joins this
    with the user's earned set (from /me/profile.badges) to render the
    'Hepsi' tab of the BadgesGrid with grayscale + criterion text for the
    not-yet-earned items."""
    out: list[dict] = []
    for badge_id, meta in BADGE_DEFS.items():
        out.append({
            "id": badge_id,
            "name": meta["name"],
            "description": meta["description"],
            "criterion": meta["criterion"],
        })
    return out
