"""Tests for backend/retention/loop.py — async retention loop."""
import asyncio
from unittest.mock import patch, MagicMock

import pytest


@pytest.mark.asyncio
async def test_retention_once_calls_run_purge_in_thread():
    """retention_once is a thin wrapper that opens a connection and
    calls run_purge in a worker thread (async-friendly). Patch both
    `connect` and `run_purge` so the test never touches the real
    DATA_DIR — mirrors test_backup_loop.py's safety pattern."""
    from backend.retention import loop as retention_loop

    fake_conn = MagicMock()
    with patch("backend.retention.loop.connect", return_value=fake_conn) as mock_connect, \
         patch("backend.retention.loop.run_purge", return_value={"ok": True}) as mock_run:
        await retention_loop.retention_once()
        mock_connect.assert_called_once()
        mock_run.assert_called_once()
        fake_conn.close.assert_called_once()  # confirms finally block runs


@pytest.mark.asyncio
async def test_loop_cancellation_is_graceful():
    """Cancelling the task returns cleanly without bubbling CancelledError."""
    from backend.retention import loop as retention_loop

    with patch("backend.retention.loop.retention_once") as mock_once, \
         patch("backend.retention.loop._read_interval", return_value=10):
        mock_once.return_value = None
        task = asyncio.create_task(retention_loop.retention_loop())
        await asyncio.sleep(0.01)  # let it enter sleep
        task.cancel()
        await asyncio.wait_for(task, timeout=1.0)
        assert task.done()
        assert not task.cancelled()
        assert task.exception() is None


@pytest.mark.asyncio
async def test_loop_swallows_cycle_exception_and_continues():
    """If retention_once raises, log + continue (don't kill the loop).
    Uses asyncio.Event for deterministic 2nd-call detection (Paket 12 polish pattern)."""
    from backend.retention import loop as retention_loop

    call_count = [0]
    second_call_done = asyncio.Event()

    async def cycle_then_raise():
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("boom")
        second_call_done.set()

    with patch("backend.retention.loop.retention_once", side_effect=cycle_then_raise), \
         patch("backend.retention.loop._read_interval", return_value=0):
        task = asyncio.create_task(retention_loop.retention_loop())
        await asyncio.wait_for(second_call_done.wait(), timeout=1.0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert call_count[0] >= 2


def test_read_interval_returns_default_when_setting_missing(tmp_path, monkeypatch):
    """If retention.cycle_interval_seconds is absent from site_settings,
    _read_interval falls back to DEFAULT_INTERVAL_SECONDS (86400)."""
    from backend.retention import loop as retention_loop_mod
    from backend.shared.db import connect
    from backend.migrations import discover_migrations
    from backend.migrations.runner import apply_migrations

    db_path = tmp_path / "test.db"
    monkeypatch.setattr("backend.retention.loop.config.DB_PATH", db_path)

    # Apply migrations so site_settings exists, then delete the retention
    # interval row to simulate a fresh DB before v0003 (defensive: the
    # fallback path should still work without the migration's row).
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    conn.execute(
        "DELETE FROM site_settings WHERE key='retention.cycle_interval_seconds'"
    )
    conn.commit()
    conn.close()

    assert retention_loop_mod._read_interval() == retention_loop_mod.DEFAULT_INTERVAL_SECONDS


def test_read_interval_picks_up_admin_change(tmp_path, monkeypatch):
    """When admin updates retention.cycle_interval_seconds via /api/admin/
    settings, the next loop iteration's _read_interval reflects it.
    Live-tuning is the whole point of the per-cycle re-read."""
    from backend.retention import loop as retention_loop_mod
    from backend.shared.db import connect
    from backend.migrations import discover_migrations
    from backend.migrations.runner import apply_migrations

    db_path = tmp_path / "test.db"
    monkeypatch.setattr("backend.retention.loop.config.DB_PATH", db_path)

    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    # Admin sets a faster cadence (e.g., 30 minutes for a stress test).
    conn.execute(
        "UPDATE site_settings SET value='1800' WHERE key='retention.cycle_interval_seconds'"
    )
    conn.commit()
    conn.close()

    assert retention_loop_mod._read_interval() == 1800
