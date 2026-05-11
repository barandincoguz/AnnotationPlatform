"""Tests for B2: acquire() is atomic under concurrent writers.

SQLite's BEGIN IMMEDIATE serializes concurrent acquires on the same
document: exactly one caller wins and the other gets LockHeldByOther.
Previously the read-then-write had no transaction wrapper, so the second
writer could silently overwrite the first's ownership.
"""
import threading
from pathlib import Path

import pytest

from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.locks import service as locks


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
