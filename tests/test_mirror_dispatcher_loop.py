"""Dispatcher core-loop tests (Phase 4 Task 8).

Uses a FakeNeonClient (in-process accumulator) so no network is touched.
Backoff + retry are exercised in test_mirror_dispatcher_retry.py (Task 9).
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from backend.mirror import dispatcher as mirror_dispatcher
from backend.mirror.dispatcher import run_dispatcher
from backend.mirror.neon_client import NeonPermanent, NeonTransient
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


def _seed_pending(conn: sqlite3.Connection, n: int = 3) -> list[int]:
    """Insert N pending outbox rows; returns their ids."""
    ids: list[int] = []
    for i in range(n):
        cur = conn.execute(
            "INSERT INTO _outbox(table_name, op, pk_value, payload_json, created_at) "
            "VALUES (?,?,?,?,?)",
            ("users", "INSERT", str(i + 1),
             json.dumps({"id": i + 1, "username": f"u{i}"}),
             "2026-05-18T00:00:00Z"),
        )
        ids.append(cur.lastrowid)
    return ids


def _bootstrap_db(tmp_path: Path) -> Path:
    """Materialize a real on-disk SQLite DB with migrations applied."""
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())
    finally:
        conn.close()
    return db_path


class FakeNeonClient:
    """In-process Neon stand-in. Records every applied call."""

    def __init__(self, raise_transient: int = 0, raise_permanent: int = 0):
        self.applied: list[tuple] = []
        self._remaining_transient = raise_transient
        self._remaining_permanent = raise_permanent
        self.last_status: bool | None = None
        self.has_connected_once = False

    def connect(self) -> bool:
        self.has_connected_once = True
        return True

    def close(self) -> None:
        pass

    def apply(self, op, table, pk_value, payload):
        if self._remaining_permanent > 0:
            self._remaining_permanent -= 1
            self.last_status = False
            raise NeonPermanent("permanent test failure")
        if self._remaining_transient > 0:
            self._remaining_transient -= 1
            self.last_status = False
            raise NeonTransient("transient test failure")
        self.applied.append((op, table, pk_value, payload))
        self.last_status = True


async def _run_dispatcher_briefly(
    db_path: Path,
    neon: FakeNeonClient,
    *,
    iterations: int = 1,
    sleep_empty: float = 0.0,
    sleep_batch: float = 0.0,
    max_retries: int = 5,
) -> None:
    """Run the dispatcher for `iterations` drain cycles then cancel."""
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_dispatcher(
            conn_factory=lambda: connect(db_path),
            neon_client=neon,
            batch_size=100,
            sleep_empty=sleep_empty,
            sleep_batch=sleep_batch,
            max_retries=max_retries,
            stop_event=stop,
        )
    )
    # Cooperative cancellation after at least one drain pass.
    for _ in range(iterations + 1):
        await asyncio.sleep(0.01)
    stop.set()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


# === Tests ===


async def test_drain_three_pending_rows_in_order(tmp_path):
    db = _bootstrap_db(tmp_path)
    conn = connect(db)
    try:
        ids = _seed_pending(conn, n=3)
    finally:
        conn.close()
    neon = FakeNeonClient()
    await _run_dispatcher_briefly(db, neon, iterations=2)
    # All three seeded user rows applied in commit order (id order).
    # NOTE: the dispatcher's own "neon_mirror_connected" system_events row
    # also fires the system_events INSERT trigger → an extra outbox row that
    # the next pass will ship. We only assert ordering of the seeded rows.
    user_applies = [a for a in neon.applied if a[1] == "users"]
    assert [a[2] for a in user_applies] == ["1", "2", "3"], neon.applied
    # All three users rows marked delivered.
    conn = connect(db)
    try:
        rows = conn.execute(
            "SELECT id, delivered_at, retry_count FROM _outbox "
            "WHERE table_name = 'users' ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 3
    assert all(r["delivered_at"] is not None for r in rows)
    assert all(r["retry_count"] == 0 for r in rows)


async def test_transient_failure_keeps_row_undelivered_and_increments_retry(tmp_path):
    db = _bootstrap_db(tmp_path)
    conn = connect(db)
    try:
        _seed_pending(conn, n=1)
    finally:
        conn.close()
    # First three attempts all raise transient; 4th attempt succeeds.
    neon = FakeNeonClient(raise_transient=3)
    # Use a higher iteration count to allow multiple drain passes. We
    # disable the backoff gating by using max_retries large and waiting
    # enough between iterations that the (1 << retry_count) seconds
    # window passes. Easier: pre-stamp created_at well in the past.
    conn = connect(db)
    try:
        conn.execute("UPDATE _outbox SET created_at='2020-01-01T00:00:00Z'")
    finally:
        conn.close()
    await _run_dispatcher_briefly(db, neon, iterations=10, sleep_empty=0.0, sleep_batch=0.0)
    # The row should now be delivered (after 3 transient + 1 success).
    conn = connect(db)
    try:
        row = conn.execute("SELECT * FROM _outbox").fetchone()
    finally:
        conn.close()
    assert row["delivered_at"] is not None, row["error"]
    # retry_count was bumped exactly 3 times before final success.
    assert row["retry_count"] == 3


async def test_max_retries_dead_letters_row(tmp_path):
    db = _bootstrap_db(tmp_path)
    conn = connect(db)
    try:
        _seed_pending(conn, n=1)
        # Backdate created_at so backoff gate is open immediately.
        conn.execute("UPDATE _outbox SET created_at='2020-01-01T00:00:00Z'")
    finally:
        conn.close()
    # 10 transient failures > max_retries=5 — the row dead-letters at attempt 5.
    neon = FakeNeonClient(raise_transient=10)
    await _run_dispatcher_briefly(db, neon, iterations=15, sleep_empty=0.0, sleep_batch=0.0, max_retries=5)
    conn = connect(db)
    try:
        row = conn.execute("SELECT * FROM _outbox").fetchone()
    finally:
        conn.close()
    # Dead-lettered: retry_count = MAX_RETRIES, delivered_at NULL.
    assert row["retry_count"] == 5
    assert row["delivered_at"] is None
    assert "transient" in (row["error"] or "")


async def test_permanent_failure_jumps_to_dead_letter(tmp_path):
    db = _bootstrap_db(tmp_path)
    conn = connect(db)
    try:
        _seed_pending(conn, n=1)
        conn.execute("UPDATE _outbox SET created_at='2020-01-01T00:00:00Z'")
    finally:
        conn.close()
    neon = FakeNeonClient(raise_permanent=1)
    await _run_dispatcher_briefly(db, neon, iterations=2, sleep_empty=0.0, sleep_batch=0.0)
    conn = connect(db)
    try:
        row = conn.execute("SELECT * FROM _outbox").fetchone()
    finally:
        conn.close()
    # NeonPermanent jumps to MAX_RETRIES (5) on the first try.
    assert row["retry_count"] == 5
    assert row["delivered_at"] is None
    assert "permanent" in (row["error"] or "")


async def test_empty_queue_does_not_call_apply(tmp_path):
    db = _bootstrap_db(tmp_path)
    # No seed: outbox is empty.
    neon = FakeNeonClient()
    await _run_dispatcher_briefly(db, neon, iterations=2)
    assert neon.applied == []


async def test_dispatcher_cancellation_is_clean(tmp_path):
    db = _bootstrap_db(tmp_path)
    conn = connect(db)
    try:
        _seed_pending(conn, n=2)
    finally:
        conn.close()
    neon = FakeNeonClient()
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_dispatcher(
            conn_factory=lambda: connect(db),
            neon_client=neon,
            batch_size=100,
            sleep_empty=0.0,
            sleep_batch=0.0,
            stop_event=stop,
        )
    )
    # Let it run briefly, then cancel.
    await asyncio.sleep(0.05)
    stop.set()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    # No partial state: rows should be delivered OR untouched, never both.
    conn = connect(db)
    try:
        rows = conn.execute("SELECT * FROM _outbox").fetchall()
    finally:
        conn.close()
    for r in rows:
        # An outbox row is either delivered (delivered_at set) or untouched
        # (delivered_at NULL and retry_count == 0).
        if r["delivered_at"] is None:
            assert r["retry_count"] == 0


async def test_dispatcher_uses_canonical_connect_helper(tmp_path, monkeypatch):
    """The dispatcher's SQLite connection inherits busy_timeout + WAL PRAGMAs."""
    db = _bootstrap_db(tmp_path)
    pragma_journal: list[str] = []
    pragma_busy: list[int] = []
    pragma_fk: list[int] = []
    real_connect = connect

    def _spy_connect(p):
        c = real_connect(p)
        # Capture PRAGMA state before the dispatcher closes the connection.
        try:
            j = c.execute("PRAGMA journal_mode").fetchone()
            pragma_journal.append(str(j[0] if not hasattr(j, "keys") else j["journal_mode"]).lower())
            b = c.execute("PRAGMA busy_timeout").fetchone()
            pragma_busy.append(int(b[0] if not hasattr(b, "keys") else b["timeout"]))
            f = c.execute("PRAGMA foreign_keys").fetchone()
            pragma_fk.append(int(f[0] if not hasattr(f, "keys") else f["foreign_keys"]))
        except Exception:
            pass
        return c

    monkeypatch.setattr("backend.mirror.dispatcher.connect", _spy_connect)
    # Point config.DB_PATH at our test DB for the default factory.
    import backend.config as bcfg
    monkeypatch.setattr(bcfg, "DB_PATH", db)
    conn = real_connect(db)
    try:
        _seed_pending(conn, n=1)
    finally:
        conn.close()
    neon = FakeNeonClient()
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_dispatcher(
            conn_factory=None,
            neon_client=neon,
            batch_size=100,
            sleep_empty=0.0,
            sleep_batch=0.0,
            stop_event=stop,
        )
    )
    await asyncio.sleep(0.1)
    stop.set()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    assert pragma_journal, "spy did not capture any connection"
    assert pragma_journal[0] == "wal", pragma_journal
    assert pragma_busy[0] == 5000, pragma_busy
    assert pragma_fk[0] == 1, pragma_fk
