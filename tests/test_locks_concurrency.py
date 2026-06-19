"""Tests for B2: acquire() is atomic under concurrent writers.

SQLite's BEGIN IMMEDIATE serializes concurrent acquires on the same
document: exactly one caller wins and the other gets LockHeldByOther.
Previously the read-then-write had no transaction wrapper, so the second
writer could silently overwrite the first's ownership.

Phase 5 BE-1 + BE-2: heartbeat() and sweep_expired() must also wrap
their read-then-write sequences in BEGIN IMMEDIATE.
"""
import threading
import time
from pathlib import Path

import pytest

from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.locks import service as locks
from backend.locks.service import NotLockHolder


# ---------------------------------------------------------------------------
# Fixture: two independent connections to the SAME on-disk database
# ---------------------------------------------------------------------------


@pytest.fixture
def two_dbs(tmp_path: Path):
    """Yield (conn_a, conn_b) pointing at the same on-disk WAL database.

    Each connection has its own isolation_level=None + WAL setup (via
    db.connect()) so they behave exactly as two separate request threads
    would in production.
    """
    db_path = tmp_path / "lock_race.db"

    conn_a = connect(db_path)
    apply_migrations(conn_a, discover_migrations())

    now = "2026-01-01T00:00:00+00:00"
    conn_a.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) "
        "VALUES ('alice','x','user',?,?), ('bob','x','user',?,?)",
        (now, now, now, now),
    )
    conn_a.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
        "sentence_count, text_density, estimated_difficulty, created_at) "
        "VALUES ('doc_1','x.json','text',1,1,1.0,'Kolay',?)",
        (now,),
    )

    conn_b = connect(db_path)

    yield conn_a, conn_b

    conn_a.close()
    conn_b.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_acquire_is_atomic_under_concurrent_writers(two_dbs):
    """Spawn two threads that both call acquire() on the same document at the
    same time.  Exactly one must succeed; the other must raise LockHeldByOther.

    This is the canonical B2 regression test: without BEGIN IMMEDIATE the two
    threads can both read 'no existing lock' and then the second INSERT/UPDATE
    silently overwrites the first — ownership is corrupted.  With BEGIN
    IMMEDIATE the RESERVED lock forces them to serialize.
    """
    conn_a, conn_b = two_dbs

    results: list = []
    errors: list = []
    lock = threading.Lock()

    def _acquire(conn, user_id):
        try:
            info = locks.acquire(conn, document_id="doc_1", user_id=user_id)
            with lock:
                results.append(("ok", user_id, info["user_id"]))
        except locks.LockHeldByOther as exc:
            with lock:
                errors.append(("conflict", user_id, exc.info["by_user_id"]))
        except Exception as exc:
            with lock:
                errors.append(("error", user_id, str(exc)))

    t1 = threading.Thread(target=_acquire, args=(conn_a, 1))
    t2 = threading.Thread(target=_acquire, args=(conn_b, 2))

    # Start both threads as close together as possible
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # No unexpected errors (OperationalError from SQLite is acceptable only
    # if it manifests as a LockHeldByOther — the busy_timeout handles retries)
    unexpected = [e for e in errors if e[0] == "error"]
    assert not unexpected, f"unexpected errors: {unexpected}"

    total = len(results) + len(errors)
    assert total == 2, f"expected exactly 2 outcomes, got results={results} errors={errors}"

    # Exactly one success, exactly one conflict
    assert len(results) == 1, f"expected exactly one winner, got results={results}"
    assert len(errors) == 1, f"expected exactly one loser, got errors={errors}"
    assert errors[0][0] == "conflict"

    # The winner recorded in the DB must match who actually won
    winner_user_id = results[0][1]
    loser_user_id = errors[0][1]
    assert winner_user_id != loser_user_id

    # DB state: the lock row must be owned by the winner
    # Use conn_a (or conn_b — both read the same WAL file)
    row = conn_a.execute(
        "SELECT user_id FROM document_locks WHERE document_id='doc_1'"
    ).fetchone()
    assert row is not None, "lock row must exist"
    assert row["user_id"] == winner_user_id, (
        f"DB owner ({row['user_id']}) must equal the thread that won ({winner_user_id})"
    )


def test_acquire_same_user_concurrent_is_idempotent(two_dbs):
    """Two concurrent acquires from the *same* user must both succeed and leave
    exactly one lock row (the second is a heartbeat-style refresh)."""
    conn_a, conn_b = two_dbs

    results: list = []
    errors: list = []
    lock = threading.Lock()

    def _acquire(conn):
        try:
            info = locks.acquire(conn, document_id="doc_1", user_id=1)
            with lock:
                results.append(info["user_id"])
        except Exception as exc:
            with lock:
                errors.append(str(exc))

    t1 = threading.Thread(target=_acquire, args=(conn_a,))
    t2 = threading.Thread(target=_acquire, args=(conn_b,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, f"unexpected errors: {errors}"
    assert len(results) == 2

    row_count = conn_a.execute(
        "SELECT COUNT(*) AS c FROM document_locks WHERE document_id='doc_1'"
    ).fetchone()["c"]
    assert row_count == 1, "must be exactly one lock row even after two same-user acquires"


def test_acquire_serializes_after_release(two_dbs):
    """After the first user releases, a second user can acquire without conflict."""
    conn_a, conn_b = two_dbs

    locks.acquire(conn_a, document_id="doc_1", user_id=1)
    locks.release(conn_a, document_id="doc_1", user_id=1)

    info = locks.acquire(conn_b, document_id="doc_1", user_id=2)
    assert info["user_id"] == 2


def test_stale_release_cannot_delete_reacquired_lock(two_dbs):
    """An expired Alice lock is read by release while Bob tries to acquire it.

    release() must hold BEGIN IMMEDIATE across its owner check and conditional
    delete. Bob therefore waits, acquires after Alice commits, and his new row
    remains. Without the transaction, Bob can replace the expired row between
    Alice's SELECT and DELETE and Alice then deletes Bob's lock.
    """
    conn_a, conn_b = two_dbs
    locks.acquire(conn_a, document_id="doc_1", user_id=1)
    conn_a.execute(
        "UPDATE document_locks SET expires_at='2020-01-01T00:00:00+00:00' "
        "WHERE document_id='doc_1'"
    )

    owner_read = threading.Event()
    resume_release = threading.Event()

    class _CursorProxy:
        def __init__(self, cursor):
            self._cursor = cursor

        def fetchone(self):
            row = self._cursor.fetchone()
            owner_read.set()
            assert resume_release.wait(timeout=5)
            return row

        def __getattr__(self, name):
            return getattr(self._cursor, name)

    class _PauseAfterOwnerRead:
        def __getattr__(self, name):
            return getattr(conn_a, name)

        def execute(self, statement, *args, **kwargs):
            cursor = conn_a.execute(statement, *args, **kwargs)
            normalized = " ".join(statement.split()).lower()
            if normalized.startswith(
                "select user_id from document_locks where document_id=?"
            ):
                return _CursorProxy(cursor)
            return cursor

    release_error: list[Exception] = []
    acquire_result: list[dict] = []

    def stale_release():
        try:
            locks.release(
                _PauseAfterOwnerRead(), document_id="doc_1", user_id=1,
            )
        except Exception as exc:
            release_error.append(exc)

    def reacquire():
        acquire_result.append(
            locks.acquire(conn_b, document_id="doc_1", user_id=2)
        )

    release_thread = threading.Thread(target=stale_release)
    release_thread.start()
    assert owner_read.wait(timeout=5)

    acquire_thread = threading.Thread(target=reacquire)
    acquire_thread.start()
    time.sleep(0.05)
    assert acquire_thread.is_alive(), "Bob must wait for Alice's release transaction"

    resume_release.set()
    release_thread.join(timeout=5)
    acquire_thread.join(timeout=5)

    assert not release_error
    assert acquire_result[0]["user_id"] == 2
    row = conn_a.execute(
        "SELECT user_id FROM document_locks WHERE document_id='doc_1'"
    ).fetchone()
    assert row is not None
    assert row["user_id"] == 2


# ---------------------------------------------------------------------------
# Phase 5 BE-1: heartbeat() must be transactional — re-verify ownership inside
# BEGIN IMMEDIATE so a concurrent acquire() swap is detected.
# ---------------------------------------------------------------------------


@pytest.fixture
def two_dbs_hb(tmp_path: Path):
    """Two independent connections to the same on-disk DB, seeded with two
    users and one document.  Used for heartbeat/sweep race tests."""
    db_path = tmp_path / "hb_race.db"

    conn_a = connect(db_path)
    apply_migrations(conn_a, discover_migrations())

    now = "2026-01-01T00:00:00+00:00"
    conn_a.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) "
        "VALUES ('alice','x','user',?,?), ('bob','x','user',?,?)",
        (now, now, now, now),
    )
    conn_a.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
        "sentence_count, text_density, estimated_difficulty, created_at) "
        "VALUES ('doc_1','x.json','text',1,1,1.0,'Kolay',?)",
        (now,),
    )

    conn_b = connect(db_path)

    yield conn_a, conn_b

    conn_a.close()
    conn_b.close()


def test_heartbeat_refuses_after_concurrent_acquire_swap(two_dbs_hb):
    """BE-1: heartbeat() must NOT silently overwrite Bob's expiry when Alice
    calls it after Bob has already acquired the lock on another connection.

    Sequence:
      1. Alice acquires on conn_a.
      2. Alice's lock expires.
      3. Bob acquires on conn_b (writes user_id=2).
      4. Alice fires heartbeat(conn_a, user_id=1).

    Without BEGIN IMMEDIATE: heartbeat() SELECT reads user_id=2 on conn_a
    (correct — it already sees Bob's committed row), raises NotLockHolder.

    This test establishes the *desired contract*: even when heartbeat() is
    called sequentially after the swap, it must raise NotLockHolder.  The
    transaction wrapper ensures this contract also holds under concurrent
    interleavings where the SELECT and UPDATE straddle a concurrent acquire.
    """
    conn_a, conn_b = two_dbs_hb

    # Alice acquires on conn_a.
    locks.acquire(conn_a, document_id="doc_1", user_id=1)

    # Expire Alice's lock so Bob can acquire.
    conn_a.execute(
        "UPDATE document_locks SET expires_at = '2020-01-01T00:00:00+00:00' "
        "WHERE document_id = 'doc_1'"
    )
    conn_a.commit()

    # Bob acquires on conn_b — doc_1 is now owned by user_id=2.
    locks.acquire(conn_b, document_id="doc_1", user_id=2)

    # Alice fires a stale heartbeat on conn_a.
    # heartbeat() must raise NotLockHolder, not silently update Bob's row.
    with pytest.raises(NotLockHolder):
        locks.heartbeat(conn_a, document_id="doc_1", user_id=1)

    # Bob's row must not have been corrupted by Alice's heartbeat.
    row = conn_b.execute(
        "SELECT user_id FROM document_locks WHERE document_id='doc_1'"
    ).fetchone()
    assert row is not None, "lock row must still exist"
    assert row["user_id"] == 2, (
        f"Bob must own the lock after Alice's stale heartbeat; got user_id={row['user_id']}"
    )


def test_heartbeat_is_transactional(two_dbs_hb):
    """BE-1: heartbeat() must wrap its SELECT+UPDATE in BEGIN IMMEDIATE.

    We assert the structural property by proxying db.execute and recording
    all statement keywords.  A BEGIN must appear, followed by the UPDATE
    inside the transaction, closed by COMMIT.
    """
    conn_a, _conn_b = two_dbs_hb
    db = conn_a

    locks.acquire(db, document_id="doc_1", user_id=1)

    calls: list[str] = []

    class _TraceConn:
        def __getattr__(self, name):
            return getattr(db, name)

        def execute(self, stmt, *args, **kw):
            first_word = stmt.strip().split()[0].upper()
            if first_word in ("BEGIN", "COMMIT", "ROLLBACK", "SELECT", "DELETE", "INSERT", "UPDATE"):
                calls.append(first_word)
            return db.execute(stmt, *args, **kw)

        def cursor(self):
            return _TraceCursor(db.cursor(), calls)

        def commit(self):
            calls.append("COMMIT")
            return db.commit()

        def rollback(self):
            calls.append("ROLLBACK")
            return db.rollback()

    class _TraceCursor:
        def __init__(self, cur, call_list):
            self._cur = cur
            self._calls = call_list

        def __getattr__(self, name):
            return getattr(self._cur, name)

        def execute(self, stmt, *args, **kw):
            first_word = stmt.strip().split()[0].upper()
            if first_word in ("BEGIN", "COMMIT", "ROLLBACK", "SELECT", "DELETE", "INSERT", "UPDATE"):
                self._calls.append(first_word)
            return self._cur.execute(stmt, *args, **kw)

    locks.heartbeat(_TraceConn(), document_id="doc_1", user_id=1)

    assert "BEGIN" in calls, f"heartbeat did not BEGIN a transaction: {calls}"
    begin_idx = calls.index("BEGIN")
    post_begin = calls[begin_idx + 1:]
    assert "COMMIT" in post_begin, f"heartbeat did not COMMIT: {calls}"
    commit_idx = post_begin.index("COMMIT")
    inside = post_begin[:commit_idx]
    assert "UPDATE" in inside, (
        f"heartbeat UPDATE ran outside the transaction; sequence: {calls}"
    )


# ---------------------------------------------------------------------------
# Phase 5 BE-2: sweep_expired() must execute SELECT+DELETE inside one transaction
# ---------------------------------------------------------------------------


def test_sweep_expired_is_atomic_against_heartbeat(two_dbs_hb):
    """BE-2: sweep_expired() must wrap its SELECT+DELETE in BEGIN IMMEDIATE.

    We assert the structural invariant by wrapping db.execute on a fresh
    wrapper object so sqlite3.Connection's read-only .execute is not mutated.
    The BEGIN must appear before any DELETE and a COMMIT must close it.
    """
    conn_a, _conn_b = two_dbs_hb
    db = conn_a

    # Acquire then immediately expire the lock.
    locks.acquire(db, document_id="doc_1", user_id=1)
    db.execute(
        "UPDATE document_locks SET expires_at = '2020-01-01T00:00:00+00:00' "
        "WHERE document_id = ?",
        ("doc_1",),
    )
    db.commit()

    calls: list[str] = []

    class _TraceConn:
        """Thin proxy that records statement keywords and delegates to the
        real connection.  Attribute reads fall through to the real object."""

        def __getattr__(self, name):
            return getattr(db, name)

        def execute(self, stmt, *args, **kw):
            first_word = stmt.strip().split()[0].upper()
            if first_word in ("BEGIN", "COMMIT", "ROLLBACK", "SELECT", "DELETE", "INSERT", "UPDATE"):
                calls.append(first_word)
            return db.execute(stmt, *args, **kw)

        def cursor(self):
            return _TraceCursor(db.cursor(), calls)

        def commit(self):
            calls.append("COMMIT")
            return db.commit()

        def rollback(self):
            calls.append("ROLLBACK")
            return db.rollback()

    class _TraceCursor:
        def __init__(self, cur, call_list):
            self._cur = cur
            self._calls = call_list

        def __getattr__(self, name):
            return getattr(self._cur, name)

        def execute(self, stmt, *args, **kw):
            first_word = stmt.strip().split()[0].upper()
            if first_word in ("BEGIN", "COMMIT", "ROLLBACK", "SELECT", "DELETE", "INSERT", "UPDATE"):
                self._calls.append(first_word)
            return self._cur.execute(stmt, *args, **kw)

    locks.sweep_expired(_TraceConn())

    assert "BEGIN" in calls, f"sweep_expired did not BEGIN a transaction: {calls}"
    begin_idx = calls.index("BEGIN")
    post_begin = calls[begin_idx + 1:]
    assert "COMMIT" in post_begin, f"sweep_expired did not COMMIT: {calls}"
    commit_idx = post_begin.index("COMMIT")
    inside = post_begin[:commit_idx]
    assert "DELETE" in inside, (
        f"sweep_expired DELETE ran outside the transaction; sequence: {calls}"
    )
