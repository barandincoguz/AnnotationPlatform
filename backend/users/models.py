"""Pydantic request/response models for auth + users."""
from typing import Optional, Literal
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    invite_code: str
    email: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str]
    role: Literal["user", "admin"]
    is_active: bool
    has_passed_training: bool
    has_seen_manual: bool
    avatar_color: Optional[str]
    created_at: str


class UsersListResponse(BaseModel):
    users: list[UserOut]
    total: int


class OkResponse(BaseModel):
    ok: bool = True
