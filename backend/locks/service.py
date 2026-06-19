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
    """Read current lock state for a document, removing it if expired.

    Expiry cleanup is a conditional DELETE rather than SELECT-then-DELETE.
    A concurrent heartbeat that has already extended the row therefore cannot
    be erased by a stale expiry observation.
    """
    now_iso = _now().isoformat()
    db.execute(
        "DELETE FROM document_locks "
        "WHERE document_id=? AND expires_at < ?",
        (document_id, now_iso),
    )
    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    return None if row is None else _row_to_info(row, db)


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
    """Create or refresh a lock. Raises LockHeldByOther if another user holds it.

    B2 fix: the read-then-write is wrapped in BEGIN IMMEDIATE so two
    concurrent callers serialize at the SQLite RESERVED lock.  The
    connection is opened with isolation_level=None (autocommit off, manual
    BEGIN), so BEGIN IMMEDIATE is the correct pattern here.
    The 5-second busy_timeout set in db.connect() lets the second thread
    retry instead of failing immediately with OperationalError.
    """
    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)

    cursor = db.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")

        existing = get_lock(db, document_id)
        if existing is not None and existing["user_id"] != user_id:
            db.rollback()
            raise LockHeldByOther(existing)

        now = _now()
        expires = now + timedelta(seconds=_expires_seconds(db))
        cursor.execute(
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
        db.commit()
    except Exception:
        db.rollback()
        raise

    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    return _row_to_info(row, db)


def heartbeat(db: sqlite3.Connection, *, document_id: str, user_id: int) -> dict:
    """Bump expires_at. Raises NotLockHolder if user doesn't hold the lock.

    BE-1 fix: the SELECT-then-UPDATE is wrapped in BEGIN IMMEDIATE so a
    concurrent acquire() on another connection cannot swap the owner between
    the read and the write.  Ownership is re-verified inside the transaction
    after acquiring the RESERVED lock.
    """
    cursor = db.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")

        row = db.execute(
            "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
        ).fetchone()
        # No expires_at check: original holder may refresh during the 0–60s
        # gap before the next sweep. Tradeoff for user-friendliness.
        if row is None or row["user_id"] != user_id:
            db.rollback()
            raise NotLockHolder(document_id)

        now = _now()
        expires = now + timedelta(seconds=_expires_seconds(db))
        cursor.execute(
            "UPDATE document_locks SET last_heartbeat=?, expires_at=? WHERE document_id=?",
            (now.isoformat(), expires.isoformat(), document_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    return _row_to_info(row, db)


def release(db: sqlite3.Connection, *, document_id: str, user_id: int) -> None:
    """Drop the caller's lock atomically.

    No-op if no lock exists; raises NotLockHolder if another user owns it.
    The owner check and delete share a write transaction so an expired lock
    cannot be replaced by another user between the two statements and then
    accidentally deleted by the stale releaser.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute(
            "SELECT user_id FROM document_locks WHERE document_id=?",
            (document_id,),
        ).fetchone()
        if row is None:
            db.execute("COMMIT")
            return
        if row["user_id"] != user_id:
            raise NotLockHolder(document_id)
        db.execute(
            "DELETE FROM document_locks WHERE document_id=? AND user_id=?",
            (document_id, user_id),
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def force_release(db: sqlite3.Connection, *, document_id: str) -> None:
    """Admin override; unconditional delete."""
    db.execute("DELETE FROM document_locks WHERE document_id=?", (document_id,))


def sweep_expired(db: sqlite3.Connection) -> list[str]:
    """Delete expired locks; return released document_ids.

    BE-2 fix: the SELECT-then-DELETE is wrapped in BEGIN IMMEDIATE so a
    heartbeat() on a concurrent connection cannot observe a lock between the
    sweep's SELECT (which marks it for deletion) and the DELETE itself.
    Both statements see the same snapshot and execute atomically.
    """
    now_iso = _now().isoformat()
    cursor = db.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        rows = db.execute(
            "SELECT document_id FROM document_locks WHERE expires_at < ?", (now_iso,),
        ).fetchall()
        released = [r["document_id"] for r in rows]
        if released:
            db.execute("DELETE FROM document_locks WHERE expires_at < ?", (now_iso,))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return released
