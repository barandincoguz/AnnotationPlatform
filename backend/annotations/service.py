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
from backend.notifications import service as notifications_service
from backend.quality import service as quality_service
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

    # B-01: O(1) EXISTS check — does this user already have a version row
    # for this document?  If not, they are a new contributor and the
    # unique_users_count must be incremented by 1.  This query is O(index
    # lookup) via idx_ver_doc_user(document_id, user_id) rather than the
    # prior O(N) COUNT(DISTINCT user_id) full-chain scan.
    #
    # NOTE: the check runs BEFORE inserting the new version row so that
    # the current user's own row is not counted as "already present".
    prior_row = db.execute(
        "SELECT 1 FROM annotation_versions WHERE document_id=? AND user_id=? LIMIT 1",
        (document_id, user_id),
    ).fetchone()
    user_is_new_contributor = prior_row is None

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

    if is_new:
        # First annotation row for this document; unique_users_count starts
        # at 1 (the creating user is always a new contributor here).
        db.execute(
            """
            INSERT INTO annotations(
                document_id, references_json, is_completed,
                last_editor_user_id, edit_count, unique_users_count,
                created_at, updated_at
            ) VALUES (?, ?, 0, ?, 1, 1, ?, ?)
            """,
            (document_id, json.dumps(cleaned), user_id, now, now),
        )
    else:
        db.execute(
            """
            UPDATE annotations SET
                references_json=?,
                last_editor_user_id=?,
                edit_count=edit_count+1,
                unique_users_count=unique_users_count + ?,
                updated_at=?
            WHERE document_id=?
            """,
            (
                json.dumps(cleaned), user_id,
                1 if user_is_new_contributor else 0,
                now, document_id,
            ),
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
    # Remember whether caller held the lock at pre-txn check time so the
    # inside-txn re-check (BE-3) can detect a swap that happened in the window.
    _caller_held_lock_pretxn = _active is not None and _active["user_id"] == user_id

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
        # BE-3: re-verify lock ownership INSIDE the transaction.  The pre-txn
        # check above is a TOCTOU: a lock can expire and be re-acquired by a
        # different user in the window between that check and this BEGIN
        # IMMEDIATE acquiring the writer's RESERVED state.  Re-querying here
        # closes the window — if ownership changed we raise (the outer except
        # block handles the ROLLBACK).
        _lock_row = db.execute(
            "SELECT user_id, expires_at FROM document_locks WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        _now_iso = datetime.now(timezone.utc).isoformat()
        # Two failure cases that indicate a swap in the window:
        #   (a) caller had the lock pre-txn but the row is now gone (expired +
        #       swept, or another path released it) → someone else can acquire
        #   (b) any lock row currently belongs to a different user or is expired
        _lock_held_by_other = _lock_row is not None and (
            _lock_row["user_id"] != user_id
            and _lock_row["expires_at"] > _now_iso
        )
        if _lock_held_by_other:
            raise LockOwnedByOther(document_id)

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
    audit_ack: Optional[str] = None,
) -> dict:
    """Flip the is_completed flag and unconditionally drop any active lock.
    When completed=False, `references` MUST be None (rejected by Pydantic).

    When `completed=True`, the quality audit is recomputed inside this
    transaction against the references being committed (atomic path) or the
    stored ones (legacy flag-flip path). A RED/YELLOW bucket without
    `audit_ack` raises quality_service.AuditAckRequired; an ack naming a
    superseded prediction raises quality_service.AuditAckStale. Both roll the
    transaction back, so a rejected complete leaves no trace.

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
        save creates the annotation in this call (chain invariant
        preserved by writing both 'create' and 'complete_mark' version
        rows).

    Returns a dict carrying enough information for the route layer to
    decide which side effects to fire (annotation_saved SSE + behavioral
    + run_after_save; annotation_completed SSE + run_after_complete):
        {
            "is_completed": bool,              # final state
            "changed": bool,                   # flag transitioned this call
            "did_save": bool,                  # atomic path ran a save
            "save_action": Optional[str],      # 'create' | 'edit' for SSE
            "save_is_diff_zero": Optional[bool],
            "save_ref_count": Optional[int],
        }

    Raises AnnotationNotFound, DocumentNotFound, LockOwnedByOther.
    """
    # Defense in depth (model_validator should have caught this).
    if not completed and references is not None:
        raise ValueError("references only allowed when completed=true")

    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)

    # Pre-txn lock check (early reject; real safety comes from BEGIN
    # IMMEDIATE serializing writers). The idempotence + AnnotationNotFound
    # checks now live INSIDE BEGIN IMMEDIATE — without that, a concurrent
    # writer could change `is_completed` between a pre-txn read and the
    # BEGIN, letting this caller write a duplicate `complete_mark` /
    # `uncomplete` version for an already-applied state.
    _active = locks_service.get_lock(db, document_id)
    if _active is not None and _active["user_id"] != user_id:
        raise LockOwnedByOther(document_id)
    # Remember whether caller held the lock at pre-txn check time (BE-3).
    _caller_held_lock_pretxn = _active is not None and _active["user_id"] == user_id

    now = _now()
    db.execute("BEGIN IMMEDIATE")
    try:
        # BE-3: re-verify lock ownership INSIDE the transaction for the same
        # reason as save_annotation — the pre-txn check is a TOCTOU.  Raise
        # here; the outer except block handles the ROLLBACK.
        _lock_row = db.execute(
            "SELECT user_id, expires_at FROM document_locks WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        _now_iso = datetime.now(timezone.utc).isoformat()
        _lock_held_by_other = _lock_row is not None and (
            _lock_row["user_id"] != user_id
            and _lock_row["expires_at"] > _now_iso
        )
        if _lock_held_by_other:
            raise LockOwnedByOther(document_id)

        cur = db.execute(
            "SELECT references_json, is_completed FROM annotations WHERE document_id=?",
            (document_id,),
        ).fetchone()

        if references is None:
            # Legacy flag-flip-only path.
            if cur is None:
                raise AnnotationNotFound(document_id)
            was_completed = bool(cur["is_completed"])
            if was_completed == completed:
                # Idempotent same-state poke — COMMIT empty so the
                # outer try/except still releases via the normal path.
                db.execute("COMMIT")
                return {
                    "is_completed": completed,
                    "changed": False,
                    "did_save": False,
                    "save_action": None,
                    "save_is_diff_zero": None,
                    "save_ref_count": None,
                }
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
            changed = True
            did_save = False
            save_action_ret: Optional[str] = None
            save_diff_zero: Optional[bool] = None
            save_ref_count: Optional[int] = None
            audit_extra: Optional[dict] = None
        else:
            # Atomic save+complete path. `_apply_save_inside_txn` upserts
            # the annotations row (creating it if absent) and writes one
            # version row whose action depends on what we're really doing:
            #   is_new          → 'create'        (then ALSO write 'complete_mark')
            #   becoming-done   → 'complete_mark' (single row carries refs + diff)
            #   already-done    → 'edit'          (refs edit on a completed doc;
            #                                      flag stays True, no transition)
            is_new = cur is None
            was_completed = bool(cur["is_completed"]) if cur is not None else False
            if is_new:
                save_action_label = "create"
            elif was_completed:
                save_action_label = "edit"
            else:
                save_action_label = "complete_mark"

            save_result = _apply_save_inside_txn(
                db,
                document_id=document_id,
                user_id=user_id,
                references=references,
                now=now,
                action_override=save_action_label,
            )

            if is_new:
                # Chain invariant: every completed annotation must have
                # at least one 'complete_mark' version. With the
                # 'create' row above carrying the refs, we add a
                # zero-diff 'complete_mark' to mark the transition.
                db.execute(
                    """
                    INSERT INTO annotation_versions(
                        document_id, user_id, references_json, diff_from_previous,
                        is_diff_zero, action, created_at
                    ) VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        document_id, user_id, json.dumps(save_result["cleaned"]),
                        json.dumps({"added": [], "removed": []}),
                        "complete_mark", now,
                    ),
                )

            # Update flag — idempotent UPDATE when already_completed.
            if not was_completed:
                db.execute(
                    "UPDATE annotations SET is_completed=1, completed_by_user_id=?, "
                    "updated_at=? WHERE document_id=?",
                    (user_id, now, document_id),
                )

            changed = not was_completed
            did_save = True
            # `save_action` is what the route uses to broadcast the
            # save SSE — frontend treats 'create' and 'edit' equally
            # for save attribution. is_new → 'create'; otherwise 'edit'
            # (this is the action consumers expect to see, even when
            # the version row itself was tagged 'complete_mark').
            save_action_ret = "create" if is_new else "edit"
            save_diff_zero = save_result["is_diff_zero"]
            save_ref_count = len(save_result["cleaned"])
            # Audit log distinguishes a real transition from an edit
            # on an already-completed doc — different operational
            # meaning (compliance/throughput stats).
            if changed:
                audit_action = "complete_mark"
            else:
                audit_action = "annotation_save"
            audit_extra = {
                "atomic": True,
                "is_diff_zero": save_diff_zero,
                "ref_count": save_ref_count,
                "added_count": len(save_result["diff"]["added"]),
                "removed_count": len(save_result["diff"]["removed"]),
                "first_time": is_new,
            }

        # Quality audit — recomputed from committed truth, never from what the
        # client claims. `changed or did_save` skips idempotent same-state
        # pokes (the legacy path already returned early for those).
        audit_report = None
        audit_decision = None
        if completed and (changed or did_save):
            if references is not None:
                final_references = save_result["cleaned"]
                previous_references = [] if is_new else json.loads(cur["references_json"])
            else:
                final_references = json.loads(cur["references_json"])
                previous_references = final_references
            audit_report, audit_decision = quality_service.evaluate_for_commit(
                db,
                document_id=document_id,
                references=final_references,
                previous_references=previous_references,
                ack_fingerprint=audit_ack,
            )

        locks_service.release_if_held(db, document_id=document_id, user_id=user_id)
        audit.log_activity(
            db, user_id, audit_action,
            document_id=document_id,
            extra=audit_extra,
        )

        if audit_report is not None:
            quality_service.log_decision(
                db,
                document_id=document_id,
                user_id=user_id,
                report=audit_report,
                decision=str(audit_decision),
                now=now,
            )

        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return {
        "is_completed": completed,
        "changed": changed,
        "did_save": did_save,
        "save_action": save_action_ret,
        "save_is_diff_zero": save_diff_zero,
        "save_ref_count": save_ref_count,
        "audit_bucket": audit_report.bucket if audit_report is not None else None,
        "audit_decision": audit_decision,
    }
