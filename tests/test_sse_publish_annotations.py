"""Verify annotation routes publish the right SSE events to the broker."""
import asyncio
import pytest
from backend.shared.sse import broker as sse_broker


def _reset_broker():
    sse_broker._subscribers.clear()


def _ref(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "x"}
    base.update(kwargs)
    return base


def test_save_publishes_annotation_saved(passed_user, ingest_doc):
    """POST /api/annotations broadcasts annotation_saved with action + ref_count + diff_zero."""
    _reset_broker()
    user_id = passed_user["user"]["id"]
    queue = sse_broker.subscribe(user_id=user_id)
    try:
        ingest_doc("doc_pub_save")
        r = passed_user["client"].post("/api/annotations", json={
            "document_id": "doc_pub_save",
            "references": [_ref(source_text="x"), _ref(kanun_no="193", source_text="y")],
        })
        assert r.status_code == 200

        async def _wait():
            return await asyncio.wait_for(queue.get(), timeout=2.0)
        event = asyncio.run(_wait())
        assert event.event_type == "annotation_saved"
        assert event.data["document_id"] == "doc_pub_save"
        assert event.data["user_id"] == user_id
        assert event.data["username"] == "alice"
        assert event.data["action"] == "create"
        assert event.data["ref_count"] == 2
        assert event.data["is_diff_zero"] is False
    finally:
        sse_broker.unsubscribe(user_id, queue)


def test_save_validation_failure_does_not_publish(passed_user, ingest_doc):
    """Duplicate-ref payload returns 422 — no event should fire."""
    _reset_broker()
    user_id = passed_user["user"]["id"]
    queue = sse_broker.subscribe(user_id=user_id)
    try:
        ingest_doc("doc_pub_fail")
        r = passed_user["client"].post("/api/annotations", json={
            "document_id": "doc_pub_fail",
            "references": [_ref(kanun_no="193", source_text="dup"),
                           _ref(kanun_no="193", source_text="dup")],
        })
        assert r.status_code == 422

        async def _wait():
            return await asyncio.wait_for(queue.get(), timeout=0.5)
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(_wait())
    finally:
        sse_broker.unsubscribe(user_id, queue)


def test_complete_publishes_annotation_completed(passed_user, ingest_doc):
    """POST /api/annotations/{id}/complete broadcasts annotation_completed."""
    _reset_broker()
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_pub_complete")
    c.post("/api/annotations", json={"document_id": "doc_pub_complete", "references": []})

    queue = sse_broker.subscribe(user_id=user_id)
    try:
        r = c.post("/api/annotations/doc_pub_complete/complete", json={"completed": True})
        assert r.status_code == 200

        async def _wait():
            return await asyncio.wait_for(queue.get(), timeout=2.0)
        event = asyncio.run(_wait())
        assert event.event_type == "annotation_completed"
        assert event.data["document_id"] == "doc_pub_complete"
        assert event.data["user_id"] == user_id
        assert event.data["username"] == "alice"
        assert event.data["completed"] is True
    finally:
        sse_broker.unsubscribe(user_id, queue)


def test_complete_uncomplete_publishes_with_completed_false(passed_user, ingest_doc):
    """Toggling back to uncompleted publishes completed:False."""
    _reset_broker()
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_pub_uncomplete")
    c.post("/api/annotations", json={"document_id": "doc_pub_uncomplete", "references": []})
    c.post("/api/annotations/doc_pub_uncomplete/complete", json={"completed": True})

    queue = sse_broker.subscribe(user_id=user_id)
    try:
        c.post("/api/annotations/doc_pub_uncomplete/complete", json={"completed": False})

        async def _wait():
            return await asyncio.wait_for(queue.get(), timeout=2.0)
        event = asyncio.run(_wait())
        assert event.event_type == "annotation_completed"
        assert event.data["completed"] is False
    finally:
        sse_broker.unsubscribe(user_id, queue)


def test_complete_idempotent_noop_does_not_publish(passed_user, ingest_doc):
    """Same-state toggle (already completed → completed=True) is a no-op — no event."""
    _reset_broker()
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_pub_noop")
    c.post("/api/annotations", json={"document_id": "doc_pub_noop", "references": []})
    c.post("/api/annotations/doc_pub_noop/complete", json={"completed": True})

    queue = sse_broker.subscribe(user_id=user_id)
    try:
        # Toggle to the same state — service early-returns
        r = c.post("/api/annotations/doc_pub_noop/complete", json={"completed": True})
        assert r.status_code == 200

        async def _wait():
            return await asyncio.wait_for(queue.get(), timeout=0.5)
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(_wait())
    finally:
        sse_broker.unsubscribe(user_id, queue)


def test_skip_does_not_publish(passed_user, ingest_doc):
    """Skip is private — no event broadcast."""
    _reset_broker()
    user_id = passed_user["user"]["id"]
    queue = sse_broker.subscribe(user_id=user_id)
    try:
        ingest_doc("doc_pub_skip")
        passed_user["client"].post("/api/annotations/doc_pub_skip/skip")

        async def _wait():
            return await asyncio.wait_for(queue.get(), timeout=0.5)
        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(_wait())
    finally:
        sse_broker.unsubscribe(user_id, queue)
