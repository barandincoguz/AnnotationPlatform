"""Notifications inbox CRUD.

Public API:
  create(db, *, user_id, kind, title, body=None, data=None) -> int (new id)
  list_for_user(db, *, user_id, unread_only=True, limit=50) -> list[dict]
  mark_read(db, *, notification_id, user_id) -> None
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional


class NotificationNotFound(Exception):
    """Either id doesn't exist or it's not this user's notification."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(
    db: sqlite3.Connection,
    *,
    user_id: int,
    kind: str,
    title: str,
    body: Optional[str] = None,
    data: Optional[dict] = None,
) -> int:
    cur = db.execute(
        """
        INSERT INTO notifications(user_id, kind, title, body, data_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, kind, title, body, json.dumps(data) if data is not None else None, _now()),
    )
    return cur.lastrowid


def list_for_user(
    db: sqlite3.Connection,
    *,
    user_id: int,
    unread_only: bool = True,
    limit: int = 50,
) -> list[dict]:
    if limit > 200:
        limit = 200
    if limit < 1:
        limit = 1
    if unread_only:
        sql = (
            "SELECT id, kind, title, body, data_json, is_read, created_at "
            "FROM notifications WHERE user_id=? AND is_read=0 "
            "ORDER BY id DESC LIMIT ?"
        )
    else:
        sql = (
            "SELECT id, kind, title, body, data_json, is_read, created_at "
            "FROM notifications WHERE user_id=? "
            "ORDER BY id DESC LIMIT ?"
        )
    rows = db.execute(sql, (user_id, limit)).fetchall()
    out: list[dict] = []
    for r in rows:
        out.append({
            "id": r["id"],
            "kind": r["kind"],
            "title": r["title"],
            "body": r["body"],
            "data": json.loads(r["data_json"]) if r["data_json"] else None,
            "is_read": bool(r["is_read"]),
            "created_at": r["created_at"],
        })
    return out


def mark_read(
    db: sqlite3.Connection,
    *,
    notification_id: int,
    user_id: int,
) -> None:
    # Single UPDATE keyed on (id, user_id) replaces the prior
    # SELECT-then-UPDATE: one round-trip instead of two, and the
    # ownership check is enforced by the same statement that performs
    # the write (no TOCTOU window). `rowcount == 0` means either the
    # notification doesn't exist or it belongs to a different user;
    # either way the caller's correct response is NotificationNotFound.
    cur = db.execute(
        "UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",
        (notification_id, user_id),
    )
    if cur.rowcount == 0:
        raise NotificationNotFound(notification_id)


def mark_all_read(db: sqlite3.Connection, *, user_id: int) -> int:
    """Mark every unread notification for this user as read in a single
    atomic UPDATE. Returns the count of rows actually flipped (0 if the
    inbox was already clean). Idempotent.

    Frontend uses this instead of batching N individual POST /read calls
    (Codex BROKEN, Pass 1) — batching is racy and half-success is hard
    to detect from the client.
    """
    cur = db.execute(
        "UPDATE notifications SET is_read=1 "
        "WHERE user_id=? AND is_read=0",
        (user_id,),
    )
    # Connection is opened with isolation_level=None (autocommit), so
    # calling .commit() here was misleading — implied this function
    # owned a transaction it didn't actually have. Drop it.
    return cur.rowcount or 0
