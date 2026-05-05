"""Pydantic response models for lock endpoints."""
from typing import Optional
from pydantic import BaseModel


class LockInfo(BaseModel):
    document_id: str
    user_id: int
    by_username: Optional[str]
    acquired_at: str
    last_heartbeat: str
    expires_at: str


class LockConflict(BaseModel):
    error: str = "lock_held_by_other"
    by_user_id: int
    by_username: Optional[str]
    acquired_at: str
    expires_at: str


class OkResponse(BaseModel):
    ok: bool = True
