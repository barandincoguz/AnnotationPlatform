"""Verify locks routes + sweep publish the right SSE events to the broker."""
import asyncio
import pytest
from backend.shared.sse import broker as sse_broker


def _reset_broker():
    sse_broker._subscribers.clear()


def test_acquire_publishes_lock_acquired(passed_user, ingest_doc):
    """POST /api/locks/{id}/acquire publishes lock_acquired with full metadata."""
    _reset_broker()
    user_id = passed_user["user"]["id"]
    queue = sse_broker.subscribe(user_id=user_id)
    try:
        ingest_doc("doc_pub_acquire")
        r = passed_user["client"].post("/api/locks/doc_pub_acquire/acquire")
        assert r.status_code == 200

        async def _wait():
            return await asyncio.wait_for(queue.get(), timeout=2.0)
        event = asyncio.run(_wait())
        assert event.event_type == "lock_acquired"
        assert event.data["document_id"] == "doc_pub_acquire"
        assert event.data["by_user_id"] == user_id
        assert event.data["by_username"] == "alice"
        assert "expires_at" in event.data
    finally:
        sse_broker.unsubscribe(user_id, queue)


def test_release_publishes_lock_released(passed_user, ingest_doc):
    """POST /api/locks/{id}/release publishes lock_released."""
    _reset_broker()
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_pub_release")
    c.post("/api/locks/doc_pub_release/acquire")  # ignore the broadcast for this

    queue = sse_broker.subscribe(user_id=user_id)
    try:
        c.post("/api/locks/doc_pub_release/release")

        async def _wait():
            return await asyncio.wait_for(queue.get(), timeout=2.0)
        event = asyncio.run(_wait())
        assert event.event_type == "lock_released"
        assert event.data["document_id"] == "doc_pub_release"
        assert event.data["by_user_id"] == user_id
        assert event.data["reason"] == "user_release"
    finally:
        sse_broker.unsubscribe(user_id, queue)


def test_release_when_no_lock_does_not_publish(passed_user, ingest_doc):
    """release() is silent on absent lock — no event published in that case."""
    _reset_broker()
    user_id = passed_user["user"]["id"]
    queue = sse_broker.subscribe(user_id=user_id)
    try:
        ingest_doc("doc_pub_release2")
        r = passed_user["client"].post("/api/locks/doc_pub_release2/release")
        assert r.status_code == 200

        # No event should arrive within a short window
        async def _wait():
            return await asyncio.wait_for(queue.get(), timeout=0.5)
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(_wait())
    finally:
        sse_broker.unsubscribe(user_id, queue)


def test_acquire_held_by_other_does_not_publish(second_passed_user, ingest_doc):
    """409 conflict path doesn't fire a lock_acquired (because nothing changed)."""
    _reset_broker()
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_pub_409")

    ctx["login"]("alice")
    c.post("/api/locks/doc_pub_409/acquire")

    bob_id = ctx["bob"]["id"]
    queue = sse_broker.subscribe(user_id=bob_id)
    try:
        ctx["login"]("bob")
        r = c.post("/api/locks/doc_pub_409/acquire")
        assert r.status_code == 409

        async def _wait():
            return await asyncio.wait_for(queue.get(), timeout=0.5)
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(_wait())
    finally:
        sse_broker.unsubscribe(bob_id, queue)


def test_sweep_publishes_lock_released_for_each_expired(tmp_path, monkeypatch):
    """Background sweep_expired publishes one lock_released per released doc."""
    _reset_broker()

    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("backend.config.DB_DIR", tmp_path / "db")
    monkeypatch.setattr("backend.config.DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr("backend.config.DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr("backend.config.BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr("backend.config.EXPORTS_DIR", tmp_path / "exports")

    from backend.shared.db import connect
    from backend.migrations import discover_migrations
    from backend.migrations.runner import apply_migrations
    from backend.locks import sweep as locks_sweep_module
    from backend import config

    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    apply_migrations(conn, discover_migrations())
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) "
        "VALUES ('alice','x','user',?,?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
        "sentence_count, text_density, estimated_difficulty, created_at) "
        "VALUES ('doc_swp','x.json','text',1,1,1.0,'Kolay',?)",
        (now,),
    )
    # Insert an already-expired lock
    from datetime import datetime, timezone, timedelta
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    conn.execute(
        "INSERT INTO document_locks(document_id, user_id, acquired_at, last_heartbeat, expires_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("doc_swp", 1, past, past, past),
    )
    conn.close()

    queue = sse_broker.subscribe(user_id=1)
    try:
        async def _do_sweep():
            # Use the public helper that wraps a single sweep iteration with publish
            await locks_sweep_module.sweep_once_and_publish()

        asyncio.run(_do_sweep())

        async def _wait():
            return await asyncio.wait_for(queue.get(), timeout=2.0)
        event = asyncio.run(_wait())
        assert event.event_type == "lock_released"
        assert event.data["document_id"] == "doc_swp"
        # by_user_id is None for sweep-driven releases (we don't track which user held it)
        assert event.data.get("by_user_id") is None
        assert event.data["reason"] == "sweep_expired"
    finally:
        sse_broker.unsubscribe(1, queue)
