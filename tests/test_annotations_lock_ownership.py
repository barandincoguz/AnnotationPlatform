"""Tests for B1: Lock ownership enforcement in save_annotation / set_complete.

Guards that a user without the lock cannot overwrite another user's locked
document by POSTing directly to /api/annotations or /complete.
"""
import json
from datetime import datetime, timezone, timedelta

import pytest

from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.annotations import service as ann_service
from backend.locks import service as lock_service
from backend.documents import service as doc_service


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(db_path, tmp_path):
    """Isolated DB with schema, 2 users (alice=1, bob=2), and 1 document."""
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) "
        "VALUES ('alice','x','user',?,?), ('bob','x','user',?,?)",
        (now, now, now, now),
    )
    sample = {
        "evrakOid": "doc_1", "sayi": 1, "tarih": "20260101",
        "konu": "Test", "pdfText": "x" * 50,
        "kanunBilgileri": [], "bkkTebligSirkuBilgileri": [],
    }
    fpath = tmp_path / "doc_1.json"
    fpath.write_text(json.dumps(sample))
    doc_service.ingest_file(conn, fpath)
    yield conn
    conn.close()


def _ref(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "x"}
    base.update(kwargs)
    return base


def _insert_lock(conn, document_id, user_id, *, expires_delta_seconds=300):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=expires_delta_seconds)
    conn.execute(
        "INSERT INTO document_locks(document_id, user_id, acquired_at, last_heartbeat, expires_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (document_id, user_id, now.isoformat(), now.isoformat(), expires.isoformat()),
    )


# ---------------------------------------------------------------------------
# save_annotation: service-layer tests
# ---------------------------------------------------------------------------


def test_save_rejects_when_lock_owned_by_other(db):
    """User B cannot save when User A holds an active lock."""
    _insert_lock(db, "doc_1", user_id=1)  # alice holds lock
    with pytest.raises(ann_service.LockOwnedByOther):
        ann_service.save_annotation(
            db, document_id="doc_1", user_id=2,  # bob tries to save
            references=[_ref(source_text="bob-save")],
        )


def test_save_allowed_when_caller_owns_lock(db):
    """Caller can save when they themselves hold the lock."""
    lock_service.acquire(db, document_id="doc_1", user_id=1)
    result = ann_service.save_annotation(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="alice-save")],
    )
    assert result["is_new"] is True


def test_save_allowed_when_no_active_lock(db):
    """No lock at all → save proceeds normally."""
    result = ann_service.save_annotation(
        db, document_id="doc_1", user_id=1, references=[],
    )
    assert result["is_new"] is True


def test_save_allowed_when_lock_expired(db):
    """An expired lock must NOT block a different user's save."""
    # Insert a lock that already expired
    _insert_lock(db, "doc_1", user_id=1, expires_delta_seconds=-10)
    # Bob should be allowed to save because alice's lock is expired
    result = ann_service.save_annotation(
        db, document_id="doc_1", user_id=2, references=[],
    )
    assert result["is_new"] is True


def test_save_rejects_does_not_create_annotation_row(db):
    """When LockOwnedByOther fires the transaction must be fully rolled back —
    no partial annotation row should be written."""
    _insert_lock(db, "doc_1", user_id=1)
    with pytest.raises(ann_service.LockOwnedByOther):
        ann_service.save_annotation(db, document_id="doc_1", user_id=2, references=[])

    row = db.execute(
        "SELECT * FROM annotations WHERE document_id=?", ("doc_1",)
    ).fetchone()
    assert row is None, "annotation row must not exist after a rejected save"


def test_save_rejects_does_not_delete_draft(db):
    """When LockOwnedByOther fires, the caller's draft must NOT be deleted
    (precheck happens before the transaction that deletes drafts)."""
    _insert_lock(db, "doc_1", user_id=1)
    db.execute(
        "INSERT INTO drafts(document_id, user_id, references_json, updated_at) "
        "VALUES ('doc_1', 2, '[]', datetime('now'))"
    )
    with pytest.raises(ann_service.LockOwnedByOther):
        ann_service.save_annotation(db, document_id="doc_1", user_id=2, references=[])

    draft = db.execute(
        "SELECT * FROM drafts WHERE document_id='doc_1' AND user_id=2"
    ).fetchone()
    assert draft is not None, "draft must survive a rejected save"


# ---------------------------------------------------------------------------
# set_complete: service-layer tests
# ---------------------------------------------------------------------------


def test_complete_rejects_when_lock_owned_by_other(db):
    """User B cannot mark complete when User A holds an active lock."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    _insert_lock(db, "doc_1", user_id=1)  # alice still holds lock

    with pytest.raises(ann_service.LockOwnedByOther):
        ann_service.set_complete(db, document_id="doc_1", user_id=2, completed=True)


def test_complete_allowed_when_caller_owns_lock(db):
    """Caller can toggle complete when they hold the lock."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    lock_service.acquire(db, document_id="doc_1", user_id=1)
    result = ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)
    assert result["is_completed"] is True


def test_complete_allowed_when_no_active_lock(db):
    """No lock → complete toggle proceeds normally."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    result = ann_service.set_complete(db, document_id="doc_1", user_id=2, completed=True)
    assert result["is_completed"] is True


def test_complete_allowed_when_lock_expired(db):
    """Expired lock must NOT block a different user from toggling complete."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    _insert_lock(db, "doc_1", user_id=1, expires_delta_seconds=-10)
    result = ann_service.set_complete(db, document_id="doc_1", user_id=2, completed=True)
    assert result["is_completed"] is True


def test_complete_rejects_does_not_change_completion_state(db):
    """When LockOwnedByOther fires inside set_complete the annotation must
    remain unchanged (transaction rolled back)."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    _insert_lock(db, "doc_1", user_id=1)

    with pytest.raises(ann_service.LockOwnedByOther):
        ann_service.set_complete(db, document_id="doc_1", user_id=2, completed=True)

    row = db.execute(
        "SELECT is_completed FROM annotations WHERE document_id=?", ("doc_1",)
    ).fetchone()
    assert row["is_completed"] == 0, "is_completed must remain 0 after rejected complete"


# ---------------------------------------------------------------------------
# Route-layer (HTTP) tests
# ---------------------------------------------------------------------------


def _ref_payload(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "default"}
    base.update(kwargs)
    return base


def test_route_save_returns_409_lock_owned_by_other(second_passed_user, ingest_doc):
    """POST /api/annotations returns 409 lock_owned_by_other when another user
    holds an active lock on the target document."""
    ctx = second_passed_user
    ingest_doc("doc_test")

    # Alice acquires the lock
    ctx["login"]("alice")
    r = ctx["client"].post("/api/locks/doc_test/acquire")
    assert r.status_code == 200, r.text

    # Bob tries to save without acquiring
    ctx["login"]("bob")
    r = ctx["client"].post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref_payload(kanun_no="193", source_text="bob")],
    })
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["error"] == "lock_owned_by_other"
    assert "kilitli" in body["detail"]["message"]


def test_route_save_succeeds_when_caller_owns_lock(passed_user, ingest_doc):
    """Alice can save when she herself holds the lock."""
    c = passed_user["client"]
    ingest_doc("doc_test")
    r = c.post("/api/locks/doc_test/acquire")
    assert r.status_code == 200, r.text

    r = c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [],
    })
    assert r.status_code == 200, r.text


def test_route_save_succeeds_when_no_lock(passed_user, ingest_doc):
    """Save without any lock held → 200."""
    c = passed_user["client"]
    ingest_doc("doc_test")
    r = c.post("/api/annotations", json={"document_id": "doc_test", "references": []})
    assert r.status_code == 200, r.text


def test_route_complete_returns_409_lock_owned_by_other(second_passed_user, ingest_doc):
    """POST /api/annotations/:id/complete returns 409 when another user holds the lock."""
    ctx = second_passed_user
    ingest_doc("doc_test")

    # Alice saves so an annotation row exists, then holds the lock
    ctx["login"]("alice")
    ctx["client"].post("/api/annotations", json={"document_id": "doc_test", "references": []})
    r = ctx["client"].post("/api/locks/doc_test/acquire")
    assert r.status_code == 200, r.text

    # Bob tries to mark complete
    ctx["login"]("bob")
    r = ctx["client"].post("/api/annotations/doc_test/complete", json={"completed": True})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["error"] == "lock_owned_by_other"
