"""Tests for the async backup loop."""
import asyncio
from unittest.mock import patch, MagicMock

import pytest


@pytest.mark.asyncio
async def test_backup_once_calls_cycle_in_thread(tmp_path, monkeypatch):
    """backup_once is a single iteration — runs run_backup_cycle inside
    asyncio.to_thread."""
    from backend.backup import loop as backup_loop_mod

    calls = []

    def fake_cycle(db):
        calls.append("cycle")
        return {"snapshot_path": "/x", "committed_sha": None, "pushed": False, "rotated_count": 0}

    with patch("backend.backup.loop.run_backup_cycle", side_effect=fake_cycle), \
         patch("backend.backup.loop.connect") as fake_connect:
        fake_connect.return_value = MagicMock()
        await backup_loop_mod.backup_once()
    assert calls == ["cycle"]


@pytest.mark.asyncio
async def test_backup_loop_cancellation_is_graceful():
    """task.cancel() returns cleanly; CancelledError is swallowed."""
    from backend.backup import loop as backup_loop_mod

    async def slow_cycle():
        await asyncio.sleep(10)

    with patch("backend.backup.loop.backup_once", side_effect=slow_cycle), \
         patch("backend.backup.loop.connect"), \
         patch("backend.backup.loop._read_interval", return_value=600):
        task = asyncio.create_task(backup_loop_mod.backup_loop())
        await asyncio.sleep(0.01)
        task.cancel()
        # Cancellation should propagate cleanly: backup_loop catches
        # CancelledError and returns, so awaiting the task should NOT
        # raise. The task should be done with no exception.
        await asyncio.wait_for(task, timeout=1.0)
        assert task.done()
        assert not task.cancelled()  # we returned cleanly, didn't bubble cancel
        assert task.exception() is None


@pytest.mark.asyncio
async def test_backup_loop_swallows_cycle_exception_and_continues():
    """If backup_once raises, log + continue (don't kill the loop)."""
    from backend.backup import loop as backup_loop_mod

    call_count = [0]
    second_call_done = asyncio.Event()

    async def cycle_then_raise():
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("boom")
        second_call_done.set()

    with patch("backend.backup.loop.backup_once", side_effect=cycle_then_raise), \
         patch("backend.backup.loop._read_interval", return_value=0):
        task = asyncio.create_task(backup_loop_mod.backup_loop())
        # Wait for the second call to actually happen (proves the loop didn't
        # die on the first exception). 1s ceiling guards against deadlocks
        # without coupling the assertion to scheduler timing.
        await asyncio.wait_for(second_call_done.wait(), timeout=1.0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert call_count[0] >= 2


def test_read_interval_returns_default_when_setting_missing(tmp_path):
    from backend.backup import loop as backup_loop_mod
    from backend.shared.db import connect
    from backend.migrations import discover_migrations
    from backend.migrations.runner import apply_migrations

    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    interval = backup_loop_mod._read_interval(conn)
    assert interval == 600
    conn.close()


@pytest.mark.asyncio
async def test_backup_loop_emits_system_events_with_null_trace_id(tmp_path, monkeypatch):
    """Background loop must NOT generate trace_ids — those rows mark
    'autonomous origin' and stay NULL by design (admin-triggered chains
    are the only ones that get a non-NULL trace_id)."""
    from backend.backup import loop as backup_loop
    from backend.shared.db import connect
    from backend.migrations import discover_migrations
    from backend.migrations.runner import apply_migrations
    from backend import config

    # Wire up an isolated tmp DB with full schema.
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    conn.close()

    # Redirect config so backup_once() writes to our tmp locations.
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backup")
    # Ensure no-remote path (no git stubbing needed).
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "")
    monkeypatch.setattr(config, "GITHUB_PAT", "")

    await backup_loop.backup_once()

    db = connect(db_path)
    try:
        rows = db.execute(
            "SELECT trace_id FROM system_events "
            "WHERE event_type IN ('backup_success','backup_skipped_no_remote')"
        ).fetchall()
        assert len(rows) >= 1
        assert all(r["trace_id"] is None for r in rows)
    finally:
        db.close()


def test_read_interval_picks_up_admin_change(tmp_path):
    from backend.backup import loop as backup_loop_mod
    from backend.shared.db import connect
    from backend.migrations import discover_migrations
    from backend.migrations.runner import apply_migrations
    from backend.shared import settings as S

    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    S.set_value(conn, "backup.interval_seconds", 1200, updated_by_user_id=None)
    interval = backup_loop_mod._read_interval(conn)
    assert interval == 1200
    conn.close()
