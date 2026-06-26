"""Tests for run_backup_cycle orchestrator."""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "test.db"
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    # Patch config to use this tmp data dir
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("backend.config.DB_PATH", db_path)
    monkeypatch.setattr("backend.config.BACKUP_DIR", backup_dir)

    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def test_run_backup_cycle_no_remote_skips_git(fresh_db, tmp_path, monkeypatch):
    """BACKUP_REPO_URL empty → dump + rotate happen, git is skipped,
    system_events row written with event_type='backup_skipped_no_remote'."""
    from backend.backup import service
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "")
    result = service.run_backup_cycle(fresh_db)
    assert result["pushed"] is False
    assert result["committed_sha"] is None
    assert result["snapshot_path"].endswith(".json.gz")
    backup_dir = tmp_path / "backup"
    assert (backup_dir / "latest.json.gz").exists()
    row = fresh_db.execute(
        "SELECT * FROM system_events WHERE event_type='backup_skipped_no_remote'"
    ).fetchone()
    assert row is not None
    assert row["severity"] == "info"


def test_run_backup_cycle_logs_success_when_git_succeeds(fresh_db, tmp_path, monkeypatch):
    """Stub the git wrapper; verify event_type='backup_success' is logged."""
    from backend.backup import service
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL",
                        "https://github.com/x/y.git")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "fake")

    with patch("backend.backup.service.git_remote.ensure_initialized"), \
         patch("backend.backup.service.git_remote.commit_and_push", return_value="abc123def"):
        result = service.run_backup_cycle(fresh_db)

    assert result["pushed"] is True
    assert result["committed_sha"] == "abc123def"
    row = fresh_db.execute(
        "SELECT * FROM system_events WHERE event_type='backup_success'"
    ).fetchone()
    assert row is not None
    assert row["severity"] == "info"


def test_run_backup_cycle_logs_failure_on_git_error(fresh_db, tmp_path, monkeypatch):
    """Git push fails → event_type='backup_failed', severity='error',
    extra_json has step + error fields. Cycle raises so the route can 500."""
    from backend.backup import service
    from backend.backup.git_remote import GitRemoteError
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL",
                        "https://github.com/x/y.git")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "fake")

    with patch("backend.backup.service.git_remote.ensure_initialized"), \
         patch("backend.backup.service.git_remote.commit_and_push",
               side_effect=GitRemoteError("git push failed: Permission denied")):
        with pytest.raises(GitRemoteError):
            service.run_backup_cycle(fresh_db)

    row = fresh_db.execute(
        "SELECT * FROM system_events WHERE event_type='backup_failed'"
    ).fetchone()
    assert row is not None
    assert row["severity"] == "error"
    extra = json.loads(row["extra_json"])
    assert extra["step"] == "push"
    assert "Permission denied" in extra["error"]


def test_run_backup_cycle_snapshot_failure_logged_and_raised(fresh_db, monkeypatch):
    """Streaming snapshot failures are logged and re-raised."""
    from backend.backup import service
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "")

    with patch("backend.backup.service.write_database_snapshot",
               side_effect=sqlite3.OperationalError("database is locked")):
        with pytest.raises(sqlite3.OperationalError):
            service.run_backup_cycle(fresh_db)

    row = fresh_db.execute(
        "SELECT * FROM system_events WHERE event_type='backup_failed'"
    ).fetchone()
    assert row is not None
    extra = json.loads(row["extra_json"])
    assert extra["step"] == "snapshot"


def test_run_backup_cycle_rotates_snapshots(fresh_db, tmp_path, monkeypatch):
    from backend.backup import service
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "")

    backup_dir = tmp_path / "backup"
    for i in range(200):
        f = backup_dir / f"20260101-{i:04d}.json"
        f.write_text("{}")
        os.utime(f, (time.time() - 86400 + i, time.time() - 86400 + i))

    service.run_backup_cycle(fresh_db)
    snapshots = list(backup_dir.glob("20260101-*.json"))
    new_snapshots = list(backup_dir.glob("20260[5-9]*.json"))
    total_dated = len(snapshots) + len(new_snapshots)
    assert total_dated <= 144


def test_run_backup_cycle_removes_legacy_uncompressed_snapshots(
    fresh_db,
    tmp_path,
    monkeypatch,
):
    from backend.backup import service

    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "")

    backup_dir = tmp_path / "backup"
    (backup_dir / "latest.json").write_text("{}")
    (backup_dir / "20260617-2227.json").write_text("{}")

    service.run_backup_cycle(fresh_db)

    assert not (backup_dir / "latest.json").exists()
    assert not (backup_dir / "20260617-2227.json").exists()
    assert (backup_dir / "latest.json.gz").exists()


def test_run_backup_cycle_avoids_same_minute_snapshot_collision(
    fresh_db,
    tmp_path,
    monkeypatch,
):
    """Manual/background cycles in the same minute must not overwrite the
    first timestamped snapshot."""
    from backend.backup import service

    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "")
    monkeypatch.setattr(service, "utc_timestamp", lambda: "20260626-1234")

    first = service.run_backup_cycle(fresh_db)
    second = service.run_backup_cycle(fresh_db)

    assert first["snapshot_path"] != second["snapshot_path"]
    assert Path(first["snapshot_path"]).exists()
    assert Path(second["snapshot_path"]).exists()


def test_run_backup_cycle_serializes_concurrent_runs(fresh_db, tmp_path, monkeypatch):
    """Concurrent manual/background cycles must not enter the snapshot/git
    critical section at the same time."""
    from backend import config
    from backend.backup import service

    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "")

    active = 0
    max_active = 0
    call_count = 0
    state_lock = threading.Lock()
    first_inside = threading.Event()
    release_first = threading.Event()
    errors: list[BaseException] = []

    def fake_snapshot(db, backup_dir, ts):
        nonlocal active, call_count, max_active
        with state_lock:
            call_count += 1
            is_first_call = call_count == 1
            active += 1
            max_active = max(max_active, active)

        if is_first_call:
            first_inside.set()
            assert release_first.wait(timeout=2)

        path = backup_dir / f"{ts}-{threading.get_ident()}.json"
        path.write_text("{}")
        (backup_dir / "latest.json").write_text("{}")

        with state_lock:
            active -= 1
        return path, 1

    def run_cycle(db):
        try:
            service.run_backup_cycle(db)
        except BaseException as exc:
            errors.append(exc)

    second_conn = connect(config.DB_PATH)
    try:
        with patch(
            "backend.backup.service.write_database_snapshot",
            side_effect=fake_snapshot,
        ):
            first = threading.Thread(target=run_cycle, args=(fresh_db,))
            second = threading.Thread(target=run_cycle, args=(second_conn,))

            first.start()
            assert first_inside.wait(timeout=1)
            second.start()
            time.sleep(0.05)
            release_first.set()
            first.join(timeout=2)
            second.join(timeout=2)

        assert not first.is_alive()
        assert not second.is_alive()
        assert errors == []
        assert max_active == 1
    finally:
        second_conn.close()
