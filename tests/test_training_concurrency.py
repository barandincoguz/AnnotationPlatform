"""Phase 5 BE-4: submit_quiz / submit_annotation + finalize_if_complete must be
transactional.

Two concurrent submit_annotation calls for different gold_ids on the same attempt
must not clobber each other's result in annotation_details_json (last-writer-wins).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.training import service as training_service


# ---------------------------------------------------------------------------
# Fixture: single on-disk database with migrations + a seeded user
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_db(tmp_path: Path):
    """One connection to an on-disk WAL database, fully migrated with a user.

    Returns the connection; leaves the file on disk so worker threads can
    open their own independent connections to the same file.
    """
    db_path = tmp_path / "training_race.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, has_seen_manual, "
        "has_passed_training, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', 1, 0, ?, ?)",
        (now, now),
    )

    yield conn

    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ref(**kw):
    base = {"kanun_no": "", "kanun_ad": "", "madde": "",
            "fikra": "", "bent": "", "source_text": "x"}
    base.update(kw)
    return base


def _db_file(conn) -> Path:
    """Return the on-disk path for the given connection."""
    row = conn.execute("PRAGMA database_list").fetchone()
    return Path(row["file"])


# ---------------------------------------------------------------------------
# Concurrent clobber test
# ---------------------------------------------------------------------------


def test_concurrent_submit_annotation_does_not_clobber_details(fresh_db):
    """Two concurrent submit_annotation calls for different gold_ids on the
    same training attempt must BOTH end up in annotation_details_json.

    Without BEGIN IMMEDIATE, last-writer-wins on the JSON blob silently drops
    one result.  With the wrapper the two writes serialize cleanly.
    """
    conn = fresh_db
    db_file = _db_file(conn)

    # Start a fresh attempt for user 1
    out = training_service.start_attempt(conn, user_id=1)
    attempt_id = out["attempt_id"]

    # Find the two gold docs that were assigned to this attempt
    docs = training_service._select_gold_docs_for_attempt(conn, attempt_id)
    assert len(docs) >= 2, "need at least 2 gold docs to test concurrent submit"
    gid_0 = docs[0]["gold_id"]
    gid_1 = docs[1]["gold_id"]

    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def worker(gold_id: str) -> None:
        try:
            worker_conn = connect(db_file)
            try:
                barrier.wait(timeout=5)
                training_service.submit_annotation(
                    worker_conn,
                    attempt_id=attempt_id,
                    user_id=1,
                    gold_id=gold_id,
                    references=[_ref()],
                )
            finally:
                worker_conn.close()
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=worker, args=(gid_0,))
    t2 = threading.Thread(target=worker, args=(gid_1,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, f"submit_annotation raised: {errors}"

    # Both gold_ids must be present in annotation_details_json
    row = conn.execute(
        "SELECT annotation_details_json FROM training_attempts WHERE id=?",
        (attempt_id,),
    ).fetchone()
    assert row is not None
    details = json.loads(row["annotation_details_json"])
    gold_ids_present = {k for k in details if not k.startswith("_")}
    assert gold_ids_present == {gid_0, gid_1}, (
        f"clobber detected — only {gold_ids_present} present, expected both "
        f"{{{gid_0!r}, {gid_1!r}}}"
    )


# ---------------------------------------------------------------------------
# Structural assertion: submit_annotation wraps its mutations in BEGIN IMMEDIATE
# ---------------------------------------------------------------------------


def test_submit_annotation_is_transactional_structural(fresh_db):
    """submit_annotation must issue BEGIN IMMEDIATE before any UPDATE and
    COMMIT after.  Verified by tracing executed statement keywords."""
    conn = fresh_db

    out = training_service.start_attempt(conn, user_id=1)
    attempt_id = out["attempt_id"]
    docs = training_service._select_gold_docs_for_attempt(conn, attempt_id)
    gid = docs[0]["gold_id"]

    calls: list[str] = []

    class _TraceConn:
        def __getattr__(self, name):
            return getattr(conn, name)

        def execute(self, stmt, *args, **kw):
            first = stmt.strip().split()[0].upper()
            if first in ("BEGIN", "COMMIT", "ROLLBACK", "SELECT", "UPDATE", "INSERT", "DELETE"):
                calls.append(first)
            return conn.execute(stmt, *args, **kw)

        def commit(self):
            calls.append("COMMIT")
            return conn.commit()

        def rollback(self):
            calls.append("ROLLBACK")
            return conn.rollback()

    training_service.submit_annotation(
        _TraceConn(),
        attempt_id=attempt_id,
        user_id=1,
        gold_id=gid,
        references=[_ref()],
    )

    assert "BEGIN" in calls, f"submit_annotation did not BEGIN a transaction: {calls}"
    begin_idx = calls.index("BEGIN")
    post_begin = calls[begin_idx + 1:]
    assert "COMMIT" in post_begin, f"submit_annotation did not COMMIT: {calls}"
    commit_idx = post_begin.index("COMMIT")
    inside = post_begin[:commit_idx]
    assert "UPDATE" in inside, (
        f"submit_annotation UPDATE ran outside the transaction; sequence: {calls}"
    )


# ---------------------------------------------------------------------------
# Structural assertion: submit_quiz wraps its mutations in BEGIN IMMEDIATE
# ---------------------------------------------------------------------------


def test_submit_quiz_is_transactional_structural(fresh_db):
    """submit_quiz must issue BEGIN IMMEDIATE before its UPDATE and COMMIT after."""
    conn = fresh_db

    out = training_service.start_attempt(conn, user_id=1)
    attempt_id = out["attempt_id"]
    selected = training_service._select_questions_for_attempt(conn, attempt_id)
    answers = {q["id"]: q["correct_choice_idx"] for q in selected}

    calls: list[str] = []

    class _TraceConn:
        def __getattr__(self, name):
            return getattr(conn, name)

        def execute(self, stmt, *args, **kw):
            first = stmt.strip().split()[0].upper()
            if first in ("BEGIN", "COMMIT", "ROLLBACK", "SELECT", "UPDATE", "INSERT", "DELETE"):
                calls.append(first)
            return conn.execute(stmt, *args, **kw)

        def commit(self):
            calls.append("COMMIT")
            return conn.commit()

        def rollback(self):
            calls.append("ROLLBACK")
            return conn.rollback()

    training_service.submit_quiz(
        _TraceConn(),
        attempt_id=attempt_id,
        user_id=1,
        answers=answers,
    )

    assert "BEGIN" in calls, f"submit_quiz did not BEGIN a transaction: {calls}"
    begin_idx = calls.index("BEGIN")
    post_begin = calls[begin_idx + 1:]
    assert "COMMIT" in post_begin, f"submit_quiz did not COMMIT: {calls}"
    commit_idx = post_begin.index("COMMIT")
    inside = post_begin[:commit_idx]
    assert "UPDATE" in inside, (
        f"submit_quiz UPDATE ran outside the transaction; sequence: {calls}"
    )
