"""Document lock service — heartbeat-based exclusive editing.

Lifecycle:
  acquire    → creates a row (or refreshes if same user holds it)
  heartbeat  → bumps expires_at by lock.expires_seconds
  release    → deletes the row (idempotent; raises if held by another user)
  sweep_expired → background job: deletes rows where expires_at < now

Settings (admin-tunable via site_settings):
  lock.expires_seconds        default 300 (5 minutes)
  lock.heartbeat_interval_seconds default 30 (frontend uses this)
"""
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

from backend.shared import settings


DEFAULT_LOCK_EXPIRES_SECONDS = 300


class LockServiceError(Exception):
    pass


class DocumentNotFound(LockServiceError):
    pass


class NotLockHolder(LockServiceError):
    """Caller does not currently hold the lock (or no lock exists)."""


class LockHeldByOther(LockServiceError):
    """Lock exists and is held by another user."""

    def __init__(self, info: dict):
        super().__init__(f"locked by {info.get('by_username')!r}")
        self.info = info


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _document_exists(db: sqlite3.Connection, document_id: str) -> bool:
    return db.execute(
        "SELECT 1 FROM documents_meta WHERE document_id=?", (document_id,)
    ).fetchone() is not None


def _expires_seconds(db: sqlite3.Connection) -> int:
    return settings.get_int(db, "lock.expires_seconds", DEFAULT_LOCK_EXPIRES_SECONDS)


def _row_to_info(row: sqlite3.Row, db: sqlite3.Connection) -> dict:
    user = db.execute(
        "SELECT username FROM users WHERE id=?", (row["user_id"],)
    ).fetchone()
    return {
        "document_id": row["document_id"],
        "user_id": row["user_id"],
        "by_user_id": row["user_id"],
        "by_username": user["username"] if user else None,
        "acquired_at": row["acquired_at"],
        "last_heartbeat": row["last_heartbeat"],
        "expires_at": row["expires_at"],
    }


def get_lock(db: sqlite3.Connection, document_id: str) -> Optional[dict]:
    """Read current lock state for a document. Sweeps if expired."""
    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    if row is None:
        return None
    if row["expires_at"] < _now().isoformat():
        db.execute("DELETE FROM document_locks WHERE document_id=?", (document_id,))
        return None
    return _row_to_info(row, db)


def release_if_held(
    db: sqlite3.Connection, *, document_id: str, user_id: int
) -> None:
    """Release the user's lock on a document if they hold it. Silent otherwise.

    Used by services that want to auto-release a lock at the end of a
    related operation (e.g. save_annotation, set_complete) — never raises.
    Distinct from release(), which raises NotLockHolder if the lock is
    held by someone else.
    """
    db.execute(
        "DELETE FROM document_locks WHERE document_id=? AND user_id=?",
        (document_id, user_id),
    )


def acquire(db: sqlite3.Connection, *, document_id: str, user_id: int) -> dict:
    """Create or refresh a lock. Raises LockHeldByOther if another user holds it."""
    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)

    existing = get_lock(db, document_id)
    if existing is not None and existing["user_id"] != user_id:
        raise LockHeldByOther(existing)

    now = _now()
    expires = now + timedelta(seconds=_expires_seconds(db))
    db.execute(
        """
        INSERT INTO document_locks(document_id, user_id, acquired_at, last_heartbeat, expires_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(document_id) DO UPDATE SET
            user_id=excluded.user_id,
            last_heartbeat=excluded.last_heartbeat,
            expires_at=excluded.expires_at
        """,
        (document_id, user_id, now.isoformat(), now.isoformat(), expires.isoformat()),
    )
    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    return _row_to_info(row, db)


def heartbeat(db: sqlite3.Connection, *, document_id: str, user_id: int) -> dict:
    """Bump expires_at. Raises NotLockHolder if user doesn't hold the lock."""
    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    # No expires_at check: original holder may refresh during the 0–60s
    # gap before the next sweep. Tradeoff for user-friendliness.
    if row is None or row["user_id"] != user_id:
        raise NotLockHolder(document_id)

    now = _now()
    expires = now + timedelta(seconds=_expires_seconds(db))
    db.execute(
        "UPDATE document_locks SET last_heartbeat=?, expires_at=? WHERE document_id=?",
        (now.isoformat(), expires.isoformat(), document_id),
    )
    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    return _row_to_info(row, db)


def release(db: sqlite3.Connection, *, document_id: str, user_id: int) -> None:
    """Drop lock. No-op if no lock; raises NotLockHolder if held by another user."""
    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    if row is None:
        return  # already released — silent
    if row["user_id"] != user_id:
        raise NotLockHolder(document_id)
    db.execute("DELETE FROM document_locks WHERE document_id=?", (document_id,))


def force_release(db: sqlite3.Connection, *, document_id: str) -> None:
    """Admin override; unconditional delete."""
    db.execute("DELETE FROM document_locks WHERE document_id=?", (document_id,))


def sweep_expired(db: sqlite3.Connection) -> list[str]:
    """Delete expired locks; return released document_ids."""
    now_iso = _now().isoformat()
    rows = db.execute(
        "SELECT document_id FROM document_locks WHERE expires_at < ?", (now_iso,),
    ).fetchall()
    released = [r["document_id"] for r in rows]
    if released:
        db.execute("DELETE FROM document_locks WHERE expires_at < ?", (now_iso,))
    return released
