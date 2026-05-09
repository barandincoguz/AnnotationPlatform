"""Tests for run_backup_cycle orchestrator."""
import json
import os
import sqlite3
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
    assert result["snapshot_path"].endswith(".json")
    backup_dir = tmp_path / "backup"
    assert (backup_dir / "latest.json").exists()
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


def test_run_backup_cycle_dump_failure_logged_and_raised(fresh_db, monkeypatch):
    """If dump_all_tables_to_json raises, log failure with step='dump' and re-raise."""
    from backend.backup import service
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "")

    with patch("backend.backup.service.dump_all_tables_to_json",
               side_effect=sqlite3.OperationalError("database is locked")):
        with pytest.raises(sqlite3.OperationalError):
            service.run_backup_cycle(fresh_db)

    row = fresh_db.execute(
        "SELECT * FROM system_events WHERE event_type='backup_failed'"
    ).fetchone()
    assert row is not None
    extra = json.loads(row["extra_json"])
    assert extra["step"] == "dump"


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
