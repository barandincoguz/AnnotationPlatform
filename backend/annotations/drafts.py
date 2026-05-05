"""Per-user draft (WIP) reference list service.

Drafts are write-through: PUT replaces the row. They store raw payload (no
strict validation) — frontend may save incomplete rows during typing. The
moment the user hits Save, the matching annotation service.save_annotation()
call deletes the draft as part of its atomic transaction.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional


class DraftServiceError(Exception):
    pass


class DocumentNotFound(DraftServiceError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _document_exists(db: sqlite3.Connection, document_id: str) -> bool:
    return db.execute(
        "SELECT 1 FROM documents_meta WHERE document_id=?", (document_id,)
    ).fetchone() is not None


def set_draft(
    db: sqlite3.Connection,
    *,
    document_id: str,
    user_id: int,
    references: list[dict],
) -> None:
    """Upsert draft. Stores raw references payload (no validation)."""
    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)
    db.execute(
        """
        INSERT INTO drafts(document_id, user_id, references_json, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(document_id, user_id) DO UPDATE SET
            references_json=excluded.references_json,
            updated_at=excluded.updated_at
        """,
        (document_id, user_id, json.dumps(references), _now()),
    )


def get_draft(
    db: sqlite3.Connection, *, document_id: str, user_id: int
) -> Optional[dict]:
    row = db.execute(
        "SELECT * FROM drafts WHERE document_id=? AND user_id=?",
        (document_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return {
        "document_id": row["document_id"],
        "references": json.loads(row["references_json"]),
        "updated_at": row["updated_at"],
    }


def clear_draft(
    db: sqlite3.Connection, *, document_id: str, user_id: int
) -> None:
    """Idempotent — no error if draft absent."""
    db.execute(
        "DELETE FROM drafts WHERE document_id=? AND user_id=?",
        (document_id, user_id),
    )
