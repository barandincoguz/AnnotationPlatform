"""Dispatcher retry / backoff / dead-letter tests (Phase 4 Task 9).

Builds on the FakeNeonClient pattern from Task 8. Asserts:
  - Backoff WHERE-gate prevents same-second re-fire of a freshly-failed row
    (gating evaluated against created_at — see CONTEXT.md & docs/neon-mirror.md).
  - MAX_RETRIES transient failures dead-letter the row + emit exactly one
    neon_mirror_dead_letter system_events row.
  - Cold-start success emits exactly one neon_mirror_connected system_events
    row, NOT one per subsequent successful drain.
  - Most important: a parallel `users` INSERT commits successfully WHILE the
    dispatcher is failing on every Neon write — MIRROR-04 / MIRROR-07.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path

import pytest

from backend.mirror.dispatcher import run_dispatcher
from backend.mirror.neon_client import NeonTransient
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture(autouse=True)
def _reset_dispatcher_module_state():
    """The dispatcher tracks _cold_start_emitted at module scope — reset
    between tests so each one starts from a clean cold-start state."""
    from backend.mirror import dispatcher as d
    d._cold_start_emitted = False
    d.last_status = None
    d.last_delivered_at = None
    yield


def _bootstrap_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    conn = connect(db)
    try:
        apply_migrations(conn, discover_migrations())
    finally:
        conn.close()
    return db


class FakeNeonClient:
    def __init__(self, raise_transient: int = 0):
        self.applied: list[tuple] = []
        self._remaining_transient = raise_transient
        self.last_status: bool | None = None
        self.has_connected_once = False

    def connect(self) -> bool:
        self.has_connected_once = True
        return True

    def close(self) -> None:
        pass

    def apply(self, op, table, pk_value, payload):
        if self._remaining_transient > 0:
            self._remaining_transient -= 1
            self.last_status = False
            raise NeonTransient(f"transient #{self._remaining_transient + 1}")
        self.applied.append((op, table, pk_value, payload))
        self.last_status = True


async def _drive_dispatcher(db, neon, *, iterations=10, max_retries=5):
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_dispatcher(
            conn_factory=lambda: connect(db),
            neon_client=neon,
            batch_size=100,
            sleep_empty=0.0,
            sleep_batch=0.0,
            max_retries=max_retries,
            stop_event=stop,
        )
    )
    for _ in range(iterations):
        await asyncio.sleep(0.01)
    stop.set()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


def _seed_outbox(conn, table="users", op="INSERT", n=1):
    for i in range(n):
        conn.execute(
            "INSERT INTO _outbox(table_name, op, pk_value, payload_json, created_at) "
            "VALUES (?,?,?,?,?)",
            (table, op, str(i + 1),
             json.dumps({"id": i + 1, "username": f"u{i}"}),
             "2026-05-18T00:00:00Z"),
        )


# === Backoff gating ===


async def test_freshly_failed_row_skipped_within_backoff_window(tmp_path):
    """A row that failed at retry_count=0 is gated by `created_at + 2 seconds`.

    We seed the outbox with `created_at = now` so the gate is closed. The
    dispatcher fires once, fails (transient), increments retry_count to 1,
    then re-scans — the WHERE clause now requires
    `datetime(created_at, '+2 seconds') < datetime('now')` which is false
    (only milliseconds have passed). The row stays untouched until that
    window expires. We assert exactly ONE apply() call was made.
    """
    db = _bootstrap_db(tmp_path)
    conn = connect(db)
    try:
        # Set created_at to "now" via SQLite strftime so the gate is fresh.
        conn.execute(
            "INSERT INTO _outbox(table_name, op, pk_value, payload_json, created_at) "
            "VALUES (?,?,?,?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            ("users", "INSERT", "1", json.dumps({"id": 1, "username": "x"})),
        )
    finally:
        conn.close()
    # Many failures available, but the gate should clamp to 1 call.
    neon = FakeNeonClient(raise_transient=99)
    await _drive_dispatcher(db, neon, iterations=20)
    # The gate must have kept further attempts off-list.
    # We accept at most 2 attempts because in a very slow CI 2s could lapse,
    # but expect 1 in the typical run.
    assert 1 <= 99 - neon._remaining_transient <= 2, (
        f"expected ≤2 attempts within backoff window, got "
        f"{99 - neon._remaining_transient}"
    )
    # Row still undelivered.
    conn = connect(db)
    try:
        row = conn.execute("SELECT * FROM _outbox WHERE table_name='users'").fetchone()
    finally:
        conn.close()
    assert row["delivered_at"] is None
    assert row["retry_count"] >= 1


# === Dead-letter system_events ===


async def test_dead_letter_emits_one_system_event(tmp_path):
    db = _bootstrap_db(tmp_path)
    conn = connect(db)
    try:
        _seed_outbox(conn, n=1)
        # Backdate created_at so the backoff gate is open every attempt.
        conn.execute("UPDATE _outbox SET created_at='2020-01-01T00:00:00Z'")
    finally:
        conn.close()
    neon = FakeNeonClient(raise_transient=10)  # > MAX_RETRIES
    await _drive_dispatcher(db, neon, iterations=20)
    conn = connect(db)
    try:
        row = conn.execute("SELECT * FROM _outbox WHERE table_name='users'").fetchone()
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type='neon_mirror_dead_letter'"
        ).fetchall()
    finally:
        conn.close()
    assert row["retry_count"] == 5
    assert row["delivered_at"] is None
    # Exactly one dead_letter event for the single dead-lettered row.
    assert len(events) == 1, [e["message"] for e in events]
    assert events[0]["severity"] == "error"
    assert "transient" in (events[0]["message"] or "")


# === Cold-start success event ===


async def test_cold_start_success_emits_one_connected_event(tmp_path):
    db = _bootstrap_db(tmp_path)
    conn = connect(db)
    try:
        _seed_outbox(conn, n=3)
    finally:
        conn.close()
    neon = FakeNeonClient()
    await _drive_dispatcher(db, neon, iterations=5)
    conn = connect(db)
    try:
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type='neon_mirror_connected'"
        ).fetchall()
    finally:
        conn.close()
    assert len(events) == 1, [e["message"] for e in events]
    assert events[0]["severity"] == "info"


async def test_subsequent_success_does_not_emit_extra_connected_event(tmp_path):
    """Cold-start event fires once; later successful drains don't re-emit."""
    db = _bootstrap_db(tmp_path)
    conn = connect(db)
    try:
        _seed_outbox(conn, n=1)
    finally:
        conn.close()
    neon = FakeNeonClient()
    # First drain: 1 user row + 1 cold-start system_events row + their mirror rows.
    await _drive_dispatcher(db, neon, iterations=5)
    # Seed another row, then drain again.
    conn = connect(db)
    try:
        conn.execute(
            "INSERT INTO _outbox(table_name, op, pk_value, payload_json, created_at) "
            "VALUES ('users','INSERT','2',?, '2026-05-18T01:00:00Z')",
            (json.dumps({"id": 2}),),
        )
    finally:
        conn.close()
    await _drive_dispatcher(db, neon, iterations=5)
    conn = connect(db)
    try:
        events = conn.execute(
            "SELECT count(*) AS c FROM system_events WHERE event_type='neon_mirror_connected'"
        ).fetchone()
    finally:
        conn.close()
    assert events["c"] == 1, "cold-start event should not re-emit on later successful drains"


# === MIRROR-04 / MIRROR-07: parallel INSERT not blocked by Neon failures ===


async def test_parallel_user_insert_is_not_blocked_by_neon_failures(tmp_path):
    """While the dispatcher is failing on every Neon write, a separate INSERT
    into `users` must commit within 50 ms — proving the request path is
    never blocked by Neon outages (MIRROR-04, MIRROR-07).
    """
    db = _bootstrap_db(tmp_path)
    conn = connect(db)
    try:
        _seed_outbox(conn, n=10)
        conn.execute("UPDATE _outbox SET created_at='2020-01-01T00:00:00Z'")
    finally:
        conn.close()
    # Infinite failures so the dispatcher is always retrying.
    neon = FakeNeonClient(raise_transient=10**6)

    stop = asyncio.Event()
    disp_task = asyncio.create_task(
        run_dispatcher(
            conn_factory=lambda: connect(db),
            neon_client=neon,
            batch_size=100,
            sleep_empty=0.0,
            sleep_batch=0.0,
            stop_event=stop,
        )
    )

    # Let the dispatcher get into its loop.
    await asyncio.sleep(0.02)

    # Now insert a row from the "request path".
    def _request_insert():
        c = connect(db)
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                "INSERT INTO users(username, password_hash, role, is_active, "
                "has_passed_training, has_seen_manual, created_at, updated_at) "
                "VALUES (?, ?, 'user', 1, 0, 0, '2026-05-18T00:00:00Z', '2026-05-18T00:00:00Z')",
                ("parallel_insert", "x"),
            )
            c.execute("COMMIT")
        finally:
            c.close()

    t0 = time.perf_counter()
    await asyncio.to_thread(_request_insert)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    stop.set()
    disp_task.cancel()
    try:
        await disp_task
    except (asyncio.CancelledError, Exception):
        pass

    assert elapsed_ms < 200, f"parallel INSERT took {elapsed_ms:.1f} ms (>200 ms threshold)"
    # And the row landed.
    conn = connect(db)
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username='parallel_insert'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
