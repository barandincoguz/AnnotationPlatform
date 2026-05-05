"""User service: register, login, logout, admin operations.

Custom exceptions are caught by route handlers and mapped to HTTP errors.
"""
import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.shared import auth
# audit imported lazily inside admin functions (Task 7)


# === Exception types ===
class UsersServiceError(Exception):
    """Base class for user-related errors."""


class InvalidInviteCode(UsersServiceError):
    pass


class UsernameTaken(UsersServiceError):
    pass


class EmailTaken(UsersServiceError):
    pass


class InvalidPassword(UsersServiceError):
    pass


class UserNotFound(UsersServiceError):
    pass


class InvalidCredentials(UsersServiceError):
    pass


class UserDisabled(UsersServiceError):
    pass


class NotAdmin(UsersServiceError):
    pass


class LastAdminCannotBeRemoved(UsersServiceError):
    pass


# === Constants ===
AVATAR_PALETTE = [
    "#ef4444", "#f97316", "#eab308", "#22c55e",
    "#10b981", "#06b6d4", "#3b82f6", "#6366f1",
    "#a855f7", "#ec4899", "#f43f5e", "#84cc16",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _avatar_color_for(username: str) -> str:
    """Deterministic color from username (SHA-256 hash → palette index)."""
    h = hashlib.sha256(username.lower().encode("utf-8")).hexdigest()
    idx = int(h, 16) % len(AVATAR_PALETTE)
    return AVATAR_PALETTE[idx]


def _check_active_invite(db: sqlite3.Connection, code: str) -> None:
    row = db.execute(
        "SELECT id FROM invite_codes WHERE code=? AND is_active=1", (code,)
    ).fetchone()
    if row is None:
        raise InvalidInviteCode("invite code not recognized or inactive")


def register(
    db: sqlite3.Connection,
    *,
    username: str,
    password: str,
    invite_code: str,
    email: Optional[str],
) -> int:
    """Register a new bursiyer. Returns new user_id."""
    if len(password) < 8:
        raise InvalidPassword("password must be at least 8 characters")

    _check_active_invite(db, invite_code)

    # Username uniqueness
    if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        raise UsernameTaken(f"username '{username}' already exists")

    if email and db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise EmailTaken(f"email '{email}' already registered")

    now = _now()
    cur = db.execute(
        """
        INSERT INTO users(username, email, password_hash, role, is_active,
                          avatar_color, created_at, updated_at)
        VALUES (?, ?, ?, 'user', 1, ?, ?, ?)
        """,
        (
            username, email,
            auth.hash_password(password),
            _avatar_color_for(username),
            now, now,
        ),
    )
    user_id = cur.lastrowid
    assert user_id is not None  # AUTOINCREMENT

    # Initialize gamification state
    db.execute(
        """
        INSERT INTO gamification_state(user_id, updated_at)
        VALUES (?, ?)
        """,
        (user_id, now),
    )

    return user_id
