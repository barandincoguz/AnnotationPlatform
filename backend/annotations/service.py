"""Annotation chain service.

Public API:
  save_annotation(db, document_id, user_id, references) -> dict
  get_annotation(db, document_id) -> Optional[dict]
  get_chain(db, document_id) -> list[dict]
  skip_annotation(db, document_id, user_id) -> None
  set_complete(db, document_id, user_id, completed, references=None) -> dict

Each save is atomic:
  1. Validate references (normalize + dedupe)
  2. Compute set-semantic diff vs. previous current state
  3. Append annotation_versions snapshot (with diff_from_previous, is_diff_zero, action)
  4. Upsert annotations CURRENT row (last_editor, edit_count++, unique_users)
  5. Rebuild annotation_references denorm table
  6. Delete the caller's draft
  7. Release the caller's lock if any (no-op if not held)
  8. Log activity_event 'annotation_save'

skip writes only an activity_event + lock release + caller-draft delete.
complete toggle creates a 'complete_mark'/'uncomplete' version and updates
the CURRENT row. When `references` is supplied alongside `completed=True`,
set_complete runs the full save pipeline AND flips the flag inside a single
BEGIN IMMEDIATE — collapses the frontend's save→complete→delete_draft chain.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.annotations.diff import (
    normalize_references, references_diff, is_diff_zero,
)
from backend.locks import service as locks_service
from backend.shared import audit


class AnnotationServiceError(Exception):
    """Base."""


class DocumentNotFound(AnnotationServiceError):
    pass


class AnnotationNotFound(AnnotationServiceError):
    """set_complete called on a document with no annotation row yet."""


class LockOwnedByOther(AnnotationServiceError):
    """An active lock exists on the document and is held by a different user.

    Raised by save_annotation and set_complete when a caller attempts to
    write to a document locked by someone else.  The route handler maps
    this to HTTP 409 lock_owned_by_other.
    """

    def __init__(self, document_id: str):
        super().__init__(f"document {document_id!r} is locked by another user")
        self.document_id = document_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _document_exists(db: sqlite3.Connection, document_id: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM documents_meta WHERE document_id=?", (document_id,)
    ).fetchone()
    return row is not None


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


def _apply_save_inside_txn(
    db: sqlite3.Connection,
    *,
    document_id: str,
    user_id: int,
    references: list[dict],
    now: str,
    action_override: Optional[str] = None,
) -> dict:
    """Persist references + write a version row + rebuild denorm + clear
    caller's draft. Caller MUST have already executed BEGIN IMMEDIATE on
    `db`. This helper performs NO transaction control of its own.

    `action_override` lets set_complete tag the version as 'complete_mark'
    instead of 'create'/'edit' when refs are saved as part of completing.
    Otherwise the action is derived from the upsert path.

    Returns a dict the caller uses to build audit extras:
        {is_new, is_diff_zero, cleaned, diff, action}
    """
    cleaned = normalize_references(references)

    cur_row = db.execute(
        "SELECT references_json FROM annotations WHERE document_id=?",
        (document_id,),
    ).fetchone()
    is_new = cur_row is None
    prev = [] if is_new else json.loads(cur_row["references_json"])

    diff = references_diff(prev, cleaned)
    diff_zero = is_diff_zero(diff)
    action = action_override or ("create" if is_new else "edit")

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

    return {
        "is_new": is_new,
        "is_diff_zero": diff_zero,
        "cleaned": cleaned,
        "diff": diff,
        "action": action,
    }


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

    # B1: Reject writes when an active lock is held by a *different* user.
    # get_lock() already sweeps expired rows and returns None for them, so
    # this check only fires when the lock is genuinely active and foreign.
    _active = locks_service.get_lock(db, document_id)
    if _active is not None and _active["user_id"] != user_id:
        raise LockOwnedByOther(document_id)

    now = _now()

    # Read the prior state INSIDE the same write transaction as the
    # INSERT/UPDATE below. Otherwise two concurrent saves both read
    # references_json=<old>, both compute their diff against the same
    # baseline, and the second UPDATE silently overwrites the first
    # (lost-update race; the version chain ends up with a wrong
    # diff_from_previous on the loser). BEGIN IMMEDIATE serializes the
    # writers; SQLite's default journal_mode keeps the lock until COMMIT
    # so the read sees the latest committed value.
    db.execute("BEGIN IMMEDIATE")
    try:
        result = _apply_save_inside_txn(
            db,
            document_id=document_id,
            user_id=user_id,
            references=references,
            now=now,
        )
        locks_service.release_if_held(db, document_id=document_id, user_id=user_id)
        audit.log_activity(
            db, user_id, "annotation_save",
            document_id=document_id,
            extra={
                "action": result["action"],
                "is_diff_zero": result["is_diff_zero"],
                "ref_count": len(result["cleaned"]),
                "added_count": len(result["diff"]["added"]),
                "removed_count": len(result["diff"]["removed"]),
            },
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    return {
        "is_new": result["is_new"],
        "is_diff_zero": result["is_diff_zero"],
        "current_references": result["cleaned"],
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
    """Skip = no DB row in annotations; clear the caller's draft, release
    their lock, and log the skip event — all atomic.

    Pre-Phase-2 the draft was left behind, which let a skipped doc still
    surface in the caller's Devam Eden tab (any non-empty draft puts the
    doc there). Skipping is a "drop this work" signal: matching the
    intent requires removing the draft alongside lock release.
    """
    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)
    db.execute("BEGIN")
    try:
        _delete_caller_draft(db, document_id, user_id)
        locks_service.release_if_held(db, document_id=document_id, user_id=user_id)
        audit.log_activity(
            db, user_id, "annotation_skip", document_id=document_id,
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def set_complete(
    db: sqlite3.Connection,
    *,
    document_id: str,
    user_id: int,
    completed: bool,
    references: Optional[list[dict]] = None,
) -> dict:
    """Toggle is_completed. Writes a 'complete_mark'/'uncomplete' version.

    When `references` is supplied with `completed=True`, runs the full
    save pipeline (refs persist + version row + denorm rebuild + draft
    cleanup) AND flips the flag inside a single BEGIN IMMEDIATE. Callers
    get atomicity for the user action "commit my current refs as
    complete" — frontend's pre-Phase-2 chain (save → complete →
    delete_draft) becomes one round-trip.

    Contract guards (defense in depth — CompleteRequest's model_validator
    catches these at the HTTP boundary, but the service is callable
    directly from tests + internal code):
      * completed=False with references is rejected (ValueError).
      * Legacy path (references=None) requires an existing annotation
        row; AnnotationNotFound otherwise.
      * Atomic path tolerates a missing annotation row — the embedded
        save creates it before the flag flip.

    Raises AnnotationNotFound, DocumentNotFound, LockOwnedByOther.
    """
    # Defense in depth (model_validator should have caught this).
    if not completed and references is not None:
        raise ValueError("references only allowed when completed=true")

    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)

    # Pre-txn idempotence shortcut: pure flag toggle to the same state
    # with no refs to save → no-op without entering BEGIN IMMEDIATE.
    # Mirrors the legacy fast path so concurrent same-state pokes don't
    # pile up empty transactions on the write lock.
    cur_pre = db.execute(
        "SELECT is_completed FROM annotations WHERE document_id=?",
        (document_id,),
    ).fetchone()
    if references is None and cur_pre is None:
        raise AnnotationNotFound(document_id)
    if references is None and bool(cur_pre["is_completed"]) == completed:
        return {"is_completed": completed}

    # B1: Same ownership guard as save_annotation — reject if a different
    # user currently holds the lock. (Pre-txn check; final safety comes
    # from BEGIN IMMEDIATE serializing writers.)
    _active = locks_service.get_lock(db, document_id)
    if _active is not None and _active["user_id"] != user_id:
        raise LockOwnedByOther(document_id)

    now = _now()
    db.execute("BEGIN IMMEDIATE")
    try:
        if references is not None:
            # Atomic save+complete. `_apply_save_inside_txn` upserts the
            # annotations row (creating it if absent) and writes a
            # single version row tagged 'complete_mark' carrying the
            # final refs + the diff vs. the prior committed state.
            save_result = _apply_save_inside_txn(
                db,
                document_id=document_id,
                user_id=user_id,
                references=references,
                now=now,
                action_override="complete_mark",
            )
            db.execute(
                "UPDATE annotations SET is_completed=1, completed_by_user_id=?, "
                "updated_at=? WHERE document_id=?",
                (user_id, now, document_id),
            )
            audit_action = "complete_mark"
            audit_extra: Optional[dict] = {
                "atomic": True,
                "is_diff_zero": save_result["is_diff_zero"],
                "ref_count": len(save_result["cleaned"]),
                "added_count": len(save_result["diff"]["added"]),
                "removed_count": len(save_result["diff"]["removed"]),
            }
        else:
            # Legacy flag-flip-only path. cur_pre is non-None here (the
            # AnnotationNotFound branch above would have raised), and
            # the state actually differs (idempotent branch returned).
            cur = db.execute(
                "SELECT references_json FROM annotations WHERE document_id=?",
                (document_id,),
            ).fetchone()
            audit_action = "complete_mark" if completed else "uncomplete"
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
                    audit_action, now,
                ),
            )
            if completed:
                db.execute(
                    "UPDATE annotations SET is_completed=1, completed_by_user_id=?, "
                    "updated_at=? WHERE document_id=?",
                    (user_id, now, document_id),
                )
            else:
                db.execute(
                    "UPDATE annotations SET is_completed=0, completed_by_user_id=NULL, "
                    "updated_at=? WHERE document_id=?",
                    (now, document_id),
                )
            audit_extra = None

        locks_service.release_if_held(db, document_id=document_id, user_id=user_id)
        audit.log_activity(
            db, user_id, audit_action,
            document_id=document_id,
            extra=audit_extra,
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return {"is_completed": completed}
