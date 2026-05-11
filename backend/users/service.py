"""User service: register, login, logout, admin operations.

Custom exceptions are caught by route handlers and mapped to HTTP errors.
"""
import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.shared import auth, audit


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


def login(
    db: sqlite3.Connection,
    *,
    username: str,
    password: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """Verify credentials and create a session. Returns session token."""
    user = db.execute(
        "SELECT * FROM users WHERE username=?", (username,)
    ).fetchone()
    if user is None:
        raise InvalidCredentials("invalid username or password")
    if not auth.verify_password(password, user["password_hash"]):
        raise InvalidCredentials("invalid username or password")
    if user["is_active"] != 1:
        raise UserDisabled("user account is disabled")

    token = auth.generate_session_token()
    now = _now()
    db.execute(
        """
        INSERT INTO user_sessions(
            user_id, session_token, ip_hash, user_agent,
            started_at, last_activity_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"], token,
            auth.hash_ip(ip) if ip else None,
            user_agent,
            now, now,
        ),
    )
    return token


def logout(db: sqlite3.Connection, *, session_token: str) -> None:
    db.execute(
        "UPDATE user_sessions SET ended_at=? WHERE session_token=? AND ended_at IS NULL",
        (_now(), session_token),
    )


def get_user_by_session(
    db: sqlite3.Connection, *, session_token: str
) -> Optional[sqlite3.Row]:
    """Return user row if session is active, else None.

    Also updates last_activity_at as side effect (sliding window).
    """
    row = db.execute(
        """
        SELECT u.*, s.id AS session_id
        FROM user_sessions s JOIN users u ON s.user_id = u.id
        WHERE s.session_token = ?
          AND s.ended_at IS NULL
          AND u.is_active = 1
        """,
        (session_token,),
    ).fetchone()
    if row is None:
        return None
    db.execute(
        "UPDATE user_sessions SET last_activity_at=? WHERE id=?",
        (_now(), row["session_id"]),
    )
    return row


def count_active_admins(db: sqlite3.Connection) -> int:
    return db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE role='admin' AND is_active=1"
    ).fetchone()["c"]


def _ensure_admin(db: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if user is None or user["role"] != "admin" or user["is_active"] != 1:
        raise NotAdmin(f"user {user_id} is not an active admin")
    return user


def promote_admin(
    db: sqlite3.Connection, *, admin_user_id: int, target_user_id: int,
    trace_id: Optional[str] = None,
) -> None:
    _ensure_admin(db, admin_user_id)
    target = db.execute(
        "SELECT * FROM users WHERE id=?", (target_user_id,)
    ).fetchone()
    if target is None:
        raise UserNotFound(f"user {target_user_id} not found")
    db.execute(
        "UPDATE users SET role='admin', updated_at=? WHERE id=?",
        (_now(), target_user_id),
    )
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="promote_admin",
        target_kind="user", target_id=str(target_user_id),
        trace_id=trace_id,
    )


def demote_admin(
    db: sqlite3.Connection, *, admin_user_id: int, target_user_id: int,
    trace_id: Optional[str] = None,
) -> None:
    _ensure_admin(db, admin_user_id)
    target = db.execute(
        "SELECT * FROM users WHERE id=?", (target_user_id,)
    ).fetchone()
    if target is None or target["role"] != "admin":
        raise UserNotFound(f"user {target_user_id} is not an admin")
    # Last-admin guardrail
    if count_active_admins(db) <= 1:
        raise LastAdminCannotBeRemoved("cannot demote the last active admin")
    db.execute(
        "UPDATE users SET role='user', updated_at=? WHERE id=?",
        (_now(), target_user_id),
    )
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="demote_admin",
        target_kind="user", target_id=str(target_user_id),
        trace_id=trace_id,
    )


def disable_user(
    db: sqlite3.Connection, *, admin_user_id: int, target_user_id: int,
    trace_id: Optional[str] = None,
) -> None:
    _ensure_admin(db, admin_user_id)
    target = db.execute(
        "SELECT * FROM users WHERE id=?", (target_user_id,)
    ).fetchone()
    if target is None:
        raise UserNotFound(f"user {target_user_id} not found")
    if target["role"] == "admin" and count_active_admins(db) <= 1:
        raise LastAdminCannotBeRemoved("cannot disable the last active admin")
    db.execute(
        "UPDATE users SET is_active=0, updated_at=? WHERE id=?",
        (_now(), target_user_id),
    )
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="disable_user",
        target_kind="user", target_id=str(target_user_id),
        trace_id=trace_id,
    )


def enable_user(
    db: sqlite3.Connection, *, admin_user_id: int, target_user_id: int,
    trace_id: Optional[str] = None,
) -> None:
    _ensure_admin(db, admin_user_id)
    target = db.execute(
        "SELECT id FROM users WHERE id=?", (target_user_id,)
    ).fetchone()
    if target is None:
        raise UserNotFound(f"user {target_user_id} not found")
    db.execute(
        "UPDATE users SET is_active=1, updated_at=? WHERE id=?",
        (_now(), target_user_id),
    )
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="enable_user",
        target_kind="user", target_id=str(target_user_id),
        trace_id=trace_id,
    )


def rotate_invite_code(
    db: sqlite3.Connection, *, admin_user_id: int, new_code: str,
    trace_id: Optional[str] = None,
) -> str:
    _ensure_admin(db, admin_user_id)
    now = _now()
    db.execute(
        "UPDATE invite_codes SET is_active=0, rotated_at=? WHERE is_active=1",
        (now,),
    )
    db.execute(
        """
        INSERT INTO invite_codes(code, is_active, created_by_admin_id, created_at)
        VALUES (?, 1, ?, ?)
        """,
        (new_code, admin_user_id, now),
    )
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="rotate_invite_code",
        target_kind="invite", target_id=new_code,
        trace_id=trace_id,
    )
    return new_code
