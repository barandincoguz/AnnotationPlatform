"""User service: register, login, logout, admin operations.

Custom exceptions are caught by route handlers and mapped to HTTP errors.
"""
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend import config
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


def _parse_utc(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
    """Register a new bursiyer. Returns new user_id.

    Both inserts run inside BEGIN IMMEDIATE / COMMIT so a mid-sequence
    failure cannot orphan a user row without its gamification state.
    The uniqueness pre-checks happen inside the same transaction; an
    `sqlite3.IntegrityError` from a concurrent registration of the same
    username/email is translated to UsernameTaken/EmailTaken (HTTP 409)
    rather than leaking as a 500.

    Invite check ordering: the invite is checked AFTER username/email
    uniqueness so an attacker pairing a guessed invite code with a
    known-taken username always receives 409, never 403. Probing the
    invite still requires a fresh free username, raising the friction
    versus the prior 403/409 oracle.
    """
    if len(password) < 8:
        raise InvalidPassword("password must be at least 8 characters")

    now = _now()
    pw_hash = auth.hash_password(password)
    avatar = _avatar_color_for(username)

    db.execute("BEGIN IMMEDIATE")
    try:
        if db.execute(
            "SELECT 1 FROM users WHERE username=?", (username,)
        ).fetchone():
            raise UsernameTaken(f"username '{username}' already exists")

        if email and db.execute(
            "SELECT 1 FROM users WHERE email=?", (email,)
        ).fetchone():
            raise EmailTaken(f"email '{email}' already registered")

        # Invite check is the last gate so 403 only escapes for a
        # FREE username; combined with any taken-name probe the
        # response collapses to 409 regardless of invite validity.
        _check_active_invite(db, invite_code)

        cur = db.execute(
            """
            INSERT INTO users(username, email, password_hash, role, is_active,
                              avatar_color, created_at, updated_at)
            VALUES (?, ?, ?, 'user', 1, ?, ?, ?)
            """,
            (username, email, pw_hash, avatar, now, now),
        )
        user_id = cur.lastrowid
        assert user_id is not None  # AUTOINCREMENT

        # Initialize gamification state (same transaction so a failure
        # here aborts the whole register flow, no orphan user rows).
        db.execute(
            """
            INSERT INTO gamification_state(user_id, updated_at)
            VALUES (?, ?)
            """,
            (user_id, now),
        )
        db.execute("COMMIT")
    except sqlite3.IntegrityError as exc:
        db.execute("ROLLBACK")
        # UNIQUE collision raced past our SELECTs above. Translate to
        # the same domain exceptions so the route still returns 409,
        # not 500.
        msg = str(exc).lower()
        if "users.username" in msg or "users_username" in msg:
            raise UsernameTaken(f"username '{username}' already exists") from exc
        if "users.email" in msg or "users_email" in msg:
            raise EmailTaken(f"email '{email}' already registered") from exc
        raise
    except Exception:
        db.execute("ROLLBACK")
        raise

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
            user["id"], auth.hash_session_token(token),
            auth.hash_ip(ip) if ip else None,
            user_agent,
            now, now,
        ),
    )
    return token


def logout(
    db: sqlite3.Connection, *, session_token: str
) -> tuple[Optional[int], list[str]]:
    """End one session and atomically release that user's current locks."""
    token_hash = auth.hash_session_token(session_token)
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute(
            "SELECT user_id FROM user_sessions "
            "WHERE session_token=? AND ended_at IS NULL",
            (token_hash,),
        ).fetchone()
        if row is None:
            db.execute("COMMIT")
            return None, []

        user_id = int(row["user_id"])
        released_document_ids = [
            str(lock["document_id"])
            for lock in db.execute(
                "SELECT document_id FROM document_locks WHERE user_id=?",
                (user_id,),
            ).fetchall()
        ]
        now = _now()
        db.execute(
            "UPDATE user_sessions SET ended_at=? "
            "WHERE session_token=? AND ended_at IS NULL",
            (now, token_hash),
        )
        db.execute(
            "DELETE FROM document_locks WHERE user_id=?",
            (user_id,),
        )
        db.execute("COMMIT")
        return user_id, released_document_ids
    except Exception:
        db.execute("ROLLBACK")
        raise


def get_user_by_session(
    db: sqlite3.Connection, *, session_token: str
) -> Optional[sqlite3.Row]:
    """Return user row if session is active, else None.

    Also updates last_activity_at as side effect (sliding window).
    """
    row = db.execute(
        """
        SELECT u.*, s.id AS session_id, s.started_at AS session_started_at
        FROM user_sessions s JOIN users u ON s.user_id = u.id
        WHERE s.session_token = ?
          AND s.ended_at IS NULL
          AND u.is_active = 1
        """,
        (auth.hash_session_token(session_token),),
    ).fetchone()
    if row is None:
        return None
    started_at = _parse_utc(row["session_started_at"])
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=config.SESSION_MAX_AGE_SECONDS
    )
    if started_at is None or started_at <= cutoff:
        db.execute(
            "UPDATE user_sessions SET ended_at=? "
            "WHERE id=? AND ended_at IS NULL",
            (_now(), row["session_id"]),
        )
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
    # Last-admin guardrail: re-check INSIDE the write lock so two concurrent
    # demotions of different admins cannot both pass when exactly two remain.
    db.execute("BEGIN IMMEDIATE")
    try:
        if count_active_admins(db) <= 1:
            db.execute("ROLLBACK")
            raise LastAdminCannotBeRemoved("cannot demote the last active admin")
        db.execute(
            "UPDATE users SET role='user', updated_at=? WHERE id=?",
            (_now(), target_user_id),
        )
        db.execute("COMMIT")
    except Exception:
        try:
            db.execute("ROLLBACK")
        except Exception:
            pass
        raise
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="demote_admin",
        target_kind="user", target_id=str(target_user_id),
        trace_id=trace_id,
    )


def disable_user(
    db: sqlite3.Connection, *, admin_user_id: int, target_user_id: int,
    trace_id: Optional[str] = None,
) -> list[str]:
    _ensure_admin(db, admin_user_id)
    target = db.execute(
        "SELECT * FROM users WHERE id=?", (target_user_id,)
    ).fetchone()
    if target is None:
        raise UserNotFound(f"user {target_user_id} not found")
    # Last-admin guardrail: re-check INSIDE the write lock so two concurrent
    # disable calls on different admins cannot both pass when exactly two remain.
    db.execute("BEGIN IMMEDIATE")
    try:
        if target["role"] == "admin" and count_active_admins(db) <= 1:
            db.execute("ROLLBACK")
            raise LastAdminCannotBeRemoved("cannot disable the last active admin")
        db.execute(
            "UPDATE users SET is_active=0, updated_at=? WHERE id=?",
            (_now(), target_user_id),
        )
        released_document_ids = [
            str(lock["document_id"])
            for lock in db.execute(
                "SELECT document_id FROM document_locks WHERE user_id=?",
                (target_user_id,),
            ).fetchall()
        ]
        now = _now()
        db.execute(
            "UPDATE user_sessions SET ended_at=? "
            "WHERE user_id=? AND ended_at IS NULL",
            (now, target_user_id),
        )
        db.execute(
            "DELETE FROM document_locks WHERE user_id=?",
            (target_user_id,),
        )
        db.execute("COMMIT")
    except Exception:
        try:
            db.execute("ROLLBACK")
        except Exception:
            pass
        raise
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="disable_user",
        target_kind="user", target_id=str(target_user_id),
        trace_id=trace_id,
    )
    return released_document_ids


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
    # Deactivate-all and insert-new run inside one BEGIN IMMEDIATE so a
    # concurrent registration request cannot land in the gap between the two
    # statements and see zero active codes.
    db.execute("BEGIN IMMEDIATE")
    try:
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
        db.execute("COMMIT")
    except Exception:
        try:
            db.execute("ROLLBACK")
        except Exception:
            pass
        raise
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="rotate_invite_code",
        target_kind="invite", target_id=new_code,
        trace_id=trace_id,
    )
    return new_code


def seed_bootstrap_admin(
    db: sqlite3.Connection,
    *,
    username: str,
    password: str,
) -> None:
    """Idempotent first-admin seed for production bootstrap.

    Triggered by lifespan after migrations. Behaviour:
      - Skip silently if either username or password is empty.
      - Skip silently if any active admin already exists.
      - Raise RuntimeError if username collides with an existing non-admin.
      - Otherwise: insert admin user (training+manual flags pre-set),
        log to admin_audit_log, print one stderr line.

    Atomicity: all three INSERTs (users + gamification_state +
    admin_audit_log) run inside BEGIN IMMEDIATE / COMMIT so a
    mid-sequence failure cannot orphan an admin row without a
    gamification state or audit entry.

    TOCTOU safety: the no-admin check is re-run inside the write lock
    so two containers booting against the same volume cannot both pass
    the pre-check and then race to INSERT.  The loser catches
    sqlite3.IntegrityError and returns without re-raising.
    """
    import sys
    if not username or not password:
        return

    # Check if a user with this username already exists
    existing = db.execute(
        "SELECT id, role, password_hash, is_active FROM users WHERE username=?", (username,)
    ).fetchone()

    if existing is not None:
        if existing["role"] != "admin":
            raise RuntimeError(
                f"BOOTSTRAP_ADMIN_USERNAME={username!r} conflicts with "
                f"existing non-admin user"
            )
        
        # It is an admin. Check if we need to update password hash or activation status.
        from backend.shared import auth as auth_mod
        if auth_mod.verify_password(password, existing["password_hash"]) and existing["is_active"] == 1:
            # Already active and password matches. Idempotent early exit.
            return

        new_hash = auth_mod.hash_password(password)
        trace_id = audit.gen_trace_id()
        now = _now()

        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute(
                "UPDATE users SET password_hash=?, is_active=1, updated_at=? WHERE id=?",
                (new_hash, now, existing["id"]),
            )
            audit.log_admin_action(
                db,
                admin_user_id=existing["id"],
                action_type="bootstrap_admin_update",
                target_kind="user",
                target_id=str(existing["id"]),
                metadata={"source": "lifespan_update"},
                trace_id=trace_id,
            )
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise

        print(
            f"Bootstrap admin {username!r} password/status updated (trace_id={trace_id})",
            file=sys.stderr,
        )
        return

    # No user with this username exists. Proceed with original logic.
    # Cheap pre-check: if any other active admin exists, skip seeding new one.
    if db.execute(
        "SELECT 1 FROM users WHERE role='admin' AND is_active=1 LIMIT 1"
    ).fetchone() is not None:
        return

    trace_id = audit.gen_trace_id()
    now = _now()

    db.execute("BEGIN IMMEDIATE")
    try:
        # Re-check under write lock — defeats TOCTOU race between containers.
        if db.execute(
            "SELECT 1 FROM users WHERE role='admin' AND is_active=1 LIMIT 1"
        ).fetchone() is not None:
            db.execute("ROLLBACK")
            return

        cur = db.execute(
            """
            INSERT INTO users(
                username, email, password_hash, role, is_active,
                has_seen_manual, has_passed_training,
                avatar_color, created_at, updated_at
            )
            VALUES (?, NULL, ?, 'admin', 1, 1, 1, ?, ?, ?)
            """,
            (
                username,
                auth.hash_password(password),
                _avatar_color_for(username),
                now, now,
            ),
        )
        user_id = cur.lastrowid
        assert user_id is not None

        db.execute(
            """
            INSERT INTO gamification_state(user_id, updated_at)
            VALUES (?, ?)
            """,
            (user_id, now),
        )

        audit.log_admin_action(
            db,
            admin_user_id=user_id,
            action_type="bootstrap_admin_seed",
            target_kind="user",
            target_id=str(user_id),
            metadata={"source": "lifespan"},
            trace_id=trace_id,
        )

        db.execute("COMMIT")
    except sqlite3.IntegrityError:
        db.execute("ROLLBACK")
        print(
            f"Bootstrap admin {username!r} race lost — "
            f"another instance created it; continuing",
            file=sys.stderr,
        )
        return
    except Exception:
        db.execute("ROLLBACK")
        raise

    print(
        f"Bootstrap admin {username!r} created (id={user_id}, trace_id={trace_id})",
        file=sys.stderr,
    )
