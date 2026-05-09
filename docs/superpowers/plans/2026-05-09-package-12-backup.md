# Paket 12 — Backup + Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automated periodic SQL→JSON backup of the entire SQLite database to a private GitHub repo, plus a manual CLI restore tool. The backup loop runs as an asyncio task driven by FastAPI's lifespan; restore is a one-shot CLI command that wipes and rebuilds the local DB from a chosen snapshot. No new schema; observability via the existing `system_events` table.

**Architecture:** New `backend/backup/` package with: a pure-function dump/rotate layer (`service.py`), a subprocess-driven git wrapper (`git_remote.py`), an async loop (`loop.py`) mirroring the existing `backend/locks/sweep.py` pattern, an admin HTTP endpoint (`routes.py`), and a restore module (`restore.py`) consumed by the CLI. The cycle reads env vars (`BACKUP_REPO_URL`, `GITHUB_PAT`) on each iteration so missing config means silent skip + info event, not startup failure. Per-step fault isolation between dump/write/rotate/git steps keeps observability granular.

**Tech Stack:** Existing FastAPI + SQLite + Pydantic. New: `subprocess.run` for git, `asyncio.to_thread` for blocking work in the async loop. No new third-party deps. Reuses `backend.shared.audit.log_system_event`, `backend.shared.audit.log_admin_action`, `backend.shared.settings`, `backend.users.deps.require_admin`.

---

## Mimari Kararlar (Locked from spec 2026-05-09-paket-12-backup-design.md, commit 0e9b722)

- **Module layout:**
  - `backend/backup/__init__.py` — empty
  - `backend/backup/service.py` — `dump_all_tables_to_json`, `write_snapshot`, `rotate_snapshots`, `run_backup_cycle`
  - `backend/backup/git_remote.py` — `inject_pat`, `ensure_initialized`, `commit_and_push`
  - `backend/backup/loop.py` — `backup_once`, `backup_loop`, `start`, `stop` (mirrors `backend/locks/sweep.py`)
  - `backend/backup/models.py` — Pydantic schemas for the admin endpoint
  - `backend/backup/routes.py` — `POST /api/admin/backup/run-now`
  - `backend/backup/restore.py` — `restore_from_snapshot` (consumed by CLI)
  - `backend/main.py` — extended lifespan to start backup task; mount backup router
  - `backend/cli.py` — `restore-from-github` subcommand
- **Auth:** All new HTTP routes use `Depends(require_admin)` → 404 existence-hide.
- **Trigger pattern:** mirrors existing `backend/locks/sweep.py` (asyncio task in lifespan, started via `start()`, cancelled via `stop()` on shutdown). The backup loop runs `run_backup_cycle` inside `asyncio.to_thread` because the dump + git work is blocking.
- **Settings live-tuning:** Each loop iteration re-reads `backup.interval_seconds` (default 600) from `site_settings` so admin tweaks via Paket 8 settings PUT take effect on the next cycle.
- **Missing env vars:** `BACKUP_REPO_URL` or `GITHUB_PAT` empty → dump + rotation still run; git step skipped; `system_events` row with `event_type='backup_skipped_no_remote', severity='info'`. Endpoint returns 200 with `pushed: false, committed_sha: null`.
- **Backup snapshot format:** single JSON object `{<table>: [{col: val, ...}, ...]}`. **Excludes `schema_migrations`** (re-derived on restore). Uses `BEGIN IMMEDIATE` for read consistency.
- **Atomic write:** write to `<file>.tmp` then `os.replace` for crash-safe snapshot writes. (Same pattern as Paket 5 annotations.)
- **Snapshot rotation:** keep `latest.json` + 144 most recent `<UTC YYYYMMDD-HHMM>.json` snapshots; delete older. `latest.json` and `.git/` never deleted.
- **Git wrapper:**
  - `inject_pat("https://github.com/owner/repo.git", "abc")` → `"https://x-access-token:abc@github.com/owner/repo.git"`
  - `ensure_initialized` is idempotent: if `.git` exists, no-op.
  - First-run flow: `git init` → set `user.email/name` → `commit --allow-empty -m "init"` → `git remote add origin <pat-url>`. This guarantees a HEAD before the first real backup, so `git push origin main` doesn't fail on empty branch.
  - Subprocess timeout: 30 seconds per git invocation. Hung pushes raise `subprocess.TimeoutExpired` → caught by orchestrator → logged as failure.
  - PAT scrubbing: any captured stderr/stdout has the PAT regex-stripped before logging or returning to user.
  - Branch fallback: try `git push origin main` first; if it returns nonzero with "src refspec main does not match", retry with `master`.
- **Audit + system events:**
  - Manual trigger writes `admin_audit_log` row: `action_type='backup_run_now', target_kind='backup', target_id=<snapshot_filename>, metadata={pushed, committed_sha}`.
  - Every cycle writes `system_events`: `event_type='backup_success'` with `extra_json={snapshot_path, committed_sha, pushed, rotated_count}` OR `event_type='backup_failed', severity='error'` with `extra_json={step, error}`.
- **Concurrent admin manual + scheduled cycle:** both grab `BEGIN IMMEDIATE`; one blocks. Acceptable.
- **Restore semantics:**
  - CLI command: `python -m backend.cli restore-from-github [--snapshot <YYYYMMDD-HHMM>] [--yes] [--force]`.
  - Step 1: read env, exit 1 if missing.
  - Step 2: rename `<DATA_DIR>/db/annotations.db` → `<DATA_DIR>/db/corrupt-<UTC ISO>.db.bak`. Literal substring `corrupt` so operators can find these files.
  - Step 3: `git clone <pat-url>` to `/tmp/restore-<ts>/`.
  - Step 4: pick snapshot file (`<stamp>.json` or `latest.json`).
  - Step 5: prompt `[y/N]` unless `--yes`.
  - Step 6: open new sqlite3 connection (creates fresh DB), apply migrations, then BEGIN IMMEDIATE → DELETE per table → INSERT per table → COMMIT.
  - Step 7: print row counts.
  - Step 8: clean up `/tmp/restore-<ts>/`.
  - On any error after step 2: ROLLBACK the open transaction, restore the corrupt-bak to original path, exit 1.
  - WAL lock detection: if `PRAGMA quick_check` on the existing DB succeeds without lock acquisition error, assume server is stopped. If lock detected and `--force` not passed, exit 1 with message.
- **Type hints on `db`:** `db: sqlite3.Connection` (Paket 7+ convention).
- **Fixtures:** Tests use `client`, `db_path`, `bootstrap_admin`, `seen_manual_user` from `tests/conftest.py` (Paket 11 polish landed these). New tests for backup-only logic (dump, rotate, git wrapper) don't need `client` — they operate on a fresh sqlite connection.
- **Pyright import-resolution warnings:** cosmetic; runtime/tests unaffected.

## Dosya Yapısı

```
backend/backup/                      # NEW package
├── __init__.py                      # empty
├── service.py                       # dump_all_tables_to_json, write_snapshot,
│                                    #   rotate_snapshots, run_backup_cycle
├── git_remote.py                    # inject_pat, ensure_initialized,
│                                    #   commit_and_push
├── loop.py                          # backup_once, backup_loop, start, stop
├── models.py                        # Pydantic schemas
├── routes.py                        # POST /api/admin/backup/run-now
└── restore.py                       # restore_from_snapshot

backend/main.py                      # MODIFIED: lifespan starts backup task;
                                     #   mount backup router
backend/cli.py                       # MODIFIED: + restore-from-github subcommand

tests/test_backup_service.py         # NEW — dump_all_tables_to_json, rotation
tests/test_backup_git_remote.py      # NEW — git wrapper unit tests
tests/test_backup_cycle.py           # NEW — run_backup_cycle orchestrator
tests/test_backup_loop.py            # NEW — async loop cancellation, live tuning
tests/test_backup_lifespan.py        # NEW — server startup/shutdown smoke
tests/test_backup_admin_route.py     # NEW — POST /api/admin/backup/run-now
tests/test_backup_restore.py         # NEW — restore_from_snapshot
tests/test_cli_restore_from_github.py # NEW — CLI subcommand
```

---

## Task 1: Dump + Rotate (Pure-Function Layer)

**Goal:** Ship the JSON dump and snapshot rotation primitives. No DB writes; reads only. No git involvement.

**Files:**
- Create: `backend/backup/__init__.py` (empty)
- Create: `backend/backup/service.py`
- Create: `tests/test_backup_service.py`

- [ ] **Step 1: Create empty package**

```bash
mkdir -p /Users/barandincoguz/Desktop/deneme/backend/backup
touch /Users/barandincoguz/Desktop/deneme/backend/backup/__init__.py
```

- [ ] **Step 2: Write `tests/test_backup_service.py`**

```python
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
    # Tables defined in v0001 + v0002 should be keys
    assert "users" in out
    assert "documents_meta" in out
    assert "annotations" in out
    assert "training_quiz_overrides" in out


def test_dump_excludes_schema_migrations(fresh_db):
    from backend.backup.service import dump_all_tables_to_json
    out = dump_all_tables_to_json(fresh_db)
    assert "schema_migrations" not in out


def test_dump_returns_empty_lists_on_fresh_db(fresh_db):
    from backend.backup.service import dump_all_tables_to_json
    out = dump_all_tables_to_json(fresh_db)
    # users table has no rows in a freshly migrated DB
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
    # Should not raise
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
    # Both files have the same content
    assert json.loads(latest.read_text()) == payload
    assert json.loads(timestamped.read_text()) == payload


def test_write_snapshot_is_atomic(backup_dir):
    """Verify write goes through temp + rename pattern (no partial files)."""
    from backend.backup.service import write_snapshot
    payload = {"x": [1, 2, 3]}
    write_snapshot(payload, backup_dir, ts="20260509-1430")
    # No leftover .tmp files
    tmps = list(backup_dir.glob("*.tmp"))
    assert tmps == []


def test_rotate_snapshots_keeps_last_n(backup_dir):
    from backend.backup.service import rotate_snapshots
    # Create 200 timestamped snapshot files; ensure mtimes are distinct
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
    # .git dir untouched
    assert (backup_dir / ".git" / "HEAD").exists()


def test_rotate_no_op_when_under_threshold(backup_dir):
    from backend.backup.service import rotate_snapshots
    for i in range(10):
        (backup_dir / f"20260509-{i:04d}.json").write_text("{}")
    deleted = rotate_snapshots(backup_dir, keep=144)
    assert deleted == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_backup_service.py -v`
Expected: FAIL — `cannot import name 'dump_all_tables_to_json' from 'backend.backup.service'`.

- [ ] **Step 4: Implement `backend/backup/service.py`**

```python
"""Backup primitives: dump tables to JSON, write snapshot files atomically,
rotate older snapshots. No git involvement here — that's git_remote.py."""
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


log = logging.getLogger(__name__)


# Tables NOT dumped — schema_migrations is re-derived from migrations
# on the restored DB, so persisting it would create version-skew risk.
EXCLUDED_TABLES = {"schema_migrations"}


def dump_all_tables_to_json(db: sqlite3.Connection) -> dict:
    """Return a snapshot dict {<table>: [{col: val, ...}, ...]} of every
    user table in the DB. Excludes schema_migrations.

    Reads under BEGIN IMMEDIATE so the snapshot is consistent across tables
    even if other writers are active.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        tables = [
            r["name"] for r in db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if r["name"] not in EXCLUDED_TABLES
        ]

        out: dict = {}
        for table in tables:
            cols = [
                r["name"] for r in db.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            ]
            rows = db.execute(f"SELECT * FROM {table}").fetchall()
            out[table] = [
                {c: r[c] for c in cols}
                for r in rows
            ]
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    return out


def write_snapshot(payload: dict, backup_dir: Path, ts: str) -> Path:
    """Atomically write `payload` to two files in `backup_dir`:
       - latest.json
       - <ts>.json
    Uses temp-file + os.replace for crash safety. Returns the timestamped path.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    latest = backup_dir / "latest.json"
    timestamped = backup_dir / f"{ts}.json"
    body = json.dumps(payload, ensure_ascii=False, indent=None, sort_keys=True)

    for target in (latest, timestamped):
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, target)

    return timestamped


def rotate_snapshots(backup_dir: Path, keep: int = 144) -> list[Path]:
    """Delete oldest timestamped snapshots, keeping the `keep` most recent
    by modification time. Never touches latest.json or the .git/ directory.

    Returns the list of deleted paths.
    """
    candidates = [
        p for p in backup_dir.iterdir()
        if p.is_file() and p.name != "latest.json"
        and p.suffix == ".json"
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    to_delete = candidates[keep:]
    for p in to_delete:
        try:
            p.unlink()
        except Exception:
            log.exception("failed to delete old snapshot %s", p)
    return to_delete


def utc_timestamp() -> str:
    """Return UTC timestamp formatted as YYYYMMDD-HHMM. Used for snapshot
    filenames so lexicographic sort matches chronological sort."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_backup_service.py -v`
Expected: 11 PASS.

- [ ] **Step 6: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 515 prior + 11 new = 526 PASS.

- [ ] **Step 7: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/backup/__init__.py backend/backup/service.py tests/test_backup_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket12): backup dump + rotate primitives

dump_all_tables_to_json reads under BEGIN IMMEDIATE for cross-table
consistency, excludes schema_migrations. write_snapshot writes
latest.json + <ts>.json atomically (temp + replace). rotate_snapshots
keeps 144 most recent timestamped files; skips latest.json and .git/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Git Remote Wrapper

**Goal:** Subprocess-based git wrapper. PAT URL injection, idempotent init, commit + push with PAT scrubbing and timeout.

**Files:**
- Create: `backend/backup/git_remote.py`
- Create: `tests/test_backup_git_remote.py`

- [ ] **Step 1: Write `tests/test_backup_git_remote.py`**

```python
"""Tests for backend.backup.git_remote — subprocess-driven git wrapper."""
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

import pytest


def test_inject_pat_https_url():
    from backend.backup.git_remote import inject_pat
    out = inject_pat("https://github.com/owner/repo.git", "secret123")
    assert out == "https://x-access-token:secret123@github.com/owner/repo.git"


def test_inject_pat_idempotent_does_not_double_inject():
    """If the URL already contains a PAT, return it unchanged."""
    from backend.backup.git_remote import inject_pat
    already = "https://x-access-token:abc@github.com/owner/repo.git"
    out = inject_pat(already, "different")
    assert out == already


def test_inject_pat_raises_on_non_https():
    from backend.backup.git_remote import inject_pat
    with pytest.raises(ValueError):
        inject_pat("git@github.com:owner/repo.git", "secret")


def test_scrub_pat_removes_token_from_text():
    from backend.backup.git_remote import scrub_pat
    raw = "fatal: Authentication failed for 'https://x-access-token:abc123@github.com/owner/repo/'"
    out = scrub_pat(raw)
    assert "abc123" not in out
    assert "x-access-token:***" in out


def test_ensure_initialized_creates_git_dir(tmp_path):
    from backend.backup.git_remote import ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    assert (backup_dir / ".git").exists()
    # initial empty commit exists
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=backup_dir,
        capture_output=True, text=True,
    )
    assert log.returncode == 0
    assert "init" in log.stdout


def test_ensure_initialized_is_idempotent(tmp_path):
    from backend.backup.git_remote import ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    # Second call should not raise or duplicate the init commit
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=backup_dir,
        capture_output=True, text=True,
    )
    # Still exactly one commit
    assert log.stdout.count("\n") == 1


def test_commit_and_push_runs_subprocess_with_timeout(tmp_path):
    """Verify commit_and_push invokes git with the 30s timeout."""
    from backend.backup.git_remote import commit_and_push, ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    # Drop a file to be committed
    (backup_dir / "x.json").write_text("{}")

    captured_calls = []
    real_run = subprocess.run

    def fake_run(*args, **kwargs):
        captured_calls.append((args, kwargs))
        if args[0][:2] == ["git", "push"]:
            # Stub push success
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result
        return real_run(*args, **kwargs)

    with patch("backend.backup.git_remote.subprocess.run", side_effect=fake_run):
        sha = commit_and_push(backup_dir, "test commit")

    assert isinstance(sha, str) and len(sha) >= 7
    # Verify push was called with timeout=30
    push_calls = [c for c in captured_calls if c[0][0][:2] == ["git", "push"]]
    assert len(push_calls) == 1
    assert push_calls[0][1].get("timeout") == 30


def test_commit_and_push_falls_back_to_master(tmp_path):
    """If 'git push origin main' fails with 'src refspec main', retry with master."""
    from backend.backup.git_remote import commit_and_push, ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    (backup_dir / "x.json").write_text("{}")

    real_run = subprocess.run
    push_attempts = []

    def fake_run(*args, **kwargs):
        cmd = args[0]
        if cmd[:2] == ["git", "push"]:
            push_attempts.append(cmd)
            result = MagicMock()
            if "main" in cmd:
                result.returncode = 1
                result.stdout = ""
                result.stderr = "error: src refspec main does not match any"
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result
        return real_run(*args, **kwargs)

    with patch("backend.backup.git_remote.subprocess.run", side_effect=fake_run):
        sha = commit_and_push(backup_dir, "test")

    assert len(push_attempts) == 2
    assert "main" in push_attempts[0]
    assert "master" in push_attempts[1]
    assert isinstance(sha, str)


def test_commit_and_push_raises_on_real_failure(tmp_path):
    """Auth failures (or any non-refspec error) should raise."""
    from backend.backup.git_remote import commit_and_push, ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    (backup_dir / "x.json").write_text("{}")

    real_run = subprocess.run

    def fake_run(*args, **kwargs):
        cmd = args[0]
        if cmd[:2] == ["git", "push"]:
            result = MagicMock()
            result.returncode = 128
            result.stdout = ""
            result.stderr = "remote: Permission denied"
            return result
        return real_run(*args, **kwargs)

    with patch("backend.backup.git_remote.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError) as exc:
            commit_and_push(backup_dir, "test")
        assert "Permission denied" in str(exc.value)
        # Crucially, the PAT must NOT appear in the raised message
        assert "pat" not in str(exc.value).lower() or "x-access-token:***" in str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_backup_git_remote.py -v`
Expected: FAIL — `cannot import name 'inject_pat' from 'backend.backup.git_remote'`.

- [ ] **Step 3: Implement `backend/backup/git_remote.py`**

```python
"""Subprocess-driven git wrapper. Handles PAT URL construction, idempotent
init, commit + push with timeout and PAT scrubbing in error output."""
import logging
import re
import subprocess
from pathlib import Path


log = logging.getLogger(__name__)

# 30-second cap on every git invocation. Hung pushes (network stalls)
# raise TimeoutExpired which the orchestrator catches.
GIT_TIMEOUT = 30


def inject_pat(url: str, pat: str) -> str:
    """Return https URL with PAT injected as username, in the form
    https://x-access-token:<pat>@github.com/owner/repo.git.
    Idempotent: a URL that already has 'x-access-token:' is returned unchanged.
    Raises ValueError on non-https URLs (we don't support ssh)."""
    if not url.startswith("https://"):
        raise ValueError(f"only https URLs are supported, got: {url!r}")
    if "x-access-token:" in url:
        return url
    return url.replace("https://", f"https://x-access-token:{pat}@", 1)


_PAT_PATTERN = re.compile(r"x-access-token:[^@]+@")


def scrub_pat(text: str) -> str:
    """Replace any embedded PAT with x-access-token:*** for safe logging."""
    return _PAT_PATTERN.sub("x-access-token:***@", text)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Wrapper that always passes timeout, capture, text mode."""
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=GIT_TIMEOUT,
    )


def ensure_initialized(backup_dir: Path, remote_url: str, pat: str) -> None:
    """If `backup_dir/.git` exists, no-op. Otherwise:
       - git init
       - configure user.email + user.name
       - commit --allow-empty -m "init" (so HEAD exists before first push)
       - git remote add origin <pat-injected-url>
    """
    if (backup_dir / ".git").exists():
        return

    backup_dir.mkdir(parents=True, exist_ok=True)
    pat_url = inject_pat(remote_url, pat)

    _run(["git", "init", "-b", "main"], cwd=backup_dir)
    _run(["git", "config", "user.email", "backup@localhost"], cwd=backup_dir)
    _run(["git", "config", "user.name", "Backup Bot"], cwd=backup_dir)
    _run(["git", "commit", "--allow-empty", "-m", "init"], cwd=backup_dir)
    _run(["git", "remote", "add", "origin", pat_url], cwd=backup_dir)


def commit_and_push(backup_dir: Path, message: str) -> str:
    """git add . → git commit (allow-empty so empty cycles still tag a HEAD)
    → git push origin main (fall back to master on src-refspec failure).
    Returns the resulting commit SHA. Raises RuntimeError on push failure
    after PAT-scrubbing the captured stderr."""
    _run(["git", "add", "."], cwd=backup_dir)
    _run(["git", "commit", "--allow-empty", "-m", message], cwd=backup_dir)

    sha_proc = _run(["git", "rev-parse", "HEAD"], cwd=backup_dir)
    sha = sha_proc.stdout.strip()

    push = _run(["git", "push", "origin", "main"], cwd=backup_dir)
    if push.returncode != 0:
        if "src refspec main" in push.stderr:
            push = _run(["git", "push", "origin", "master"], cwd=backup_dir)
        if push.returncode != 0:
            stderr = scrub_pat(push.stderr or "")
            raise RuntimeError(f"git push failed: {stderr}")

    return sha
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_backup_git_remote.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 526 prior + 9 new = 535 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/backup/git_remote.py tests/test_backup_git_remote.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket12): backup git wrapper

inject_pat builds https://x-access-token:<pat>@github.com URL form
(idempotent if PAT already present). ensure_initialized seeds git dir
with --allow-empty init commit and remote. commit_and_push runs with
30s timeout, falls back from main→master, scrubs PAT from any error
output before raising.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `run_backup_cycle` Orchestrator

**Goal:** Top-level orchestrator that reads env, runs dump → write → rotate → git → log. Per-step fault isolation; missing env triggers silent skip with info event.

**Files:**
- Modify: `backend/backup/service.py` (append orchestrator)
- Create: `tests/test_backup_cycle.py`

- [ ] **Step 1: Write `tests/test_backup_cycle.py`**

```python
"""Tests for run_backup_cycle orchestrator."""
import json
import sqlite3
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
    monkeypatch.setattr("backend.backup.service.config.BACKUP_REPO_URL", "")
    monkeypatch.setattr("backend.backup.service.config.GITHUB_PAT", "")
    result = service.run_backup_cycle(fresh_db)
    assert result["pushed"] is False
    assert result["committed_sha"] is None
    assert result["snapshot_path"].endswith(".json")
    # snapshot files were created
    backup_dir = tmp_path / "backup"
    assert (backup_dir / "latest.json").exists()
    # system_events row exists
    row = fresh_db.execute(
        "SELECT * FROM system_events WHERE event_type='backup_skipped_no_remote'"
    ).fetchone()
    assert row is not None
    assert row["severity"] == "info"


def test_run_backup_cycle_logs_success_when_git_succeeds(fresh_db, tmp_path, monkeypatch):
    """Stub the git wrapper; verify event_type='backup_success' is logged."""
    from backend.backup import service
    monkeypatch.setattr("backend.backup.service.config.BACKUP_REPO_URL",
                        "https://github.com/x/y.git")
    monkeypatch.setattr("backend.backup.service.config.GITHUB_PAT", "fake")

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
    monkeypatch.setattr("backend.backup.service.config.BACKUP_REPO_URL",
                        "https://github.com/x/y.git")
    monkeypatch.setattr("backend.backup.service.config.GITHUB_PAT", "fake")

    with patch("backend.backup.service.git_remote.ensure_initialized"), \
         patch("backend.backup.service.git_remote.commit_and_push",
               side_effect=RuntimeError("git push failed: Permission denied")):
        with pytest.raises(RuntimeError):
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
    monkeypatch.setattr("backend.backup.service.config.BACKUP_REPO_URL", "")
    monkeypatch.setattr("backend.backup.service.config.GITHUB_PAT", "")

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
    monkeypatch.setattr("backend.backup.service.config.BACKUP_REPO_URL", "")
    monkeypatch.setattr("backend.backup.service.config.GITHUB_PAT", "")

    backup_dir = tmp_path / "backup"
    # Pre-seed 200 fake snapshot files
    import os, time
    for i in range(200):
        f = backup_dir / f"20260101-{i:04d}.json"
        f.write_text("{}")
        os.utime(f, (time.time() - 86400 + i, time.time() - 86400 + i))

    service.run_backup_cycle(fresh_db)
    # After rotation: at most 144 files remain (the new one + 143 of the older ones)
    snapshots = list(backup_dir.glob("20260101-*.json"))
    new_snapshots = list(backup_dir.glob("20260[5-9]*.json"))
    total_dated = len(snapshots) + len(new_snapshots)
    assert total_dated <= 144
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_backup_cycle.py -v`
Expected: FAIL — `cannot import name 'run_backup_cycle'`.

- [ ] **Step 3: Append orchestrator to `backend/backup/service.py`**

Add these imports at the top of `backend/backup/service.py` (alongside the existing ones):

```python
import json as _json  # avoid clash with json variable inside functions
```

(If `json` is already imported, you don't need this; just keep using `json`.)

Then append at the bottom:

```python
from backend import config
from backend.backup import git_remote
from backend.shared import audit


def run_backup_cycle(db: sqlite3.Connection) -> dict:
    """Top-level orchestrator. Runs:
       dump → write → rotate → (git if env set) → log.

    Returns {snapshot_path, committed_sha, pushed, rotated_count}.

    On any step failure: logs system_events('backup_failed', severity='error')
    with extra_json={step, error} and re-raises so callers (the loop swallows;
    the manual route translates to 500). Missing BACKUP_REPO_URL/GITHUB_PAT
    is NOT a failure: dump+rotate still run, git is skipped, success event
    is event_type='backup_skipped_no_remote' (severity='info').
    """
    backup_dir = config.BACKUP_DIR
    repo_url = config.BACKUP_REPO_URL
    pat = config.GITHUB_PAT

    # --- dump ---
    try:
        payload = dump_all_tables_to_json(db)
    except Exception as e:
        audit.log_system_event(
            db, "backup_failed", "error",
            message="dump failed",
            extra={"step": "dump", "error": str(e)},
        )
        raise

    # --- write snapshot ---
    ts = utc_timestamp()
    try:
        snapshot_path = write_snapshot(payload, backup_dir, ts=ts)
    except Exception as e:
        audit.log_system_event(
            db, "backup_failed", "error",
            message="write failed",
            extra={"step": "write", "error": str(e)},
        )
        raise

    # --- rotate ---
    try:
        rotated = rotate_snapshots(backup_dir, keep=144)
    except Exception as e:
        audit.log_system_event(
            db, "backup_failed", "error",
            message="rotate failed",
            extra={"step": "rotate", "error": str(e)},
        )
        raise

    # --- git push (skip if no remote configured) ---
    if not repo_url or not pat:
        audit.log_system_event(
            db, "backup_skipped_no_remote", "info",
            message="BACKUP_REPO_URL or GITHUB_PAT not set; skipping git push",
            extra={"snapshot_path": str(snapshot_path), "rotated_count": len(rotated)},
        )
        return {
            "snapshot_path": str(snapshot_path),
            "committed_sha": None,
            "pushed": False,
            "rotated_count": len(rotated),
        }

    try:
        git_remote.ensure_initialized(backup_dir, repo_url, pat)
        sha = git_remote.commit_and_push(backup_dir, f"auto-backup {ts}")
    except Exception as e:
        # Determine step for the event
        step = "init" if "init" in str(e).lower() else "push"
        audit.log_system_event(
            db, "backup_failed", "error",
            message="git push failed",
            extra={"step": step, "error": str(e)},
        )
        raise

    audit.log_system_event(
        db, "backup_success", "info",
        message=f"backed up {len(payload)} tables",
        extra={
            "snapshot_path": str(snapshot_path),
            "committed_sha": sha,
            "rotated_count": len(rotated),
        },
    )
    return {
        "snapshot_path": str(snapshot_path),
        "committed_sha": sha,
        "pushed": True,
        "rotated_count": len(rotated),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_backup_cycle.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 535 prior + 5 new = 540 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/backup/service.py tests/test_backup_cycle.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket12): run_backup_cycle orchestrator

Top-level dump → write → rotate → git → log flow with per-step fault
isolation. Missing BACKUP_REPO_URL/GITHUB_PAT means dump+rotate still
run; git is skipped with 'backup_skipped_no_remote' info event. Any
step failure logs 'backup_failed' with {step, error} extra and re-raises
so the admin route can return 500.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Async Backup Loop

**Goal:** `backup_loop()` async task that runs `run_backup_cycle` inside `asyncio.to_thread`, mirrors `backend/locks/sweep.py` pattern. Settings live-tuning, cancellation handling, exception swallowing.

**Files:**
- Create: `backend/backup/loop.py`
- Create: `tests/test_backup_loop.py`

- [ ] **Step 1: Write `tests/test_backup_loop.py`**

```python
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

    async def slow_cycle(db):
        await asyncio.sleep(10)

    with patch("backend.backup.loop.backup_once", side_effect=slow_cycle), \
         patch("backend.backup.loop.connect"), \
         patch("backend.backup.loop._read_interval", return_value=600):
        task = asyncio.create_task(backup_loop_mod.backup_loop())
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.wait_for(task, timeout=1.0)
        # Task done without raising
        assert task.done()


@pytest.mark.asyncio
async def test_backup_loop_swallows_cycle_exception_and_continues():
    """If backup_once raises, log + continue (don't kill the loop)."""
    from backend.backup import loop as backup_loop_mod

    call_count = [0]

    async def cycle_then_raise():
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("boom")

    with patch("backend.backup.loop.backup_once", side_effect=cycle_then_raise), \
         patch("backend.backup.loop._read_interval", return_value=0):
        task = asyncio.create_task(backup_loop_mod.backup_loop())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # Loop iterated at least twice (first raised, second was the resilient continuation)
        assert call_count[0] >= 2


def test_read_interval_returns_default_when_setting_missing(tmp_path, monkeypatch):
    from backend.backup import loop as backup_loop_mod
    from backend.shared.db import connect
    from backend.migrations import discover_migrations
    from backend.migrations.runner import apply_migrations

    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    # Default is 600 (seeded by v0001)
    interval = backup_loop_mod._read_interval(conn)
    assert interval == 600
    conn.close()


def test_read_interval_picks_up_admin_change(tmp_path, monkeypatch):
    from backend.backup import loop as backup_loop_mod
    from backend.shared.db import connect
    from backend.migrations import discover_migrations
    from backend.migrations.runner import apply_migrations
    from backend.shared import settings as S

    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    # Admin changes interval to 1200
    S.set_value(conn, "backup.interval_seconds", 1200, updated_by_user_id=None)
    interval = backup_loop_mod._read_interval(conn)
    assert interval == 1200
    conn.close()
```

(Note: install `pytest-asyncio` if not already present. Check requirements.txt.)

- [ ] **Step 2: Verify `pytest-asyncio` is available**

Run: `.venv/bin/python -c "import pytest_asyncio; print('ok')"`
Expected: `ok`. If `ImportError`, run `.venv/bin/pip install pytest-asyncio` then add to requirements.txt.

If `pytest-asyncio` is unavailable AND not in requirements.txt, prefer adapting tests to use synchronous wrappers via `asyncio.run()` calls inside the test bodies instead of `@pytest.mark.asyncio`. Read the existing tests in `tests/test_locks_sweep.py` for the pattern used by Paket 7 (sweep) — that's likely the established convention. Match it.

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_backup_loop.py -v`
Expected: FAIL — `cannot import name 'backup_once' from 'backend.backup.loop'`.

- [ ] **Step 4: Implement `backend/backup/loop.py`**

```python
"""Async backup loop. Mirrors backend/locks/sweep.py pattern.

Started from backend/main.py lifespan, cancelled on shutdown. Single-process,
safe with WAL mode. Each iteration re-reads backup.interval_seconds from
site_settings so admin tuning takes effect on the next cycle."""
import asyncio
import logging
import sqlite3
from typing import Optional

from backend import config
from backend.backup.service import run_backup_cycle
from backend.shared import settings as S
from backend.shared.db import connect


log = logging.getLogger(__name__)


def _read_interval(db: sqlite3.Connection) -> int:
    return S.get_int(db, "backup.interval_seconds", default=600)


async def backup_once() -> dict:
    """Run a single backup cycle. Exposed for tests so the cycle can be
    triggered without the loop's sleep."""
    def _do() -> dict:
        conn = connect(config.DB_PATH)
        try:
            return run_backup_cycle(conn)
        finally:
            conn.close()
    return await asyncio.to_thread(_do)


async def backup_loop() -> None:
    """Async loop. Cancel via task.cancel().

    Each iteration:
      1. Re-read backup.interval_seconds (live admin tuning).
      2. Sleep `interval_seconds`.
      3. Run one backup cycle inside asyncio.to_thread.
      4. Swallow any non-Cancelled exception; log + continue.
    """
    while True:
        # Read interval at start of each iteration
        try:
            conn = connect(config.DB_PATH)
            try:
                interval = _read_interval(conn)
            finally:
                conn.close()
        except Exception:
            log.exception("backup loop: failed to read interval; using default 600")
            interval = 600

        try:
            await asyncio.sleep(interval)
            await backup_once()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("backup cycle iteration failed")


_task: Optional[asyncio.Task] = None


def start() -> asyncio.Task:
    """Start the backup task; returns the task handle for shutdown cancellation."""
    global _task
    _task = asyncio.create_task(backup_loop())
    return _task


def stop() -> None:
    """Cancel the running backup task (no-op if not started)."""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
    _task = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_backup_loop.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 540 prior + 5 new = 545 PASS.

- [ ] **Step 7: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/backup/loop.py tests/test_backup_loop.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket12): async backup loop

Mirrors backend/locks/sweep.py pattern. Each iteration re-reads
backup.interval_seconds from site_settings (live admin tuning).
asyncio.to_thread wraps the blocking dump+git work. CancelledError
exits cleanly; other exceptions are logged and the loop continues.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Lifespan Integration

**Goal:** Mount the backup loop into `backend/main.py` lifespan alongside the existing locks sweep. Server startup creates the task; shutdown cancels and awaits it.

**Files:**
- Modify: `backend/main.py`
- Create: `tests/test_backup_lifespan.py`

- [ ] **Step 1: Read the current `backend/main.py` lifespan**

Run: `cat /Users/barandincoguz/Desktop/deneme/backend/main.py | head -80`

Locate the `lifespan` function (around lines 33-60) and the existing pattern for `locks_sweep.start()` / `stop()`. Mirror that pattern for backup.

- [ ] **Step 2: Write `tests/test_backup_lifespan.py`**

```python
"""Smoke tests verifying the backup task starts and stops cleanly with the server."""
from fastapi.testclient import TestClient
from unittest.mock import patch


def test_lifespan_starts_and_stops_backup_task(tmp_path, monkeypatch):
    """Server lifespan creates the backup task on startup and cancels it on
    shutdown without raising."""
    from backend import main, config
    from backend.backup import loop as backup_loop_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr(config, "DB_DIR", tmp_path / "db")
    monkeypatch.setattr(config, "DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path / "exports")

    started = []
    stopped = []
    real_start = backup_loop_mod.start
    real_stop = backup_loop_mod.stop

    def fake_start():
        started.append(True)
        return real_start()

    def fake_stop():
        stopped.append(True)
        return real_stop()

    with patch("backend.main.backup_loop.start", side_effect=fake_start), \
         patch("backend.main.backup_loop.stop", side_effect=fake_stop):
        with TestClient(main.app) as client:
            r = client.get("/api/health")
            assert r.status_code == 200
        # After exiting the with block, lifespan shutdown ran
        assert started == [True]
        assert stopped == [True]


def test_lifespan_logs_startup_includes_backup_task(tmp_path, monkeypatch):
    """A cosmetic-but-useful test: when server starts, the existing
    'startup' system_events row should be written (already a regression
    target). Ensures the backup task addition doesn't break startup."""
    from backend import main, config
    from backend.shared.db import connect

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr(config, "DB_DIR", tmp_path / "db")
    monkeypatch.setattr(config, "DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path / "exports")

    with TestClient(main.app) as client:
        client.get("/api/health")

    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT * FROM system_events WHERE event_type='startup'"
        ).fetchall()
        assert len(rows) >= 1
    finally:
        conn.close()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_backup_lifespan.py -v`
Expected: FAIL — `backup_loop` is not imported in main.py yet.

- [ ] **Step 4: Modify `backend/main.py` — add backup loop to lifespan**

In `backend/main.py`, add an import at the top (alongside other backend.* imports):

```python
from backend.backup import loop as backup_loop
from backend.backup.routes import router as backup_router
```

Then update the `lifespan` function to start/stop the backup task. Find the existing block:

```python
    sweep_task = locks_sweep.start(interval_seconds=60)
    yield

    locks_sweep.stop()
    try:
        await sweep_task
    except Exception:
        pass
```

Replace with:

```python
    sweep_task = locks_sweep.start(interval_seconds=60)
    backup_task = backup_loop.start()
    yield

    locks_sweep.stop()
    try:
        await sweep_task
    except Exception:
        pass

    backup_loop.stop()
    try:
        await backup_task
    except Exception:
        pass
```

Also mount the backup router (Task 6 will create it; for now this import will fail. Defer the `app.include_router(backup_router)` line until Task 6 — DON'T add the router mount yet, only the lifespan integration.)

To make Task 5 work without Task 6's router file: at the top of `backend/main.py` import only `backup_loop`, NOT `backup_router`. Add the router import + mount in Task 6.

So the actual change in Task 5 is just:

```python
# Top of file:
from backend.backup import loop as backup_loop

# In lifespan, after sweep_task = locks_sweep.start(...):
backup_task = backup_loop.start()

# In lifespan shutdown, after the existing sweep stop block:
backup_loop.stop()
try:
    await backup_task
except Exception:
    pass
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_backup_lifespan.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 545 prior + 2 new = 547 PASS.

- [ ] **Step 7: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/main.py tests/test_backup_lifespan.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket12): start backup loop in FastAPI lifespan

Mirrors locks sweep integration. backup_loop.start() returns the task;
shutdown calls stop() and awaits the task with exception swallowing
(consistent with existing sweep pattern).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Manual Trigger Endpoint

**Goal:** `POST /api/admin/backup/run-now` — admin-only synchronous trigger that runs `run_backup_cycle` and returns its result. Audits via `admin_audit_log`. 500 on cycle failure.

**Files:**
- Create: `backend/backup/models.py`
- Create: `backend/backup/routes.py`
- Modify: `backend/main.py` (mount backup router — last task touched it for lifespan)
- Create: `tests/test_backup_admin_route.py`

- [ ] **Step 1: Write `tests/test_backup_admin_route.py`**

(Use the `bootstrap_admin` and `seen_manual_user` conftest fixtures introduced in Paket 11 polish. They are in `tests/conftest.py`.)

```python
"""Admin endpoint POST /api/admin/backup/run-now."""
from unittest.mock import patch


def test_run_now_succeeds_with_no_remote(client, bootstrap_admin):
    """No BACKUP_REPO_URL → 200, pushed=False, committed_sha=None."""
    bootstrap_admin()
    r = client.post("/api/admin/backup/run-now")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["pushed"] is False
    assert body["committed_sha"] is None
    assert body["snapshot_path"].endswith(".json")


def test_run_now_writes_audit_row(client, bootstrap_admin):
    admin_id = bootstrap_admin()
    client.post("/api/admin/backup/run-now")

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='backup_run_now'"
    ).fetchone()
    assert row is not None
    assert row["admin_user_id"] == admin_id
    db.close()


def test_run_now_writes_system_event(client, bootstrap_admin):
    bootstrap_admin()
    client.post("/api/admin/backup/run-now")

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM system_events "
        "WHERE event_type IN ('backup_skipped_no_remote','backup_success') "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    db.close()


def test_run_now_requires_admin(client, seen_manual_user):
    """Non-admin → 404 existence-hide."""
    seen_manual_user("bursiyer1", "INVITE-2026")
    r = client.post("/api/admin/backup/run-now")
    assert r.status_code == 404


def test_run_now_returns_500_on_cycle_failure(client, bootstrap_admin):
    """If run_backup_cycle raises, the route returns 500 with an error body.
    The system_events failure row was already written by the cycle."""
    bootstrap_admin()
    with patch("backend.backup.routes.run_backup_cycle",
               side_effect=RuntimeError("git push failed")):
        r = client.post("/api/admin/backup/run-now")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"]["error"] == "backup_failed"
    assert "git push failed" in body["detail"]["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_backup_admin_route.py -v`
Expected: FAIL — route doesn't exist yet.

- [ ] **Step 3: Create `backend/backup/models.py`**

```python
"""Pydantic schemas for backup endpoints."""
from pydantic import BaseModel


class BackupRunNowResponse(BaseModel):
    ok: bool
    snapshot_path: str
    committed_sha: str | None
    pushed: bool
    rotated_count: int
```

- [ ] **Step 4: Create `backend/backup/routes.py`**

```python
"""Admin HTTP endpoint for manual backup trigger."""
import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.backup.models import BackupRunNowResponse
from backend.backup.service import run_backup_cycle
from backend.shared import audit
from backend.users.deps import get_db, require_admin


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/backup", tags=["admin-backup"])


@router.post("/run-now", response_model=BackupRunNowResponse)
def admin_backup_run_now(
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Trigger a backup cycle synchronously. Blocks until complete.
    Returns 500 on any cycle failure (system_events row already written
    by the cycle's per-step error logging)."""
    try:
        result = run_backup_cycle(db)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "backup_failed", "message": str(e)},
        )

    try:
        from pathlib import Path
        snapshot_filename = Path(result["snapshot_path"]).name
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="backup_run_now",
            target_kind="backup", target_id=snapshot_filename,
            metadata={
                "pushed": result["pushed"],
                "committed_sha": result["committed_sha"],
                "rotated_count": result["rotated_count"],
            },
        )
    except Exception:
        log.exception("audit backup_run_now failed")

    return {
        "ok": True,
        "snapshot_path": result["snapshot_path"],
        "committed_sha": result["committed_sha"],
        "pushed": result["pushed"],
        "rotated_count": result["rotated_count"],
    }
```

- [ ] **Step 5: Mount the router in `backend/main.py`**

At the top of `backend/main.py`, add:

```python
from backend.backup.routes import router as backup_router
```

Then in the router-mount block (after the existing `app.include_router(...)` lines), add:

```python
app.include_router(backup_router)
```

- [ ] **Step 6: Run target tests**

Run: `.venv/bin/python -m pytest tests/test_backup_admin_route.py -v`
Expected: 5 PASS.

- [ ] **Step 7: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 547 prior + 5 new = 552 PASS.

- [ ] **Step 8: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/backup/models.py backend/backup/routes.py backend/main.py tests/test_backup_admin_route.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket12): admin manual backup trigger

POST /api/admin/backup/run-now blocks until run_backup_cycle returns.
500 on cycle failure (cycle has already written the system_events row).
Audit row uses metadata={pushed, committed_sha, rotated_count}. Audit
write failure is logged but does not fail the request (per-step fault
isolation pattern).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Restore Core (`restore_from_snapshot`)

**Goal:** Pure function that reads a snapshot JSON, runs migrations on the target DB, then DELETE+INSERT per table inside a transaction. Returns `{tables: {<name>: row_count}, total_rows}`. Raises on any error.

**Files:**
- Create: `backend/backup/restore.py`
- Create: `tests/test_backup_restore.py`

- [ ] **Step 1: Write `tests/test_backup_restore.py`**

```python
"""Tests for restore_from_snapshot."""
import json
import sqlite3
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


def _write_snapshot(tmp_path: Path, payload: dict) -> Path:
    snap = tmp_path / "test_snapshot.json"
    snap.write_text(json.dumps(payload, ensure_ascii=False))
    return snap


def test_restore_populates_tables(fresh_db, tmp_path):
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "invite_codes": [
            {"id": 1, "code": "RESTORED", "is_active": 1, "created_at": "2026-05-09T00:00:00+00:00"},
        ],
        "users": [],
    }
    snap = _write_snapshot(tmp_path, payload)
    out = restore_from_snapshot(fresh_db, snap)
    assert out["tables"]["invite_codes"] == 1
    row = fresh_db.execute("SELECT code FROM invite_codes WHERE id=1").fetchone()
    assert row["code"] == "RESTORED"


def test_restore_does_not_touch_schema_migrations(fresh_db, tmp_path):
    """schema_migrations should NOT be in the snapshot or restored. The DB
    has its own migration state via apply_migrations."""
    from backend.backup.restore import restore_from_snapshot
    pre_migrations = fresh_db.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    pre_versions = [r["version"] for r in pre_migrations]

    payload = {"users": []}  # snapshot does not include schema_migrations
    snap = _write_snapshot(tmp_path, payload)
    restore_from_snapshot(fresh_db, snap)

    post_migrations = fresh_db.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [r["version"] for r in post_migrations] == pre_versions


def test_restore_clears_existing_rows_first(fresh_db, tmp_path):
    """Tables in the snapshot are TRUNCATE-INSERT. Pre-existing rows should be gone."""
    fresh_db.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,?)",
        ("OLD", "2026-05-01T00:00:00+00:00"),
    )
    fresh_db.commit()
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "invite_codes": [
            {"id": 1, "code": "NEW", "is_active": 1, "created_at": "2026-05-09T00:00:00+00:00"},
        ],
    }
    snap = _write_snapshot(tmp_path, payload)
    restore_from_snapshot(fresh_db, snap)
    rows = fresh_db.execute("SELECT code FROM invite_codes").fetchall()
    codes = [r["code"] for r in rows]
    assert "OLD" not in codes
    assert "NEW" in codes


def test_restore_returns_total_row_count(fresh_db, tmp_path):
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "invite_codes": [
            {"id": 1, "code": "A", "is_active": 1, "created_at": "2026-05-09T00:00:00+00:00"},
            {"id": 2, "code": "B", "is_active": 1, "created_at": "2026-05-09T00:00:00+00:00"},
        ],
    }
    snap = _write_snapshot(tmp_path, payload)
    out = restore_from_snapshot(fresh_db, snap)
    assert out["total_rows"] == 2
    assert out["tables"]["invite_codes"] == 2


def test_restore_rolls_back_on_failure(fresh_db, tmp_path):
    """If a single INSERT fails (e.g. unknown column), nothing is committed."""
    fresh_db.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,?)",
        ("PRE_EXISTING", "2026-05-01T00:00:00+00:00"),
    )
    fresh_db.commit()
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "invite_codes": [{"this_column_does_not_exist": "x"}],
    }
    snap = _write_snapshot(tmp_path, payload)
    with pytest.raises(Exception):
        restore_from_snapshot(fresh_db, snap)
    # Pre-existing row should still be there (rollback worked)
    row = fresh_db.execute(
        "SELECT code FROM invite_codes WHERE code='PRE_EXISTING'"
    ).fetchone()
    assert row is not None


def test_restore_skips_unknown_table(fresh_db, tmp_path):
    """If a snapshot contains a table not in the current schema, skip it
    with a warning rather than crash. Forward-compatible."""
    from backend.backup.restore import restore_from_snapshot
    payload = {
        "future_table_does_not_exist_yet": [{"id": 1, "x": "y"}],
        "invite_codes": [
            {"id": 1, "code": "A", "is_active": 1, "created_at": "2026-05-09T00:00:00+00:00"},
        ],
    }
    snap = _write_snapshot(tmp_path, payload)
    out = restore_from_snapshot(fresh_db, snap)
    # invite_codes restored; future_table is silently skipped
    assert out["tables"]["invite_codes"] == 1
    assert "future_table_does_not_exist_yet" not in out["tables"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_backup_restore.py -v`
Expected: FAIL — `cannot import name 'restore_from_snapshot' from 'backend.backup.restore'`.

- [ ] **Step 3: Implement `backend/backup/restore.py`**

```python
"""Restore from a JSON snapshot. The DB must already have the current
schema applied (migrations) before this is called. The function does
DELETE+INSERT per table inside a single BEGIN IMMEDIATE transaction;
on any error it rolls back so the caller can decide how to recover.

Tables in the snapshot that don't exist in the current schema are
silently skipped (forward-compatible: a future table name in an old
snapshot won't break restore)."""
import json
import logging
import sqlite3
from pathlib import Path


log = logging.getLogger(__name__)


def restore_from_snapshot(db: sqlite3.Connection, snapshot_path: Path) -> dict:
    """Read snapshot JSON, DELETE+INSERT each known table inside a
    transaction. Returns {tables: {<name>: row_count}, total_rows}.

    Raises on any error after rolling back the transaction so the caller
    can swap the DB back to the corrupt-bak file.
    """
    with open(snapshot_path, encoding="utf-8") as f:
        payload = json.load(f)

    # Find which tables exist in the current schema
    existing = {
        r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    db.execute("BEGIN IMMEDIATE")
    try:
        result_tables: dict[str, int] = {}
        total = 0
        for table, rows in payload.items():
            if table not in existing:
                log.warning("restore: skipping unknown table %s", table)
                continue
            db.execute(f"DELETE FROM {table}")
            for row in rows:
                cols = list(row.keys())
                placeholders = ",".join("?" for _ in cols)
                col_list = ",".join(cols)
                db.execute(
                    f"INSERT INTO {table}({col_list}) VALUES ({placeholders})",
                    [row[c] for c in cols],
                )
            result_tables[table] = len(rows)
            total += len(rows)
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    return {"tables": result_tables, "total_rows": total}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_backup_restore.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 552 prior + 6 new = 558 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/backup/restore.py tests/test_backup_restore.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket12): restore_from_snapshot core

Reads JSON snapshot, runs DELETE+INSERT per known table inside
BEGIN IMMEDIATE. Unknown tables (snapshot from a newer schema) are
silently skipped — forward-compatible. Any error rolls back; caller
decides recovery (the CLI will swap back the corrupt-bak file).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Restore CLI Subcommand

**Goal:** `python -m backend.cli restore-from-github [--snapshot <YYYYMMDD-HHMM>] [--yes] [--force]`. Drives env validation, corrupt-bak rename, git clone, snapshot pick, confirmation prompt, dispatch to `restore_from_snapshot`, cleanup.

**Files:**
- Modify: `backend/cli.py` (add `restore-from-github` subcommand)
- Create: `tests/test_cli_restore_from_github.py`

- [ ] **Step 1: Write `tests/test_cli_restore_from_github.py`**

```python
"""Tests for backend.cli restore-from-github subcommand."""
import json
import os
import shutil
import sqlite3
import sys
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
        # Simulate `git clone` by copying the prepared clone to dest
        shutil.copytree(clone, dest)

    with patch("backend.cli._clone_backup_repo", side_effect=fake_clone):
        rc = cli.main(["restore-from-github", "--yes"])

    assert rc == 0
    # Verify the restored row is in the DB
    conn = connect(config.DB_PATH)
    row = conn.execute(
        "SELECT code FROM invite_codes WHERE code='RESTORED'"
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
    # corrupt-*.db.bak file should exist in db/ dir
    bak_files = list((fresh_data_dir / "db").glob("corrupt-*.db.bak"))
    assert len(bak_files) == 1


def test_restore_rolls_back_on_failure(fresh_data_dir, monkeypatch):
    """If the restore step itself fails, the corrupt-bak is restored to
    annotations.db so the operator's pre-restore state is preserved."""
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "https://github.com/x/y.git")
    monkeypatch.setattr(config, "GITHUB_PAT", "fake-pat")

    # Pre-write a recognizable row so we can verify it's restored
    conn = connect(config.DB_PATH)
    conn.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,?)",
        ("PRESTORE", "2026-05-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    # Snapshot has a malformed row that will cause INSERT to fail
    bad_payload = {"invite_codes": [{"unknown_column": "x"}]}
    clone = _write_clone(fresh_data_dir, bad_payload)

    def fake_clone(_url, dest):
        shutil.copytree(clone, dest)

    with patch("backend.cli._clone_backup_repo", side_effect=fake_clone):
        rc = cli.main(["restore-from-github", "--yes"])
    assert rc == 1

    # Original DB content was restored
    conn = connect(config.DB_PATH)
    row = conn.execute(
        "SELECT code FROM invite_codes WHERE code='PRESTORE'"
    ).fetchone()
    assert row is not None
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli_restore_from_github.py -v`
Expected: FAIL — `'restore-from-github' subcommand not recognized`.

- [ ] **Step 3: Add `restore-from-github` subcommand to `backend/cli.py`**

Open `backend/cli.py`. Find the existing pattern (e.g. `cmd_import_gold_docs` and the `COMMANDS` dict). Add:

```python
import shutil
import subprocess
import sys
from datetime import datetime, timezone


def _clone_backup_repo(pat_url: str, dest: Path) -> None:
    """Wrapper for `git clone <pat-url> <dest>`. Extracted as its own
    function so tests can patch it without spawning real git processes."""
    result = subprocess.run(
        ["git", "clone", pat_url, str(dest)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        from backend.backup.git_remote import scrub_pat
        stderr = scrub_pat(result.stderr or "")
        raise RuntimeError(f"git clone failed: {stderr}")


def cmd_restore_from_github(args) -> int:
    """Restore the local DB from a snapshot in the GitHub backup repo.

    Flow:
      1. Read BACKUP_REPO_URL + GITHUB_PAT from config (env-backed).
      2. Rename current DB to corrupt-<UTC ISO>.db.bak.
      3. Clone the backup repo to /tmp/restore-<ts>/.
      4. Pick the requested snapshot (default: latest.json).
      5. Confirmation prompt (skipped with --yes).
      6. Run migrations on the new (empty) DB, then restore.
      7. On error: rename corrupt-bak back to annotations.db.
      8. Clean up the /tmp clone.
    """
    if not config.BACKUP_REPO_URL or not config.GITHUB_PAT:
        print(
            "error: BACKUP_REPO_URL and GITHUB_PAT must both be set "
            "in the environment.",
            file=sys.stderr,
        )
        return 1

    # Step 2: rename current DB
    db_path = config.DB_PATH
    bak_path = None
    if db_path.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bak_path = db_path.parent / f"corrupt-{ts}.db.bak"
        db_path.rename(bak_path)

    # Step 3: clone
    from backend.backup.git_remote import inject_pat
    pat_url = inject_pat(config.BACKUP_REPO_URL, config.GITHUB_PAT)
    clone_dir = Path(f"/tmp/restore-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")

    try:
        _clone_backup_repo(pat_url, clone_dir)
    except Exception as e:
        print(f"error: clone failed: {e}", file=sys.stderr)
        if bak_path is not None:
            bak_path.rename(db_path)
        return 1

    try:
        # Step 4: pick snapshot
        if args.snapshot:
            snap_path = clone_dir / f"{args.snapshot}.json"
        else:
            snap_path = clone_dir / "latest.json"
        if not snap_path.exists():
            print(f"error: snapshot not found: {snap_path.name}", file=sys.stderr)
            if bak_path is not None:
                bak_path.rename(db_path)
            return 1

        # Step 5: prompt
        if not args.yes:
            with open(snap_path, encoding="utf-8") as f:
                preview = json.load(f)
            n_tables = len(preview)
            n_rows = sum(len(rows) for rows in preview.values())
            print(f"Will restore {n_tables} tables, {n_rows} total rows from {snap_path.name}.")
            answer = input("Continue? [y/N] ").strip().lower()
            if answer != "y":
                print("aborted")
                if bak_path is not None:
                    bak_path.rename(db_path)
                return 1

        # Step 6: open new DB, run migrations, restore
        config.ensure_dirs()
        conn = connect(db_path)
        try:
            from backend.migrations import discover_migrations
            from backend.migrations.runner import apply_migrations
            apply_migrations(conn, discover_migrations())

            from backend.backup.restore import restore_from_snapshot
            result = restore_from_snapshot(conn, snap_path)
        finally:
            conn.close()

        # Step 7: print summary
        print(f"Restored {result['total_rows']} rows across {len(result['tables'])} tables:")
        for table, count in result["tables"].items():
            print(f"  {table}: {count}")

    except Exception as e:
        print(f"error: restore failed: {e}", file=sys.stderr)
        # Roll back: remove the new (partial) DB and rename bak back
        if db_path.exists():
            db_path.unlink()
        if bak_path is not None:
            bak_path.rename(db_path)
        # Clean up clone
        if clone_dir.exists():
            shutil.rmtree(clone_dir, ignore_errors=True)
        return 1

    # Step 8: clean up clone
    if clone_dir.exists():
        shutil.rmtree(clone_dir, ignore_errors=True)

    print(f"\nRestore complete. Pre-restore DB saved at: {bak_path}")
    return 0
```

Then register it in the existing `COMMANDS` dict:

```python
COMMANDS = {
    "migrate": cmd_migrate,
    "promote-admin": cmd_promote_admin,
    "demote-admin": cmd_demote_admin,
    "create-invite": cmd_create_invite,
    "rotate-invite": cmd_rotate_invite,
    "ingest": cmd_ingest,
    "import-gold-docs": cmd_import_gold_docs,
    "restore-from-github": cmd_restore_from_github,  # NEW
}
```

And add the subparser inside `main()`:

```python
    p_restore = sub.add_parser(
        "restore-from-github", help="Restore DB from latest GitHub backup snapshot",
    )
    p_restore.add_argument(
        "--snapshot", default=None,
        help="Specific snapshot stamp (e.g. 20260509-1430); default uses latest.json",
    )
    p_restore.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    p_restore.add_argument("--force", action="store_true",
        help="Proceed even if a sqlite3 lock is detected on the existing DB",
    )
```

(Note: `--force` is reserved per spec for WAL lock detection. Implement the lock check inside `cmd_restore_from_github` if you have time; otherwise leave the flag declared and document it as "reserved" — the spec mentions this risk but it's deferred.)

For Task 8 polish, omit the WAL lock check (would require either ATTACHing the DB read-only first or running PRAGMA quick_check; both have edge cases). Mention in the commit message that lock detection is deferred to a follow-up if it becomes a real operational issue.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli_restore_from_github.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 558 prior + 7 new = 565 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/cli.py tests/test_cli_restore_from_github.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket12): restore-from-github CLI subcommand

python -m backend.cli restore-from-github [--snapshot stamp] [--yes] [--force]
- Renames current DB to corrupt-<UTC>.db.bak before any risky step
- Clones backup repo to /tmp/restore-<ts>/
- Picks snapshot (latest.json or --snapshot stamp.json)
- Prompts unless --yes
- Runs migrations on fresh DB then restore_from_snapshot
- On any failure: removes partial DB, restores corrupt-bak in place, exit 1
- WAL lock detection deferred (--force flag declared but lock check
  is a future enhancement)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Polish + Tag

**Goal:** Cleanup pass; ensure dead imports removed, full suite green, tag the paket.

- [ ] **Step 1: Run full suite, check expected count**

Run: `.venv/bin/python -m pytest -q`
Expected: 565 PASS (515 baseline + 50 new = 565). If different, investigate before tagging.

- [ ] **Step 2: Run pyright (cosmetic, but flag any real type errors)**

Run: `.venv/bin/python -m pyright backend/ 2>&1 | grep -E "error" | head -30`
Expected: no errors beyond pre-existing import-resolution warnings.

- [ ] **Step 3: Quick dead-import scan in new files**

Run: `grep -rn "^import\|^from " backend/backup/ | head -50`

Look for: imports added during intermediate steps that aren't actually used. Fix obvious ones with Edit.

Also check `backend/main.py` for any dangling imports if Task 5/6 left some.

- [ ] **Step 4: Read your own diff**

```bash
git log --oneline paket-11-admin-panel..HEAD
git diff paket-11-admin-panel..HEAD --stat
```

Expected: 8 commits (Tasks 1-8), each focused; messages match conventions; ~12-15 files changed; net ~+1500 lines.

- [ ] **Step 5: Polish commit (if anything found in step 3)**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add <files>
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
chore(paket12): polish — dead imports, pyright cleanup

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Tag the paket**

```bash
git tag paket-12-backup
```

- [ ] **Step 7: Final summary**

Run: `git log --oneline paket-11-admin-panel..paket-12-backup`
Expected: a clean linear sequence of feat/chore commits, all signed-off by Co-Authored-By footer.

---

## Verification Checklist (post-completion)

- [ ] All 9 tasks committed with the prescribed messages
- [ ] `paket-12-backup` tag created
- [ ] `.venv/bin/python -m pytest -q` reports 565 PASS, 0 FAIL
- [ ] Fresh DB: `DATA_DIR=/tmp/p12-fresh .venv/bin/python -m backend.cli migrate` applies v0001 + v0002 cleanly on a fresh data dir (no v0003 — Paket 12 has no migration)
- [ ] Manual smoke (no real GitHub repo needed):
  - Start server with `BACKUP_REPO_URL=""` → loop runs every 600s; system_events shows `backup_skipped_no_remote` after first interval
  - `curl -X POST -b cookies.txt http://127.0.0.1:8000/api/admin/backup/run-now` → returns `{ok: true, pushed: false}`
  - Check `<DATA_DIR>/backup/latest.json` exists and is valid JSON
- [ ] Manual smoke with real test repo (optional, requires PAT):
  - Set `BACKUP_REPO_URL=...` and `GITHUB_PAT=...`
  - Trigger via admin endpoint → commit lands on remote, `committed_sha` returned
  - Run `python -m backend.cli restore-from-github --yes` against the same repo → row counts match
- [ ] No regressions in Paket 7-10 SSE/lock/training tests (lifespan changes affect their tests' fixture lifecycle)
- [ ] No regressions in Paket 11 admin tests (audit-log endpoint format unchanged)
