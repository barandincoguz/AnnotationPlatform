"""Feedback service — submit and list user feedback."""
import sqlite3
from typing import Literal, Optional

FeedbackType = Literal["complaint", "suggestion"]


def submit_feedback(
    db: sqlite3.Connection,
    *,
    user_id: int,
    type: FeedbackType,
    message: str,
) -> int:
    """Insert feedback row. Returns the new row id."""
    cur = db.execute(
        """
        INSERT INTO user_feedback(user_id, type, message, created_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (user_id, type, message),
    )
    return int(cur.lastrowid)


def list_feedback(
    db: sqlite3.Connection,
    *,
    type_filter: Optional[FeedbackType] = None,
) -> list[dict]:
    """Return feedback rows with username, optionally filtered by type."""
    if type_filter:
        rows = db.execute(
            """
            SELECT uf.id, uf.user_id, u.username, uf.type, uf.message, uf.created_at
            FROM user_feedback uf
            JOIN users u ON u.id = uf.user_id
            WHERE uf.type = ?
            ORDER BY uf.created_at DESC
            """,
            (type_filter,),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT uf.id, uf.user_id, u.username, uf.type, uf.message, uf.created_at
            FROM user_feedback uf
            JOIN users u ON u.id = uf.user_id
            ORDER BY uf.created_at DESC
            """,
        ).fetchall()
    return [dict(r) for r in rows]
