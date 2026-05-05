"""Annotation chain service.

Public API:
  save_annotation(db, document_id, user_id, references) -> dict
  get_annotation(db, document_id) -> Optional[dict]
  get_chain(db, document_id) -> list[dict]
  skip_annotation(db, document_id, user_id) -> None
  set_complete(db, document_id, user_id, completed) -> dict

Each save is atomic:
  1. Validate references (normalize + dedupe)
  2. Compute set-semantic diff vs. previous current state
  3. Append annotation_versions snapshot (with diff_from_previous, is_diff_zero, action)
  4. Upsert annotations CURRENT row (last_editor, edit_count++, unique_users)
  5. Rebuild annotation_references denorm table
  6. Delete the caller's draft
  7. Release the caller's lock if any (no-op if not held)
  8. Log activity_event 'annotation_save'

skip writes only an activity_event + lock release. complete toggle creates a
'complete_mark'/'uncomplete' version and updates the CURRENT row.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.annotations.diff import (
    normalize_references, references_diff, is_diff_zero,
)
from backend.shared import audit


class AnnotationServiceError(Exception):
    """Base."""


class DocumentNotFound(AnnotationServiceError):
    pass


class AnnotationNotFound(AnnotationServiceError):
    """set_complete called on a document with no annotation row yet."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _document_exists(db: sqlite3.Connection, document_id: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM documents_meta WHERE document_id=?", (document_id,)
    ).fetchone()
    return row is not None


def _release_caller_lock(db: sqlite3.Connection, document_id: str, user_id: int) -> None:
    db.execute(
        "DELETE FROM document_locks WHERE document_id=? AND user_id=?",
        (document_id, user_id),
    )


def _delete_caller_draft(db: sqlite3.Connection, document_id: str, user_id: int) -> None:
    db.execute(
        "DELETE FROM drafts WHERE document_id=? AND user_id=?",
        (document_id, user_id),
    )


def _rebuild_denormalized(
    db: sqlite3.Connection, document_id: str, refs: list[dict]
) -> None:
    db.execute(
        "DELETE FROM annotation_references WHERE document_id=?", (document_id,)
    )
    for seq, r in enumerate(refs):
        db.execute(
            """
            INSERT INTO annotation_references(
                document_id, seq, kanun_no, kanun_ad, madde, fikra, bent, source_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id, seq,
                r["kanun_no"], r["kanun_ad"], r["madde"],
                r["fikra"], r["bent"], r["source_text"],
            ),
        )


def _count_unique_users(db: sqlite3.Connection, document_id: str) -> int:
    row = db.execute(
        "SELECT COUNT(DISTINCT user_id) AS c FROM annotation_versions WHERE document_id=?",
        (document_id,),
    ).fetchone()
    return row["c"]


def save_annotation(
    db: sqlite3.Connection,
    *,
    document_id: str,
    user_id: int,
    references: list[dict],
) -> dict:
    """Save reference list, snapshot version, rebuild denorm. Atomic.

    Returns: {is_new, is_diff_zero, current_references}.
    Raises: DocumentNotFound, DuplicateReference, InvalidReference.
    """
    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)

    cleaned = normalize_references(references)

    cur_row = db.execute(
        "SELECT references_json FROM annotations WHERE document_id=?", (document_id,)
    ).fetchone()
    is_new = cur_row is None
    prev = [] if is_new else json.loads(cur_row["references_json"])

    diff = references_diff(prev, cleaned)
    diff_zero = is_diff_zero(diff)
    action = "create" if is_new else "edit"
    now = _now()

    db.execute("BEGIN")
    try:
        db.execute(
            """
            INSERT INTO annotation_versions(
                document_id, user_id, references_json, diff_from_previous,
                is_diff_zero, action, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id, user_id, json.dumps(cleaned),
                json.dumps(diff), 1 if diff_zero else 0, action, now,
            ),
        )

        unique_users = _count_unique_users(db, document_id)
        if is_new:
            db.execute(
                """
                INSERT INTO annotations(
                    document_id, references_json, is_completed,
                    last_editor_user_id, edit_count, unique_users_count,
                    created_at, updated_at
                ) VALUES (?, ?, 0, ?, 1, ?, ?, ?)
                """,
                (document_id, json.dumps(cleaned), user_id, unique_users, now, now),
            )
        else:
            db.execute(
                """
                UPDATE annotations SET
                    references_json=?,
                    last_editor_user_id=?,
                    edit_count=edit_count+1,
                    unique_users_count=?,
                    updated_at=?
                WHERE document_id=?
                """,
                (json.dumps(cleaned), user_id, unique_users, now, document_id),
            )

        _rebuild_denormalized(db, document_id, cleaned)
        _delete_caller_draft(db, document_id, user_id)
        _release_caller_lock(db, document_id, user_id)

        audit.log_activity(
            db, user_id, "annotation_save",
            document_id=document_id,
            extra={
                "action": action,
                "is_diff_zero": diff_zero,
                "ref_count": len(cleaned),
                "added_count": len(diff["added"]),
                "removed_count": len(diff["removed"]),
            },
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    return {
        "is_new": is_new,
        "is_diff_zero": diff_zero,
        "current_references": cleaned,
    }


def get_annotation(db: sqlite3.Connection, document_id: str) -> Optional[dict]:
    row = db.execute(
        "SELECT * FROM annotations WHERE document_id=?", (document_id,)
    ).fetchone()
    if row is None:
        return None
    return {
        "document_id": row["document_id"],
        "references": json.loads(row["references_json"]),
        "is_completed": bool(row["is_completed"]),
        "last_editor_user_id": row["last_editor_user_id"],
        "completed_by_user_id": row["completed_by_user_id"],
        "edit_count": row["edit_count"],
        "unique_users_count": row["unique_users_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_chain(db: sqlite3.Connection, document_id: str) -> list[dict]:
    """Return all versions oldest-first with attribution + diff summary."""
    rows = db.execute(
        """
        SELECT v.id, v.user_id, u.username, v.action, v.diff_from_previous,
               v.is_diff_zero, v.created_at,
               v.references_json
        FROM annotation_versions v
        LEFT JOIN users u ON u.id=v.user_id
        WHERE v.document_id=?
        ORDER BY v.id ASC
        """,
        (document_id,),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        diff_blob = json.loads(r["diff_from_previous"]) if r["diff_from_previous"] else {"added": [], "removed": []}
        refs = json.loads(r["references_json"])
        out.append({
            "version_id": r["id"],
            "user_id": r["user_id"],
            "username": r["username"],
            "action": r["action"],
            "is_diff_zero": bool(r["is_diff_zero"]),
            "ref_count": len(refs),
            "diff_summary": {
                "added_count": len(diff_blob["added"]),
                "removed_count": len(diff_blob["removed"]),
            },
            "created_at": r["created_at"],
        })
    return out


def skip_annotation(
    db: sqlite3.Connection, *, document_id: str, user_id: int
) -> None:
    """Skip = no DB row in annotations; log activity + release lock."""
    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)
    db.execute("BEGIN")
    try:
        _release_caller_lock(db, document_id, user_id)
        audit.log_activity(
            db, user_id, "annotation_skip", document_id=document_id,
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def set_complete(
    db: sqlite3.Connection, *, document_id: str, user_id: int, completed: bool
) -> dict:
    """Toggle is_completed. Writes a 'complete_mark'/'uncomplete' version.

    Raises AnnotationNotFound if no annotation row exists for the document.
    """
    cur = db.execute(
        "SELECT references_json, is_completed FROM annotations WHERE document_id=?",
        (document_id,),
    ).fetchone()
    if cur is None:
        raise AnnotationNotFound(document_id)
    if bool(cur["is_completed"]) == completed:
        # no-op (idempotent toggle)
        return {"is_completed": completed}

    now = _now()
    action = "complete_mark" if completed else "uncomplete"
    db.execute("BEGIN")
    try:
        db.execute(
            """
            INSERT INTO annotation_versions(
                document_id, user_id, references_json, diff_from_previous,
                is_diff_zero, action, created_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                document_id, user_id, cur["references_json"],
                json.dumps({"added": [], "removed": []}),
                action, now,
            ),
        )
        if completed:
            db.execute(
                "UPDATE annotations SET is_completed=1, completed_by_user_id=?, updated_at=? WHERE document_id=?",
                (user_id, now, document_id),
            )
        else:
            db.execute(
                "UPDATE annotations SET is_completed=0, completed_by_user_id=NULL, updated_at=? WHERE document_id=?",
                (now, document_id),
            )
        audit.log_activity(
            db, user_id, action, document_id=document_id,
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return {"is_completed": completed}
