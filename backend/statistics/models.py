"""Pydantic schemas for aggregate user statistics."""
from typing import Literal, Optional

from pydantic import BaseModel


StatisticsPeriod = Literal["today", "last_7_days", "last_30_days", "all_time"]


class StatisticsUser(BaseModel):
    id: int
    username: str
    role: str
    avatar_color: Optional[str] = None


class StatisticsMetrics(BaseModel):
    distinct_documents: int = 0
    save_events: int = 0
    complete_events: int = 0
    uncomplete_events: int = 0
    skip_events: int = 0
    version_events: int = 0
    create_versions: int = 0
    edit_versions: int = 0
    complete_mark_versions: int = 0
    zero_diff_versions: int = 0
    final_completed_documents: int = 0
    xp_delta: int = 0


class UserStatisticsRow(BaseModel):
    user: StatisticsUser
    xp_total: int
    badges_count: int
    streak_current: int
    last_active_date: Optional[str] = None
    metrics: dict[StatisticsPeriod, StatisticsMetrics]


class UserStatisticsResponse(BaseModel):
    generated_at: str
    summary: dict[StatisticsPeriod, StatisticsMetrics]
    users: list[UserStatisticsRow]
