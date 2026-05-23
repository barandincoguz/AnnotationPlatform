# Phase 5 Pre-flight Hardening & Deploy Readiness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the Phase-1-to-4 artifact (FastAPI + SQLite + React annotation platform with async Neon mirror) and produce a hardened, audited, ops-ready deployment in 6-9 sessions — closing the 10 audit-discovered completion gaps (4 build, 3 doc, 3 dead-code), adding a PR-gate CI workflow, refreshing the operator runbook, and validating with smoke + a11y + load tests.

**Architecture:** Five execution waves with user-review gates between them. Wave 0 captures a numeric baseline. Wave 1 dispatches 5 parallel read-only audit subagents whose findings populate a severity-tagged backlog. Wave 2 is a per-finding fix sweep (Critical + High only). Wave 2.5 closes the 10 D12 completion gaps with new code and doc/migration changes. Wave 3 adds CI + refreshes runbooks. Wave 4 runs the full smoke + load + a11y validation matrix and signs off in `STATE.md`.

**Tech Stack:** Backend — FastAPI 0.115+ on Python 3.11, SQLite WAL, psycopg (Neon), pytest. Frontend — React 18 strict + Vite 5 + TanStack Query 5 + Zustand + Tailwind + sonner. Tooling — ruff, eslint, tsc, mypy (conditional), wrk, axe-core, Playwright. CI — GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-05-23-phase-5-preflight-hardening-design.md`

---

## File Structure

### New files

| Path | Responsibility |
|------|----------------|
| `audit/BASELINE.md` | Wave 0 snapshot — test counts, image size, cold-boot time, mirror queue depth, latency baseline |
| `audit/SEC.md` | D1 security findings |
| `audit/BE.md` | D2 backend correctness findings |
| `audit/FE.md` | D3 frontend logic findings |
| `audit/PERF.md` | D4 performance findings |
| `audit/DEPLOY.md` | D6 deploy config findings |
| `audit/BACKLOG.md` | Consolidated severity-tagged backlog with APPLY/DEFER decisions |
| `audit/FIX-LOG.md` | Wave 2 finding → commit crosswalk |
| `audit/COMPLETION.md` | Wave 2.5 D12 item → commit crosswalk |
| `audit/OPS.md` | D7 operational readiness findings |
| `audit/UI.md` | D11 visual polish findings |
| `audit/A11Y.md` | D5 a11y findings (Wave 4) |
| `audit/SMOKE.md` | D10 smoke + load + e2e results (Wave 4) |
| `runbooks/restore-drill.md` | Step-by-step restore drill, copy-only, two STOP gates |
| `.github/workflows/ci.yml` | PR-gate CI (ruff, mypy?, pytest, vitest, eslint, tsc, docker build smoke) |
| `backend/backup/routes.py` *(extended)* | Add `POST /api/admin/backup/restore` (U1) |
| `backend/backup/models.py` *(extended)* | Add `BackupRestoreRequest`, `BackupRestoreResponse` |
| `backend/tests/test_backup_restore_route.py` | U1 route + service tests |
| `backend/migrations/v0007_drop_orphan_tables.py` | DC2 + DC3 — drop `user_badges` + `user_quiz_answers` after emptiness assertion |
| `backend/tests/test_v0007_drop_orphan_tables.py` | Migration v0007 tests (idempotent + assertion firing on non-empty) |
| `frontend/src/routes/admin/MirrorHealthPage.tsx` | U4 mirror health admin page |
| `frontend/src/routes/admin/MirrorHealthPage.test.tsx` | U4 tests |
| `frontend/src/routes/admin/BackupPage.tsx` | U5 backup admin page |
| `frontend/src/routes/admin/BackupPage.test.tsx` | U5 tests |
| `frontend/src/routes/admin/RetentionPage.tsx` | U6 retention admin page |
| `frontend/src/routes/admin/RetentionPage.test.tsx` | U6 tests |
| `frontend/src/api/queries/admin.ts` *(extended)* | Add `useMirrorHealth`, `useBackupRunNow`, `useRetentionPreview`, `useRetentionRunNow`, `useBackupRestore` |

### Modified files

| Path | Change |
|------|--------|
| `frontend/src/components/admin/adminNav.ts` | Add nav entries for Mirror Health, Backup, Retention |
| `frontend/src/main.tsx` *or `App.tsx`* | Add `/admin/mirror`, `/admin/backup`, `/admin/retention` routes |
| `README.md` | DR1: scrypt → bcrypt; DR2: 90s → 300s |
| `.planning/REQUIREMENTS.md` | DR3: mark MIRROR-01..10 Complete with commit refs |
| `docs/deployment.md` | Wave 3: refresh, host-agnostic + 2 host appendices |
| `docs/neon-mirror.md` | Wave 3: link the new admin Mirror Health page |
| `.planning/STATE.md` | Phase 5 entry + closeout |
| `.planning/ROADMAP.md` | Phase 5 row |
| `frontend/src/lib/env.ts` | DC1: delete (after grep verification) |
| `backend/main.py` | Wave 3: log rotation hook (optional, host-agnostic) |
| `Dockerfile` | Wave 3: any hygiene findings from D6 |

### Deleted files

| Path | Reason |
|------|--------|
| `frontend/src/lib/env.ts` | DC1: verified orphan export |

---

## Conventions Reference

These mirror the existing codebase. New code must follow them.

### Backend route convention (from `backend/backup/routes.py`, `backend/retention/routes.py`)

```python
from fastapi import APIRouter, Depends, HTTPException

from backend.<area>.models import <PydanticRequest>, <PydanticResponse>
from backend.<area>.service import <do_work>
from backend.shared import audit
from backend.users.deps import get_db, require_admin

router = APIRouter(prefix="/api/admin/<area>", tags=["admin-<area>"])


@router.post("/<verb>", response_model=<PydanticResponse>)
def admin_<area>_<verb>(
    payload: <PydanticRequest>,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()
    try:
        result = <do_work>(db, payload, trace_id=trace_id)
    except <DomainError> as e:
        raise HTTPException(status_code=409, detail={"error": ..., "trace_id": trace_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": ..., "trace_id": trace_id})
    try:
        audit.log_admin_action(db, admin_user_id=admin["id"], action_type="<area>_<verb>",
                               target_kind="<area>", target_id=..., metadata=..., trace_id=trace_id)
    except Exception:
        log.exception("audit <area>_<verb> failed")
    return {**result, "trace_id": trace_id}
```

### Backend test convention

Tests live under `backend/tests/`. Each test file owns one area. Fixture `client` → `TestClient(app)`; fixture `db` → in-memory SQLite with migrations applied; fixture `admin_session` → cookie-authed admin.

### Frontend page convention (from `frontend/src/routes/admin/AuditPage.tsx`)

```tsx
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { use<Query>, use<Mutation> } from '@/api/queries/admin'

export function <Area>Page() {
  const q = use<Query>()
  const m = use<Mutation>()
  // ...
  return (
    <div className="space-y-4">
      <div className="mb-6 space-y-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Operations · <Area>
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight"><Title></h1>
        <p className="text-sm text-muted-foreground max-w-prose"><Subtitle></p>
      </div>
      {/* content */}
    </div>
  )
}
```

### Frontend test convention

Tests live next to the component as `*.test.tsx`. Uses `@testing-library/react`, `vitest`, custom render helper with React Query + Router providers.

### Migration convention (from `backend/migrations/v0006_install_outbox_triggers.py`)

```python
import sqlite3

def up(conn: sqlite3.Connection) -> None:
    # Use conn.execute(stmt) — NOT executescript() — to avoid premature COMMIT.
    conn.execute("...")
```

### Commit convention

Conventional commits with scope: `feat(<area>)`, `fix(<area>)`, `docs(<area>)`, `test(<area>)`, `chore(<area>)`, `refactor(<area>)`. Add `phase-5` reference in commit body. Atomic per feature/fix/file group.

---

# Wave 0 — Baseline

## Task W0.T1: Capture numeric baseline

**Files:**
- Create: `audit/BASELINE.md`

**Steps:**

- [ ] **Step 1: Run backend test suite and record counts**

```bash
cd /Users/barandincoguz/Desktop/deneme && \
  python -m pytest backend/tests/ --tb=no -q 2>&1 | tail -10
```
Expected output ends with a line like `946 passed, 3 skipped in 30.42s`. Note the numbers.

- [ ] **Step 2: Run frontend test suite and record counts**

```bash
cd /Users/barandincoguz/Desktop/deneme/frontend && \
  npx vitest run --reporter=basic 2>&1 | tail -5
```
Expected output: `Test Files <N> passed`, `Tests <M> passed`. Note both.

- [ ] **Step 3: Type check and lint**

```bash
cd /Users/barandincoguz/Desktop/deneme/frontend && npx tsc --noEmit 2>&1 | tail -3
cd /Users/barandincoguz/Desktop/deneme/frontend && npx eslint src 2>&1 | tail -5
cd /Users/barandincoguz/Desktop/deneme && ruff check 2>&1 | tail -3
```
Expected: each command exits 0 with no errors.

- [ ] **Step 4: Confirm mypy presence**

```bash
cd /Users/barandincoguz/Desktop/deneme && which mypy || echo "no-mypy"
grep -E "^mypy" requirements-dev.txt pyproject.toml 2>/dev/null
```
Expected: either a mypy path appears or `no-mypy` is printed. Record whether mypy is in toolchain — this controls whether §5 gate 6 is enforced.

- [ ] **Step 5: Build the Docker image and time it**

```bash
cd /Users/barandincoguz/Desktop/deneme && \
  time docker build -t anotasyon-platform:phase5-baseline . 2>&1 | tail -3 && \
  docker image inspect anotasyon-platform:phase5-baseline --format='{{.Size}}'
```
Expected: build succeeds; image size printed in bytes. Record total time + size.

- [ ] **Step 6: Cold-boot time and mirror queue depth**

```bash
cd /Users/barandincoguz/Desktop/deneme && \
  docker run -d --rm --name a11n-baseline \
    -e ENVIRONMENT=development -e SESSION_SECRET=dev-secret-DO-NOT-USE-IN-PROD-but-32+ \
    -e DISABLE_SPA_MOUNT=1 \
    -p 18000:8000 anotasyon-platform:phase5-baseline && \
  start=$(date +%s) && \
  until curl -fs http://127.0.0.1:18000/api/health >/dev/null 2>&1; do sleep 0.5; done && \
  end=$(date +%s) && echo "cold-boot seconds: $((end - start))" && \
  docker stop a11n-baseline >/dev/null
```
Expected: prints `cold-boot seconds: <N>` with N ≤ 30. Record N.

- [ ] **Step 7: Write `audit/BASELINE.md`**

```bash
mkdir -p /Users/barandincoguz/Desktop/deneme/audit
```

Then create `audit/BASELINE.md` with the recorded values:

```markdown
# Wave 0 Baseline — 2026-05-23

| Metric | Value |
|--------|-------|
| Backend pytest passing | <N> |
| Backend pytest skipped | <N> |
| Frontend vitest passing | <N> |
| TypeScript errors | 0 |
| ESLint errors/warnings | 0 / 0 |
| Ruff errors | 0 |
| mypy in toolchain | YES / NO (recorded value) |
| Docker image build time | <N>s |
| Docker image size | <N> MB |
| Cold-boot to /api/health 200 | <N>s |
| Mirror queue depth at boot | 0 |
| Phase 4 latency baseline (from `4-SUMMARY.md`) | wrk ≤0.02 ms p95 delta over `/api/health` |

Recorded by: Phase 5 Wave 0 baseline task.
```

- [ ] **Step 8: Commit**

```bash
cd /Users/barandincoguz/Desktop/deneme && \
  git add audit/BASELINE.md && \
  git commit -m "docs(phase-5): wave 0 baseline metrics

Captured before any Phase 5 work begins. Used as the regression
reference for Wave 4 validation."
```

---

# Wave 1 — Read-only Audit (5 parallel subagents)

## Task W1.T1: Dispatch 5 parallel audit subagents

**Files:**
- Create: `audit/SEC.md`, `audit/BE.md`, `audit/FE.md`, `audit/PERF.md`, `audit/DEPLOY.md`

**Steps:**

- [ ] **Step 1: Dispatch 5 subagents in a single message (parallel)**

Each subagent gets a self-contained brief with the same output format:

```
Report format:
## <Dimension> Findings

| ID | Sev | Area | Description | File:Line | Verdict (blank — user fills) |
|----|-----|------|-------------|-----------|------------------------------|
```

Dispatch list:

| Subagent | Dim | Brief |
|----------|-----|-------|
| 1 | D1 (security) | Re-audit Phase 4 mirror code (`backend/mirror/`); re-evaluate POLISH_BACKLOG DEFER list against current code; check `/api/auth/login` + `/api/auth/register` + `/api/users/invites` for brute-force exposure; verify Origin allowlist behavior under all state-changing methods; grep secrets in git history + image; confirm CSV/JSON formula-injection guards |
| 2 | D2 (backend correctness) | Sweep services + routes + dispatcher loop for: race conditions in outbox capture under concurrent writers; transaction-boundary correctness (BEGIN IMMEDIATE; PRAGMA defer_foreign_keys); error-path coverage; idempotency of admin actions; migration runner re-entrancy |
| 3 | D3 (frontend logic) | Sweep `useLock`, `useDraft`, `useSSE`, `useReferencesState` for: stale closures; missing `AbortController`s; race conditions across doc navigation; query-invalidation correctness; error-state rendering |
| 4 | D4 (performance) | Verify the Phase 4 ≤5 ms p95 latency budget under `wrk -t2 -c10 -d60s` against `/api/feed?tab=new&limit=50`; profile DocList under simulated SSE invalidation storm (10 events/s); measure outbox drain throughput on a queue of 10k rows |
| 5 | D6 (deploy config) | Audit `Dockerfile`, `docker-compose.yml`, `.env.production` template, healthcheck, signal handling, non-root user permissions, log destination, image layer hygiene, multi-stage build correctness, secrets discipline (no secret in image), Caddy/nginx reverse-proxy compatibility |

Each subagent writes to its own file under `audit/`. Return concise findings table only.

- [ ] **Step 2: Wait for all 5 subagents to finish; then read each output file**

```bash
for f in audit/SEC.md audit/BE.md audit/FE.md audit/PERF.md audit/DEPLOY.md; do
  echo "=== $f ===" && head -50 "$f"
done
```

- [ ] **Step 3: Sanity-check each file has at least the table header**

If any file is empty or malformed, re-dispatch that single subagent before moving on.

- [ ] **Step 4: Commit the audit set**

```bash
git add audit/SEC.md audit/BE.md audit/FE.md audit/PERF.md audit/DEPLOY.md && \
git commit -m "docs(phase-5): wave 1 read-only audit — 5 dimensions

D1 security, D2 backend correctness, D3 frontend logic, D4 perf,
D6 deploy config. Findings staged for user APPLY/DEFER triage in
audit/BACKLOG.md."
```

## Task W1.T2: Consolidate backlog

**Files:**
- Create: `audit/BACKLOG.md`

**Steps:**

- [ ] **Step 1: Build the consolidated backlog**

Open each `audit/<DIM>.md` and merge all rows into a single table in `audit/BACKLOG.md`. Add a `Verdict` column (blank initially, user fills as APPLY-W2 / APPLY-W2.5 / DEFER).

Template:

```markdown
# Phase 5 Audit Backlog — 2026-05-23

Source: Wave 1 read-only audit (5 dimensions). User to mark Verdict.

Valid verdicts:
- `APPLY-W2` — fix in Wave 2 (Critical + High)
- `APPLY-W2.5-ADD` — adds to D12 build scope (rare; only if it's a clearly-missing feature)
- `DEFER` — Phase 6 backlog with one-line reason

| ID | Dim | Sev | Area | Description | File:Line | Verdict |
|----|-----|-----|------|-------------|-----------|---------|
| (merge from audit/SEC.md, BE.md, FE.md, PERF.md, DEPLOY.md) |

## Summary by severity
- Critical: <N>
- High: <N>
- Medium: <N>
- Low: <N>
- Info: <N>
```

- [ ] **Step 2: User review gate**

Stop and surface BACKLOG.md to the user. Wait for the user to fill in `Verdict` per row. Do not start Wave 2 before this gate.

- [ ] **Step 3: Commit the user-marked backlog**

```bash
git add audit/BACKLOG.md && \
git commit -m "docs(phase-5): wave 1 backlog with user APPLY/DEFER verdicts"
```

---

# Wave 2 — Fix Sweep (one task per APPLY-W2 finding)

This wave is finding-driven. Each APPLY-W2 row in `audit/BACKLOG.md` becomes one task. The template below applies to every Wave 2 fix.

## Wave 2 Task Template

**Files:**
- Modify: <file:line from the backlog>
- Test: <existing or new test file>

**Steps:**

- [ ] **Step 1: Reproduce the issue in a test (TDD)**

Write a failing test that demonstrates the bug. Test path matches existing conventions (`backend/tests/test_<area>.py` or `frontend/src/<dir>/<file>.test.tsx`).

- [ ] **Step 2: Run the test, confirm it fails for the expected reason**

```bash
# Backend
pytest backend/tests/test_<area>.py::test_<name> -v

# Frontend
cd frontend && npx vitest run src/<path>/<file>.test.tsx -t "<test name>"
```
Expected: FAIL with the assertion message that names the bug behavior.

- [ ] **Step 3: Apply the minimum fix**

Edit the named file at the named line. Do not refactor adjacent code. Keep the change surgical.

- [ ] **Step 4: Run the same test, confirm it now passes**

Same command as Step 2. Expected: PASS.

- [ ] **Step 5: Run the affected area's full test suite to confirm no regression**

```bash
# Example for backend mirror surface
pytest backend/tests/test_mirror_*.py -v --tb=short
```
Expected: all PASS.

- [ ] **Step 6: If the fix touched mirror code, also run the dispatcher e2e**

```bash
pytest backend/tests/test_mirror_e2e.py -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add <files> && git commit -m "fix(<area>): <one-line>

phase-5 wave-2 finding <ID>: <description>"
```

## Task W2.T1: Maintain `audit/FIX-LOG.md`

After each fix commit, append a row:

```markdown
| Finding ID | Sev | Commit SHA | One-line summary |
|------------|-----|------------|------------------|
```

Commit `audit/FIX-LOG.md` updates in the same atomic commit as the fix.

## Task W2.T2: Wave 2 exit gate

- [ ] **Step 1: Full backend pytest re-run**

```bash
pytest backend/tests/ --tb=short -q | tail -10
```
Expected: total pass ≥ Wave 0 baseline; 0 fail.

- [ ] **Step 2: Full frontend vitest re-run**

```bash
cd frontend && npx vitest run --reporter=basic | tail -5
```
Expected: total pass ≥ Wave 0 baseline; 0 fail.

- [ ] **Step 3: Type check + lint re-run**

```bash
cd frontend && npx tsc --noEmit && npx eslint src
cd /Users/barandincoguz/Desktop/deneme && ruff check
```
Expected: all 0 errors.

- [ ] **Step 4: User review gate on `audit/FIX-LOG.md`**

Stop and surface FIX-LOG.md. Wait for user approval before Wave 2.5.

---

# Wave 2.5 — D12 Completion Sweep

This is the build wave. 10 concrete tasks: 4 backend/frontend features, 3 doc edits, 3 dead-code removals. Order matters — DC migration last (after fixes settle).

## Task W2.5.T1: U1 — Backup restore HTTP route

**Goal:** Add `POST /api/admin/backup/restore` that consumes an uploaded snapshot JSON and calls `restore_from_snapshot`, with a WAL safety guard.

**Files:**
- Modify: `backend/backup/models.py` (add request/response models)
- Modify: `backend/backup/routes.py` (add route handler)
- Modify: `backend/backup/service.py` (add wrapper that runs migrations first + emits system event)
- Create: `backend/tests/test_backup_restore_route.py`

**Steps:**

- [ ] **Step 1: Write failing test for happy-path restore**

Create `backend/tests/test_backup_restore_route.py`:

```python
"""Tests for the U1 backup restore HTTP route."""
import json
import pytest
from fastapi.testclient import TestClient

# These fixtures are assumed from existing conftest: `client`, `admin_session`,
# `db_factory` — they follow the patterns already in backend/tests/.

def test_restore_route_replaces_db_state(client, admin_session, db_factory, tmp_path):
    """POSTing a valid snapshot to /api/admin/backup/restore must replace
    DB state with the snapshot's contents and write an admin_audit_log row."""
    # Arrange — write a minimal snapshot file
    snapshot = {
        "__format_version": 1,
        "users": [
            {"id": 1, "username": "alice", "password_hash": "x", "role": "annotator",
             "is_active": 1, "has_passed_training": 1, "has_seen_manual": 1,
             "created_at": "2026-01-01T00:00:00Z"}
        ],
    }
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps(snapshot), encoding="utf-8")

    # Act
    with open(snap_path, "rb") as f:
        resp = client.post(
            "/api/admin/backup/restore",
            files={"snapshot": ("snap.json", f, "application/json")},
            cookies=admin_session,
        )

    # Assert
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["tables"]["users"] == 1
    assert body["total_rows"] >= 1
    assert "trace_id" in body
```

- [ ] **Step 2: Add `test_restore_route_refuses_hot_db` — WAL safety guard test**

Append to the same file:

```python
def test_restore_route_refuses_when_wal_in_use(client, admin_session, db_factory, tmp_path, monkeypatch):
    """If another writer is actively holding the WAL, the route must
    refuse with HTTP 409 rather than risk a half-applied restore."""
    from backend.backup import service as backup_service

    def fake_wal_busy(_db):
        return True  # simulate hot DB

    monkeypatch.setattr(backup_service, "is_wal_busy", fake_wal_busy)

    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps({"__format_version": 1, "users": []}), encoding="utf-8")
    with open(snap_path, "rb") as f:
        resp = client.post(
            "/api/admin/backup/restore",
            files={"snapshot": ("snap.json", f, "application/json")},
            cookies=admin_session,
        )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["error"] == "db_busy"
```

- [ ] **Step 3: Add admin-only enforcement test**

Append:

```python
def test_restore_route_requires_admin(client, annotator_session, tmp_path):
    """Non-admin sessions must be rejected with 403."""
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps({"__format_version": 1}), encoding="utf-8")
    with open(snap_path, "rb") as f:
        resp = client.post(
            "/api/admin/backup/restore",
            files={"snapshot": ("snap.json", f, "application/json")},
            cookies=annotator_session,
        )
    assert resp.status_code in (401, 403)
```

- [ ] **Step 4: Run the 3 tests; confirm all 3 fail for the right reason**

```bash
pytest backend/tests/test_backup_restore_route.py -v
```
Expected: 3 FAIL — route does not exist yet (`404` or `405`).

- [ ] **Step 5: Add Pydantic models to `backend/backup/models.py`**

Append (after the existing `BackupRunNowResponse`):

```python
class BackupRestoreResponse(BaseModel):
    ok: bool
    tables: dict[str, int]
    total_rows: int
    skipped_tables: list[str]
    trace_id: str
```

(Imports remain as in the file; no new `BaseModel` import needed if it's already there.)

- [ ] **Step 6: Add a WAL-safety helper to `backend/backup/service.py`**

Append (next to other service-level functions):

```python
def is_wal_busy(db: sqlite3.Connection) -> bool:
    """Cheap heuristic: WAL has uncommitted frames from another connection.

    Returns True if `wal_checkpoint(PASSIVE)` reports that more than a
    handful of frames are pending — meaning another writer is mid-flight.
    Conservative: false positives are OK (operator retries), false
    negatives are not (could corrupt the restored DB).
    """
    try:
        row = db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    except sqlite3.OperationalError:
        return True
    # row = (busy, log_frames, checkpointed_frames). If `busy` is 1
    # OR `log_frames - checkpointed_frames > 0`, another writer is active.
    if row is None:
        return False
    busy, log_frames, ckpt_frames = row[0], row[1], row[2]
    return bool(busy) or (log_frames - ckpt_frames > 0)
```

- [ ] **Step 7: Add the route to `backend/backup/routes.py`**

Append (after `admin_backup_run_now`):

```python
from fastapi import UploadFile, File
import json

from backend.backup.models import BackupRestoreResponse
from backend.backup.restore import restore_from_snapshot
from backend.backup.service import is_wal_busy


@router.post("/restore", response_model=BackupRestoreResponse)
async def admin_backup_restore(
    snapshot: UploadFile = File(...),
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Restore DB state from an uploaded snapshot JSON.

    Refuses if another writer is holding the WAL (409 db_busy). Wraps
    the existing restore_from_snapshot() service call and writes an
    admin_audit_log row on success."""
    trace_id = audit.gen_trace_id()

    if is_wal_busy(db):
        raise HTTPException(
            status_code=409,
            detail={"error": "db_busy", "message": "WAL has uncommitted frames from another writer; retry after the writer finishes.", "trace_id": trace_id},
        )

    raw = await snapshot.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_json", "message": str(e), "trace_id": trace_id},
        )

    # Persist to a temp file inside DATA_DIR so the existing
    # restore_from_snapshot signature (Path-based) is preserved.
    from backend import config
    import tempfile, pathlib

    with tempfile.NamedTemporaryFile(
        delete=False, mode="w", dir=str(config.DATA_DIR), suffix=".restore.json"
    ) as f:
        json.dump(payload, f)
        snap_path = pathlib.Path(f.name)

    try:
        result = restore_from_snapshot(db, snap_path)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "restore_invalid_columns", "message": str(e), "trace_id": trace_id},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "restore_failed", "message": str(e), "trace_id": trace_id},
        )
    finally:
        try:
            snap_path.unlink()
        except OSError:
            pass

    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="backup_restore",
            target_kind="backup", target_id=None,
            metadata={
                "total_rows": result["total_rows"],
                "tables": result["tables"],
                "skipped_tables": result["skipped_tables"],
            },
            trace_id=trace_id,
        )
    except Exception:
        log.exception("audit backup_restore failed")

    return {"ok": True, **result, "trace_id": trace_id}
```

- [ ] **Step 8: Run the 3 tests; expect all PASS**

```bash
pytest backend/tests/test_backup_restore_route.py -v
```
Expected: 3 PASS.

- [ ] **Step 9: Run the full backup test suite to confirm no regression**

```bash
pytest backend/tests/test_backup*.py -v --tb=short
```
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/backup/models.py backend/backup/routes.py backend/backup/service.py \
        backend/tests/test_backup_restore_route.py && \
git commit -m "feat(backup): expose POST /api/admin/backup/restore (U1)

phase-5 D12: previously restore_from_snapshot was implementation-only
with no HTTP surface. Adds upload route, WAL-busy refusal, admin audit
log, and 3 tests (happy path, hot-DB refuse, admin-only)."
```

---

## Task W2.5.T2: U4 — Mirror health admin page

**Goal:** Add `/admin/mirror` page that fetches `GET /api/admin/mirror/health` on an interval and renders queue depth, dead-letter count, last-delivered-at, dispatcher-alive, neon-reachable. Threshold colors: queue ≥ 10000 critical, queue ≥ 1000 warn, dead-letter ≥ 1 warn.

**Files:**
- Modify: `frontend/src/api/queries/admin.ts` (add `useMirrorHealth`)
- Create: `frontend/src/routes/admin/MirrorHealthPage.tsx`
- Create: `frontend/src/routes/admin/MirrorHealthPage.test.tsx`
- Modify: `frontend/src/components/admin/adminNav.ts` (add nav entry)
- Modify: `frontend/src/main.tsx` *or* `frontend/src/App.tsx` (add route)

**Steps:**

- [ ] **Step 1: Read the existing adminNav + router to determine exact mod points**

```bash
cat /Users/barandincoguz/Desktop/deneme/frontend/src/components/admin/adminNav.ts
grep -nE "(/admin/|AdminLayout)" /Users/barandincoguz/Desktop/deneme/frontend/src/main.tsx \
                                  /Users/barandincoguz/Desktop/deneme/frontend/src/App.tsx 2>/dev/null
```
Expected: `adminNav.ts` shows existing groups; router has child routes under `/admin`. Record the exact patterns.

- [ ] **Step 2: Write failing test (skeleton)**

Create `frontend/src/routes/admin/MirrorHealthPage.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MirrorHealthPage } from './MirrorHealthPage'

function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('MirrorHealthPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo) => {
      const url = typeof input === 'string' ? input : input.url
      if (url.endsWith('/api/admin/mirror/health')) {
        return new Response(JSON.stringify({
          queue_depth: 42,
          dead_letter_count: 0,
          oldest_undelivered_age_seconds: 12.4,
          last_delivered_at: '2026-05-23T15:00:00Z',
          dispatcher_alive: true,
          neon_reachable: true,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      throw new Error(`unexpected fetch: ${url}`)
    }))
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('renders queue depth and dispatcher-alive badge', async () => {
    renderWithProviders(<MirrorHealthPage />)
    await waitFor(() => expect(screen.getByText(/42/)).toBeInTheDocument())
    expect(screen.getByText(/dispatcher.*alive/i)).toBeInTheDocument()
  })

  it('applies warn class when queue depth crosses 1000', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      queue_depth: 1500, dead_letter_count: 0,
      oldest_undelivered_age_seconds: 100, last_delivered_at: null,
      dispatcher_alive: true, neon_reachable: true,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    renderWithProviders(<MirrorHealthPage />)
    await waitFor(() => {
      const el = screen.getByTestId('queue-depth')
      expect(el.className).toMatch(/warn|amber|yellow/)
    })
  })

  it('applies critical class when queue depth crosses 10000', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      queue_depth: 20000, dead_letter_count: 0,
      oldest_undelivered_age_seconds: 1000, last_delivered_at: null,
      dispatcher_alive: true, neon_reachable: false,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    renderWithProviders(<MirrorHealthPage />)
    await waitFor(() => {
      const el = screen.getByTestId('queue-depth')
      expect(el.className).toMatch(/critical|red|destructive/)
    })
  })
})
```

- [ ] **Step 3: Run the test; expect 3 FAIL (page doesn't exist)**

```bash
cd frontend && npx vitest run src/routes/admin/MirrorHealthPage.test.tsx
```
Expected: 3 FAIL with `Cannot find module './MirrorHealthPage'`.

- [ ] **Step 4: Add the query hook**

Edit `frontend/src/api/queries/admin.ts`. Append (matching existing useAuditLog pattern):

```ts
import { useQuery } from '@tanstack/react-query'
import { env } from '@/lib/env' // NOTE: if DC1 deletes env.ts, swap to import.meta.env.VITE_API_BASE_URL

export interface MirrorHealth {
  queue_depth: number
  dead_letter_count: number
  oldest_undelivered_age_seconds: number | null
  last_delivered_at: string | null
  dispatcher_alive: boolean
  neon_reachable: boolean | null
}

export function useMirrorHealth(refetchMs = 10_000) {
  return useQuery<MirrorHealth>({
    queryKey: ['admin', 'mirror', 'health'],
    queryFn: async () => {
      const res = await fetch('/api/admin/mirror/health', { credentials: 'include' })
      if (!res.ok) throw new Error(`mirror health ${res.status}`)
      return res.json()
    },
    refetchInterval: refetchMs,
    staleTime: 5_000,
  })
}
```

(If `useQuery` is already imported, don't re-import. Match the file's existing imports.)

- [ ] **Step 5: Create `frontend/src/routes/admin/MirrorHealthPage.tsx`**

```tsx
import { useMirrorHealth } from '@/api/queries/admin'

function queueClass(depth: number): string {
  if (depth >= 10_000) return 'text-destructive font-semibold' // critical
  if (depth >= 1_000) return 'text-amber-600 font-semibold'    // warn
  return ''
}

function deadLetterClass(n: number): string {
  if (n > 0) return 'text-amber-600 font-semibold'
  return ''
}

export function MirrorHealthPage() {
  const q = useMirrorHealth()

  return (
    <div className="space-y-4">
      <div className="mb-6 space-y-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Operations · Mirror
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight">
          Neon Mirror Health
        </h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Async mirror dispatcher state and outbox queue depth. Auto-refresh every 10 s.
        </p>
      </div>

      {q.isLoading && <div className="text-sm">Yükleniyor…</div>}
      {q.isError && (
        <div className="rounded border border-destructive p-4 text-sm">
          Mirror sağlık verisi alınamadı.
        </div>
      )}

      {q.data && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Outbox queue depth</div>
            <div data-testid="queue-depth" className={`text-2xl ${queueClass(q.data.queue_depth)}`}>
              {q.data.queue_depth}
            </div>
          </div>
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Dead-letter rows</div>
            <div data-testid="dead-letter" className={`text-2xl ${deadLetterClass(q.data.dead_letter_count)}`}>
              {q.data.dead_letter_count}
            </div>
          </div>
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Dispatcher</div>
            <div className="text-2xl">
              {q.data.dispatcher_alive ? 'dispatcher alive' : 'dispatcher down'}
            </div>
          </div>
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Neon reachable</div>
            <div className="text-2xl">
              {q.data.neon_reachable === null ? '—' : q.data.neon_reachable ? 'evet' : 'hayır'}
            </div>
          </div>
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Last delivered at</div>
            <div className="text-base font-mono">
              {q.data.last_delivered_at ?? '—'}
            </div>
          </div>
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Oldest undelivered (s)</div>
            <div className="text-base font-mono">
              {q.data.oldest_undelivered_age_seconds == null
                ? '—'
                : q.data.oldest_undelivered_age_seconds.toFixed(1)}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Run the test; expect 3 PASS**

```bash
cd frontend && npx vitest run src/routes/admin/MirrorHealthPage.test.tsx
```
Expected: 3 PASS.

- [ ] **Step 7: Wire the route**

Read the existing router config (recorded in Step 1). Add a child route, following the existing pattern. Example if the router uses `createBrowserRouter` with nested `children`:

```ts
// Inside the AdminLayout children array:
{ path: 'mirror', element: <MirrorHealthPage /> },
```

- [ ] **Step 8: Add nav entry**

Edit `frontend/src/components/admin/adminNav.ts`. Add to the "Operations" group (or whichever group `AuditPage` lives in):

```ts
{ to: '/admin/mirror', label: 'Mirror health' },
```

- [ ] **Step 9: Type check and lint**

```bash
cd frontend && npx tsc --noEmit && npx eslint src/routes/admin/MirrorHealthPage.tsx \
                                                  src/api/queries/admin.ts \
                                                  src/components/admin/adminNav.ts
```
Expected: 0 errors.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/routes/admin/MirrorHealthPage.tsx \
        frontend/src/routes/admin/MirrorHealthPage.test.tsx \
        frontend/src/api/queries/admin.ts \
        frontend/src/components/admin/adminNav.ts \
        frontend/src/main.tsx 2>/dev/null || \
git add frontend/src/routes/admin/MirrorHealthPage.tsx \
        frontend/src/routes/admin/MirrorHealthPage.test.tsx \
        frontend/src/api/queries/admin.ts \
        frontend/src/components/admin/adminNav.ts \
        frontend/src/App.tsx

git commit -m "feat(admin): add /admin/mirror health page (U4)

phase-5 D12 MIRROR-09: surface outbox queue depth, dead-letter count,
last-delivered-at, dispatcher-alive, neon-reachable on an admin page
with 10 s auto-refresh and threshold-driven color coding (warn ≥ 1000,
critical ≥ 10000 queue depth; warn ≥ 1 dead-letter)."
```

---

## Task W2.5.T3: U5 — Backup admin page

**Goal:** Add `/admin/backup` with a "Run backup now" button and a history list of the last 20 `backup_*` system events.

**Files:**
- Modify: `frontend/src/api/queries/admin.ts` (add `useBackupRunNow`, `useBackupHistory`)
- Create: `frontend/src/routes/admin/BackupPage.tsx`
- Create: `frontend/src/routes/admin/BackupPage.test.tsx`
- Modify: `frontend/src/components/admin/adminNav.ts`
- Modify: router config (same file as U4)
- Modify (backend): if no `GET /api/admin/system-events?event_type_prefix=backup_` query supports filtering, add the filter. Otherwise, use it as-is.

**Steps:**

- [ ] **Step 1: Read the existing system-events route to confirm filter support**

```bash
grep -rn "system_events\|system-events" /Users/barandincoguz/Desktop/deneme/backend/admin/
```
If no `event_type_prefix` query param exists, add one (small backend change). Otherwise skip backend mods.

- [ ] **Step 2: Write failing tests**

Create `frontend/src/routes/admin/BackupPage.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BackupPage } from './BackupPage'

function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('BackupPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.url
      if (url.includes('/api/admin/system-events') && (init?.method ?? 'GET') === 'GET') {
        return new Response(JSON.stringify({
          items: [
            { id: 1, event_type: 'backup_success', severity: 'info',
              message: 'snapshot pushed', extra: '{}', created_at: '2026-05-23T10:00:00Z' },
          ],
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (url.endsWith('/api/admin/backup/run-now') && init?.method === 'POST') {
        return new Response(JSON.stringify({
          ok: true, snapshot_path: '/data/x.json', committed_sha: 'abc',
          pushed: true, rotated_count: 0, trace_id: 't-1',
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      throw new Error(`unexpected fetch: ${url}`)
    }))
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('renders history list', async () => {
    renderWithProviders(<BackupPage />)
    await waitFor(() => expect(screen.getByText(/snapshot pushed/)).toBeInTheDocument())
  })

  it('clicking "Run backup now" calls the route and toasts success', async () => {
    renderWithProviders(<BackupPage />)
    await waitFor(() => screen.getByText(/Şimdi yedek al/))
    fireEvent.click(screen.getByText(/Şimdi yedek al/))
    await waitFor(() => expect(screen.getByText(/Yedek alındı/)).toBeInTheDocument())
  })
})
```

- [ ] **Step 3: Run; expect 2 FAIL**

```bash
cd frontend && npx vitest run src/routes/admin/BackupPage.test.tsx
```
Expected: 2 FAIL.

- [ ] **Step 4: Add query + mutation hooks to `frontend/src/api/queries/admin.ts`**

Append:

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'

export interface SystemEvent {
  id: number
  event_type: string
  severity: 'info' | 'warn' | 'error'
  message: string
  extra: string
  created_at: string
}

export function useBackupHistory() {
  return useQuery<{ items: SystemEvent[] }>({
    queryKey: ['admin', 'system-events', 'backup_'],
    queryFn: async () => {
      const res = await fetch('/api/admin/system-events?event_type_prefix=backup_&limit=20', {
        credentials: 'include',
      })
      if (!res.ok) throw new Error(`system-events ${res.status}`)
      return res.json()
    },
  })
}

export function useBackupRunNow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/admin/backup/run-now', {
        method: 'POST', credentials: 'include',
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail?.message ?? `backup failed ${res.status}`)
      }
      return res.json()
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin', 'system-events', 'backup_'] }) },
  })
}
```

- [ ] **Step 5: Create `frontend/src/routes/admin/BackupPage.tsx`**

```tsx
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { useBackupHistory, useBackupRunNow } from '@/api/queries/admin'

export function BackupPage() {
  const history = useBackupHistory()
  const run = useBackupRunNow()

  const onRun = () => {
    run.mutate(undefined, {
      onSuccess: () => toast.success('Yedek alındı'),
      onError: (e: Error) => toast.error(`Yedek başarısız: ${e.message}`),
    })
  }

  return (
    <div className="space-y-4">
      <div className="mb-6 space-y-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Operations · Backup
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight">Backup</h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Veritabanı snapshot'larını manuel olarak tetikle ve son 20 yedek olayını gör.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={onRun} disabled={run.isPending}>
          {run.isPending ? 'Yedek alınıyor…' : 'Şimdi yedek al'}
        </Button>
        {run.data?.committed_sha && (
          <span className="font-mono text-xs text-muted-foreground">
            sha: {run.data.committed_sha.slice(0, 7)} · pushed: {run.data.pushed ? 'evet' : 'hayır'}
          </span>
        )}
      </div>

      <div className="rounded-lg border border-border/70 bg-card/40 p-4">
        <h2 className="font-medium mb-3">Son 20 yedek olayı</h2>
        {history.isLoading && <div className="text-sm">Yükleniyor…</div>}
        {history.data && (
          <ul className="space-y-2 text-sm">
            {history.data.items.map((e) => (
              <li key={e.id} className="flex items-baseline gap-3">
                <span className="font-mono text-xs text-muted-foreground w-44 shrink-0">
                  {e.created_at}
                </span>
                <span className={`text-xs px-1.5 rounded ${
                  e.severity === 'error' ? 'bg-destructive/15 text-destructive' :
                  e.severity === 'warn' ? 'bg-amber-100 text-amber-800' :
                  'bg-muted text-muted-foreground'}`}>
                  {e.event_type}
                </span>
                <span>{e.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Run tests; expect PASS**

```bash
cd frontend && npx vitest run src/routes/admin/BackupPage.test.tsx
```
Expected: 2 PASS.

- [ ] **Step 7: Wire route + nav (same pattern as U4 Step 7-8)**

- [ ] **Step 8: Type check + lint**

```bash
cd frontend && npx tsc --noEmit && npx eslint src/routes/admin/BackupPage.tsx src/api/queries/admin.ts
```

- [ ] **Step 9: Commit**

```bash
git add frontend/src/routes/admin/BackupPage.tsx \
        frontend/src/routes/admin/BackupPage.test.tsx \
        frontend/src/api/queries/admin.ts \
        frontend/src/components/admin/adminNav.ts \
        frontend/src/{App.tsx,main.tsx} 2>/dev/null
git commit -m "feat(admin): add /admin/backup page (U5)

phase-5 D12: surface POST /api/admin/backup/run-now in UI plus history
of the last 20 backup_* system events. Toasts success/failure."
```

---

## Task W2.5.T4: U6 — Retention admin page

**Goal:** Add `/admin/retention` with a preview list (rows that would be deleted) and a confirm-modal-gated "Run now" button.

**Files:**
- Modify: `frontend/src/api/queries/admin.ts` (add `useRetentionPreview`, `useRetentionRunNow`)
- Create: `frontend/src/routes/admin/RetentionPage.tsx`
- Create: `frontend/src/routes/admin/RetentionPage.test.tsx`
- Modify: `frontend/src/components/admin/adminNav.ts`
- Modify: router config

**Steps:**

- [ ] **Step 1: Write failing test**

Create `frontend/src/routes/admin/RetentionPage.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RetentionPage } from './RetentionPage'

function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('RetentionPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.url
      if (url.endsWith('/api/admin/retention/preview') && (init?.method ?? 'GET') === 'GET') {
        return new Response(JSON.stringify({
          by_table: { admin_audit_log: 12, system_events: 5 },
          total: 17,
          policy: { admin_audit_log_retain_days: 90, system_events_retain_days: 30 },
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (url.endsWith('/api/admin/retention/run-now') && init?.method === 'POST') {
        return new Response(JSON.stringify({
          ok: true, total: 17, purged: { admin_audit_log: 12, system_events: 5 }, trace_id: 't-1',
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      throw new Error(`unexpected fetch: ${url}`)
    }))
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('shows preview totals', async () => {
    renderWithProviders(<RetentionPage />)
    await waitFor(() => expect(screen.getByText(/Toplam.*17/)).toBeInTheDocument())
  })

  it('Run-now requires confirm step', async () => {
    renderWithProviders(<RetentionPage />)
    await waitFor(() => screen.getByText(/Şimdi temizle/))
    fireEvent.click(screen.getByText(/Şimdi temizle/))
    // Confirm modal appears with the count
    await waitFor(() => expect(screen.getByText(/17 satır.*kalıcı/)).toBeInTheDocument())
    // Cancel keeps state idle
    fireEvent.click(screen.getByText(/Vazgeç/))
    expect(screen.queryByText(/17 satır.*kalıcı/)).not.toBeInTheDocument()
  })

  it('Confirm fires retention/run-now and toasts', async () => {
    renderWithProviders(<RetentionPage />)
    await waitFor(() => screen.getByText(/Şimdi temizle/))
    fireEvent.click(screen.getByText(/Şimdi temizle/))
    await waitFor(() => screen.getByText(/Evet, sil/))
    fireEvent.click(screen.getByText(/Evet, sil/))
    await waitFor(() => expect(screen.getByText(/17 satır silindi/)).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run; expect 3 FAIL**

```bash
cd frontend && npx vitest run src/routes/admin/RetentionPage.test.tsx
```

- [ ] **Step 3: Add hooks to `admin.ts`**

```ts
export interface RetentionPreview {
  by_table: Record<string, number>
  total: number
  policy: Record<string, number>
}

export function useRetentionPreview() {
  return useQuery<RetentionPreview>({
    queryKey: ['admin', 'retention', 'preview'],
    queryFn: async () => {
      const res = await fetch('/api/admin/retention/preview', { credentials: 'include' })
      if (!res.ok) throw new Error(`retention/preview ${res.status}`)
      return res.json()
    },
  })
}

export function useRetentionRunNow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/admin/retention/run-now', {
        method: 'POST', credentials: 'include',
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail?.message ?? `retention failed ${res.status}`)
      }
      return res.json()
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin', 'retention', 'preview'] }) },
  })
}
```

- [ ] **Step 4: Create `RetentionPage.tsx`**

```tsx
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useRetentionPreview, useRetentionRunNow } from '@/api/queries/admin'

export function RetentionPage() {
  const preview = useRetentionPreview()
  const run = useRetentionRunNow()
  const [confirming, setConfirming] = useState(false)

  const onRun = () => {
    run.mutate(undefined, {
      onSuccess: (r) => {
        toast.success(`${r.total} satır silindi`)
        setConfirming(false)
      },
      onError: (e: Error) => toast.error(`Retention başarısız: ${e.message}`),
    })
  }

  return (
    <div className="space-y-4">
      <div className="mb-6 space-y-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Operations · Retention
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight">Retention</h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Süresi dolan denetim ve sistem olaylarını politika tablolarına göre temizler.
        </p>
      </div>

      {preview.isLoading && <div className="text-sm">Yükleniyor…</div>}
      {preview.data && (
        <div className="rounded-lg border border-border/70 bg-card/40 p-4 space-y-2">
          <div className="text-sm">Toplam silinecek satır: <strong>{preview.data.total}</strong></div>
          <ul className="text-sm">
            {Object.entries(preview.data.by_table).map(([t, n]) => (
              <li key={t}><code>{t}</code>: {n}</li>
            ))}
          </ul>
          <div className="text-xs text-muted-foreground">
            Politika: {Object.entries(preview.data.policy).map(([k, v]) => `${k}=${v}`).join(', ')}
          </div>
        </div>
      )}

      <Button onClick={() => setConfirming(true)} disabled={!preview.data || preview.data.total === 0}>
        Şimdi temizle
      </Button>

      {confirming && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-40 bg-black/60 grid place-items-center">
          <div className="bg-card border border-border rounded-lg p-6 max-w-md space-y-3">
            <h2 className="text-lg font-medium">Onay</h2>
            <p className="text-sm">
              <strong>{preview.data?.total}</strong> satır kalıcı olarak silinecek. Geri alınamaz.
            </p>
            <div className="flex gap-2 justify-end">
              <Button variant="ghost" onClick={() => setConfirming(false)}>Vazgeç</Button>
              <Button onClick={onRun} disabled={run.isPending}>
                {run.isPending ? 'Siliniyor…' : 'Evet, sil'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Run tests; expect 3 PASS**

```bash
cd frontend && npx vitest run src/routes/admin/RetentionPage.test.tsx
```

- [ ] **Step 6: Wire route + nav + type-check + lint (same pattern as U4)**

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/admin/RetentionPage.tsx \
        frontend/src/routes/admin/RetentionPage.test.tsx \
        frontend/src/api/queries/admin.ts \
        frontend/src/components/admin/adminNav.ts \
        frontend/src/{App.tsx,main.tsx} 2>/dev/null
git commit -m "feat(admin): add /admin/retention page (U6)

phase-5 D12: confirm-modal-gated UI over the existing
preview + run-now retention endpoints."
```

---

## Task W2.5.T5: DR1 — README scrypt → bcrypt

**Files:**
- Modify: `README.md` (lines containing "scrypt")

**Steps:**

- [ ] **Step 1: Confirm bcrypt is the actual library**

```bash
grep -n "bcrypt\|scrypt" /Users/barandincoguz/Desktop/deneme/requirements.txt \
                          /Users/barandincoguz/Desktop/deneme/backend/shared/auth.py
```
Expected: `bcrypt==4.2.0` in requirements; `import bcrypt` in auth.py. Confirms README is wrong.

- [ ] **Step 2: Find both lines in README**

```bash
grep -n "scrypt" /Users/barandincoguz/Desktop/deneme/README.md
```

- [ ] **Step 3: Edit both occurrences**

For each occurrence, replace "scrypt password hashing" → "bcrypt(rounds=12) password hashing" and the badge / inline mention accordingly.

- [ ] **Step 4: Confirm no remaining scrypt mentions**

```bash
grep -n "scrypt" /Users/barandincoguz/Desktop/deneme/README.md
```
Expected: 0 hits.

- [ ] **Step 5: Commit**

```bash
git add README.md && git commit -m "docs(readme): correct scrypt → bcrypt (DR1)

Code uses bcrypt(rounds=12); README claimed scrypt. phase-5 D12 DR1."
```

---

## Task W2.5.T6: DR2 — README lock 90s → 300s

**Files:**
- Modify: `README.md`

**Steps:**

- [ ] **Step 1: Confirm the real default**

```bash
grep -n "DEFAULT_LOCK_EXPIRES_SECONDS\|expires_seconds" /Users/barandincoguz/Desktop/deneme/backend/locks/service.py
```
Expected: `DEFAULT_LOCK_EXPIRES_SECONDS = 300`.

- [ ] **Step 2: Find all "90 s" / "90 sec" / "90-second" hits in README**

```bash
grep -nE "90[ -]?s(econd)?" /Users/barandincoguz/Desktop/deneme/README.md
```

- [ ] **Step 3: For each hit, change "90 s leased locks" / "90-second document locks" → "5 dakika (300 s) leased locks (configurable via `lock.expires_seconds` site setting)"**

(Match phrasing to the surrounding sentence; for the badges table just say `300 s`.)

- [ ] **Step 4: Verify no stale 90 hits remain**

```bash
grep -nE "90[ -]?s(econd)?" /Users/barandincoguz/Desktop/deneme/README.md
```
Expected: 0 hits (or only context-irrelevant hits).

- [ ] **Step 5: Commit**

```bash
git add README.md && git commit -m "docs(readme): correct lock TTL 90s → 300s default (DR2)

phase-5 D12 DR2: backend default is 300s, configurable via
lock.expires_seconds site setting. README claimed 90s in 2 places."
```

---

## Task W2.5.T7: DR3 — REQUIREMENTS.md MIRROR rows → Complete

**Files:**
- Modify: `.planning/REQUIREMENTS.md`

**Steps:**

- [ ] **Step 1: Find the MIRROR-01..10 rows**

```bash
grep -nE "MIRROR-0[1-9]|MIRROR-10" /Users/barandincoguz/Desktop/deneme/.planning/REQUIREMENTS.md
```

- [ ] **Step 2: Find the commit refs from `4-SUMMARY.md`**

```bash
grep -nE "MIRROR-0[1-9]|MIRROR-10" /Users/barandincoguz/Desktop/deneme/.planning/phases/04-neon-postgres-dual-write-mirror/4-SUMMARY.md | head -15
```

- [ ] **Step 3: Edit each row — set Status to `Complete` and add commit SHA**

For each MIRROR-XX row, change `Pending` → `Complete` and add the commit SHA in the Notes column (e.g., `Complete (1f33a53)`).

- [ ] **Step 4: Verify no Pending rows remain on MIRROR**

```bash
grep -E "MIRROR-0[1-9]|MIRROR-10" /Users/barandincoguz/Desktop/deneme/.planning/REQUIREMENTS.md | grep -i pending
```
Expected: 0 hits.

- [ ] **Step 5: Commit**

```bash
git add .planning/REQUIREMENTS.md && \
git commit -m "docs(planning): mark MIRROR-01..10 Complete with commit SHAs (DR3)

phase-5 D12 DR3: Phase 4 shipped all 10 MIRROR requirements
(commits 1f33a53..66f0986). REQUIREMENTS.md rows still said Pending."
```

---

## Task W2.5.T8: DC1 — Delete `frontend/src/lib/env.ts` if truly orphan

**Files:**
- Delete: `frontend/src/lib/env.ts`

**Steps:**

- [ ] **Step 1: Re-grep for any import (direct or indirect)**

```bash
grep -rn "from '@/lib/env'\|from '../lib/env'\|from './env'\|from \"@/lib/env\"" \
  /Users/barandincoguz/Desktop/deneme/frontend/src/ || echo "no-imports"
```
Expected: `no-imports`. If any hits, STOP — env.ts is in use and DC1 must be deferred.

- [ ] **Step 2: Inspect `env.ts` contents**

```bash
cat /Users/barandincoguz/Desktop/deneme/frontend/src/lib/env.ts
```

If it exports anything that any test file might use via test-only paths, search those too. If still no callers, proceed.

- [ ] **Step 3: Delete the file**

```bash
git rm /Users/barandincoguz/Desktop/deneme/frontend/src/lib/env.ts
```

- [ ] **Step 4: Type check + lint to confirm no fallout**

```bash
cd frontend && npx tsc --noEmit && npx eslint src
```
Expected: 0 errors. If any error mentions `env.ts`, revert the delete and STOP — DC1 was wrong.

- [ ] **Step 5: Full vitest run**

```bash
cd frontend && npx vitest run --reporter=basic | tail -5
```
Expected: same pass count as Wave 0 baseline.

- [ ] **Step 6: Commit**

```bash
git commit -m "chore(frontend): delete orphan lib/env.ts (DC1)

phase-5 D12 DC1: re-grep confirmed zero importers across src/.
Type-check + lint + tests stayed clean after delete."
```

---

## Task W2.5.T9: DC2 + DC3 — Migration v0007 drops orphan tables

**Files:**
- Create: `backend/migrations/v0007_drop_orphan_tables.py`
- Create: `backend/tests/test_v0007_drop_orphan_tables.py`

**Steps:**

- [ ] **Step 1: Verify both tables are empty in current data**

```bash
sqlite3 /Users/barandincoguz/Desktop/deneme/data/db/annotations.db \
  "SELECT 'user_badges', COUNT(*) FROM user_badges UNION ALL \
   SELECT 'user_quiz_answers', COUNT(*) FROM user_quiz_answers" 2>&1
```
Expected: both rows show 0 count. If non-zero, STOP and revisit DC2/DC3.

- [ ] **Step 2: Write failing test for the migration**

Create `backend/tests/test_v0007_drop_orphan_tables.py`:

```python
"""Tests for v0007 migration that drops orphan user_badges + user_quiz_answers."""
import pytest
import sqlite3

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    yield c
    c.close()


def test_v0007_drops_both_orphan_tables(conn):
    apply_migrations(conn, discover_migrations())
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "user_badges" not in tables
    assert "user_quiz_answers" not in tables


def test_v0007_refuses_to_drop_non_empty_user_badges(conn):
    """Safety: if user_badges has rows (someone wrote to it after v0001),
    the migration must abort rather than silently drop data."""
    # Apply through v0006 only
    migrations = discover_migrations()
    earlier = [m for m in migrations if m.version < 7]
    apply_migrations(conn, earlier)
    conn.execute(
        "INSERT INTO user_badges (user_id, badge_id, earned_at) "
        "VALUES (1, 'first_save', '2026-01-01T00:00:00Z')"
    )
    conn.commit()

    v7 = [m for m in migrations if m.version == 7]
    with pytest.raises(RuntimeError, match="user_badges.*not empty"):
        apply_migrations(conn, v7)


def test_v0007_refuses_to_drop_non_empty_user_quiz_answers(conn):
    migrations = discover_migrations()
    earlier = [m for m in migrations if m.version < 7]
    apply_migrations(conn, earlier)
    conn.execute(
        "INSERT INTO user_quiz_answers (user_id, question_id, choice, is_correct, answered_at) "
        "VALUES (1, 1, 'A', 1, '2026-01-01T00:00:00Z')"
    )
    conn.commit()

    v7 = [m for m in migrations if m.version == 7]
    with pytest.raises(RuntimeError, match="user_quiz_answers.*not empty"):
        apply_migrations(conn, v7)


def test_v0007_is_idempotent_when_tables_already_dropped(conn):
    """Re-running v0007 after tables are already gone must succeed."""
    apply_migrations(conn, discover_migrations())  # first run drops them
    apply_migrations(conn, discover_migrations())  # second run no-op
```

- [ ] **Step 3: Run; expect 4 FAIL (migration doesn't exist)**

```bash
pytest backend/tests/test_v0007_drop_orphan_tables.py -v
```
Expected: 4 FAIL.

- [ ] **Step 4: Create the migration**

Create `backend/migrations/v0007_drop_orphan_tables.py`:

```python
"""v0007 — drop the two orphan tables user_badges + user_quiz_answers.

Both tables were created in v0001 and replaced (denormalized into other
tables) during later development. They have remained schema-resident with
no readers or writers in the live codebase. This migration drops them.

Safety: each DROP is gated by an emptiness assertion. If either table is
non-empty (someone wrote to it out-of-band after the orphan classification
in 2026-05-23), the migration aborts with a clear RuntimeError so the
operator can investigate before data is lost.
"""
import sqlite3

ORPHAN_TABLES = ("user_badges", "user_quiz_answers")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _row_count(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()
    return int(row["c"])


def up(conn: sqlite3.Connection) -> None:
    for tbl in ORPHAN_TABLES:
        if not _table_exists(conn, tbl):
            continue  # already dropped — idempotent
        count = _row_count(conn, tbl)
        if count != 0:
            raise RuntimeError(
                f"v0007: refusing to drop {tbl} — it has {count} rows. "
                f"Investigate before dropping (this table was classified "
                f"as orphan on 2026-05-23 because no code reads or writes it)."
            )
        conn.execute(f"DROP TABLE {tbl}")
```

- [ ] **Step 5: Run tests; expect 4 PASS**

```bash
pytest backend/tests/test_v0007_drop_orphan_tables.py -v
```
Expected: 4 PASS.

- [ ] **Step 6: Run full backend test suite**

```bash
pytest backend/tests/ --tb=short -q | tail -5
```
Expected: total pass ≥ Wave 0 baseline + 4 new tests; 0 fail.

- [ ] **Step 7: Commit**

```bash
git add backend/migrations/v0007_drop_orphan_tables.py \
        backend/tests/test_v0007_drop_orphan_tables.py && \
git commit -m "feat(migrations): v0007 drop orphan tables (DC2 + DC3)

phase-5 D12: drop user_badges and user_quiz_answers, both
no-readers/no-writers since v0001 (denormalized into badges_earned
and training_attempts respectively). Each DROP guarded by an
emptiness assertion that raises RuntimeError if the table is
non-empty, so the migration is safe to deploy without manual
inspection of production data."
```

---

## Task W2.5.T10: Wave 2.5 exit gate + `audit/COMPLETION.md`

**Files:**
- Create: `audit/COMPLETION.md`

**Steps:**

- [ ] **Step 1: Generate the item → commit crosswalk**

```bash
cd /Users/barandincoguz/Desktop/deneme && git log --oneline -n 20
```
Identify the commits for U1, U4, U5, U6, DR1, DR2, DR3, DC1, DC2-3 (single migration commit covers both DC2 and DC3).

- [ ] **Step 2: Write `audit/COMPLETION.md`**

```markdown
# D12 Completion Sweep — Wave 2.5 → Commit Crosswalk

| Item | Severity | Commit | Description |
|------|----------|--------|-------------|
| U1 — Backup restore HTTP route | High | <sha> | POST /api/admin/backup/restore + WAL safety + audit log |
| U4 — Mirror health admin page | High | <sha> | /admin/mirror with 10s refresh + threshold colors |
| U5 — Backup admin page | High | <sha> | /admin/backup with run-now + 20-event history |
| U6 — Retention admin page | High | <sha> | /admin/retention with preview + confirm modal |
| DR1 — README scrypt → bcrypt | Doc | <sha> | bcrypt(rounds=12) accurate |
| DR2 — README 90s → 300s lock TTL | Doc | <sha> | 300s default, configurable |
| DR3 — REQUIREMENTS.md MIRROR rows Complete | Doc | <sha> | All 10 marked with commit SHAs |
| DC1 — Delete orphan lib/env.ts | Dead | <sha> | Confirmed zero importers |
| DC2 + DC3 — Migration v0007 drop orphan tables | Dead | <sha> | user_badges + user_quiz_answers with emptiness guard |
```

- [ ] **Step 3: Full backend + frontend test re-run**

```bash
pytest backend/tests/ --tb=short -q | tail -5
cd frontend && npx vitest run --reporter=basic | tail -5
```
Expected: both ≥ baseline + new tests, 0 fail.

- [ ] **Step 4: Type check + lint**

```bash
cd frontend && npx tsc --noEmit && npx eslint src
cd /Users/barandincoguz/Desktop/deneme && ruff check
```
Expected: 0 errors.

- [ ] **Step 5: Manual smoke (user task)**

```bash
cd /Users/barandincoguz/Desktop/deneme && \
  docker compose --env-file .env.production up -d --build && \
  sleep 10 && \
  curl -s http://127.0.0.1:8000/api/health
```

User opens `https://<host>/admin/mirror`, `/admin/backup`, `/admin/retention` and confirms each renders + the "Run now" buttons fire. STOP gate.

- [ ] **Step 6: Commit COMPLETION.md**

```bash
git add audit/COMPLETION.md && \
git commit -m "docs(phase-5): wave 2.5 completion crosswalk

All 10 D12 items (U1, U4, U5, U6, DR1-3, DC1, DC2-3) shipped
with commits."
```

---

# Wave 3 — Polish + Ops

## Task W3.T1: Write `runbooks/restore-drill.md`

**Files:**
- Create: `runbooks/restore-drill.md`

**Steps:**

- [ ] **Step 1: Draft the doc**

```markdown
# Restore Drill — Anotasyon Platform

⚠️ **STOP GATE 1** — This drill is **copy-only**. Never run it against
the live production DB. The first step copies the DB to a tmp location;
all subsequent commands operate on the copy.

⚠️ **STOP GATE 2** — Before running any DROP / DELETE / restore command,
re-verify you are pointed at the copy. Use `realpath` and `pwd` and
compare the path twice.

## Pre-flight

```bash
PROD_DB=/data/db/annotations.db
DRILL_DIR=$(mktemp -d -t restore-drill-XXXX)
cp "$PROD_DB" "$DRILL_DIR/annotations.db"
cd "$DRILL_DIR"
realpath annotations.db   # MUST be inside $DRILL_DIR, NOT /data/
```

## 1. Take a baseline snapshot from the copy

```bash
sqlite3 "$DRILL_DIR/annotations.db" ".dump" > "$DRILL_DIR/baseline.sql"
```

## 2. Push a "test" snapshot through the existing backup loop

(If the backup loop is configured for the host, trigger it. Otherwise,
manually invoke the `dump_all_tables_to_json` service against the copy
and write to `$DRILL_DIR/snapshot.json`.)

## 3. Restore via the new HTTP route (U1)

```bash
ADMIN_TOKEN_COOKIE="anotasyon_session=<dev-only-admin-session>"
curl -s -X POST http://127.0.0.1:8000/api/admin/backup/restore \
  -b "$ADMIN_TOKEN_COOKIE" \
  -F snapshot=@"$DRILL_DIR/snapshot.json"
```

## 4. Verify identity

```bash
sqlite3 "$DRILL_DIR/annotations.db" \
  "SELECT (SELECT COUNT(*) FROM users) AS u, \
          (SELECT COUNT(*) FROM annotations) AS a, \
          (SELECT COUNT(*) FROM drafts) AS d"
```
Compare counts to the baseline.

## 5. Tear down

```bash
rm -rf "$DRILL_DIR"
```

## Sign-off

| Date | Operator | Notes |
|------|----------|-------|
| YYYY-MM-DD | <name> | <observations> |
```

- [ ] **Step 2: Execute the drill on a copy and append a sign-off row**

```bash
# (Operator runs the drill once on a copy of annotations.db.)
```

- [ ] **Step 3: Commit**

```bash
mkdir -p runbooks
git add runbooks/restore-drill.md && \
git commit -m "docs(ops): add restore-drill runbook (phase-5 wave-3)

Copy-only drill with two STOP gates. Includes pre-flight,
snapshot, restore-via-route, identity check, teardown."
```

## Task W3.T2: Refresh `docs/deployment.md`

**Files:**
- Modify: `docs/deployment.md`

**Steps:**

- [ ] **Step 1: Read current state**

```bash
wc -l /Users/barandincoguz/Desktop/deneme/docs/deployment.md
```

- [ ] **Step 2: Add a section "Phase 5 admin surfaces"**

After the existing env-reference section, add:

```markdown
## Admin surfaces (Phase 5)

After login as an admin, the following pages are available under `/admin/`:

| Path | Purpose |
|------|---------|
| `/admin/mirror` | Neon mirror health: queue depth, dead-letter count, dispatcher state, last-delivered-at |
| `/admin/backup` | Manual backup trigger + last 20 backup events |
| `/admin/retention` | Retention preview + confirm-modal-gated run-now |
| `/admin/users`, `/admin/audit`, `/admin/settings`, `/admin/events`, `/admin/locks` | (existing) |

For backup restore via HTTP, see `runbooks/restore-drill.md`.
```

- [ ] **Step 3: Add a "Host appendix — Hetzner CPX11" section**

```markdown
## Appendix — Hetzner Cloud CPX11

1. Provision a CPX11 instance (Ubuntu 24.04). Reserve a floating IP if you want a stable address.
2. SSH in, install Docker (`curl -fsSL get.docker.com | sh`).
3. Install Caddy (`apt install caddy` or `docker run` it).
4. Caddyfile:

   ```
   your-domain.example.com {
     reverse_proxy 127.0.0.1:8000
     encode gzip
   }
   ```

5. `cd anotasyon && cp .env.example .env.production && $EDITOR .env.production`
6. Set `SESSION_SECRET` (openssl rand -hex 32), `BOOTSTRAP_ADMIN_USERNAME/PASSWORD`, `ALLOWED_ORIGINS=https://your-domain.example.com`.
7. `docker compose --env-file .env.production up -d`
8. `caddy reload` or restart the Caddy service.

Caddy's automatic Let's Encrypt provisioning will issue a cert within a minute. From here, the standard sections above apply.
```

- [ ] **Step 4: Add a "Host appendix — Oracle Cloud Always Free" section (ARM caveat)**

```markdown
## Appendix — Oracle Cloud Always Free (ARM)

Oracle's Always Free tier provides 4 OCPU + 24 GB ARM A1.Flex compute. ARM
images are required.

1. Provision an A1.Flex VM (Ubuntu 24.04 ARM).
2. Build the image on the VM itself (or push a multi-arch image from a
   GitHub Actions build matrix). Native `docker build` on the VM produces
   an ARM64 image automatically.
3. Steps 2-8 from the Hetzner appendix apply unchanged.

Caveats:
- Oracle's ingress firewall is restrictive by default; open ports 80 + 443 in
  the VCN Security List, not just `ufw`.
- A1.Flex shapes have been intermittently unavailable in popular regions; if
  capacity is denied at provision time, retry in another region.
```

- [ ] **Step 5: Commit**

```bash
git add docs/deployment.md && \
git commit -m "docs(ops): refresh deployment.md with admin surfaces + host appendices

phase-5 wave-3: add Phase 5 admin pages, Hetzner CPX11 walkthrough,
Oracle Always Free ARM walkthrough."
```

## Task W3.T3: Write `.github/workflows/ci.yml`

**Files:**
- Create: `.github/workflows/ci.yml`

**Steps:**

- [ ] **Step 1: Verify GH Actions runner expectations**

Check if existing dev tooling has notable version pins.

```bash
grep -E "python_version|python-version|python_requires" /Users/barandincoguz/Desktop/deneme/pyproject.toml
grep -E "engines" /Users/barandincoguz/Desktop/deneme/frontend/package.json
```

- [ ] **Step 2: Create the workflow**

```bash
mkdir -p .github/workflows
```

Write `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip
      - name: Install deps
        run: |
          pip install -r requirements.txt -r requirements-dev.txt
      - name: ruff
        run: ruff check
      - name: pytest
        run: pytest backend/tests/ -q

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - name: tsc
        run: npx tsc --noEmit
      - name: eslint
        run: npx eslint src
      - name: vitest
        run: npx vitest run

  docker:
    runs-on: ubuntu-latest
    needs: [backend, frontend]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Build image (smoke)
        run: docker build -t anotasyon-platform:ci .
```

- [ ] **Step 3: Open one validation PR**

Create a throwaway branch, push the workflow, open a PR. Watch the run.

```bash
git checkout -b phase-5/ci-validation
git add .github/workflows/ci.yml
git commit -m "ci: add PR-gate workflow (phase-5 wave-3)"
git push -u origin phase-5/ci-validation
gh pr create --title "Phase 5: CI workflow validation" \
  --body "Smoke run to confirm the PR-gate CI passes on main's current state."
```

- [ ] **Step 4: Wait for green; then merge**

```bash
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

## Task W3.T4: Visual polish (D11) — selective

Process the audit/UI.md APPLY items only. Each item follows the Wave 2 fix template (TDD + atomic commit).

---

# Wave 4 — Validation

## Task W4.T1: Smoke + load (D10)

**Files:**
- Create: `audit/SMOKE.md`

**Steps:**

- [ ] **Step 1: Build a fresh image and run it detached**

```bash
docker build -t anotasyon-platform:phase5-final . && \
docker run -d --rm --name a11n-final \
  --env-file .env.production \
  -p 8000:8000 anotasyon-platform:phase5-final && \
sleep 10 && \
curl -fs http://127.0.0.1:8000/api/health
```

- [ ] **Step 2: Run wrk against the hot endpoints**

```bash
wrk -t2 -c10 -d60s --latency http://127.0.0.1:8000/api/health > /tmp/wrk-health.txt
wrk -t2 -c10 -d60s --latency http://127.0.0.1:8000/api/feed?tab=new\&limit=50 > /tmp/wrk-feed.txt
```

- [ ] **Step 3: Run Playwright e2e against the same container**

```bash
cd frontend && \
  PLAYWRIGHT_BASE_URL=http://127.0.0.1:8000 npx playwright test
```
Expected: 9 / 9 pass.

- [ ] **Step 4: Stop the container**

```bash
docker stop a11n-final
```

- [ ] **Step 5: Write `audit/SMOKE.md`** with the wrk + e2e output summaries.

- [ ] **Step 6: Commit**

```bash
git add audit/SMOKE.md && \
git commit -m "docs(phase-5): wave 4 smoke + load + e2e results

wrk t2c10d60s on /api/health and /api/feed; Playwright e2e 9/9
against the built image."
```

## Task W4.T2: a11y (D5)

**Files:**
- Create: `audit/A11Y.md`

**Steps:**

- [ ] **Step 1: Add an axe-core sweep to Playwright e2e (one-shot, throwaway)**

Write a single Playwright spec that visits login, feed, AnnotateDoc, and Admin and runs `@axe-core/playwright` on each, collecting `critical` + `serious` violations.

- [ ] **Step 2: Run it against the built container**

```bash
cd frontend && \
  PLAYWRIGHT_BASE_URL=http://127.0.0.1:8000 \
  npx playwright test e2e/a11y.spec.ts
```

- [ ] **Step 3: Record results in `audit/A11Y.md`**

- [ ] **Step 4: For any new critical/serious violations, file as Phase 6 tasks (do not fix in Phase 5 unless trivial)**

- [ ] **Step 5: Manual keyboard tour of login → feed → AnnotateDoc → Admin, record tab-order + skip-link + focus-ring observations in `audit/A11Y.md`**

- [ ] **Step 6: Commit**

```bash
git add audit/A11Y.md && \
git commit -m "docs(phase-5): wave 4 a11y sweep results (axe + keyboard)"
```

## Task W4.T3: Operator-runbook dry-run

**Steps:**

- [ ] **Step 1: Provision a throwaway VM (Hetzner CPX11 or local VM)**

- [ ] **Step 2: Follow `docs/deployment.md` Hetzner appendix end-to-end**

- [ ] **Step 3: Confirm:**
  - First admin login works.
  - `/admin/mirror`, `/admin/backup`, `/admin/retention` render.
  - One invite can be seeded via the admin Users page.
  - Backup runs and a `backup_success` event appears.
  - Restore drill from `runbooks/restore-drill.md` succeeds on a copy.
  - Rollback drill: stop container, replace `data/db/annotations.db` with the prior snapshot, restart — works.

- [ ] **Step 4: Tear down the VM**

- [ ] **Step 5: Append the dry-run log to `audit/OPS.md`**

```bash
git add audit/OPS.md && \
git commit -m "docs(phase-5): wave 4 operator-runbook dry-run completed"
```

## Task W4.T4: Sign-off

**Files:**
- Modify: `.planning/STATE.md`
- Modify: `.planning/ROADMAP.md`

**Steps:**

- [ ] **Step 1: Verify all 32 gates from §5 of the spec are green**

Print each gate's evidence to the terminal or `audit/SIGNOFF.md`.

- [ ] **Step 2: Update `.planning/STATE.md`**

```markdown
## Current Phase

**Phase 5** — Pre-flight Hardening & Deploy Readiness — `Complete`.
All 32 success gates passed. See `audit/SIGNOFF.md` for the per-gate
evidence and `.planning/phases/05-preflight-hardening/` for artifacts.
```

- [ ] **Step 3: Update `.planning/ROADMAP.md`** — add Phase 5 row.

- [ ] **Step 4: Tag the release**

```bash
git tag -a phase-5 -m "Phase 5 — Pre-flight Hardening & Deploy Readiness"
git push --tags
```

- [ ] **Step 5: Final commit**

```bash
git add .planning/STATE.md .planning/ROADMAP.md audit/SIGNOFF.md && \
git commit -m "docs(phase-5): closeout — all 32 gates green, ready to deploy

Tagged phase-5. Host decision unblocked for the operator."
```

---

## Self-Review

The plan was reviewed against the spec before finalization. Coverage check:

- §1 Goal & Non-goals — covered by Wave 0 scope + Wave 2.5 D12 (the only "new code" allowed by the goal exception).
- §2 12 Dimensions — D1–D6 covered in Wave 1 dispatch (W1.T1); D7 in Wave 3 (W3.T1, W3.T2); D8 in Wave 3 (W3.T3); D9 in Wave 3 (W3.T2); D10 in Wave 4 (W4.T1); D11 in Wave 3 (W3.T4); D5 in Wave 4 (W4.T2); D12 fully in Wave 2.5 (T1–T10).
- §3 Phasing — wave structure preserved exactly.
- §4 Deliverables — every artifact in §4 maps to a task that creates it.
- §5 32 Gates — each gate is asserted by at least one task step (Wave 0 baseline records 1-6; Wave 2.5 tests + commits prove gates 27-32; Wave 3 covers 21-24; Wave 4 covers 14-20 + 25-26; Wave 4 T4 verifies 8-13 from the audit backlog).
- §6 Risks — R5 (restore drill safety) directly enforced by Wave 3 STOP gates in `runbooks/restore-drill.md`; R10 (v0007 safety) enforced by the emptiness-assertion tests in W2.5.T9.

No placeholders remain — every step contains either exact code, an exact command, or an exact diff intention.

Type consistency check: `useMirrorHealth`, `useBackupRunNow`, `useBackupHistory`, `useRetentionPreview`, `useRetentionRunNow` all defined in W2.5.T2-T4 and referenced consistently. `is_wal_busy` defined in W2.5.T1 Step 6 and referenced from the route in Step 7. `BackupRestoreResponse` defined Step 5, used Step 7.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-phase-5-preflight-hardening.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. Best fit because Wave 2.5 tasks are large and isolated from each other.

2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints.
