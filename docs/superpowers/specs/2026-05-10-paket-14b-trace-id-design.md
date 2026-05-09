# Paket 14b — Trace-ID Co-Correlation (Mini-Pack)

**Status:** DESIGN APPROVED — ready for plan
**Date:** 2026-05-10
**Depends on:** Paket 1-14 (foundation, audit helpers, admin routes, backup/retention services)
**Numbering:** "14b" = mini-pack inserted after Paket 14, before Paket 15 (Dockerization). Does not consume the Paket 15 slot in the roadmap.

---

## 1. Problem

Two independent log streams exist, with no shared key:

- `admin_audit_log` — admin intent ("baran triggered manual backup")
- `system_events` — system side-effects ("backup_started", "backup_complete" / "backup_failed")

When an admin clicks "Backup Now" or "Run Retention Now", an audit row and one-or-more system_events rows are emitted. To correlate "this admin click → this outcome chain," operators today have only `created_at` timestamps. With concurrent admin actions or overlapping loops, timestamp-only correlation is fragile.

**Goal:** introduce a single `trace_id` column on both tables, populated for admin-triggered chains. JOIN/filter by `trace_id` returns a complete operation trail.

---

## 2. Scope (locked)

**IN scope:**
- Two tables receive `trace_id TEXT` column: `admin_audit_log`, `system_events`.
- Helper `gen_trace_id()` produces a 16-char lowercase hex token (uuid4-derived).
- Two log helpers (`log_admin_action`, `log_system_event`) accept optional `trace_id` keyword.
- All 14 admin call sites that invoke `log_admin_action` are updated to generate and pass `trace_id`.
- Two service functions called by both admin routes AND background loops (`run_backup`, `run_purge`) accept optional `trace_id` and propagate it to inner `log_system_event` calls.
- v0004 migration adds the columns + partial indexes.

**OUT of scope:**
- `behavioral_events`, `activity_events` — no trace_id column added.
- Background-loop tick-scoped trace_id — loops emit system_events with NULL trace_id by design (no admin actor to correlate to).
- Audit log viewer or system_events viewer UI changes — those land in Paket 16 (frontend).
- Filtering/search endpoints by trace_id — added when a real consumer needs it.
- Distributed tracing (OpenTelemetry, X-Trace-Id headers, etc.) — this is DB-internal correlation only.

---

## 3. Major Decisions

| Decision | Choice | Why |
|---|---|---|
| Column name | `trace_id` | Standard observability terminology; not `correlation_id` (less common in logs). |
| Token format | `uuid.uuid4().hex[:16]` (16 hex chars, 64 bits) | Collision resistance is overkill for any realistic admin-action volume; short, copy-paste friendly. No prefix (table context already disambiguates). |
| Plumbing | Explicit threading | Narrow scope (~14 call sites), no existing middleware in project, deterministic for tests, no implicit state. ContextVar would be premature. |
| Background loops | Pass nothing → NULL trace_id | Loop ticks have no admin originator. NULL is the correct null state, not a "filler" id. |
| Lifespan startup/shutdown | NULL trace_id | One-shot lifecycle events with no correlate. |
| Index strategy | `CREATE INDEX ... WHERE trace_id IS NOT NULL` (partial) | Most rows will be NULL (loop-originated + legacy). Partial index avoids indexing NULLs and stays compact. |
| Legacy rows | Stay NULL | No backfill — there's no derivable trace_id for past rows. |
| Required vs. optional | Optional everywhere | Helpers and service functions default `trace_id=None`. Backward-compatible — existing calls and tests don't break. |

---

## 4. Schema (v0004)

**File:** `backend/migrations/v0004_trace_id.py`

```sql
ALTER TABLE admin_audit_log ADD COLUMN trace_id TEXT;
ALTER TABLE system_events   ADD COLUMN trace_id TEXT;

CREATE INDEX idx_audit_trace
  ON admin_audit_log(trace_id)
  WHERE trace_id IS NOT NULL;

CREATE INDEX idx_sys_trace
  ON system_events(trace_id)
  WHERE trace_id IS NOT NULL;
```

**Notes:**
- `ALTER TABLE ADD COLUMN` is O(1) in SQLite — no table rewrite.
- Column count: `admin_audit_log` 7 → 8; `system_events` 6 → 7. Schema tablo sayısı sabit (23).
- Partial index supported since SQLite 3.8.0; project's WAL mode is fine.
- Migration is idempotent via `schema_migrations` version tracking (existing infra, no extra logic needed).

---

## 5. Helper API (`backend/shared/audit.py`)

**Add:**

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

**Modify:**

```python
def log_admin_action(
    conn, admin_user_id, action_type,
    *,
    target_kind=None, target_id=None, metadata=None,
    trace_id: Optional[str] = None,        # NEW
) -> None:
    conn.execute(
        """INSERT INTO admin_audit_log(
             admin_user_id, action_type, target_kind, target_id,
             metadata_json, created_at, trace_id
           ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (admin_user_id, action_type, target_kind, target_id,
         json.dumps(metadata) if metadata else None, _now(),
         trace_id),
    )


def log_system_event(
    conn, event_type, severity,
    *,
    message=None, extra=None,
    trace_id: Optional[str] = None,        # NEW
) -> None:
    if severity not in VALID_SEVERITIES:
        raise ValueError(...)
    conn.execute(
        """INSERT INTO system_events(
             event_type, severity, message, extra_json, created_at, trace_id
           ) VALUES (?, ?, ?, ?, ?, ?)""",
        (event_type, severity, message,
         json.dumps(extra) if extra else None, _now(),
         trace_id),
    )
```

`log_activity` and `log_behavioral` are **untouched** (out of scope per §2).

---

## 6. Plumbing — 14 admin call sites

### 6.1 Group A — trace_id has cross-table correlate (audit + system_events both written)

| # | Route | Service | Notes |
|---|---|---|---|
| 1 | `POST /api/admin/backup/run-now` (`backend/backup/routes.py:37`) | `run_backup()` | Multiple system_events: backup_started, backup_complete OR backup_failed, plus per-step events. All share trace_id. |
| 2 | `POST /api/admin/retention/run-now` (`backend/retention/routes.py:38`) | `run_purge()` | 1-2 system_events: retention_purge_started, retention_purge_complete (or failed). All share trace_id. |

### 6.2 Group B — audit-only (no system_events follow-up; trace_id for uniformity)

| # | Call site | Side-effect note |
|---|---|---|
| 3 | `backend/locks/routes.py:143` (force-release) | SSE broadcast only, no system_events |
| 4 | `backend/admin/routes.py:83` (settings update) | Direct DB write only |
| 5-9 | `backend/users/service.py:228, 250, 271, 285, 307` (5 user CRUD ops) | Direct DB writes |
| 10 | `backend/training/service.py:481` (training reset) | Direct DB writes |
| 11-14 | `backend/training/routes.py:137, 155, 192, 209` (gold-doc/quiz CRUD) | Direct DB writes |
| 15 | `backend/exports/routes.py:107` (export download) | StreamingResponse, no system_events |

Group B receives trace_id on the audit row (uniformity, future-proof). No correlate exists today; these rows simply stand alone in queries — same as before, with trace_id as a request fingerprint.

### 6.3 Service signature changes

```python
# backend/backup/service.py
def run_backup(conn, *, trace_id: Optional[str] = None) -> ...:
    audit.log_system_event(conn, "backup_started", "info",
                           extra={...}, trace_id=trace_id)
    # every log_system_event call inside this function gets trace_id=trace_id
    ...

# backend/retention/service.py
def run_purge(conn, *, trace_id: Optional[str] = None, manual: bool = False) -> ...:
    audit.log_system_event(conn, "retention_purge_started", "info",
                           extra={...}, trace_id=trace_id)
    ...
```

**Caller patterns:**

- `backup_loop._iteration` calls `run_backup(conn)` → trace_id=None → all system_events rows NULL.
- `POST /api/admin/backup/run-now` calls `run_backup(conn, trace_id=tid)` → all system_events rows tagged.
- Same pattern for `retention_loop` ↔ `POST /api/admin/retention/run-now`.

### 6.4 Admin route entry pattern (boilerplate)

```python
# Pattern (illustrative — actual signatures may differ slightly per route):
@router.post("/backup/run-now")
async def admin_backup_run_now(db = Depends(get_db), user = Depends(require_admin)):
    trace_id = audit.gen_trace_id()
    audit.log_admin_action(db, user.id, "manual_backup_run", trace_id=trace_id)
    db.commit()  # audit row durable before service runs (rollback on service failure
                 # rolls back system_events from the failure path, not the audit row)
    result = await asyncio.to_thread(run_backup, trace_id=trace_id)
    return {"trace_id": trace_id, **result}
```

The route returns `trace_id` in the response body so an admin client can echo it for support/debug. (Future audit-log viewer can deep-link by trace_id.)

---

## 7. Edge Cases

**Concurrent admin actions** — two admins clicking run-now simultaneously each get an independent trace_id (uuid4 collision probability ~2^-64). No lock or coordination needed.

**Admin-triggered service raises mid-execution** — partial writes to system_events all carry the same trace_id, so the audit row + partial trail are still joinable. ROLLBACK in the service uses BEGIN IMMEDIATE elsewhere; the audit log INSERT (committed before service call begins) is durable and not rolled back.

**Migration idempotency** — `schema_migrations` version table already gates re-application. v0004 runs once.

**Existing tests** — all current `log_admin_action` and `log_system_event` calls in tests pass `trace_id=None` implicitly (default arg) → row.trace_id IS NULL. No test breaks. New tests assert the populated path explicitly.

**Force-release without system_events** — group B audit row has trace_id set; system_events query by that trace_id returns 0 rows. That's the correct semantic ("admin force-released X; no system event was emitted").

---

## 8. Test Plan

### 8.1 New file: `tests/test_trace.py`
- `gen_trace_id()` returns 16-char lowercase hex
- 1000 calls produce 1000 distinct values (uniqueness sanity)

### 8.2 Augment `tests/test_audit.py`
- `log_admin_action(trace_id="...")` writes the value to `admin_audit_log.trace_id`
- `log_admin_action()` without trace_id leaves column NULL
- Same two cases for `log_system_event`

### 8.3 Augment `tests/test_migrations.py`
- After v0001..v0004 applied, `PRAGMA table_info(admin_audit_log)` includes `trace_id`
- Same for `system_events`
- Indexes `idx_audit_trace`, `idx_sys_trace` exist (`PRAGMA index_list`)
- Re-running migrations does not duplicate or fail (idempotency via existing infra)

### 8.4 Integration tests

- `tests/test_backup_routes.py` — admin run-now: response contains `trace_id`; SELECT from `admin_audit_log` and `system_events` JOIN by trace_id returns ≥1 audit row + ≥1 system_event row, all with the same trace_id.
- `tests/test_retention_routes.py` — same pattern for retention run-now.
- `tests/test_locks_admin_force_release.py` — audit row has populated trace_id; no system_events with that trace_id.
- `tests/test_backup_loop.py` (or equivalent) — after a loop iteration completes, `SELECT * FROM system_events WHERE event_type LIKE 'backup_%'` returns rows with **NULL** trace_id (loops do not generate one).

### 8.5 Smoke

- `cli.py migrate` re-runs cleanly on a previously-migrated DB.
- Full suite passes (646 → ~660 expected).

---

## 9. Implementation Estimate

| Element | Files | Notes |
|---|---|---|
| Migration | 1 new (`v0004_trace_id.py`) | ALTER TABLE ×2, CREATE INDEX ×2 |
| Helper | `backend/shared/audit.py` | +1 function (`gen_trace_id`), +1 param on 2 helpers |
| Service updates | `backend/backup/service.py`, `backend/retention/service.py` | +1 kwarg, propagate to inner calls |
| Route updates | 7 files (`admin/routes.py`, `users/service.py`, `training/routes.py`, `training/service.py`, `locks/routes.py`, `backup/routes.py`, `retention/routes.py`, `exports/routes.py`) | +1 line generate, pass through |
| Tests | 1 new + 3-4 augmented | ~12-15 new test cases |

Estimated: **5-7 atomic commits**, single-day implementation.

---

## 10. Out-of-Spec / Deferred

- **Trace-id deep-link from admin UI** — needs Paket 16 (frontend). For now, operator queries DB directly.
- **trace_id filter param** on `GET /api/admin/audit-log` and `GET /api/admin/system-events` — easy to add when an actual consumer exists; not adding speculatively.
- **Cross-process tracing** — single-process app today, no need.
- **Loop tick scoping** — explicit non-goal per §2. If `system_events` ever needs operational grouping for autonomous events (e.g., a long-running purge with multi-step trail), revisit.
