# Paket 11 — Admin Panel (Backend) Design

**Status:** Approved (brainstorming complete 2026-05-08)
**Predecessors:** Paket 1-10 complete (`paket-10-training-gate` tag at `ef6751b`)
**Successor:** Paket 16 (frontend SPA) consumes these endpoints

## Goal

Complete the backend admin surface so the future frontend admin panel (Paket 16) can manage users, training data, locks, audit/system event visibility, and per-user training reset. Backend-only paket: no UI work.

## Scope

Comparable in size to Paket 9-10 (~9 tasks, ~30 new tests). Backend endpoints, service layer, and one new schema migration. No new SSE event types — extend existing `lock_released` payload only.

## Non-Goals

- Frontend admin UI (Paket 16).
- CSV / bulk export (Paket 14).
- Backup admin endpoints (Paket 12).
- Retention / GDPR endpoints (Paket 13).
- Bulk user operations.

## Decisions Locked During Brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Quiz override storage | New table `training_quiz_overrides` via v0002 migration | Symmetric with `training_gold_doc_overrides`; per-question audit possible; clean migration risk-free (additive only) |
| Training reset semantics | Soft only (clear attempts + `has_passed_training=0`) | XP/badges/notifications retained; matches "give one more chance" admin intent |
| Force-release SSE | Reuse `lock_released` event with new `reason` field | Single handler in frontend; `reason ∈ {user_release, sweep_expired, admin_force}` |
| Audit-log enhancement | Full pagination + filters (`admin_id`, `action`, `date_from/to`) | Admin panel needs filter UI; mirrors `system_events` shape |
| Code organization | Distribute by domain | locks/, training/ get their admin endpoints; new `backend/admin/` only for cross-cutting (audit-log, system-events) |
| Routes module | `backend/admin/` is **new** for audit-log + system-events; existing admin routes in `users/routes.py` stay in place | Respect existing module boundaries; no churn |

## Architecture Overview

```
backend/
├── locks/
│   ├── routes.py             # + POST /api/locks/{id}/admin/force-release
│   └── service.py            # force_release() unchanged (Paket 5)
├── training/
│   ├── routes.py             # + reset, gold-doc CRUD, quiz CRUD
│   ├── service.py            # + reset_user_training, gold-doc/quiz upsert+tombstone
│   ├── gold_docs.py          # unchanged (resolver in service.py)
│   └── quiz_data.py          # + get_active_quiz_questions(db) hybrid resolver
├── admin/                    # NEW
│   ├── __init__.py
│   ├── routes.py             # GET /api/admin/audit-log, /api/admin/system-events
│   └── service.py            # list_system_events
├── users/
│   ├── routes.py             # /admin/audit-log endpoint upgraded in-place
│   └── service.py            # + list_admin_audit (pagination + filters)
├── shared/
│   └── sse/broker.py         # unchanged
└── migrations/
    └── v0002_admin_panel.sql # NEW — training_quiz_overrides table
```

All new endpoints require `Depends(require_admin)` (404 existence-hide).

## Endpoint Surface

### Locks (extend `backend/locks/routes.py`)

```
POST /api/locks/{document_id}/admin/force-release
  Body: {} (none)
  Auth: require_admin
  200: {ok: true}
  404: lock does not exist
  Side effects:
    - Calls existing locks.service.force_release(document_id, admin_user_id)
    - Broadcasts lock_released event with payload:
        {document_id, user_id, username, reason: 'admin_force'}
    - Writes admin_audit_log row: action='force_release_lock'
```

**Backwards-compatible SSE change:** The three existing `lock_released` publish sites (route-release, sweep-release in Paket 7, admin-force new) all gain a `reason` field:
- Route release → `reason: 'user_release'`
- Sweep release → `reason: 'sweep_expired'`
- Admin force → `reason: 'admin_force'`

Existing tests asserting on `lock_released` payload are updated alongside the publish sites in Task 4.

### Training (extend `backend/training/routes.py`)

```
POST /api/admin/training/users/{user_id}/reset
  Auth: require_admin
  200: {ok: true}
  404: user does not exist
  Side effects:
    - DELETE FROM training_attempts WHERE user_id = ?
    - UPDATE users SET has_passed_training = 0 WHERE id = ?
    - Inserts notification row (type='training_reset')
    - publish_to(user_id, 'notification', {...})
    - Writes admin_audit_log row: action='reset_training', target_user_id=user_id
  Idempotency: re-running on already-reset user is a no-op success
  Note: XP, ledger, badges retained. Soft reset only.

GET /api/admin/training/gold-docs
  Auth: require_admin
  200: {
    resolved: [<resolver output>],
    overrides: [<raw rows from training_gold_doc_overrides>]
  }

PUT /api/admin/training/gold-docs/{gold_id}
  Body: {content: str, expected_concepts: [...], min_concept_count: int}
  Auth: require_admin
  200: {ok: true}
  Behavior:
    - source='override' if gold_id ∈ baseline (gold_docs.GOLD_DOCS)
    - source='custom' otherwise
    - INSERT OR REPLACE; sets is_deleted=0, created_by_admin_id, updated_at
  Writes admin_audit_log: action='upsert_gold_doc', target_gold_id=gold_id

DELETE /api/admin/training/gold-docs/{gold_id}
  Auth: require_admin
  200: {ok: true}
  Behavior: soft-delete via tombstone (INSERT OR REPLACE with is_deleted=1, NULL fields)
  Writes admin_audit_log: action='delete_gold_doc', target_gold_id=gold_id

GET /api/admin/training/quiz
  Auth: require_admin
  200: {
    resolved: [<get_active_quiz_questions output>],
    overrides: [<raw rows from training_quiz_overrides>]
  }

PUT /api/admin/training/quiz/{question_id}
  Body: {text: str, choices: [str, ...], correct_choice_idx: int}
  Auth: require_admin
  question_id: matches baseline id ("q01"–"q08") to override, or new admin-supplied snake_case id to add custom
  Behavior: same upsert pattern as gold-docs
  Writes admin_audit_log: action='upsert_quiz_question'

DELETE /api/admin/training/quiz/{question_id}
  Auth: require_admin
  Behavior: soft-delete via tombstone
  Writes admin_audit_log: action='delete_quiz_question'
```

### Audit / System Events (new `backend/admin/routes.py`)

```
GET /api/admin/audit-log
  Query: limit (default 50, max 200), offset (default 0),
         admin_id (int, optional), action (str, optional),
         date_from (ISO date, optional), date_to (ISO date, optional)
  Auth: require_admin
  200: {items: [...], total: int, has_more: bool}

GET /api/admin/system-events
  Query: limit, offset, event_type, severity, date_from, date_to
  Auth: require_admin
  200: {items: [...], total: int, has_more: bool}
  Note: system_events table has no user_id column — events are system-scoped, not user-scoped.
  Severity filter accepts: 'info' | 'warn' | 'error'.
```

**Note:** Existing `GET /api/admin/audit-log` in `users/routes.py` (Paket 2) is upgraded in-place in Task 7. The route stays at the same path; the response shape changes from `{events: [...]}` (Paket 2) to `{items, total, has_more}`. No frontend depends on the old shape (frontend is Paket 16). Per-item field names are preserved (`admin_user_id`, `action_type`, `target_kind`, `target_id`, `metadata`, `created_at`); the only change is renaming the outer key (`events` → `items`) and adding `total` + `has_more`.

## Schema (v0002 migration)

```sql
-- backend/migrations/v0002_admin_panel.sql

CREATE TABLE training_quiz_overrides (
  question_id          TEXT    PRIMARY KEY,    -- matches baseline id ("q01", "q02", ...) or admin-supplied for custom
  is_deleted           INTEGER NOT NULL DEFAULT 0,
  text                 TEXT,                    -- NULL → fall back to baseline (matches QUIZ_QUESTIONS[i]["text"])
  choices_json         TEXT,                    -- NULL → fall back to baseline (JSON array of strings)
  correct_choice_idx   INTEGER,                 -- NULL → fall back to baseline
  source               TEXT    NOT NULL CHECK(source IN ('override','custom')),
  created_by_admin_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at           TIMESTAMP NOT NULL,
  updated_at           TIMESTAMP NOT NULL
);

CREATE INDEX idx_quiz_overrides_active
  ON training_quiz_overrides(question_id) WHERE is_deleted=0;
```

Single new table, additive, no v0001 changes. Symmetric with `training_gold_doc_overrides`.

## Service Layer Changes

| Module | Function | Notes |
|---|---|---|
| `training/quiz_data.py` | `get_active_quiz_questions(db) -> list[dict]` (NEW) | Hybrid resolver: code baseline + DB overrides. Same merge rules as `service.get_active_gold_docs`. |
| `training/service.py` | `reset_user_training(db, *, user_id, admin_id)` (NEW) | Soft reset orchestrator: DELETE attempts, UPDATE user, write notification, write audit. Per-step fault isolation pattern (Paket 9). |
| `training/service.py` | `upsert_gold_doc_override(db, *, gold_id, content, expected_concepts, min_concept_count, admin_id)` (NEW) | source = 'override' if in baseline else 'custom'. INSERT OR REPLACE. |
| `training/service.py` | `soft_delete_gold_doc(db, *, gold_id, admin_id)` (NEW) | Tombstone: is_deleted=1, NULL fields. |
| `training/service.py` | `upsert_quiz_override(...)`, `soft_delete_quiz_override(...)` (NEW) | Same pattern, `training_quiz_overrides` table. |
| `training/service.py` | `start_attempt`, `submit_quiz` | Migrate from `quiz_data.QUIZ_QUESTIONS` to `get_active_quiz_questions(db)` (Task 6). |
| `locks/service.py` | (no signature change) | Existing `force_release` reused. The 3 `lock_released` publish sites add `reason` field (Task 4). |
| `users/service.py` | `list_admin_audit(db, *, limit, offset, admin_id=None, action=None, date_from=None, date_to=None) -> dict` | Returns `{items, total, has_more}`. Replaces existing simple list. |
| `admin/service.py` (NEW) | `list_system_events(db, *, limit, offset, event_type=None, severity=None, date_from=None, date_to=None) -> dict` | Same pagination shape. system_events has no user_id; severity ∈ {info,warn,error}. |

**Audit row writing:** In Paket 5/8 each admin route writes its own audit row inline (no helper extracted). Continue this pattern for Paket 11. If `backend/shared/audit.py` already has a helper, reuse it; otherwise inline.

## Patterns Reused

- **Hybrid resolver** (Paket 10 gold-doc) → applied to quiz_data
- **Per-route audit row writing** (Paket 5 + 8)
- **Per-step fault isolation in orchestrators** (Paket 9 finalize, Paket 10 lifecycle)
- **Existence-hide via require_admin** (Paket 2 admin endpoints)
- **INSERT OR REPLACE for idempotent upsert** (Paket 5 annotations, Paket 10 gold-doc CLI)
- **Pagination response shape** `{items, total, has_more}` (new convention; reused for both audit-log and system-events)

## Auth Gating

All new endpoints: `Depends(require_admin)` → 404 (existence-hide) for non-admins. No changes to other auth deps.

## Error Handling

- **404:** target gold_id / question_id / user_id / lock not found.
- **400:** invalid pagination (limit > 200, negative offset), invalid date format, conflicting filter combos.
- **422:** payload validation (pydantic schemas).
- **Concurrent admin ops:** all writes are atomic single-row INSERT OR REPLACE / UPDATE / DELETE; last-write-wins is acceptable.
- **Self-modify:** admin can reset their own training, force-release their own lock, etc. — no special-case lockout. (Demote-self is already prevented in Paket 2; carry that pattern only where Paket 2 already does.)

## Testing Plan

Each task ships with failing tests first (TDD), then implementation, then green.

| Task | Test count (estimate) | Coverage |
|---|---|---|
| 1 | 0 (migration runner already tested) | Migration applies cleanly to fresh + existing DB |
| 2 | 4-5 | resolver: baseline-only, override merge, tombstone, custom append |
| 3 | 3-4 | reset happy, audit row, notification row + publish_to, idempotent re-reset, 404 unknown user |
| 4 | 4-5 | force-release happy, lock_released has reason='admin_force', audit row, 404 no-lock; SSE reason field on the other 2 publish sites |
| 5 | 5-6 | gold-doc list, upsert baseline (source=override), upsert new (source=custom), tombstone, audit each |
| 6 | 5-6 | quiz CRUD symmetric with gold-doc + start_attempt now uses resolver |
| 7 | 4-5 | audit-log pagination, each filter, combos, edge (offset > total) |
| 8 | 4-5 | system-events same as audit-log |
| 9 | 0 | Polish; full suite green; tag |

Total ≈ 30 new tests. Final suite ≈ 490+.

## Verification

After all 9 tasks land:
1. `.venv/bin/python -m pytest` — all green
2. Fresh DB: `DATA_DIR=/tmp/p11-fresh python -m backend.cli migrate` applies v0001 + v0002 cleanly
3. Manual curl walkthrough: admin user → POST every new endpoint → check `admin_audit_log` rows
4. Hybrid quiz resolver: upsert override → resolved set updates; tombstone → resolved set drops
5. `lock_released` SSE event carries `reason` for all 3 release modes
6. Tag `paket-11-admin-panel`

## Risks & Open Questions

- **None blocking.** All architectural decisions resolved during brainstorming.
- **Latent risk:** Paket 7 SSE tests may assert on `lock_released` payload shape — Task 4 includes test updates for the `reason` field. Surface area: `tests/test_locks_*` and `tests/test_sse_*`.
- **Latent risk:** Paket 2 `/admin/audit-log` test (`tests/test_admin_routes.py::test_admin_audit_log_endpoint_returns_actions`) asserts on `body["events"]`. Task 7 changes the response to `{items, total, has_more}` and updates that test in the same commit.
- **Latent risk:** If `quiz_data.QUIZ_QUESTIONS` is referenced directly in any existing test, the resolver migration in Task 6 must update those tests. Audit grep before Task 6.

## Out-of-Scope Notes for Future Pakets

- **Backup endpoints (Paket 12):** admin-triggered backup now / restore.
- **Retention (Paket 13):** GDPR delete user, configurable retention windows.
- **Export (Paket 14):** CSV/JSON export of annotations + audit log.
- **Frontend admin SPA (Paket 16):** consumes everything in this paket.
