import time
import pytest
from datetime import datetime, timezone, timedelta
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.locks import service as locks


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) "
        "VALUES ('alice','x','user',?,?), ('bob','x','user',?,?)",
        (now, now, now, now),
    )
    conn.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
        "sentence_count, text_density, estimated_difficulty, created_at) "
        "VALUES ('doc_1','x.json','text',1,1,1.0,'Kolay',?)",
        (now,),
    )
    yield conn
    conn.close()


def test_acquire_creates_lock(db):
    info = locks.acquire(db, document_id="doc_1", user_id=1)
    assert info["document_id"] == "doc_1"
    assert info["user_id"] == 1
    assert "expires_at" in info


def test_acquire_unknown_document_raises(db):
    with pytest.raises(locks.DocumentNotFound):
        locks.acquire(db, document_id="nonexistent", user_id=1)


def test_acquire_held_by_other_raises_conflict(db):
    locks.acquire(db, document_id="doc_1", user_id=1)
    with pytest.raises(locks.LockHeldByOther) as exc:
        locks.acquire(db, document_id="doc_1", user_id=2)
    info = exc.value.info
    assert info["by_user_id"] == 1
    assert info["by_username"] == "alice"
    assert "expires_at" in info


def test_acquire_same_user_refreshes(db):
    """Acquiring an already-owned lock just refreshes the heartbeat."""
    first = locks.acquire(db, document_id="doc_1", user_id=1)
    time.sleep(0.01)  # ensure timestamp tick
    second = locks.acquire(db, document_id="doc_1", user_id=1)
    assert second["expires_at"] >= first["expires_at"]


def test_heartbeat_extends_expiry(db):
    info1 = locks.acquire(db, document_id="doc_1", user_id=1)
    time.sleep(0.01)
    info2 = locks.heartbeat(db, document_id="doc_1", user_id=1)
    assert info2["expires_at"] >= info1["expires_at"]


def test_heartbeat_by_non_holder_raises(db):
    locks.acquire(db, document_id="doc_1", user_id=1)
    with pytest.raises(locks.NotLockHolder):
        locks.heartbeat(db, document_id="doc_1", user_id=2)


def test_heartbeat_when_no_lock_raises(db):
    with pytest.raises(locks.NotLockHolder):
        locks.heartbeat(db, document_id="doc_1", user_id=1)


def test_release_by_holder(db):
    locks.acquire(db, document_id="doc_1", user_id=1)
    locks.release(db, document_id="doc_1", user_id=1)
    assert locks.get_lock(db, "doc_1") is None


def test_release_by_non_holder_raises(db):
    locks.acquire(db, document_id="doc_1", user_id=1)
    with pytest.raises(locks.NotLockHolder):
        locks.release(db, document_id="doc_1", user_id=2)


def test_release_when_absent_no_op(db):
    """Releasing a lock that was already cleared (e.g. by sweep) is silent."""
    locks.release(db, document_id="doc_1", user_id=1)  # does not raise


def test_force_release_drops_lock(db):
    locks.acquire(db, document_id="doc_1", user_id=1)
    locks.force_release(db, document_id="doc_1")
    assert locks.get_lock(db, "doc_1") is None


def test_sweep_removes_expired_only(db):
    """Insert a lock with past expires_at; sweep deletes it. Active lock survives."""
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    db.execute(
        "INSERT INTO document_locks(document_id, user_id, acquired_at, last_heartbeat, expires_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("doc_1", 1, past, past, past),
    )
    # also insert a fresh active lock for a fake doc
    db.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
        "sentence_count, text_density, estimated_difficulty, created_at) "
        "VALUES ('doc_2','y.json','text',1,1,1.0,'Kolay',datetime('now'))"
    )
    locks.acquire(db, document_id="doc_2", user_id=2)

    released = locks.sweep_expired(db)
    assert "doc_1" in released
    assert "doc_2" not in released

    assert locks.get_lock(db, "doc_1") is None
    assert locks.get_lock(db, "doc_2") is not None
