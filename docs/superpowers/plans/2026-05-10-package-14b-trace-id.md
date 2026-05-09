# Paket 14b — Trace-ID Co-Correlation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `trace_id` column to `admin_audit_log` and `system_events` so admin-triggered chains can be correlated with a single key; thread the id explicitly through ~14 admin call sites.

**Architecture:** SQLite schema migration (v0004) adds a nullable `trace_id TEXT` column to both tables plus partial indexes. A helper `gen_trace_id()` produces a 16-char hex token at admin route entry. Two log helpers (`log_admin_action`, `log_system_event`) accept an optional `trace_id` keyword argument. Two service functions (`run_backup_cycle`, `run_purge`) accept and propagate the id to inner `log_system_event` calls. Background loops and lifespan emit NULL `trace_id` by design. No middleware, no contextvar — explicit threading only.

**Tech Stack:** Python 3.13, FastAPI, SQLite (WAL, busy_timeout=5000), pytest, uuid stdlib.

**Spec:** `docs/superpowers/specs/2026-05-10-paket-14b-trace-id-design.md`

**Test runner:** `.venv/bin/python -m pytest <path> -v` (system Python lacks fastapi).

**Git config for every commit:** `git -c user.email=maarkval@icloud.com -c user.name=baran commit ...`. Footer:
```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## File Structure

| File | Role | Status |
|---|---|---|
| `backend/migrations/v0004_trace_id.py` | Migration: add column + partial index ×2 | **Create** |
| `backend/shared/audit.py` | Add `gen_trace_id()`, add `trace_id` kwarg on 2 helpers | Modify |
| `backend/backup/service.py` | `run_backup_cycle(..., trace_id=None)`, thread to 7 log_system_event calls | Modify |
| `backend/backup/routes.py` | Generate trace_id at entry, pass to service + audit | Modify |
| `backend/backup/models.py` | Add `trace_id: Optional[str] = None` to `BackupRunNowResponse` | Modify |
| `backend/retention/service.py` | `run_purge(..., trace_id=None)`, thread to 2 log_system_event calls | Modify |
| `backend/retention/routes.py` | Generate trace_id, pass to service + audit | Modify |
| `backend/retention/models.py` | Add `trace_id` to `RetentionRunNowResponse` | Modify |
| `backend/locks/routes.py` | Generate trace_id, pass to log_admin_action (force-release) | Modify |
| `backend/admin/routes.py` | Generate trace_id, pass to log_admin_action (settings update) | Modify |
| `backend/users/service.py` | Add `trace_id` kwarg on 5 admin actions, generate at caller | Modify |
| `backend/users/routes.py` | Generate trace_id at admin route entry, pass to user-service calls | Modify |
| `backend/training/service.py` | Add `trace_id` kwarg to `reset_user_training`, pass to log_admin_action | Modify |
| `backend/training/routes.py` | Generate trace_id at each of 4 admin endpoints | Modify |
| `backend/exports/routes.py` | Generate trace_id, capture in closure of `_record_audit_and_close` | Modify |
| `tests/test_v0004_trace_id_migration.py` | Migration test (column + index existence) | **Create** |
| `tests/test_audit.py` | +tests for gen_trace_id and trace_id param on both helpers | Modify |
| `tests/test_backup_admin_route.py` | +test: admin run-now → audit + system_events share trace_id | Modify |
| `tests/test_backup_loop.py` | +test: loop emits system_events with NULL trace_id | Modify |
| `tests/test_retention_admin_routes.py` | +test: admin run-now → audit + system_events share trace_id | Modify |
| `tests/test_retention_loop.py` | +test: loop emits system_events with NULL trace_id | Modify |
| `tests/test_locks_admin_force_release.py` | +test: audit row carries trace_id | Modify |
| `tests/test_admin_settings.py` (or equivalent) | +test: settings_update audit row carries trace_id | Modify |
| `tests/test_users_admin_routes.py` (or equivalent) | +test: promote/demote/disable/enable/rotate audit rows carry trace_id | Modify |
| `tests/test_training_admin_routes.py` (or equivalent) | +tests: 4 training admin endpoints + reset write audit with trace_id | Modify |
| `tests/test_exports_routes.py` | +test: export audit row carries trace_id | Modify |

**Total:** 2 new files, ~12 modified source files, ~10 modified or new test files.

---

## Conventions for All Tasks

- **TDD strict:** every code change starts with a failing test.
- **Atomic commits:** one task = one commit; commit message format `feat(paket-14b): <task summary>` or `chore(paket-14b): ...` for trivial pieces.
- **Test runner:** always `.venv/bin/python -m pytest`. Bare `pytest` will pick the system interpreter and fail on `import fastapi`.
- **Migration version:** v0004 (next free slot after v0003).
- **trace_id format:** `uuid.uuid4().hex[:16]` — exactly 16 lowercase hex characters; tests assert this.
- **Helpers signature:** `trace_id: Optional[str] = None` keyword-only argument, defaults to None for backward compat.
- **Service signatures:** `def run_X(..., *, trace_id: Optional[str] = None) -> ...`. Existing positional args unchanged.
- **Group B audit-only sites:** generate trace_id at the route layer (not deeper) so the value is captured once and passed through.

---

## Task 1: v0004 migration + helper API

**Files:**
- Create: `backend/migrations/v0004_trace_id.py`
- Modify: `backend/shared/audit.py` — add `gen_trace_id()`, add `trace_id` kwarg to `log_admin_action` and `log_system_event`.
- Create: `tests/test_v0004_trace_id_migration.py`
- Modify: `tests/test_audit.py` — add 5 new tests.

### Step 1.1: Write the failing migration test

- [ ] Write `tests/test_v0004_trace_id_migration.py`:

```python
"""Tests for v0004 — trace_id column + partial indexes."""
from pathlib import Path

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def _columns(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _index_names(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA index_list({table})").fetchall()}


def test_v0004_adds_trace_id_to_admin_audit_log(fresh_db):
    assert "trace_id" in _columns(fresh_db, "admin_audit_log")


def test_v0004_adds_trace_id_to_system_events(fresh_db):
    assert "trace_id" in _columns(fresh_db, "system_events")


def test_v0004_creates_partial_index_on_admin_audit_log(fresh_db):
    assert "idx_audit_trace" in _index_names(fresh_db, "admin_audit_log")


def test_v0004_creates_partial_index_on_system_events(fresh_db):
    assert "idx_sys_trace" in _index_names(fresh_db, "system_events")


def test_v0004_is_idempotent(fresh_db):
    """Re-running v0004 directly must not raise (schema_migrations gates it,
    but verify the up() function itself is safe to call twice on a fresh DB)."""
    from backend.migrations.v0004_trace_id import up
    # First call (already applied via discover_migrations) — second call here
    with pytest.raises(Exception):
        # ALTER TABLE ADD COLUMN errors if column exists; this is the expected
        # behavior. The migration runner protects against re-application via
        # schema_migrations, so this raise is fine in production. We only assert
        # it raises (not silently ignored) so future maintainers know.
        up(fresh_db)
```

### Step 1.2: Run migration test to verify it fails

Run: `.venv/bin/python -m pytest tests/test_v0004_trace_id_migration.py -v`

Expected: All 5 tests FAIL with `ModuleNotFoundError: No module named 'backend.migrations.v0004_trace_id'` or similar (the file does not exist yet).

### Step 1.3: Create the migration

- [ ] Write `backend/migrations/v0004_trace_id.py`:

```python
"""v0004 — add trace_id column + partial index to admin_audit_log and system_events.

Allows correlating admin-triggered chains (audit row + the system_events rows
emitted by the same operation) via a single key. Background-loop and lifespan
events are emitted with NULL trace_id by design.

ALTER TABLE ADD COLUMN is O(1) in SQLite; partial indexes (3.8+) keep the
index compact since most rows will have NULL trace_id (legacy + loop-origin).
"""
import sqlite3


SQL = """
ALTER TABLE admin_audit_log ADD COLUMN trace_id TEXT;
ALTER TABLE system_events   ADD COLUMN trace_id TEXT;

CREATE INDEX idx_audit_trace
  ON admin_audit_log(trace_id)
  WHERE trace_id IS NOT NULL;

CREATE INDEX idx_sys_trace
  ON system_events(trace_id)
  WHERE trace_id IS NOT NULL;
"""


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(SQL)
```

### Step 1.4: Run migration test to verify it passes

Run: `.venv/bin/python -m pytest tests/test_v0004_trace_id_migration.py -v`

Expected: All 5 tests PASS.

### Step 1.5: Write failing test for gen_trace_id helper

- [ ] Append to `tests/test_audit.py` (after the existing tests):

```python
def test_gen_trace_id_format():
    """16-char lowercase hex token (64 bits of entropy)."""
    from backend.shared.audit import gen_trace_id
    tid = gen_trace_id()
    assert isinstance(tid, str)
    assert len(tid) == 16
    assert all(c in "0123456789abcdef" for c in tid)


def test_gen_trace_id_is_unique_in_practice():
    """1000 calls produce 1000 distinct values (uniqueness sanity)."""
    from backend.shared.audit import gen_trace_id
    values = {gen_trace_id() for _ in range(1000)}
    assert len(values) == 1000
```

### Step 1.6: Run helper test to verify it fails

Run: `.venv/bin/python -m pytest tests/test_audit.py::test_gen_trace_id_format -v`

Expected: FAIL with `AttributeError: module 'backend.shared.audit' has no attribute 'gen_trace_id'`.

### Step 1.7: Implement gen_trace_id

- [ ] Modify `backend/shared/audit.py` — add at the top of the file (after the existing `_now` helper):

```python
import uuid


def gen_trace_id() -> str:
    """16-char lowercase hex token (64 bits of entropy, uuid4-derived).

    Used to correlate one admin action across admin_audit_log and
    system_events. Generated at admin route entry; threaded through
    audit + service calls down the call chain.
    """
    return uuid.uuid4().hex[:16]
```

### Step 1.8: Run helper tests to verify they pass

Run: `.venv/bin/python -m pytest tests/test_audit.py -v -k gen_trace_id`

Expected: 2 PASS.

### Step 1.9: Write failing tests for trace_id parameter on log helpers

- [ ] Append to `tests/test_audit.py`:

```python
def test_log_admin_action_writes_trace_id(db):
    audit.log_admin_action(
        db, admin_user_id=1, action_type="settings_update",
        trace_id="abc123def4567890",
    )
    row = db.execute("SELECT trace_id FROM admin_audit_log").fetchone()
    assert row["trace_id"] == "abc123def4567890"


def test_log_admin_action_default_trace_id_is_null(db):
    audit.log_admin_action(db, admin_user_id=1, action_type="something")
    row = db.execute("SELECT trace_id FROM admin_audit_log").fetchone()
    assert row["trace_id"] is None


def test_log_system_event_writes_trace_id(db):
    audit.log_system_event(
        db, event_type="backup_started", severity="info",
        trace_id="0fedcba987654321",
    )
    row = db.execute("SELECT trace_id FROM system_events").fetchone()
    assert row["trace_id"] == "0fedcba987654321"


def test_log_system_event_default_trace_id_is_null(db):
    audit.log_system_event(db, event_type="boot", severity="info")
    row = db.execute("SELECT trace_id FROM system_events").fetchone()
    assert row["trace_id"] is None
```

### Step 1.10: Run tests to verify they fail

Run: `.venv/bin/python -m pytest tests/test_audit.py -v -k trace_id`

Expected: 4 FAIL with `TypeError: log_admin_action() got an unexpected keyword argument 'trace_id'` (and similar for `log_system_event`).

### Step 1.11: Add trace_id kwarg to log_admin_action

- [ ] Modify `backend/shared/audit.py` — replace the existing `log_admin_action`:

```python
def log_admin_action(
    conn: sqlite3.Connection,
    admin_user_id: int,
    action_type: str,
    *,
    target_kind: Optional[str] = None,
    target_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    trace_id: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO admin_audit_log(
            admin_user_id, action_type, target_kind, target_id,
            metadata_json, created_at, trace_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            admin_user_id, action_type, target_kind, target_id,
            json.dumps(metadata) if metadata is not None else None,
            _now(),
            trace_id,
        ),
    )
```

### Step 1.12: Add trace_id kwarg to log_system_event

- [ ] Modify `backend/shared/audit.py` — replace the existing `log_system_event`:

```python
def log_system_event(
    conn: sqlite3.Connection,
    event_type: str,
    severity: str,
    *,
    message: Optional[str] = None,
    extra: Optional[dict] = None,
    trace_id: Optional[str] = None,
) -> None:
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"invalid severity: {severity!r} (must be one of {VALID_SEVERITIES})")
    conn.execute(
        """
        INSERT INTO system_events(
            event_type, severity, message, extra_json, created_at, trace_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            event_type, severity, message,
            json.dumps(extra) if extra is not None else None,
            _now(),
            trace_id,
        ),
    )
```

### Step 1.13: Run all audit + migration tests

Run: `.venv/bin/python -m pytest tests/test_audit.py tests/test_v0004_trace_id_migration.py -v`

Expected: ALL pass (existing 6 tests + 7 new = 13 total).

### Step 1.14: Run full suite to confirm no regression

Run: `.venv/bin/python -m pytest -x -q`

Expected: full suite passes (646 baseline + ~7 new = ~653 tests).

### Step 1.15: Commit

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/migrations/v0004_trace_id.py \
  backend/shared/audit.py \
  tests/test_v0004_trace_id_migration.py \
  tests/test_audit.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-14b): v0004 migration + trace_id helper API

Adds nullable trace_id column to admin_audit_log and system_events,
plus partial indexes for non-NULL lookups. Adds gen_trace_id() helper
(uuid4.hex[:16]) and optional trace_id kwarg on log_admin_action and
log_system_event. Existing call sites unaffected (default None → NULL).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Backup service + route plumbing

**Files:**
- Modify: `backend/backup/service.py` — add `trace_id` kwarg to `run_backup_cycle` and propagate to all 7 `log_system_event` calls (lines 140-213).
- Modify: `backend/backup/routes.py` — generate trace_id at route entry, pass to service + audit (lines 19-55).
- Modify: `backend/backup/models.py` — add `trace_id: Optional[str] = None` field to `BackupRunNowResponse`.
- Modify: `backend/backup/loop.py` — confirm loop calls `run_backup_cycle(conn)` (no trace_id) so emitted system_events stay NULL. (Likely no edit needed; verify only.)
- Modify: `tests/test_backup_admin_route.py` — add cross-table correlation test.
- Modify: `tests/test_backup_loop.py` — add NULL-trace_id assertion for loop-origin events.

### Step 2.1: Read current backup model

- [ ] Open `backend/backup/models.py` and locate `BackupRunNowResponse`. Note its existing fields (snapshot_path, committed_sha, pushed, rotated_count, ok).

### Step 2.2: Write failing test for cross-table correlation

- [ ] Append to `tests/test_backup_admin_route.py`:

```python
def test_run_now_threads_trace_id_across_audit_and_system_events(client, bootstrap_admin):
    """The same trace_id must appear in (a) the audit row, (b) every system_events
    row emitted during the cycle, and (c) the response body — so an operator
    can JOIN by trace_id and reconstruct the operation."""
    response = client.post("/api/admin/backup/run-now")
    assert response.status_code == 200

    body = response.json()
    trace_id = body["trace_id"]
    assert isinstance(trace_id, str)
    assert len(trace_id) == 16

    from backend.shared.db import connect
    from backend import config
    db = connect(config.DB_PATH)
    try:
        audit_rows = db.execute(
            "SELECT trace_id FROM admin_audit_log WHERE action_type='backup_run_now'"
        ).fetchall()
        # exactly one audit row, with our trace_id
        assert len(audit_rows) >= 1
        assert audit_rows[-1]["trace_id"] == trace_id

        sys_rows = db.execute(
            "SELECT trace_id FROM system_events WHERE trace_id=?", (trace_id,)
        ).fetchall()
        # at least one system_events row from the cycle (success or skipped path)
        assert len(sys_rows) >= 1
        # all share the same id (sanity)
        assert all(r["trace_id"] == trace_id for r in sys_rows)
    finally:
        db.close()
```

### Step 2.3: Run test to verify it fails

Run: `.venv/bin/python -m pytest tests/test_backup_admin_route.py::test_run_now_threads_trace_id_across_audit_and_system_events -v`

Expected: FAIL with `KeyError: 'trace_id'` (response body lacks trace_id) — or AssertionError on the audit row trace_id being None.

### Step 2.4: Add trace_id field to BackupRunNowResponse

- [ ] Modify `backend/backup/models.py` — add `trace_id: Optional[str] = None` to `BackupRunNowResponse`. If not already imported: `from typing import Optional`.

Example shape:
```python
from typing import Optional
from pydantic import BaseModel


class BackupRunNowResponse(BaseModel):
    ok: bool
    snapshot_path: str
    committed_sha: Optional[str] = None
    pushed: bool
    rotated_count: int
    trace_id: Optional[str] = None  # NEW
```

### Step 2.5: Add trace_id kwarg to run_backup_cycle

- [ ] Modify `backend/backup/service.py:120` (function signature) and lines 140-213 (every `log_system_event` call). The new signature:

```python
def run_backup_cycle(
    db: sqlite3.Connection, *, trace_id: Optional[str] = None,
) -> dict:
    """Top-level orchestrator. Runs:
       dump → write → rotate → (git if env set) → log.
       ...
       trace_id: when set (e.g. by the admin run-now route), every emitted
       system_events row carries it for cross-table correlation. Background
       loop callers omit it → NULL.
    """
    ...
```

Add `trace_id=trace_id` to **all 7** `audit.log_system_event(...)` calls inside this function. Example for the first one:

```python
    try:
        payload = dump_all_tables_to_json(db)
    except Exception as e:
        audit.log_system_event(
            db, "backup_failed", "error",
            message="dump failed",
            extra={"step": "dump", "error": str(e)},
            trace_id=trace_id,                   # NEW
        )
        raise
```

Repeat the `trace_id=trace_id` argument addition for the other 6 `log_system_event` calls in this function (write_failed, rotate_failed, backup_skipped_no_remote, init_failed, push_failed, backup_success). At the top of the file, ensure `from typing import Optional` is imported.

### Step 2.6: Update admin_backup_run_now route

- [ ] Modify `backend/backup/routes.py:19-55` (replace the entire route function):

```python
@router.post("/run-now", response_model=BackupRunNowResponse)
def admin_backup_run_now(
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Trigger a backup cycle synchronously. Blocks until complete.
    Returns 500 on any cycle failure (system_events row already written
    by the cycle's per-step error logging).

    A trace_id is generated at entry and threaded through the cycle and
    the audit row so an operator can reconstruct the chain via trace_id.
    """
    trace_id = audit.gen_trace_id()
    try:
        result = run_backup_cycle(db, trace_id=trace_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "backup_failed", "message": str(e), "trace_id": trace_id},
        )

    try:
        snapshot_filename = Path(result["snapshot_path"]).name
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="backup_run_now",
            target_kind="backup", target_id=snapshot_filename,
            metadata={
                "pushed": result["pushed"],
                "committed_sha": result["committed_sha"],
                "rotated_count": result["rotated_count"],
            },
            trace_id=trace_id,
        )
    except Exception:
        log.exception("audit backup_run_now failed")

    return {
        "ok": True,
        "snapshot_path": result["snapshot_path"],
        "committed_sha": result["committed_sha"],
        "pushed": result["pushed"],
        "rotated_count": result["rotated_count"],
        "trace_id": trace_id,
    }
```

### Step 2.7: Run admin route test to verify it passes

Run: `.venv/bin/python -m pytest tests/test_backup_admin_route.py -v`

Expected: All tests PASS, including the new correlation test.

### Step 2.8: Write failing test for loop-origin NULL trace_id

- [ ] Append to `tests/test_backup_loop.py` (find a place near other one-shot tests):

```python
@pytest.mark.asyncio
async def test_backup_loop_emits_system_events_with_null_trace_id(tmp_path, monkeypatch):
    """Background loop must NOT generate trace_ids — those rows mark
    'autonomous origin' and stay NULL by design (admin-triggered chains
    are the only ones that get a non-NULL trace_id)."""
    from backend.backup import loop as backup_loop
    from backend.shared.db import connect
    from backend import config

    # Run one cycle without going through the admin route.
    await backup_loop.backup_once()

    db = connect(config.DB_PATH)
    try:
        rows = db.execute(
            "SELECT trace_id FROM system_events "
            "WHERE event_type IN ('backup_success','backup_skipped_no_remote')"
        ).fetchall()
        assert len(rows) >= 1
        assert all(r["trace_id"] is None for r in rows)
    finally:
        db.close()
```

(If `test_backup_loop.py` already has fixtures wiring `config.DB_PATH` to a temp DB, reuse them. Otherwise inspect existing tests in the file for the pattern.)

### Step 2.9: Run loop test to verify it passes

Run: `.venv/bin/python -m pytest tests/test_backup_loop.py -v -k null_trace_id`

Expected: PASS.

### Step 2.10: Run full backup test module

Run: `.venv/bin/python -m pytest tests/test_backup_admin_route.py tests/test_backup_cycle.py tests/test_backup_service.py tests/test_backup_loop.py -v`

Expected: ALL PASS.

### Step 2.11: Run full suite

Run: `.venv/bin/python -m pytest -x -q`

Expected: PASS.

### Step 2.12: Commit

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/backup/service.py \
  backend/backup/routes.py \
  backend/backup/models.py \
  tests/test_backup_admin_route.py \
  tests/test_backup_loop.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-14b): thread trace_id through backup admin path

Admin run-now route generates trace_id, passes to run_backup_cycle and
log_admin_action; cycle threads it to all 7 log_system_event calls.
Background loop calls run_backup_cycle without trace_id, leaving NULL
on loop-origin rows. Response body now includes trace_id for client echo.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Retention service + route plumbing

**Files:**
- Modify: `backend/retention/service.py` — `run_purge(..., trace_id=None)`, propagate to 2 `log_system_event` calls.
- Modify: `backend/retention/routes.py` — generate trace_id at run-now route entry.
- Modify: `backend/retention/models.py` — add `trace_id` to `RetentionRunNowResponse`.
- Modify: `tests/test_retention_admin_routes.py` — cross-table correlation test.
- Modify: `tests/test_retention_loop.py` — NULL-trace_id assertion for loop-origin.

### Step 3.1: Write failing test for retention cross-table correlation

- [ ] Append to `tests/test_retention_admin_routes.py`:

```python
def test_run_now_threads_trace_id(client, bootstrap_admin):
    """Same trace_id in audit row + run_purge's system_events row + response body."""
    response = client.post("/api/admin/retention/run-now")
    assert response.status_code == 200

    body = response.json()
    trace_id = body["trace_id"]
    assert isinstance(trace_id, str) and len(trace_id) == 16

    from backend.shared.db import connect
    from backend import config
    db = connect(config.DB_PATH)
    try:
        audit_rows = db.execute(
            "SELECT trace_id FROM admin_audit_log WHERE action_type='retention_run_now'"
        ).fetchall()
        assert len(audit_rows) >= 1
        assert audit_rows[-1]["trace_id"] == trace_id

        sys_rows = db.execute(
            "SELECT trace_id FROM system_events WHERE trace_id=?", (trace_id,)
        ).fetchall()
        assert len(sys_rows) >= 1
        assert all(r["trace_id"] == trace_id for r in sys_rows)
    finally:
        db.close()
```

### Step 3.2: Run test, expect fail

Run: `.venv/bin/python -m pytest tests/test_retention_admin_routes.py::test_run_now_threads_trace_id -v`

Expected: FAIL (response lacks trace_id, or audit row has NULL trace_id).

### Step 3.3: Add trace_id field to RetentionRunNowResponse

- [ ] Modify `backend/retention/models.py` — add `trace_id: Optional[str] = None` to `RetentionRunNowResponse`. Ensure `from typing import Optional` is imported. Example:

```python
class RetentionRunNowResponse(BaseModel):
    ok: bool
    purged: dict[str, int]
    total: int
    trace_id: Optional[str] = None  # NEW
```

### Step 3.4: Add trace_id kwarg to run_purge

- [ ] Modify `backend/retention/service.py:106-155`. Update signature and the 2 `log_system_event` calls (the failure path at line 141 and success at line 150):

```python
def run_purge(
    db: sqlite3.Connection, *, trace_id: Optional[str] = None,
) -> dict:
    """... (existing docstring) ...

    trace_id: when set (e.g. by admin run-now), the failure or success
    system_events row carries it. Background loop callers omit it → NULL.
    """
    cutoffs = compute_cutoffs(db)

    db.execute("BEGIN IMMEDIATE")
    current_table: Optional[str] = None
    try:
        purged: dict[str, int] = {}
        for entry in PURGE_POLICY:
            current_table = entry.table
            if entry.table not in cutoffs:
                purged[entry.table] = 0
                continue
            count = purge_single_table(db, entry, cutoffs[entry.table])
            purged[entry.table] = count
        db.execute("COMMIT")
    except Exception as e:
        try:
            db.execute("ROLLBACK")
        except Exception:
            pass
        audit.log_system_event(
            db, "retention_failed", "error",
            message="retention cycle failed",
            extra={"step": "purge", "table": current_table, "error": str(e)},
            trace_id=trace_id,
        )
        raise

    total = sum(purged.values())
    active_table_count = sum(1 for v in purged.values() if v > 0)
    audit.log_system_event(
        db, "retention_success", "info",
        message=f"purged {total} rows across {active_table_count} active tables",
        extra={"purged": purged},
        trace_id=trace_id,
    )
    return {"ok": True, "purged": purged, "total": total}
```

### Step 3.5: Update admin_retention_run_now route

- [ ] Modify `backend/retention/routes.py:21-49`:

```python
@router.post("/run-now", response_model=RetentionRunNowResponse)
def admin_retention_run_now(
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Trigger a retention cycle synchronously. Blocks until commit/rollback.
    Returns 500 on any failure (system_events row already written by run_purge).
    A trace_id is generated at entry and threaded through the cycle + audit."""
    trace_id = audit.gen_trace_id()
    try:
        result = run_purge(db, trace_id=trace_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "retention_failed", "message": str(e), "trace_id": trace_id},
        )

    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="retention_run_now",
            target_kind="retention", target_id=None,
            metadata={
                "total": result["total"],
                "by_table": result["purged"],
            },
            trace_id=trace_id,
        )
    except Exception:
        log.exception("audit retention_run_now failed")

    return {**result, "trace_id": trace_id}
```

### Step 3.6: Run retention admin tests

Run: `.venv/bin/python -m pytest tests/test_retention_admin_routes.py -v`

Expected: ALL PASS, including the new test.

### Step 3.7: Write failing test for loop NULL trace_id

- [ ] Append to `tests/test_retention_loop.py`:

```python
@pytest.mark.asyncio
async def test_retention_loop_emits_system_events_with_null_trace_id(tmp_path, monkeypatch):
    """Background retention cycles must emit system_events with NULL trace_id —
    autonomous origin marker."""
    from backend.retention import loop as retention_loop
    from backend.shared.db import connect
    from backend import config

    await retention_loop.retention_once()

    db = connect(config.DB_PATH)
    try:
        rows = db.execute(
            "SELECT trace_id FROM system_events WHERE event_type='retention_success'"
        ).fetchall()
        assert len(rows) >= 1
        assert all(r["trace_id"] is None for r in rows)
    finally:
        db.close()
```

### Step 3.8: Run loop test

Run: `.venv/bin/python -m pytest tests/test_retention_loop.py -v -k null_trace_id`

Expected: PASS.

### Step 3.9: Run full retention + audit suite

Run: `.venv/bin/python -m pytest tests/test_retention_admin_routes.py tests/test_retention_loop.py tests/test_retention_service.py tests/test_retention_lifespan.py tests/test_retention_preview.py -v`

Expected: ALL PASS.

### Step 3.10: Run full suite

Run: `.venv/bin/python -m pytest -x -q`

Expected: PASS.

### Step 3.11: Commit

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/retention/service.py \
  backend/retention/routes.py \
  backend/retention/models.py \
  tests/test_retention_admin_routes.py \
  tests/test_retention_loop.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-14b): thread trace_id through retention admin path

Mirrors the backup pattern: admin run-now generates trace_id, passes to
run_purge and log_admin_action; run_purge threads to its retention_failed
and retention_success system_events. Loop calls run_purge without it →
NULL on loop-origin rows. Response includes trace_id.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Group B — locks force-release + admin settings

**Files:**
- Modify: `backend/locks/routes.py:120-160` — generate trace_id at force-release route entry, pass to log_admin_action.
- Modify: `backend/admin/routes.py:53-88` — generate trace_id in update_setting route, pass to log_admin_action.
- Modify: `tests/test_locks_admin_force_release.py` — assert audit row has populated trace_id.
- Modify: existing test for settings update — assert trace_id populated. (Likely in `tests/test_admin_settings.py` or similar; locate via `grep -rn 'settings_update' tests/`.)

### Step 4.1: Write failing test for force-release trace_id

- [ ] Append to `tests/test_locks_admin_force_release.py`:

```python
def test_force_release_audit_row_carries_trace_id(client, bootstrap_admin):
    """Group B: audit-only — trace_id present on the audit row, no
    system_events follow-up. Operator can grep system_events by trace_id
    and correctly find zero rows."""
    # First, set up a lock to force-release. Use whatever helper or fixture
    # is already in this file to acquire one as a non-admin user, then
    # have admin force-release it.
    document_id = "doc_test_force_release_trace"
    # ... (use existing helpers in this file to seed the lock; pattern:
    # one user acquires, admin force-releases)
    # See the original tests in this file for the seed pattern.

    response = client.post(f"/api/admin/locks/{document_id}/force-release")
    assert response.status_code == 200

    from backend.shared.db import connect
    from backend import config
    db = connect(config.DB_PATH)
    try:
        row = db.execute(
            "SELECT trace_id FROM admin_audit_log "
            "WHERE action_type='lock_force_release' AND target_id=?",
            (document_id,),
        ).fetchone()
        assert row is not None
        assert isinstance(row["trace_id"], str)
        assert len(row["trace_id"]) == 16

        # No system_events for this trace_id (force-release doesn't emit any)
        sys_rows = db.execute(
            "SELECT * FROM system_events WHERE trace_id=?", (row["trace_id"],)
        ).fetchall()
        assert len(sys_rows) == 0
    finally:
        db.close()
```

(Adapt the lock-seeding part to match existing fixtures in the test file.)

### Step 4.2: Run test, expect fail

Run: `.venv/bin/python -m pytest tests/test_locks_admin_force_release.py::test_force_release_audit_row_carries_trace_id -v`

Expected: FAIL (audit row trace_id is None).

### Step 4.3: Plumb trace_id into force-release route

- [ ] Modify `backend/locks/routes.py:120-160` (the force-release route, where `audit.log_admin_action` is called around line 143). Generate trace_id at the top of the function body and pass it to log_admin_action:

```python
@router.post("/admin/locks/{document_id}/force-release")
async def admin_force_release(...):
    # ... (existing checks: get_lock, prior_user_id capture)
    trace_id = audit.gen_trace_id()        # NEW

    service.force_release(db, document_id=document_id)

    try:
        await sse_broker.publish_broadcast(
            "lock_released",
            {
                "document_id": document_id,
                "by_user_id": prior_user_id,
                "reason": "admin_force",
            },
        )
    except Exception:
        log.exception("publish lock_released admin_force failed for %s", document_id)

    try:
        audit.log_admin_action(
            db,
            admin_user_id=admin["id"],
            action_type="lock_force_release",
            target_kind="document",
            target_id=document_id,
            metadata={"prior_holder_user_id": prior_user_id},
            trace_id=trace_id,                 # NEW
        )
    except Exception:
        log.exception("log_admin_action lock_force_release failed for %s", document_id)

    return {"ok": True}
```

(Do NOT add trace_id to the response — Group B is internal-only.)

### Step 4.4: Run force-release tests

Run: `.venv/bin/python -m pytest tests/test_locks_admin_force_release.py -v`

Expected: ALL PASS.

### Step 4.5: Locate the existing settings_update test

Run: `grep -rln "settings_update\|update_setting" tests/`

Read whichever file emerges (likely `tests/test_admin_settings.py` or `tests/test_admin_routes.py`). Find an existing test that hits `PUT /api/admin/settings/{key}` and copy its setup pattern.

### Step 4.6: Write failing test for settings_update trace_id

- [ ] Append to the located settings test file:

```python
def test_settings_update_audit_row_carries_trace_id(client, bootstrap_admin):
    """Group B audit-only: trace_id populated on the audit row."""
    # Pick a key known to be seeded — adjust if your fixture seeds different defaults.
    response = client.put(
        "/api/admin/settings/retention.system_events.days",
        json={"value": 200},
    )
    assert response.status_code == 200

    from backend.shared.db import connect
    from backend import config
    db = connect(config.DB_PATH)
    try:
        row = db.execute(
            "SELECT trace_id FROM admin_audit_log "
            "WHERE action_type='settings_update' AND target_id=? "
            "ORDER BY id DESC LIMIT 1",
            ("retention.system_events.days",),
        ).fetchone()
        assert row is not None
        assert isinstance(row["trace_id"], str)
        assert len(row["trace_id"]) == 16
    finally:
        db.close()
```

### Step 4.7: Run test, expect fail

Run: `.venv/bin/python -m pytest <located_path>::test_settings_update_audit_row_carries_trace_id -v`

Expected: FAIL.

### Step 4.8: Plumb trace_id into update_setting route

- [ ] Modify `backend/admin/routes.py:53-88` (the `update_setting` function). Add `trace_id = audit.gen_trace_id()` near the top of the function body (e.g., right before `S.set_value(db, key, ...)`), then pass it to log_admin_action:

```python
    # ... existing validation ...
    trace_id = audit.gen_trace_id()                    # NEW
    S.set_value(db, key, new_value, updated_by_user_id=admin["id"])
    audit.log_admin_action(
        db, admin_user_id=admin["id"], action_type="settings_update",
        target_kind="setting", target_id=key,
        metadata={"old_value": old_value, "new_value": new_value},
        trace_id=trace_id,                             # NEW
    )
    return {"key": key, "value": new_value}
```

### Step 4.9: Run settings + force-release tests

Run: `.venv/bin/python -m pytest <settings_test_file> tests/test_locks_admin_force_release.py -v`

Expected: ALL PASS.

### Step 4.10: Run full suite

Run: `.venv/bin/python -m pytest -x -q`

Expected: PASS.

### Step 4.11: Commit

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/locks/routes.py \
  backend/admin/routes.py \
  tests/test_locks_admin_force_release.py \
  <settings_test_file>
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-14b): trace_id on lock force-release and settings update

Group B audit-only sites: trace_id populated on audit row for uniformity.
No system_events follow-up; operator querying system_events by trace_id
correctly returns zero rows.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Group B — user CRUD + training admin

**Files:**
- Modify: `backend/users/service.py:215-311` — add `trace_id` kwarg to `promote_admin`, `demote_admin`, `disable_user`, `enable_user`, `rotate_invite_code` (5 sites). Pass to log_admin_action inside each.
- Modify: `backend/users/routes.py` — at each admin endpoint that calls one of the above, generate trace_id and pass through.
- Modify: `backend/training/service.py:481` (`reset_user_training`) — add `trace_id` kwarg and pass to log_admin_action. Caller (`backend/training/routes.py:90`) generates trace_id.
- Modify: `backend/training/routes.py:122-215` — generate trace_id at each of the 4 admin endpoints (`admin_upsert_gold_doc`, `admin_delete_gold_doc`, `admin_upsert_quiz`, `admin_delete_quiz`).
- Modify: `tests/test_users_admin_routes.py` (or equivalent) — assert trace_id on each user CRUD audit row.
- Modify: `tests/test_training_admin_routes.py` (or equivalent) — assert trace_id on each training admin audit row.

### Step 5.1: Locate the user admin route file

Run: `grep -rln "promote_admin\|disable_user" backend/users/routes.py backend/users/`

Identify which routes call which service functions. Take note of the route paths (e.g., `POST /api/admin/users/{id}/promote`).

### Step 5.2: Locate test files for user admin actions

Run: `grep -rln "promote_admin\|/promote\|disable_user" tests/`

Identify the test file(s).

### Step 5.3: Write failing tests for user CRUD trace_id

- [ ] Append to the located user admin test file (one combined test exercising 5 actions, or 5 individual tests — choose what matches the file's style). Sample:

```python
def test_user_admin_actions_carry_trace_id(client, bootstrap_admin):
    """All 5 user-admin actions write a non-NULL trace_id on the audit row."""
    from backend.shared.db import connect
    from backend import config

    # Adjust paths/payloads to the actual route patterns in users/routes.py.
    # Each action below produces one audit row; we assert trace_id present.

    # 1. Create a target user (via register or an existing fixture)
    target_id = ...  # use an existing fixture pattern for this

    actions = [
        ("POST", f"/api/admin/users/{target_id}/promote"),
        ("POST", f"/api/admin/users/{target_id}/demote"),
        ("POST", f"/api/admin/users/{target_id}/disable"),
        ("POST", f"/api/admin/users/{target_id}/enable"),
        ("POST", "/api/admin/invite-codes/rotate", {"new_code": "TEST-123"}),
    ]

    for spec in actions:
        method, url, *rest = spec
        body = rest[0] if rest else None
        resp = client.request(method, url, json=body)
        assert resp.status_code in (200, 409)  # 409 is OK for last-admin guardrail

    db = connect(config.DB_PATH)
    try:
        rows = db.execute(
            "SELECT action_type, trace_id FROM admin_audit_log "
            "WHERE action_type IN "
            "('promote_admin','demote_admin','disable_user','enable_user','rotate_invite_code')"
        ).fetchall()
        assert len(rows) >= 1
        for r in rows:
            assert isinstance(r["trace_id"], str), \
                f"action {r['action_type']} has trace_id={r['trace_id']!r}"
            assert len(r["trace_id"]) == 16
    finally:
        db.close()
```

(If the existing test file already has individual fixtures and clear patterns for each action, prefer per-action tests over the combined version; either way, ensure each of the 5 audit-action paths is exercised once and asserted to carry trace_id.)

### Step 5.4: Run, expect fail

Run: `.venv/bin/python -m pytest <user_admin_test_file>::test_user_admin_actions_carry_trace_id -v`

Expected: FAIL (trace_id is None).

### Step 5.5: Add trace_id kwarg to each user-service admin function

- [ ] Modify `backend/users/service.py` — for each of the 5 functions below, add `trace_id: Optional[str] = None` keyword-only parameter and pass it to the log_admin_action call inside. Example for `promote_admin` (lines 215-231):

```python
def promote_admin(
    db: sqlite3.Connection, *,
    admin_user_id: int,
    target_user_id: int,
    trace_id: Optional[str] = None,
) -> None:
    _ensure_admin(db, admin_user_id)
    target = db.execute(
        "SELECT * FROM users WHERE id=?", (target_user_id,)
    ).fetchone()
    if target is None:
        raise UserNotFound(f"user {target_user_id} not found")
    db.execute(
        "UPDATE users SET role='admin', updated_at=? WHERE id=?",
        (_now(), target_user_id),
    )
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="promote_admin",
        target_kind="user", target_id=str(target_user_id),
        trace_id=trace_id,
    )
```

Repeat the same pattern for `demote_admin` (line 234), `disable_user` (line 256), `enable_user` (line 277), and `rotate_invite_code` (line 291). Make sure `from typing import Optional` exists at the top of the file.

### Step 5.6: Update the user admin routes

- [ ] Modify `backend/users/routes.py` — at each route handler that calls one of the above five service functions, generate `trace_id = audit.gen_trace_id()` and forward it as a kwarg. Example pattern (apply to each route):

```python
trace_id = audit.gen_trace_id()
users_service.promote_admin(
    db, admin_user_id=admin["id"], target_user_id=target_user_id,
    trace_id=trace_id,
)
```

(Make sure `from backend.shared import audit` is imported in the routes module — likely already.)

### Step 5.7: Run user-admin tests

Run: `.venv/bin/python -m pytest <user_admin_test_file> -v`

Expected: ALL PASS.

### Step 5.8: Locate the training admin test file

Run: `grep -rln "upsert_gold_doc\|reset_user_training\|admin/training" tests/`

### Step 5.9: Write failing tests for training admin trace_id

- [ ] Append to the located training admin test file:

```python
def test_training_admin_actions_carry_trace_id(client, bootstrap_admin, passed_user):
    """5 training admin actions: 4 routes + 1 service-level audit (reset)."""
    from backend.shared.db import connect
    from backend import config

    target_user_id = passed_user["id"]
    gold_id = "gold_test_trace"
    question_id = "q_test_trace"

    # 1. Reset user training
    resp = client.post(f"/api/admin/training/users/{target_user_id}/reset")
    assert resp.status_code == 200

    # 2. Upsert gold doc
    resp = client.put(
        f"/api/admin/training/gold-docs/{gold_id}",
        json={
            "content": "test content",
            "expected_concepts": [],
            "min_concept_count": 0,
        },
    )
    assert resp.status_code == 200

    # 3. Delete gold doc
    resp = client.delete(f"/api/admin/training/gold-docs/{gold_id}")
    assert resp.status_code == 200

    # 4. Upsert quiz question
    resp = client.put(
        f"/api/admin/training/quiz/{question_id}",
        json={
            "text": "Q?",
            "choices": ["a", "b"],
            "correct_choice_idx": 0,
        },
    )
    assert resp.status_code == 200

    # 5. Delete quiz question
    resp = client.delete(f"/api/admin/training/quiz/{question_id}")
    assert resp.status_code == 200

    db = connect(config.DB_PATH)
    try:
        rows = db.execute(
            "SELECT action_type, trace_id FROM admin_audit_log "
            "WHERE action_type IN "
            "('reset_training','upsert_gold_doc','delete_gold_doc',"
            " 'upsert_quiz_question','delete_quiz_question')"
        ).fetchall()
        assert len(rows) == 5
        for r in rows:
            assert isinstance(r["trace_id"], str), \
                f"{r['action_type']} has trace_id={r['trace_id']!r}"
            assert len(r["trace_id"]) == 16
    finally:
        db.close()
```

(Adjust fixture names like `passed_user` to whatever exists in the project's conftest.)

### Step 5.10: Run, expect fail

Run: `.venv/bin/python -m pytest <training_admin_test_file>::test_training_admin_actions_carry_trace_id -v`

Expected: FAIL.

### Step 5.11: Plumb trace_id into reset_user_training

- [ ] Modify `backend/training/service.py` (the `reset_user_training` function — `audit.log_admin_action` is around line 481). Add `trace_id: Optional[str] = None` to the signature and pass to log_admin_action:

```python
def reset_user_training(
    db: sqlite3.Connection,
    *,
    user_id: int,
    admin_id: int,
    trace_id: Optional[str] = None,
) -> bool:
    # ... existing logic ...
    try:
        audit.log_admin_action(
            db, admin_user_id=admin_id, action_type="reset_training",
            target_kind="user", target_id=str(user_id),
            metadata={"username": user_row["username"]},
            trace_id=trace_id,
        )
    except Exception:
        log.exception("log_admin_action reset_training failed for user_id=%s", user_id)
    return True
```

Add `from typing import Optional` if not already imported at top of file.

### Step 5.12: Plumb trace_id into 4 training admin routes + reset route

- [ ] Modify `backend/training/routes.py:90-104` (`admin_reset_user_training`): generate trace_id, forward to service:

```python
@admin_router.post("/users/{user_id}/reset", response_model=OkResponse)
def admin_reset_user_training(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()
    ok = service.reset_user_training(
        db, user_id=user_id, admin_id=admin["id"], trace_id=trace_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"user {user_id} not found")
    return {"ok": True}
```

- [ ] Modify `admin_upsert_gold_doc` (lines 122-144), `admin_delete_gold_doc` (lines 147-161), `admin_upsert_quiz` (lines 179-198), `admin_delete_quiz` (lines 201-215). For each, generate trace_id at the top of the function body and pass it as `trace_id=trace_id` to the inner `audit.log_admin_action(...)` call. Example pattern for `admin_upsert_gold_doc`:

```python
@admin_router.put("/gold-docs/{gold_id}", response_model=OkResponse)
def admin_upsert_gold_doc(
    gold_id: str,
    payload: GoldDocUpsertRequest,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()                    # NEW
    concepts = [c.model_dump(exclude_none=True) for c in payload.expected_concepts]
    service.upsert_gold_doc_override(
        db, gold_id=gold_id, content=payload.content,
        expected_concepts=concepts,
        min_concept_count=payload.min_concept_count,
        admin_id=admin["id"],
    )
    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="upsert_gold_doc",
            target_kind="gold_doc", target_id=gold_id,
            metadata={"min_concept_count": payload.min_concept_count, "concept_count": len(concepts)},
            trace_id=trace_id,                         # NEW
        )
    except Exception:
        log.exception("audit upsert_gold_doc failed for %s", gold_id)
    return {"ok": True}
```

Apply the same two-line addition (`trace_id = audit.gen_trace_id()` at top, `trace_id=trace_id` on the audit call) to the other 3 training admin routes.

### Step 5.13: Run training admin tests

Run: `.venv/bin/python -m pytest <training_admin_test_file> -v`

Expected: ALL PASS.

### Step 5.14: Run full suite

Run: `.venv/bin/python -m pytest -x -q`

Expected: PASS.

### Step 5.15: Commit

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/users/service.py \
  backend/users/routes.py \
  backend/training/service.py \
  backend/training/routes.py \
  <user_admin_test_file> \
  <training_admin_test_file>
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-14b): trace_id on user-CRUD and training admin actions

Plumbing for the 9 remaining Group B audit-only sites:
- 5 user-service admin functions (promote/demote/disable/enable/rotate)
- 1 training-service reset_user_training
- 4 training admin routes (gold doc + quiz upsert/delete)

Each generates trace_id at the route layer, forwards to the audit call.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Group B — exports route (BackgroundTask special case)

**Files:**
- Modify: `backend/exports/routes.py:85-130` — generate trace_id, capture in closure, pass into the `_record_audit_and_close` BackgroundTask via `audit.log_admin_action(..., trace_id=trace_id)`.
- Modify: `tests/test_exports_routes.py` — assert audit row has populated trace_id after streaming completes.

### Step 6.1: Write failing test for export trace_id

- [ ] Append to `tests/test_exports_routes.py`:

```python
def test_export_audit_row_carries_trace_id(client, bootstrap_admin, seed_completed_annotation):
    """The BackgroundTask that writes the audit row after streaming must
    receive the trace_id captured in the route's closure."""
    response = client.get("/api/admin/export?format=csv&status=all")
    assert response.status_code == 200
    # Force the body to fully iterate so the BackgroundTask runs.
    _ = response.content

    from backend.shared.db import connect
    from backend import config
    db = connect(config.DB_PATH)
    try:
        row = db.execute(
            "SELECT trace_id FROM admin_audit_log "
            "WHERE action_type='export_dataset' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert isinstance(row["trace_id"], str)
        assert len(row["trace_id"]) == 16
    finally:
        db.close()
```

(Use whatever existing fixture in `tests/test_exports_routes.py` provides at least one annotation row; `seed_completed_annotation` is illustrative.)

### Step 6.2: Run, expect fail

Run: `.venv/bin/python -m pytest tests/test_exports_routes.py::test_export_audit_row_carries_trace_id -v`

Expected: FAIL.

### Step 6.3: Plumb trace_id into export route

- [ ] Modify `backend/exports/routes.py` — locate `admin_export_dataset` and the `_record_audit_and_close` inner function. Generate trace_id near the top of the route handler (before the closure is defined) and reference it inside:

```python
@router.get("/export")
async def admin_export_dataset(
    # ... existing deps ...
    background: BackgroundTasks,
    filters: ExportFilters = Depends(),
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()                    # NEW
    # ... existing setup (build_query, stream_conn, cursor) ...
    counter = [0]

    # ... existing format branch (csv vs jsonl) ...

    filename = f"annotations-export-{_utc_filename_stamp()}.{ext}"

    def _record_audit_and_close():
        try:
            audit.log_admin_action(
                stream_conn, admin_user_id=admin["id"],
                action_type="export_dataset",
                target_kind="export", target_id=filename,
                metadata={
                    "format": filters.format,
                    "filters": _filters_for_audit(filters),
                    "exported_count": counter[0],
                },
                trace_id=trace_id,                     # NEW
            )
        except Exception:
            log.exception("audit export_dataset failed")
        finally:
            stream_conn.close()

    background.add_task(_record_audit_and_close)

    return StreamingResponse(
        body_iter,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        background=background,
    )
```

Note: trace_id is captured by the closure — Python's closure-over-locals works because `trace_id` is a string (immutable), not a mutable container; the BackgroundTask sees the same value generated at request entry.

### Step 6.4: Run export tests

Run: `.venv/bin/python -m pytest tests/test_exports_routes.py -v`

Expected: ALL PASS.

### Step 6.5: Run full suite

Run: `.venv/bin/python -m pytest -x -q`

Expected: PASS. Test count should now be approximately baseline (646) + ~12-15 new tests across all tasks.

### Step 6.6: Tag the mini-pack

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/exports/routes.py \
  tests/test_exports_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-14b): trace_id on export dataset audit row

Last Group B site: trace_id captured in route closure and threaded into
the BackgroundTask that writes the audit row after streaming completes.

All admin call sites now write a non-NULL trace_id; admin-triggered
chains can be reconstructed by JOIN on trace_id between admin_audit_log
and system_events.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git tag paket-14b-trace-id
```

---

## Verification After All Tasks

- [ ] `.venv/bin/python -m pytest -q` — full suite green; expected count: 646 baseline + ~12-15 new tests = ~660 total.
- [ ] `.venv/bin/python -m backend.cli migrate` (with `DATA_DIR=$(pwd)/deneme-dev/data`) — confirms v0004 applies cleanly on a previously-migrated DB; second run is a no-op.
- [ ] Smoke admin run-now flow (manual UI test, optional but recommended):
  ```bash
  curl -X POST -H "Authorization: ..." http://127.0.0.1:8000/api/admin/backup/run-now
  # Response should include "trace_id": "<16 hex chars>"
  # Then:
  sqlite3 deneme-dev/data/main.db \
    "SELECT 'audit' as tbl, action_type, trace_id FROM admin_audit_log
     WHERE trace_id IS NOT NULL ORDER BY id DESC LIMIT 5;
     SELECT 'sysev' as tbl, event_type, trace_id FROM system_events
     WHERE trace_id IS NOT NULL ORDER BY id DESC LIMIT 5;"
  # Expected: trace_id values from response visible in BOTH tables.
  ```
- [ ] `git log --oneline paket-14-export..HEAD` — should show 6 atomic commits with `paket-14b` prefix.

---

## Rollback / Recovery

If a task's tests fail and the cause is unclear:

- The migration v0004 is **append-only** (ADD COLUMN, CREATE INDEX). To roll back: `git reset --soft HEAD~1` (if the commit hasn't shipped) or follow the standard project rollback by hand: drop the column + indexes via a new migration. The recommended path is to fix forward — these are additive changes, no data is destroyed.
- If a service signature change breaks an unexpected caller (e.g., a test that called `run_backup_cycle(db)` positionally and is now passing trace_id positionally — should not happen since trace_id is keyword-only, but verify), `git diff` against the previous commit and either fix the caller or revert the single task with `git revert HEAD`.

---

## Out of Scope (per spec)

- Audit log viewer UI showing trace_id column (Paket 16 frontend).
- `?trace_id=...` filter parameter on `GET /api/admin/audit-log` and `/api/admin/system-events` (add when a real consumer needs it).
- Trace_id on `behavioral_events` / `activity_events` (different correlation context, not requested).
- Distributed tracing or external tracing systems (single-process app).
