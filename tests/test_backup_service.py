"""Tests for the dump + rotate primitives in backend.backup.service."""
import json
import os
import sqlite3
import time
from pathlib import Path

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


@pytest.fixture
def backup_dir(tmp_path):
    d = tmp_path / "backup"
    d.mkdir()
    yield d


def test_dump_returns_dict_keyed_by_table(fresh_db):
    from backend.backup.service import dump_all_tables_to_json
    out = dump_all_tables_to_json(fresh_db)
    assert isinstance(out, dict)
    assert "users" in out
    assert "documents_meta" in out
    assert "annotations" in out
    assert "training_quiz_overrides" in out


def test_dump_includes_format_version(fresh_db):
    """Snapshot has __format_version metadata at top level so future restorers
    can detect breaking schema changes. The key is __-prefixed to distinguish
    from table names."""
    from backend.backup.service import dump_all_tables_to_json, SNAPSHOT_FORMAT_VERSION
    out = dump_all_tables_to_json(fresh_db)
    assert out["__format_version"] == SNAPSHOT_FORMAT_VERSION


def test_dump_excludes_schema_migrations(fresh_db):
    from backend.backup.service import dump_all_tables_to_json
    out = dump_all_tables_to_json(fresh_db)
    assert "schema_migrations" not in out


def test_dump_returns_empty_lists_on_fresh_db(fresh_db):
    from backend.backup.service import dump_all_tables_to_json
    out = dump_all_tables_to_json(fresh_db)
    assert out["users"] == []
    assert out["annotations"] == []


def test_dump_returns_rows_as_dicts_with_column_names(fresh_db):
    from backend.backup.service import dump_all_tables_to_json
    fresh_db.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,?)",
        ("TEST-CODE", "2026-05-09T00:00:00+00:00"),
    )
    fresh_db.commit()
    out = dump_all_tables_to_json(fresh_db)
    assert len(out["invite_codes"]) == 1
    row = out["invite_codes"][0]
    assert row["code"] == "TEST-CODE"
    assert row["is_active"] == 1
    assert row["created_at"] == "2026-05-09T00:00:00+00:00"


def test_dump_is_json_serializable(fresh_db):
    from backend.backup.service import dump_all_tables_to_json
    fresh_db.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,?)",
        ("X", "2026-05-09T00:00:00+00:00"),
    )
    fresh_db.commit()
    out = dump_all_tables_to_json(fresh_db)
    s = json.dumps(out)
    assert isinstance(s, str)


def test_write_snapshot_creates_latest_and_timestamped(backup_dir):
    from backend.backup.service import write_snapshot
    payload = {"users": [{"id": 1, "username": "x"}]}
    snapshot_path = write_snapshot(payload, backup_dir, ts="20260509-1430")
    latest = backup_dir / "latest.json"
    timestamped = backup_dir / "20260509-1430.json"
    assert latest.exists()
    assert timestamped.exists()
    assert snapshot_path == timestamped
    assert json.loads(latest.read_text()) == payload
    assert json.loads(timestamped.read_text()) == payload


def test_write_snapshot_is_atomic(backup_dir):
    """Verify write goes through temp + rename pattern (no partial files)."""
    from backend.backup.service import write_snapshot
    payload = {"x": [1, 2, 3]}
    write_snapshot(payload, backup_dir, ts="20260509-1430")
    tmps = list(backup_dir.glob("*.tmp"))
    assert tmps == []


def test_rotate_snapshots_keeps_last_n(backup_dir):
    from backend.backup.service import rotate_snapshots
    for i in range(200):
        f = backup_dir / f"20260509-{i:04d}.json"
        f.write_text("{}")
        os.utime(f, (time.time() + i, time.time() + i))
    deleted = rotate_snapshots(backup_dir, keep=144)
    assert len(deleted) == 56
    remaining = sorted(p.name for p in backup_dir.glob("*.json"))
    assert len(remaining) == 144


def test_rotate_snapshots_skips_latest_json(backup_dir):
    from backend.backup.service import rotate_snapshots
    (backup_dir / "latest.json").write_text("{}")
    for i in range(150):
        f = backup_dir / f"20260509-{i:04d}.json"
        f.write_text("{}")
        os.utime(f, (time.time() + i, time.time() + i))
    rotate_snapshots(backup_dir, keep=144)
    assert (backup_dir / "latest.json").exists()


def test_rotate_snapshots_skips_git_dir(backup_dir):
    from backend.backup.service import rotate_snapshots
    (backup_dir / ".git").mkdir()
    (backup_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    for i in range(150):
        f = backup_dir / f"20260509-{i:04d}.json"
        f.write_text("{}")
        os.utime(f, (time.time() + i, time.time() + i))
    rotate_snapshots(backup_dir, keep=144)
    assert (backup_dir / ".git" / "HEAD").exists()


def test_rotate_no_op_when_under_threshold(backup_dir):
    from backend.backup.service import rotate_snapshots
    for i in range(10):
        (backup_dir / f"20260509-{i:04d}.json").write_text("{}")
    deleted = rotate_snapshots(backup_dir, keep=144)
    assert deleted == []
