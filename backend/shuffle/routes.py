"""3-tab shuffle feed HTTP endpoint. Auth: require_passed_training."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.shuffle import service
from backend.shuffle.models import FeedResponse
from backend.users.deps import get_db, require_passed_training


router = APIRouter(prefix="/api", tags=["shuffle"])


@router.get("/feed", response_model=FeedResponse)
def get_feed(
    tab: str = Query(..., pattern="^(new|review|verified)$"),
    limit: int = Query(service.DEFAULT_LIMIT, ge=0, le=service.MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        return service.list_feed(
            db, user_id=user["id"], tab=tab, limit=limit, offset=offset,
        )
    except service.InvalidTab as e:
        # FastAPI's pattern Query already rejects unknown tab → 422 before this runs.
        # Defensive — we surface 400 if the validation is bypassed somehow.
        raise HTTPException(status_code=400, detail=str(e))
