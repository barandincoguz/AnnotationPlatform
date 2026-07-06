"""Statistics HTTP endpoints."""
import sqlite3

from fastapi import APIRouter, Depends

from backend.statistics import service
from backend.statistics.models import UserStatisticsResponse
from backend.users.deps import get_db, require_passed_training


router = APIRouter(prefix="/api/statistics", tags=["statistics"])


@router.get("/users", response_model=UserStatisticsResponse)
def list_user_statistics(
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(require_passed_training),
):
    return service.get_user_statistics(db)
