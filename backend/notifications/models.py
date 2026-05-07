"""Pydantic schemas for notifications endpoints."""
from typing import Any, Optional

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    is_read: bool
    created_at: str


class NotificationListResponse(BaseModel):
    items: list[NotificationOut]


class OkResponse(BaseModel):
    ok: bool = True
