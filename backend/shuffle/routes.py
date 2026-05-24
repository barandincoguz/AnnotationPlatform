"""3-tab shuffle feed HTTP endpoint. Auth: require_passed_training."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.shuffle import service
from backend.shuffle.models import FeedResponse
from backend.users.deps import get_db, require_passed_training


router = APIRouter(prefix="/api", tags=["shuffle"])

# Sort whitelist exposed as a regex pattern so FastAPI's Query validation
# rejects unknown keys at the edge (422) before they reach the service.
_SORT_PATTERN = "^(document_id|shuffle|tarih|created_at|sayi|vergi_turu|konu|difficulty|word_count|updated_at|editors_count)$"
_ORDER_PATTERN = "^(asc|desc)$"


@router.get("/feed", response_model=FeedResponse)
def get_feed(
    tab: str = Query(..., pattern="^(new|review|verified)$"),
    limit: int = Query(service.DEFAULT_LIMIT, ge=0, le=service.MAX_LIMIT),
    offset: int = Query(0, ge=0),
    sort: str | None = Query(None, pattern=_SORT_PATTERN),
    order: str | None = Query(None, pattern=_ORDER_PATTERN),
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    """Return paginated feed for a tab.

    sort defaults to the tab's natural sort (DEFAULT_SORT_FOR in
    shuffle/service.py). Pass sort=shuffle for the per-user daily
    deterministic shuffle (legacy default).
    """
    try:
        return service.list_feed(
            db,
            user_id=user["id"],
            tab=tab,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
        )
    except service.InvalidTab as e:
        # FastAPI's pattern Query already rejects unknown tab → 422 before this runs.
        # Defensive — we surface 400 if the validation is bypassed somehow.
        raise HTTPException(status_code=400, detail=str(e))
    except service.InvalidSort as e:
        # The sort key whitelist is enforced by the route pattern, but
        # the tab-specific gate (e.g. updated_at only on review/verified)
        # is enforced inside the service. Surface those as 400 with
        # a structured detail.
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_sort", "message": str(e)},
        )
