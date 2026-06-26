"""Tests for backend.cli restore-from-github subcommand."""
import gzip
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from backend import cli, config
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


@pytest.fixture
def fresh_data_dir(tmp_path, monkeypatch):
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "annotations.db"

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_DIR", db_dir)
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr(config, "DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path / "exports")

    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    conn.close()
    yield tmp_path


def _write_clone(tmp_path: Path, payload: dict) -> Path:
    """Simulate the cloned repo by writing latest.json and a couple of timestamped files."""
    clone = tmp_path / "fake-clone"
    clone.mkdir()
    (clone / "latest.json").write_text(json.dumps(payload), encoding="utf-8")
    (clone / "20260509-1430.json").write_text(json.dumps(payload), encoding="utf-8")
    return clone


def _write_gzip_clone(tmp_path: Path, payload: dict) -> Path:
    clone = tmp_path / "fake-clone"
    clone.mkdir()
    body = gzip.compress(json.dumps(payload).encode("utf-8"))
    (clone / "latest.json.gz").write_bytes(body)
    (clone / "20260509-1430.json.gz").write_bytes(body)
    return clone


def test_restore_exits_when_env_missing(fresh_data_dir, monkeypatch, capsys):
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "")
    monkeypatch.setattr(config, "GITHUB_PAT", "")

    rc = cli.main(["restore-from-github", "--yes"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "BACKUP_REPO_URL" in captured.err or "BACKUP_REPO_URL" in captured.out


def test_restore_happy_path_with_yes_flag(fresh_data_dir, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "https://github.com/x/y.git")
    monkeypatch.setattr(config, "GITHUB_PAT", "fake-pat")

    payload = {
        "invite_codes": [
            {"id": 1, "code": "RESTORED", "is_active": 1,
             "created_at": "2026-05-09T00:00:00+00:00"},
        ],
        "users": [],
    }
    clone = _write_clone(fresh_data_dir, payload)

    def fake_clone(_url, dest):
        shutil.copytree(clone, dest)

    with patch("backend.cli._clone_backup_repo", side_effect=fake_clone):
        rc = cli.main(["restore-from-github", "--yes"])

    assert rc == 0
    conn = connect(config.DB_PATH)
    row = conn.execute(
        "SELECT code FROM invite_codes WHERE code='RESTORED'"
    ).fetchone()
    assert row is not None
    conn.close()


def test_restore_happy_path_with_gzip_latest(fresh_data_dir, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "https://github.com/x/y.git")
    monkeypatch.setattr(config, "GITHUB_PAT", "fake-pat")

    payload = {
        "invite_codes": [
            {"id": 1, "code": "RESTORED_GZ", "is_active": 1,
             "created_at": "2026-05-09T00:00:00+00:00"},
        ],
        "users": [],
    }
    clone = _write_gzip_clone(fresh_data_dir, payload)

    def fake_clone(_url, dest):
        shutil.copytree(clone, dest)

    with patch("backend.cli._clone_backup_repo", side_effect=fake_clone):
        rc = cli.main(["restore-from-github", "--yes"])

    assert rc == 0
    conn = connect(config.DB_PATH)
    row = conn.execute(
        "SELECT code FROM invite_codes WHERE code='RESTORED_GZ'"
    ).fetchone()
    assert row is not None
    conn.close()


def test_restore_prompts_for_confirmation_without_yes(fresh_data_dir, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "https://github.com/x/y.git")
    monkeypatch.setattr(config, "GITHUB_PAT", "fake-pat")

    payload = {"invite_codes": []}
    clone = _write_clone(fresh_data_dir, payload)

    def fake_clone(_url, dest):
        shutil.copytree(clone, dest)

    with patch("backend.cli._clone_backup_repo", side_effect=fake_clone), \
         patch("builtins.input", return_value="n"):
        rc = cli.main(["restore-from-github"])

    assert rc == 1  # user declined


def test_restore_with_snapshot_flag_picks_specific_file(fresh_data_dir, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "https://github.com/x/y.git")
    monkeypatch.setattr(config, "GITHUB_PAT", "fake-pat")

    older_payload = {"invite_codes": [
        {"id": 1, "code": "OLDER", "is_active": 1,
         "created_at": "2026-05-01T00:00:00+00:00"},
    ]}
    latest_payload = {"invite_codes": [
        {"id": 2, "code": "LATEST", "is_active": 1,
         "created_at": "2026-05-09T00:00:00+00:00"},
    ]}
    clone = fresh_data_dir / "fake-clone"
    clone.mkdir()
    (clone / "latest.json").write_text(json.dumps(latest_payload), encoding="utf-8")
    (clone / "20260501-1200.json").write_text(json.dumps(older_payload), encoding="utf-8")

    def fake_clone(_url, dest):
        shutil.copytree(clone, dest)

    with patch("backend.cli._clone_backup_repo", side_effect=fake_clone):
        rc = cli.main(["restore-from-github", "--yes", "--snapshot", "20260501-1200"])
    assert rc == 0
    conn = connect(config.DB_PATH)
    row = conn.execute("SELECT code FROM invite_codes").fetchone()
    assert row["code"] == "OLDER"
    conn.close()


def test_restore_with_snapshot_flag_picks_specific_gzip_file(fresh_data_dir, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "https://github.com/x/y.git")
    monkeypatch.setattr(config, "GITHUB_PAT", "fake-pat")

    older_payload = {"invite_codes": [
        {"id": 1, "code": "OLDER_GZ", "is_active": 1,
         "created_at": "2026-05-01T00:00:00+00:00"},
    ]}
    latest_payload = {"invite_codes": [
        {"id": 2, "code": "LATEST_GZ", "is_active": 1,
         "created_at": "2026-05-09T00:00:00+00:00"},
    ]}
    clone = fresh_data_dir / "fake-clone"
    clone.mkdir()
    (clone / "latest.json.gz").write_bytes(
        gzip.compress(json.dumps(latest_payload).encode("utf-8"))
    )
    (clone / "20260501-1200.json.gz").write_bytes(
        gzip.compress(json.dumps(older_payload).encode("utf-8"))
    )

    def fake_clone(_url, dest):
        shutil.copytree(clone, dest)

    with patch("backend.cli._clone_backup_repo", side_effect=fake_clone):
        rc = cli.main(["restore-from-github", "--yes", "--snapshot", "20260501-1200"])
    assert rc == 0
    conn = connect(config.DB_PATH)
    row = conn.execute("SELECT code FROM invite_codes").fetchone()
    assert row["code"] == "OLDER_GZ"
    conn.close()


def test_restore_missing_snapshot_exits_1(fresh_data_dir, monkeypatch, capsys):
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "https://github.com/x/y.git")
    monkeypatch.setattr(config, "GITHUB_PAT", "fake-pat")
    clone = fresh_data_dir / "fake-clone"
    clone.mkdir()
    (clone / "latest.json").write_text("{}", encoding="utf-8")

    def fake_clone(_url, dest):
        shutil.copytree(clone, dest)

    with patch("backend.cli._clone_backup_repo", side_effect=fake_clone):
        rc = cli.main(["restore-from-github", "--yes", "--snapshot", "nonexistent"])
    assert rc == 1


def test_restore_creates_corrupt_bak_before_clone(fresh_data_dir, monkeypatch):
    """Verify the original DB is renamed to corrupt-*.db.bak before any
    risky operation."""
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "https://github.com/x/y.git")
    monkeypatch.setattr(config, "GITHUB_PAT", "fake-pat")
    payload = {"invite_codes": []}
    clone = _write_clone(fresh_data_dir, payload)

    def fake_clone(_url, dest):
        shutil.copytree(clone, dest)

    with patch("backend.cli._clone_backup_repo", side_effect=fake_clone):
        rc = cli.main(["restore-from-github", "--yes"])
    assert rc == 0
    bak_files = list((fresh_data_dir / "db").glob("corrupt-*.db.bak"))
    assert len(bak_files) == 1


def test_restore_rolls_back_on_failure(fresh_data_dir, monkeypatch):
    """If the restore step itself fails, the corrupt-bak is restored to
    annotations.db so the operator's pre-restore state is preserved."""
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "https://github.com/x/y.git")
    monkeypatch.setattr(config, "GITHUB_PAT", "fake-pat")

    conn = connect(config.DB_PATH)
    conn.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,?)",
        ("PRESTORE", "2026-05-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    # Snapshot has unknown column → restore_from_snapshot raises ValueError
    bad_payload = {"invite_codes": [{"unknown_column_does_not_exist": "x"}]}
    clone = _write_clone(fresh_data_dir, bad_payload)

    def fake_clone(_url, dest):
        shutil.copytree(clone, dest)

    with patch("backend.cli._clone_backup_repo", side_effect=fake_clone):
        rc = cli.main(["restore-from-github", "--yes"])
    assert rc == 1

    conn = connect(config.DB_PATH)
    row = conn.execute(
        "SELECT code FROM invite_codes WHERE code='PRESTORE'"
    ).fetchone()
    assert row is not None
    conn.close()


def test_restore_rolls_back_on_clone_failure(fresh_data_dir, monkeypatch):
    """If the git clone step fails, the corrupt-bak is restored to
    annotations.db so the operator's pre-clone state is preserved."""
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "https://github.com/x/y.git")
    monkeypatch.setattr(config, "GITHUB_PAT", "fake-pat")

    # Pre-write a recognizable row so we can verify it's preserved
    conn = connect(config.DB_PATH)
    conn.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,?)",
        ("BEFORE_CLONE_FAIL", "2026-05-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    def fake_clone(_url, _dest):
        raise RuntimeError("git clone failed: network unreachable")

    with patch("backend.cli._clone_backup_repo", side_effect=fake_clone):
        rc = cli.main(["restore-from-github", "--yes"])
    assert rc == 1

    # Original DB content was restored from corrupt-bak
    conn = connect(config.DB_PATH)
    row = conn.execute(
        "SELECT code FROM invite_codes WHERE code='BEFORE_CLONE_FAIL'"
    ).fetchone()
    assert row is not None
    conn.close()


def test_clone_helper_scrubs_pat_on_timeout(monkeypatch):
    """If subprocess.run raises TimeoutExpired during git clone, the raised
    error must NOT contain the raw PAT (it's in the cmd argv)."""
    import subprocess
    from backend import cli

    pat_url = "https://x-access-token:supersecret@github.com/o/r.git"

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=60)

    with patch("backend.cli.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError) as exc:
            cli._clone_backup_repo(pat_url, Path("/tmp/whatever"))
    msg = str(exc.value)
    assert "supersecret" not in msg
    assert "x-access-token:***" in msg
