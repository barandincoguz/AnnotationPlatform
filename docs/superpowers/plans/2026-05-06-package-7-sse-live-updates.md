# Paket 7 — SSE + Live Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /api/events` Server-Sent Events stream + publish hooks in Paket 5 routes (locks acquire/release/sweep, annotation save/complete) so multiple connected users see live updates without polling.

**Architecture:** Existing `backend/shared/sse.py` SSEBroker singleton handles per-user-queue pub/sub (already tested). This paket adds:
1. `GET /api/events` async streaming endpoint that subscribes the user, yields SSE-formatted events from their queue, sends `: ping` keepalive every 30s, unsubscribes on disconnect.
2. Publish calls in lock acquire/release routes + sweep loop.
3. Publish calls in annotation save/complete routes.

Routes that publish convert from `def` to `async def` (sync DB calls work fine inside async handlers).

**Tech Stack:** FastAPI `StreamingResponse`, `asyncio.Queue`, JSON, the existing SSEBroker singleton at `backend.shared.sse.broker`.

---

## Mimari Kararlar (Locked)

- **Stream format:** Standard SSE — `event: TYPE\ndata: JSON\n\n`. Comments (`: ping\n\n`) sent every 30s as keepalive (proxies/load balancers cut idle connections).
- **Connection lifecycle:** On HTTP request, subscribe a fresh `asyncio.Queue` to the broker for that user. On client disconnect or any exception, unsubscribe in a `finally:` block.
- **Auth on /api/events:** `require_passed_training` (consistent with Paket 5/6 routes). Anonymous EventSource → 401.
- **Multi-tab safe:** Broker already supports multiple queues per user (verified by existing `test_user_can_have_multiple_queues_one_per_tab`). Each browser tab opens its own EventSource → its own queue.
- **Event semantics:**
  - `lock_acquired` → broadcast: `{document_id, by_user_id, by_username, expires_at}`
  - `lock_released` → broadcast: `{document_id, by_user_id?}` (`by_user_id` present when fired by route, omitted/None for sweep-driven release)
  - `annotation_saved` → broadcast: `{document_id, user_id, username, action, is_diff_zero, ref_count}`
  - `annotation_completed` → broadcast: `{document_id, user_id, username, completed: bool}`
- **Heartbeat:** Skipped — no event. Heartbeat is internal lifecycle, not user-facing news.
- **Skip:** No event. Skipping is private to the user (other users don't need to know).
- **Draft autosave:** No event. Frontend manages its own draft state.
- **`publish_to_others` vs `publish_broadcast`:** Use `broadcast` for everything. Self gets own events back too — frontend consumers idempotently handle (TanStack Query just re-fetches; UI ignores own lock_acquired since it already animates).
- **Service vs route:** Publish calls live in **routes**, not services. Services stay sync + DB-only. Routes (becoming `async def`) call sync service then `await broker.publish_broadcast(...)`.
- **Sweep:** Already async. Adds a single `await broker.publish_broadcast("lock_released", {document_id})` per released doc.
- **JSON serialization:** Standard `json.dumps(...)` — no custom encoder needed (events carry simple primitives).
- **Error isolation:** A failed publish must NOT roll back the DB write. Routes call `broker.publish_broadcast(...)` AFTER the service returns successfully, in a `try/except Exception: log.exception(...)` so a broker bug can't 500 the request.
- **Stream content type:** `text/event-stream` (FastAPI's `StreamingResponse(media_type="text/event-stream")`).
- **Reconnect:** Standard SSE clients auto-reconnect. We don't track Last-Event-ID — events are fire-and-forget, missing events on reconnect is acceptable (frontend re-fetches state on reconnect via TanStack Query).
- **Slow consumer:** Broker already handles `QueueFull` by dropping (verified in `backend/shared/sse.py:50`). No-op here.

## Dosya Yapısı

```
backend/sse/                         # NEW package
├── __init__.py                      # boş
└── routes.py                        # GET /api/events + helper format_sse_message

backend/locks/routes.py              # MODIFIED: acquire/release become async, publish events
backend/locks/sweep.py               # MODIFIED: sweep_loop publishes lock_released per doc
backend/annotations/routes.py        # MODIFIED: save/complete become async, publish events
backend/main.py                      # MODIFIED: mount sse_router

tests/test_sse_routes.py             # NEW — HTTP integration smoke + broker-via-HTTP E2E
tests/test_sse_publish_locks.py      # NEW — verify locks routes publish correct events
tests/test_sse_publish_annotations.py  # NEW — verify annotations routes publish correct events
tests/test_sse_publish_sweep.py      # NEW — verify sweep loop publishes lock_released
```

---

## Task 1: SSE Stream Endpoint (`GET /api/events`)

**Goal:** Async streaming endpoint that subscribes the requesting user, yields SSE-formatted events, sends keepalive every 30s, cleans up on disconnect.

**Files:**
- Create: `backend/sse/__init__.py`
- Create: `backend/sse/routes.py`
- Modify: `backend/main.py` (mount `sse_router`)
- Create: `tests/test_sse_routes.py`

- [ ] **Step 1: Create empty package**

Run:
```bash
mkdir -p /Users/barandincoguz/Desktop/deneme/backend/sse
touch /Users/barandincoguz/Desktop/deneme/backend/sse/__init__.py
```

- [ ] **Step 2: Write `tests/test_sse_routes.py`**

```python
"""HTTP-level tests for GET /api/events.

Stream-reading is tricky in tests, so we mostly assert content type,
auth gating, and connection establishment. The broker→event delivery is
verified end-to-end by the dedicated test_sse_publish_*.py suites.
"""
import asyncio
import json
import pytest
from backend.shared.sse import broker as sse_broker, SSEBroker


def _reset_broker_subscribers():
    """Clear the singleton broker's subscribers between tests."""
    sse_broker._subscribers.clear()


def test_events_requires_auth(client):
    _reset_broker_subscribers()
    r = client.get("/api/events", timeout=2.0)
    assert r.status_code == 401


def test_events_requires_training_passed(client):
    """Untrained user (default has_passed_training=0) gets 409."""
    _reset_broker_subscribers()
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("INV-SSE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "u_sse_untrained", "password": "password123",
        "invite_code": "INV-SSE",
    })
    client.post("/api/auth/login", json={
        "username": "u_sse_untrained", "password": "password123",
    })
    r = client.get("/api/events", timeout=2.0)
    # require_seen_manual fires before training check; either 409 surfaces
    assert r.status_code == 409
    error = r.json()["detail"]["error"]
    assert error in ("manual_not_seen", "training_not_passed")


def test_events_returns_event_stream_content_type(passed_user):
    """Authenticated trained user gets text/event-stream content type."""
    _reset_broker_subscribers()
    c = passed_user["client"]
    # Open as stream — read just the headers, then close
    with c.stream("GET", "/api/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")


def test_events_subscribes_user_to_broker(passed_user):
    """Opening the stream should register the user in broker.online_user_ids()."""
    _reset_broker_subscribers()
    c = passed_user["client"]
    user_id = passed_user["user"]["id"]

    assert user_id not in sse_broker.online_user_ids()

    # Open the stream and read at least one byte (forces handler to start)
    with c.stream("GET", "/api/events") as r:
        # consume first chunk (ping or initial event) to make sure the generator entered
        # the subscribe block — but don't block forever.
        try:
            it = r.iter_raw(chunk_size=1)
            # Wait at most 1s for first byte. If subscription is wired correctly,
            # the broker will list this user almost immediately. We don't need bytes
            # to assert that — just need the handler to have started.
            # Sleep briefly to let the async task spin up.
            import time
            time.sleep(0.2)
            assert user_id in sse_broker.online_user_ids()
        finally:
            r.close()


def test_events_unsubscribes_on_disconnect(passed_user):
    """Closing the stream removes the user from broker subscribers."""
    _reset_broker_subscribers()
    c = passed_user["client"]
    user_id = passed_user["user"]["id"]

    with c.stream("GET", "/api/events") as r:
        import time
        time.sleep(0.2)
        assert user_id in sse_broker.online_user_ids()
        # closes on context exit

    # After disconnect, broker.online_user_ids() should drop this user
    # (may take a moment for the generator's finally block to run)
    import time
    time.sleep(0.3)
    assert user_id not in sse_broker.online_user_ids()


# Module-scope helper for SSE message formatting (defined in routes.py, exported for tests)
def test_format_sse_message_event_only():
    from backend.sse.routes import format_sse_message
    msg = format_sse_message(event_type="lock_acquired", data={"document_id": "d1"})
    assert msg == 'event: lock_acquired\ndata: {"document_id": "d1"}\n\n'


def test_format_sse_message_data_only_no_event_type():
    """When event_type is None, only the data line is emitted (default 'message' event)."""
    from backend.sse.routes import format_sse_message
    msg = format_sse_message(event_type=None, data={"x": 1})
    assert msg == 'data: {"x": 1}\n\n'
```

- [ ] **Step 3: Run failing tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -m pytest tests/test_sse_routes.py -q
```
Expected: ImportError / route 404.

- [ ] **Step 4: Implement `backend/sse/routes.py`**

```python
"""GET /api/events — Server-Sent Events stream for live updates.

Each request gets its own asyncio.Queue subscribed to the broker. The
generator yields formatted SSE messages until the client disconnects or
the queue raises (broker shutdown). A `: ping\\n\\n` comment is sent
every 30s to keep the connection open through proxies/load balancers.

Cleanup: the queue is unsubscribed in `finally:` so disconnects don't
leak subscribers.
"""
import asyncio
import json
import logging
import sqlite3
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.shared.sse import broker
from backend.users.deps import require_passed_training


router = APIRouter(prefix="/api", tags=["sse"])
log = logging.getLogger(__name__)

KEEPALIVE_INTERVAL_SECONDS = 30.0


def format_sse_message(*, event_type: Optional[str], data: dict) -> str:
    """Format one event per the SSE wire protocol.

    If event_type is None, only the data line is emitted (default
    'message' event listener handles it). Otherwise an `event: TYPE`
    line precedes the data.
    """
    payload = json.dumps(data)
    if event_type is None:
        return f"data: {payload}\n\n"
    return f"event: {event_type}\ndata: {payload}\n\n"


async def _stream_for_user(user_id: int) -> AsyncIterator[str]:
    """Subscribe to broker; yield SSE messages until cancelled."""
    queue = broker.subscribe(user_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_INTERVAL_SECONDS)
                yield format_sse_message(event_type=event.event_type, data=event.data)
            except asyncio.TimeoutError:
                # Idle keepalive — comments are ignored by EventSource clients.
                yield ": ping\n\n"
    except asyncio.CancelledError:
        # Client disconnected; let the finally block clean up.
        raise
    except Exception:
        log.exception("SSE stream errored for user_id=%s", user_id)
        raise
    finally:
        broker.unsubscribe(user_id, queue)


@router.get("/events")
async def events(
    user: sqlite3.Row = Depends(require_passed_training),
):
    return StreamingResponse(
        _stream_for_user(user["id"]),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if behind proxy
        },
    )
```

- [ ] **Step 5: Mount router in `backend/main.py`**

Read the file first to find the exact insertion point. Add to the imports section (after `from backend.shuffle.routes import router as shuffle_router`):

```python
from backend.sse.routes import router as sse_router
```

After the existing `app.include_router(shuffle_router)`, add:

```python
app.include_router(sse_router)
```

- [ ] **Step 6: Run tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -m pytest tests/test_sse_routes.py -q
```
Expected: 7 tests pass.

- [ ] **Step 7: Run full suite**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -m pytest -q
```
Expected: 0 failures (current 270 + 7 new ≈ 277).

- [ ] **Step 8: Commit**

```bash
cd /Users/barandincoguz/Desktop/deneme && git -c user.email=maarkval@icloud.com -c user.name=baran add backend/sse backend/main.py tests/test_sse_routes.py && git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(sse): add GET /api/events streaming endpoint

Async generator subscribes the user to the singleton SSEBroker and yields
SSE-formatted messages from their per-request queue. Sends `: ping`
comment every 30s as keepalive (preserves connection through proxies that
cut idle TCP). Unsubscribes in finally: so disconnects don't leak queues.
Auth: require_passed_training (matches Paket 5/6 gating).

format_sse_message helper is exported for routes that need to build
messages outside the streaming generator (e.g. pre-flight buffering).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Publish on Lock Acquire/Release/Sweep

**Goal:** lock_acquired and lock_released events broadcast on every acquire/release operation. Sweep loop publishes one lock_released per expired doc.

**Files:**
- Modify: `backend/locks/routes.py` — convert acquire + release to `async def`, publish events
- Modify: `backend/locks/sweep.py` — publish lock_released for each released doc
- Create: `tests/test_sse_publish_locks.py`

- [ ] **Step 1: Write `tests/test_sse_publish_locks.py`**

```python
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


def test_sweep_publishes_lock_released_for_each_expired(db_path, tmp_path, monkeypatch):
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
    finally:
        sse_broker.unsubscribe(1, queue)
```

- [ ] **Step 2: Run failing tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -m pytest tests/test_sse_publish_locks.py -q
```
Expected: failures (no publish calls yet, no `sweep_once_and_publish` helper yet).

- [ ] **Step 3: Modify `backend/locks/routes.py` — convert acquire + release to async + publish**

Read the file first. Replace the `acquire` function with:

```python
@router.post(
    "/{document_id}/acquire",
    response_model=LockInfo,
    responses={409: {"model": LockConflict}},
)
async def acquire(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        info = service.acquire(db, document_id=document_id, user_id=user["id"])
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    except service.LockHeldByOther as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "lock_held_by_other",
                "by_user_id": e.info["by_user_id"],
                "by_username": e.info["by_username"],
                "acquired_at": e.info["acquired_at"],
                "expires_at": e.info["expires_at"],
            },
        )
    response = _strip_dup_keys(info)
    try:
        await sse_broker.publish_broadcast(
            "lock_acquired",
            {
                "document_id": document_id,
                "by_user_id": info["user_id"],
                "by_username": info["by_username"],
                "expires_at": info["expires_at"],
            },
        )
    except Exception:
        log.exception("publish lock_acquired failed for %s", document_id)
    return response
```

Replace the `release` function with:

```python
@router.post("/{document_id}/release", response_model=OkResponse)
async def release(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    # Read whether the user actually held a lock — service.release is silent on absent.
    held = service.get_lock(db, document_id)
    holder_user_id = held["user_id"] if held and held["user_id"] == user["id"] else None

    try:
        service.release(db, document_id=document_id, user_id=user["id"])
    except service.NotLockHolder:
        raise HTTPException(status_code=404, detail="lock held by another user")

    if holder_user_id is not None:
        try:
            await sse_broker.publish_broadcast(
                "lock_released",
                {"document_id": document_id, "by_user_id": holder_user_id},
            )
        except Exception:
            log.exception("publish lock_released failed for %s", document_id)
    return {"ok": True}
```

Add to the top of the file (with other imports):

```python
import logging
from backend.shared.sse import broker as sse_broker

log = logging.getLogger(__name__)
```

(The `heartbeat` route stays sync — no broadcast.)

- [ ] **Step 4: Modify `backend/locks/sweep.py` — add `sweep_once_and_publish` + use it in the loop**

Replace the existing `sweep_loop` body with one that uses a new helper:

```python
"""Background sweep — periodically clears expired locks.

Runs every `interval_seconds` (default 60). Started from main.py lifespan,
cancelled on shutdown. Single-process; safe with WAL mode.

Publishes one lock_released SSE event per released doc (by_user_id=None
since the sweep doesn't surface the original holder to consumers).
"""
import asyncio
import logging
from typing import Optional

from backend import config
from backend.shared.db import connect
from backend.shared.sse import broker as sse_broker
from backend.locks import service

log = logging.getLogger(__name__)


async def sweep_once_and_publish() -> list[str]:
    """Run one sweep iteration and broadcast lock_released for each released doc.

    Exposed for tests so a single sweep can be triggered without the loop's
    sleep. Returns the list of released document_ids.
    """
    conn = connect(config.DB_PATH)
    try:
        released = service.sweep_expired(conn)
    finally:
        conn.close()

    for document_id in released:
        try:
            await sse_broker.publish_broadcast(
                "lock_released",
                {"document_id": document_id, "by_user_id": None},
            )
        except Exception:
            log.exception("publish lock_released failed for %s", document_id)
    if released:
        log.info("Lock sweep released %d locks: %s", len(released), released)
    return released


async def sweep_loop(interval_seconds: int = 60) -> None:
    """Async loop. Cancel via task.cancel()."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await sweep_once_and_publish()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("Lock sweep iteration failed")


_task: Optional[asyncio.Task] = None


def start(interval_seconds: int = 60) -> asyncio.Task:
    """Start the sweep task; returns the task handle for shutdown cancellation."""
    global _task
    _task = asyncio.create_task(sweep_loop(interval_seconds))
    return _task


def stop() -> None:
    """Cancel the running sweep task (no-op if not started)."""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
    _task = None
```

- [ ] **Step 5: Run tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -m pytest tests/test_sse_publish_locks.py tests/test_locks_routes.py tests/test_locks_service.py -q
```
Expected: all pass (5 new + 12 + 9 = 26).

- [ ] **Step 6: Run full suite**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -m pytest -q
```
Expected: 0 failures.

- [ ] **Step 7: Commit**

```bash
cd /Users/barandincoguz/Desktop/deneme && git -c user.email=maarkval@icloud.com -c user.name=baran add backend/locks/routes.py backend/locks/sweep.py tests/test_sse_publish_locks.py && git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(sse): publish lock_acquired / lock_released events

acquire and release routes are now async and broadcast their events after
the DB write succeeds. Publish failures are logged and swallowed — broker
issues never roll back the DB write. release publishes only when the user
actually held the lock (silent no-op path emits nothing).

Sweep loop refactored: sweep_once_and_publish() does one iteration and
emits lock_released (by_user_id=null) per released doc. The loop wraps
this with the 60s sleep + cancellation handling.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Publish on Annotation Save / Complete

**Goal:** annotation_saved fires on every successful POST /api/annotations; annotation_completed fires on every successful complete toggle.

**Files:**
- Modify: `backend/annotations/routes.py` — convert save + complete to `async def`, publish events
- Create: `tests/test_sse_publish_annotations.py`

- [ ] **Step 1: Write `tests/test_sse_publish_annotations.py`**

```python
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
```

- [ ] **Step 2: Run failing tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -m pytest tests/test_sse_publish_annotations.py -q
```
Expected: failures (no publish calls in routes yet).

- [ ] **Step 3: Modify `backend/annotations/routes.py` — convert save + complete to async + publish**

Read the file first. Replace the `save` function body with:

```python
@router.post(
    "/annotations",
    response_model=SaveAnnotationResponse,
)
async def save(
    payload: SaveAnnotationRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    refs = [r.model_dump() for r in payload.references]
    try:
        result = service.save_annotation(
            db,
            document_id=payload.document_id,
            user_id=user["id"],
            references=refs,
        )
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {payload.document_id} not found")
    except (DuplicateReference, InvalidReference) as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        action = "create" if result["is_new"] else "edit"
        await sse_broker.publish_broadcast(
            "annotation_saved",
            {
                "document_id": payload.document_id,
                "user_id": user["id"],
                "username": user["username"],
                "action": action,
                "is_diff_zero": result["is_diff_zero"],
                "ref_count": len(result["current_references"]),
            },
        )
    except Exception:
        log.exception("publish annotation_saved failed for %s", payload.document_id)
    return result
```

Replace the `complete` function with:

```python
@router.post(
    "/annotations/{document_id}/complete",
    response_model=OkResponse,
)
async def complete(
    document_id: str,
    payload: CompleteRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    # Read prior state so we know whether this is a real toggle or a no-op
    prior = service.get_annotation(db, document_id)
    will_change = prior is not None and prior["is_completed"] != payload.completed

    try:
        service.set_complete(
            db, document_id=document_id, user_id=user["id"],
            completed=payload.completed,
        )
    except service.AnnotationNotFound:
        raise HTTPException(status_code=404, detail=f"no annotation for {document_id}")

    if will_change:
        try:
            await sse_broker.publish_broadcast(
                "annotation_completed",
                {
                    "document_id": document_id,
                    "user_id": user["id"],
                    "username": user["username"],
                    "completed": payload.completed,
                },
            )
        except Exception:
            log.exception("publish annotation_completed failed for %s", document_id)
    return {"ok": True}
```

Add to the top of the file (with other imports):

```python
import logging
from backend.shared.sse import broker as sse_broker

log = logging.getLogger(__name__)
```

(`skip` route stays sync — no broadcast. Drafts routes stay sync.)

- [ ] **Step 4: Run tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -m pytest tests/test_sse_publish_annotations.py tests/test_annotations_routes.py tests/test_paket5_e2e.py -q
```
Expected: all pass.

- [ ] **Step 5: Run full suite**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -m pytest -q
```
Expected: 0 failures.

- [ ] **Step 6: Commit**

```bash
cd /Users/barandincoguz/Desktop/deneme && git -c user.email=maarkval@icloud.com -c user.name=baran add backend/annotations/routes.py tests/test_sse_publish_annotations.py && git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(sse): publish annotation_saved / annotation_completed events

save and complete routes are now async and broadcast their events after
the DB write succeeds. Skip stays silent (private user action).
Idempotent complete toggle (same-state) doesn't fire — only real state
changes broadcast. Publish failures are logged and swallowed; the DB
write is never rolled back by a broker issue.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Smoke Test + Tag

**Goal:** Confirm the route is mounted, OpenAPI exposes it, and tag the package release.

**Files:**
- (no new code; verification + tag only)

- [ ] **Step 1: Smoke test the route registration**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -c "from backend.main import app; paths = sorted([r.path for r in app.routes if hasattr(r,'path')]); print('\\n'.join(p for p in paths if 'event' in p))"
```
Expected output: `/api/events`

- [ ] **Step 2: Verify the OpenAPI spec includes the endpoint**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -c "
from backend.main import app
schema = app.openapi()
events_op = schema['paths']['/api/events']['get']
print('summary tag:', events_op.get('tags'))
print('200 content:', list(events_op['responses']['200']['content'].keys()) if events_op['responses'].get('200') else 'no 200 documented')
"
```
Expected: `summary tag: ['sse']`. (200 response may be missing because StreamingResponse doesn't auto-document a schema — that's fine for v1.)

- [ ] **Step 3: Run full suite**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && .venv/bin/python -m pytest -q
```
Expected: 0 failures.

- [ ] **Step 4: Tag**

```bash
cd /Users/barandincoguz/Desktop/deneme && git tag paket-7-sse-live-updates && git tag --list "paket-*"
```
Expected: list shows paket-1 through paket-7.

---

## Verification

After Task 4:

- All Paket 7 files exist with the layout in §"Dosya Yapısı"
- `python -m pytest -q` reports 0 failures
- `paket-7-sse-live-updates` tag points at the most recent commit
- `git log --oneline 65380df..HEAD` shows the new commits ordered correctly
- 4 SSE event types are emitted by their respective sources:
  - `lock_acquired` — locks/routes.py acquire()
  - `lock_released` — locks/routes.py release() AND locks/sweep.py sweep_once_and_publish()
  - `annotation_saved` — annotations/routes.py save()
  - `annotation_completed` — annotations/routes.py complete() (only on actual state change)

## Open Items For Later Packages (NOT this paket)

- **Paket 8 (Behavioral Detectors):** speed_warning + char_limit_warning events — broker.publish_to(user_id) for personal warnings.
- **Paket 9 (Gamification):** badge_unlocked, xp_delta, streak_extended events.
- **Paket 9 (Notifications):** notification_received broadcast to specific user.
- **Presence (online users count):** Spec mentions online avatars (line 1060). Not in scope here; could be added in Paket 9 by exposing `broker.online_user_ids()` count via `/api/me/presence` or similar.
- **Reconnect with Last-Event-ID:** Spec doesn't require it. Frontend re-fetches state on reconnect via TanStack Query.
- **Paket 16 (Frontend):** `useSSE()` hook subscribes to EventSource and dispatches into TanStack Query cache.

## Self-Review Notes

- **Spec coverage:**
  - `GET /api/events SSE` from spec line 693 ✓
  - `lock_acquired` / `lock_released` broadcast events from spec line 862-863 ✓
  - `require_passed_training` gating consistent with Paket 5/6 ✓
  - SSE broker singleton already in place from Paket 1 ✓
- **Type consistency:** `format_sse_message` signature matches its tests; broker singleton imported as `sse_broker` consistently.
- **No placeholders:** Every step contains the actual file content / command / expected output. Validation errors mapped to status codes consistently.
- **Performance sanity:** Each publish is `await broker.publish_broadcast(...)` — broker iterates subscribers and `put_nowait`s to each queue; slow consumers get dropped at line 50 of sse.py (verified in test). For 30 users, this is O(30) per event.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-06-package-7-sse-live-updates.md`.**
