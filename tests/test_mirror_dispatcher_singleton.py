"""Phase 5 B-02: dispatcher PID-file singleton guard."""
from __future__ import annotations
import os

from backend.mirror.dispatcher import (
    _acquire_dispatcher_lock, _release_dispatcher_lock, _pid_is_alive,
)


def test_acquire_succeeds_when_no_pid_file(tmp_path):
    assert _acquire_dispatcher_lock(tmp_path) is True
    assert (tmp_path / ".mirror-dispatcher.pid").exists()
    _release_dispatcher_lock(tmp_path)


def test_acquire_refuses_when_existing_pid_alive(tmp_path, monkeypatch):
    """If the PID file points to a live process, acquire must return False."""
    # Use the current test process's PID — guaranteed alive.
    (tmp_path / ".mirror-dispatcher.pid").write_text(f"{os.getpid()}\n")
    assert _acquire_dispatcher_lock(tmp_path) is False


def test_acquire_takes_over_when_pid_is_stale(tmp_path):
    """If the PID file points to a dead PID, acquire must take over (overwrite)."""
    # Use a PID extremely unlikely to be alive: process ID 999999 (well above
    # most kernel max-PID defaults).
    fake_dead_pid = 999999
    (tmp_path / ".mirror-dispatcher.pid").write_text(f"{fake_dead_pid}\n")
    assert _pid_is_alive(fake_dead_pid) is False  # sanity
    assert _acquire_dispatcher_lock(tmp_path) is True
    # The new file must contain our PID, not the dead one.
    content = (tmp_path / ".mirror-dispatcher.pid").read_text()
    assert str(os.getpid()) in content
    _release_dispatcher_lock(tmp_path)


def test_acquire_takes_over_when_pid_file_is_garbage(tmp_path):
    """Malformed PID file → treated as stale."""
    (tmp_path / ".mirror-dispatcher.pid").write_text("not-a-pid garbage\n")
    assert _acquire_dispatcher_lock(tmp_path) is True
    _release_dispatcher_lock(tmp_path)


def test_release_is_idempotent(tmp_path):
    _release_dispatcher_lock(tmp_path)  # no file, no error
    (tmp_path / ".mirror-dispatcher.pid").write_text(f"{os.getpid()}\n")
    _release_dispatcher_lock(tmp_path)
    assert not (tmp_path / ".mirror-dispatcher.pid").exists()
