# Paket 13 — Retention Purge Design

**Status**: LOCKED (brainstormed 2026-05-09, approved by user)
**Depends on**: Paket 12 (backup/restore — same lifespan-task pattern, same audit/system_events tables)
**Estimated size**: 7-8 tasks, ~1500-1800 LOC, +21 tests (574 → 595)

---

## 1. Scope

Paket 13 implements **time-based retention purge**: a daily background job that hard-deletes rows older than a configurable per-table window from a fixed set of high-churn tables. Manual trigger and dry-run preview endpoints are exposed to admins.

### Locked decisions (from brainstorm)

| # | Decision | Reason |
|---|----------|--------|
| D1 | **Scope = retention only**. No GDPR user-delete feature. | `disable_user()` already exists (`backend/users/service.py:256`); `get_user_by_session` enforces `is_active=1`, so disabled users get implicit 401 on next request. No additional erasure feature needed for this internal bursiyer platform. |
| D2 | **Hard purge** (DELETE), not archival to archive tables. | Long-term recovery comes from Paket 12 backups (144 snapshots @ 10min cadence ≈ 24h horizon, plus indefinite git history). Archive tables would double schema size for no marginal benefit at our 30-user scale. |
| D3 | **Trigger = scheduled (24h) + admin manual**. | `lifespan` task mirrors `backend/backup/loop.py`. Manual trigger needed for testing and emergency runs. |
| D4 | **Dry-run preview endpoint** (`GET /api/admin/retention/preview`). | Lets admin see "this would delete N rows" before clicking Run-Now. Cheap (~20 LOC, COUNT-only queries). |
| D5 | **No VACUUM**. SQLite reuses freed pages; disk reclaim is operator-manual via future CLI subcommand if ever needed. | At 30 users + 18K docs the DB stays well under 1GB; bloat is not material. VACUUM locks the DB and risks incident. |
| D6 | **Hard-coded `PURGE_POLICY` list in code, override via `site_settings`**. | Resolver pattern reused from Paket 10 (training_quiz_overrides): `code_default → DB override`. Operators tune via Settings UI; no migration needed when adjusting retention windows. |
| D7 | **Single transaction, all-or-nothing semantics**. | If table 5/7 fails mid-cycle, rollback so DB stays coherent. Per-table fault isolation considered and rejected. |
| D8 | **No SSE broadcast**. Purge is silent. | Bursiyers don't need to see "1247 rows purged"; admins query system_events. |
| D9 | **No new tables** (uses existing `site_settings`, `system_events`, `admin_audit_log`). | Migration v0003 inserts 7 default config rows via INSERT OR IGNORE. Idempotent across re-runs and post-restore. |

### Non-goals (will NOT be built in Paket 13)

- ❌ GDPR-compliant user erasure (P14+ if ever required by stakeholder)
- ❌ Archive tables (`archive_behavioral_events` etc.)
- ❌ Automated VACUUM
- ❌ Runtime-configurable WHERE clause per table (PURGE_POLICY is code-only)
- ❌ Purging `annotations`, `annotation_versions`, `annotation_references`, `documents_meta`, `users`, `gamification_*`, `training_*`, `invite_codes`, `site_settings`, `admin_audit_log`, `badges_earned` (forever)
- ❌ Frontend UI for retention configuration (just adds keys to existing Settings table; UI work comes in Paket 16)
- ❌ Per-cycle SSE notifications

---

## 2. Architecture

### Module layout

```
backend/retention/
├── __init__.py                # empty package marker
├── service.py                 # core: PURGE_POLICY, compute_cutoffs, run_purge, preview_purge
├── loop.py                    # async lifespan task — mirrors backend/backup/loop.py
├── routes.py                  # POST /run-now, GET /preview
└── models.py                  # Pydantic: PreviewResponse, RunNowResponse

backend/main.py                # +3 lines: import + start/stop in lifespan + include_router
backend/migrations/v0003_retention_settings.sql  # 7 default config rows
```

### Lifespan integration (added to `backend/main.py`)

Mirrors the existing `backup_loop` / `locks_sweep` pattern (inline try/except on each task await — there is no shared `_swallow` helper):

```python
# inside lifespan(), after existing starts:
sweep_task     = locks_sweep.start(interval_seconds=60)
backup_task    = backup_loop.start()
retention_task = retention_loop.start()                   # NEW
yield

locks_sweep.stop()
try: await sweep_task
except Exception: pass

backup_loop.stop()
try: await backup_task
except Exception: pass

retention_loop.stop()                                     # NEW
try: await retention_task                                 # NEW
except Exception: pass                                    # NEW

# at module scope, after existing include_router calls:
app.include_router(retention_router)                      # NEW
```

### Loop pattern (canonical reference: `backend/backup/loop.py`)

```python
# backend/retention/loop.py
async def retention_loop():
    while True:
        try:
            interval = _read_interval()              # site_settings live-read
            await asyncio.sleep(interval)            # sleep-first ordering
            await asyncio.to_thread(run_purge_once)
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("retention cycle failed")  # never kill the loop
```

`run_purge_once` opens its own short-lived sqlite3 connection (same pattern as `sweep_once_and_publish`).

---

## 3. Retention Policy

### Code-baseline (`backend/retention/service.py`)

```python
@dataclass(frozen=True)
class PurgePolicyEntry:
    table: str
    cutoff_column: str            # column to compare against cutoff
    default_days: int             # used if site_settings has no override
    extra_where: Optional[str]    # additional condition (e.g. "is_read=1")

PURGE_POLICY: list[PurgePolicyEntry] = [
    PurgePolicyEntry("behavioral_events", "created_at", 30,  None),
    PurgePolicyEntry("activity_events",   "created_at", 90,  None),
    PurgePolicyEntry("system_events",     "created_at", 180, None),
    PurgePolicyEntry("user_sessions",     "ended_at",   30,  "ended_at IS NOT NULL"),
    PurgePolicyEntry("notifications",     "created_at", 30,  "is_read=1"),
    PurgePolicyEntry("drafts",            "updated_at", 14,  None),
]
```

**Why these 6**:
- **behavioral_events**: ~10-50 rows/user/day (speed/char-limit warnings). 30 users × 30 rows × 30 days = 27K cap. Pure debug telemetry, no long-term value.
- **activity_events**: feed activity, used by `/api/feed?tab=`. 90 days covers "recently active" semantics.
- **system_events**: ops log. 180 days covers any reasonable post-mortem window.
- **user_sessions** (ended): closed sessions are dead state, useful only for short-term forensics.
- **notifications** (read): unread stays forever; reading == acknowledged.
- **drafts**: abandoned drafts after 14 days of no update — user lost interest or moved on.

**Tables explicitly NOT in PURGE_POLICY** (forever-keep):
- annotations, annotation_versions, annotation_references — work product
- documents_meta, document_kanun_refs, document_bkk_refs — corpus
- users — FK target, audit anchor
- admin_audit_log — compliance trail
- gamification_state, gamification_ledger — XP history (streaks need lookback)
- badges_earned — milestone record
- training_attempts, training_gold_doc_overrides, training_quiz_overrides — proof of training
- site_settings, invite_codes — config / referans
- document_locks — already auto-purged by lock_sweep
- schema_migrations — system metadata

### DB override (resolver pattern from Paket 10)

```python
def compute_cutoffs(db) -> dict[str, datetime]:
    """For each PURGE_POLICY entry, read site_settings override
    (key = 'retention.<table>.days') if present, else default_days.
    Return {table: cutoff_iso} where cutoff = now() - days(N).

    days=0 → table is excluded entirely (kill switch). Operators can
    set this when they panic and want purge to stop touching a table
    without redeploying code.
    days<0 → ValueError raised at settings-write time, not here.
    """
```

### Settings keys (v0003 migration)

```sql
INSERT OR IGNORE INTO site_settings (key, value, updated_at) VALUES
  ('retention.cycle_interval_seconds', '86400',  datetime('now')),  -- 24h
  ('retention.behavioral_events.days', '30',     datetime('now')),
  ('retention.activity_events.days',   '90',     datetime('now')),
  ('retention.system_events.days',     '180',    datetime('now')),
  ('retention.user_sessions.days',     '30',     datetime('now')),
  ('retention.notifications.days',     '30',     datetime('now')),
  ('retention.drafts.days',            '14',     datetime('now'));
```

`INSERT OR IGNORE` so reapplying migrations after a restore doesn't overwrite operator-tuned values. (Pattern shared with bootstrap_admin idempotency from Paket 12 polish.)

---

## 4. Endpoint Surface

### `POST /api/admin/retention/run-now`

**Auth**: `require_admin`
**Body**: `{}` (empty; reserved for future filters like "only this table")
**Response 200**:
```json
{
  "ok": true,
  "purged": {
    "behavioral_events": 1247,
    "activity_events": 89,
    "system_events": 0,
    "user_sessions": 3,
    "notifications": 12,
    "drafts": 5
  },
  "total": 1356
}
```
**Response 500** (any table-purge raised):
```json
{ "detail": { "error": "retention_failed", "message": "<scrubbed>" } }
```
**Side effects**:
- `system_events` row: `event_type='retention_success'` (or `retention_failed` on error) with `extra_json={"purged": {...}}` or `{"step": "purge", "error": "..."}`.
- `admin_audit_log` row: `action_type='retention_run_now'`, `target_kind='retention'`, `target_id=NULL`, `metadata_json={"total": 1356, "by_table": {...}}`.

### `GET /api/admin/retention/preview`

**Auth**: `require_admin`
**Response 200**:
```json
{
  "rows_to_purge": {
    "behavioral_events": 1247,
    "activity_events": 89,
    "system_events": 0,
    "user_sessions": 3,
    "notifications": 12,
    "drafts": 5
  },
  "total": 1356,
  "policy": [
    {"table": "behavioral_events", "days": 30,  "cutoff_iso": "2026-04-09T00:00:00+00:00"},
    {"table": "activity_events",   "days": 90,  "cutoff_iso": "2026-02-08T00:00:00+00:00"},
    {"table": "system_events",     "days": 180, "cutoff_iso": "2025-11-10T00:00:00+00:00"},
    {"table": "user_sessions",     "days": 30,  "cutoff_iso": "2026-04-09T00:00:00+00:00"},
    {"table": "notifications",     "days": 30,  "cutoff_iso": "2026-04-09T00:00:00+00:00"},
    {"table": "drafts",            "days": 14,  "cutoff_iso": "2026-04-25T00:00:00+00:00"}
  ]
}
```
**Side effects**: NONE. Pure read.

---

## 5. Data Flow

### `run_purge` (single cycle, all-or-nothing)

```
┌─────────────────────────────────────────────────────────────┐
│ caller (loop iter or POST /run-now)                         │
│   ↓                                                          │
│ compute_cutoffs(db)                                          │
│   reads site_settings retention.<table>.days for each entry  │
│   returns {table: cutoff_datetime}                           │
│   ↓                                                          │
│ db.execute("BEGIN IMMEDIATE")                                │
│   ↓                                                          │
│ for each PurgePolicyEntry:                                   │
│   if cutoff_days == 0: skip (kill switch)                    │
│   sql = f"DELETE FROM {entry.table}                          │
│           WHERE {entry.cutoff_column} < ?                    │
│           {AND extra_where if any}"                          │
│   cursor = db.execute(sql, (cutoff_iso,))                    │
│   purged[table] = cursor.rowcount                            │
│   ↓                                                          │
│ on any exception: ROLLBACK + system_events('retention_       │
│                   failed', extra={step,error}) + raise       │
│ on success:        COMMIT  + system_events('retention_       │
│                   success', extra={purged})                  │
│   ↓                                                          │
│ return {ok, purged, total}                                   │
└─────────────────────────────────────────────────────────────┘
```

### `preview_purge` (dry run)

Same `compute_cutoffs` step, but instead of `DELETE` runs `SELECT COUNT(*)` per table inside a `BEGIN DEFERRED` transaction (read-only). No commit needed. Returns counts + policy snapshot.

### Loop cycle (sleep-first)

```
loop start
  ↓
while True:
  await sleep(_read_interval())          # 86400 default; live-tunable
  await asyncio.to_thread(run_purge_once) # blocking SQLite isolated from event loop
  except: log.exception, continue        # never kill loop
```

`run_purge_once` opens its own connection. Same idempotent pattern as `sweep_once_and_publish` and `backup_once`.

---

## 6. Error Handling

| Scenario | Behavior |
|----------|----------|
| One table's DELETE raises (e.g. SQLITE_BUSY past timeout) | Whole transaction rolled back. `system_events('retention_failed', extra={step: 'purge', error: <str>, table: <name>})`. `run-now` → HTTP 500 with `{detail: {error, message}}`. Loop logs and continues to next cycle. |
| `BEGIN IMMEDIATE` blocked > 60s (default `busy_timeout`) | `sqlite3.OperationalError` → same fail path. |
| Lifespan task gets `CancelledError` mid-DELETE | Transaction is per-cycle and `to_thread`-wrapped, so cancellation aborts the await but the worker thread completes (or rolls back) gracefully. Next shutdown beat awaits the task. |
| `retention.<table>.days = 0` | That table is silently excluded from this cycle. `purged[table]` = 0. Operator kill-switch. |
| `retention.<table>.days < 0` | Settings update endpoint validates and rejects with 422 BEFORE write. Resolver never sees negative values. |
| Settings row missing entirely (e.g. fresh DB before v0003 migration) | Falls back to `PurgePolicyEntry.default_days`. Migration is mandatory part of paket setup. |
| Settings value not parseable as int | `compute_cutoffs` raises ValueError → cycle fails → `retention_failed` event with explanation. Loop continues. Operator sees in admin Settings UI / system_events viewer. |

### Not used (deliberately)

- Per-table fault isolation (try/except per entry inside the transaction): rejected because partial purge leaves DB in inconsistent state where `system_events` says "X failed" but `behavioral_events` still got truncated. Atomicity > availability for this batch.
- Retry on busy: 60s `busy_timeout` is the only retry layer. Beyond that the cycle gives up and the loop runs again in 24h.

---

## 7. Schema — Migration v0003

### File: `backend/migrations/v0003_retention_settings.sql`

```sql
-- v0003: Insert default retention policy values into site_settings.
-- INSERT OR IGNORE so re-applying after a restore preserves operator-tuned
-- values written between v0003 application and the restore point.

INSERT OR IGNORE INTO site_settings (key, value, updated_at) VALUES
  ('retention.cycle_interval_seconds', '86400',  datetime('now')),
  ('retention.behavioral_events.days', '30',     datetime('now')),
  ('retention.activity_events.days',   '90',     datetime('now')),
  ('retention.system_events.days',     '180',    datetime('now')),
  ('retention.user_sessions.days',     '30',     datetime('now')),
  ('retention.notifications.days',     '30',     datetime('now')),
  ('retention.drafts.days',            '14',     datetime('now'));
```

**No new tables**. Schema_migrations gets v0003 row recorded by the runner.

---

## 8. Tests — TDD Coverage Matrix

```
tests/test_retention_service.py                     # core service unit tests
  ├── test_compute_cutoffs_uses_code_default_when_no_db_override
  ├── test_compute_cutoffs_prefers_db_override
  ├── test_compute_cutoffs_raises_on_negative_days_in_db
  ├── test_compute_cutoffs_treats_zero_days_as_kill_switch
  ├── test_purge_deletes_rows_older_than_cutoff
  ├── test_purge_keeps_rows_younger_than_cutoff
  ├── test_purge_respects_extra_where_clause              # notifications.is_read=1 only
  ├── test_purge_skips_table_when_cutoff_days_is_zero
  ├── test_run_purge_atomic_rollback_on_mid_cycle_failure
  ├── test_run_purge_writes_retention_success_event_with_counts
  └── test_run_purge_writes_retention_failed_event_with_step

tests/test_retention_preview.py                     # preview_purge unit tests
  ├── test_preview_returns_count_per_table_without_deleting
  ├── test_preview_includes_policy_snapshot
  └── test_preview_uses_db_override_in_policy

tests/test_retention_loop.py                        # async loop tests
  ├── test_loop_calls_run_purge_after_sleep
  ├── test_loop_cancellation_is_graceful
  └── test_loop_swallows_cycle_exception_and_continues   # asyncio.Event pattern

tests/test_retention_admin_routes.py                # HTTP layer
  ├── test_run_now_admin_only
  ├── test_run_now_returns_purged_counts
  ├── test_run_now_writes_admin_audit_log_row
  ├── test_run_now_returns_500_on_internal_failure
  ├── test_preview_admin_only
  └── test_preview_returns_dry_run_counts

tests/test_retention_lifespan.py                    # mirrors test_backup_lifespan
  └── test_retention_loop_starts_and_stops_with_app

tests/test_v0003_settings_migration.py              # migration test
  ├── test_v0003_inserts_default_retention_keys
  └── test_v0003_is_idempotent_via_insert_or_ignore   # re-apply preserves operator overrides
```

**Total**: 21 new tests. Suite size **574 → 595**.

### Reference data per test

Each test creates rows with explicit `created_at` timestamps (e.g. `datetime('now', '-31 days')` for "older than 30-day cutoff"). Uses `freezegun`-style `unittest.mock.patch('backend.retention.service._now')` only if needed for cutoff tests — most can use SQL `datetime()` directly.

---

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Operator sets `retention.system_events.days=1` and loses critical backup logs from yesterday | Medium | Medium | Settings UI tooltip recommends `>=7 days`. No hard floor in code (operator autonomy). Backup repo retains 144 snapshots so recoverable from latest.json. |
| 24h-cadence cycle conflicts with backup_loop's 10-min cycle | Low | Low | Both use `BEGIN IMMEDIATE` with default 60s `busy_timeout`. Worst case: one cycle slips, retries automatically next iteration. |
| Restore from backup overrides operator-tuned settings back to migration defaults | Low | Medium | INSERT OR IGNORE in v0003 + restore replays settings table from snapshot, so operator overrides persist across restore. Verified via test_restore_clears_existing_rows_first. |
| Bug in `compute_cutoffs` causes 0 rows to be purged silently for months | Low | High | `system_events('retention_success', extra={purged:{}})` shows zero counts; admin Settings page can show "last cycle: 0 rows" red flag. Future Paket 16 UI surfaces this. |
| Single transaction holding lock too long (large drafts table after years) | Low | Low | At our scale this is < 1s. SQLite WAL means concurrent readers continue. Future scaling concern, not 30-user concern. |

---

## 10. Open Questions

None. Brainstorming converged on every decision.

---

## 11. Estimated Sub-Tasks (preliminary; finalized in PLAN.md)

1. **T1**: Migration v0003 + service module skeleton + `compute_cutoffs`
2. **T2**: `run_purge` orchestrator + transaction + system_events
3. **T3**: `preview_purge` (dry-run COUNT)
4. **T4**: `loop.py` async lifespan task (mirrors backup/loop)
5. **T5**: `routes.py` POST /run-now + GET /preview + admin_audit_log
6. **T6**: Lifespan integration in main.py (start/stop/router mount)
7. **T7**: Lifespan integration test + end-to-end smoke
8. **T8** (review polish): catch-up after spec compliance + code quality reviewers

Total: 7 implementation tasks + 1 polish task. Same shape as Paket 12 (which had 8+1).
