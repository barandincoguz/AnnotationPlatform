"""Tests for backend/retention/loop.py — async retention loop."""
import asyncio
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_retention_once_calls_run_purge_in_thread():
    """retention_once is a thin wrapper that opens a connection and
    calls run_purge in a worker thread (async-friendly)."""
    from backend.retention import loop as retention_loop

    with patch("backend.retention.loop.run_purge", return_value={"ok": True}) as mock_run:
        await retention_loop.retention_once()
        mock_run.assert_called_once()


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
