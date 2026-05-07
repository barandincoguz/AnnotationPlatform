"""Pydantic schemas for gamification endpoints."""
from typing import Optional

from pydantic import BaseModel


class UserSection(BaseModel):
    id: int
    username: str
    role: str
    avatar_color: str


class XpSection(BaseModel):
    total: int


class StreakSection(BaseModel):
    current: int
    longest: int
    last_active_date: Optional[str]


class TodaySection(BaseModel):
    save: int
    complete: int
    review: int
    skip: int
    daily_target: int


class BadgeOut(BaseModel):
    id: str
    name: str
    description: str
    earned_at: str


class ProfileResponse(BaseModel):
    user: UserSection
    xp: XpSection
    streak: StreakSection
    today: TodaySection
    badges: list[BadgeOut]
