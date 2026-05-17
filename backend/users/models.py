"""Pydantic request/response models for auth + users."""
from typing import Optional, Literal
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    # Caps on invite_code match the rotate-invite contract — uppercase
    # base-32-ish slugs of ~8-32 chars. Without caps, an attacker can
    # spray multi-KB payloads with `_check_active_invite` doing a string
    # comparison against every active row.
    invite_code: str = Field(min_length=1, max_length=64)
    # Light email cap; full RFC validation is out of scope and existing
    # callers may pass anything. A 254-char cap matches the SMTP limit.
    email: Optional[str] = Field(default=None, max_length=254)


class LoginRequest(BaseModel):
    # Caps mirror RegisterRequest. Without these, empty strings would hit
    # the DB (which then reports "user not found") and unbounded payloads
    # would let an attacker submit megabyte-long fields just to occupy a
    # bcrypt thread for the timing budget. 422 is the right answer for
    # both cases — it fails fast before the lookup.
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)


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
