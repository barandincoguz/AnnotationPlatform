# Phase 4: Neon Postgres dual-write mirror - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Asynchronously mirror every committed SQLite write into a partner team's
Neon Postgres database, under the table-name prefix `baran_<table>`. The
mirror is **one-way only** (SQLite → Neon), **fail-silent** (a Neon
outage never blocks or rolls back the originating SQLite write), and
**zero added latency** on the request path (all Neon I/O runs on a
background coroutine). Coverage spans **all 24 project tables**,
including `documents_meta`.

Out of scope for this phase: bidirectional sync, Postgres becoming the
primary store, distributed transaction guarantees, schema-drift
auto-migration on Neon.

</domain>

<decisions>
## Implementation Decisions

### Capture mechanism
- **D-01:** Use the **outbox pattern**: SQLite trigger writes to a local
  `_outbox` table inside the same transaction as the originating
  INSERT/UPDATE/DELETE. This gives zero invasiveness to the existing
  service layer (services don't change) and atomic capture (no outbox
  row without a corresponding committed write).
- **D-02:** Triggers are generated programmatically (one generator
  script invokes a small Python helper at migration time). Coverage:
  23 in-scope project tables × 3 ops (INSERT/UPDATE/DELETE) = **69
  triggers**. `schema_migrations` is excluded as operational metadata
  (see D-06 family). Manually authoring is brittle.
- **D-03:** Trigger payload format: `json_object(...)` of all source
  columns plus operation type (`'INSERT' | 'UPDATE' | 'DELETE'`) and a
  stable primary-key string (`pk_value`). For composite-PK tables (e.g.
  `drafts (document_id, user_id)`) the PK is serialized as
  `f"{a}::{b}"`.

### Outbox schema
- **D-04:** Columns: `id INTEGER PRIMARY KEY AUTOINCREMENT, table_name
  TEXT NOT NULL, op TEXT NOT NULL, pk_value TEXT NOT NULL, payload_json
  TEXT NOT NULL, created_at TEXT NOT NULL, delivered_at TEXT, error
  TEXT, retry_count INTEGER NOT NULL DEFAULT 0`.
- **D-05:** Indexes: `(delivered_at)` for the drain query;
  `(created_at)` for archival sweeps.
- **D-06:** `_outbox` itself is NOT mirrored (no recursion).

### Dispatcher
- **D-07:** `backend/mirror/dispatcher.py` implements an async loop:
  `select WHERE delivered_at IS NULL AND retry_count < MAX_RETRIES
  ORDER BY id LIMIT N` → push to Neon → mark delivered.
- **D-08:** Started in FastAPI lifespan via
  `asyncio.create_task(run_dispatcher())`. Cancelled and drained on
  lifespan shutdown.
- **D-09:** Backoff schedule: empty queue → 5 s sleep. Items present →
  100 ms inter-batch. Error → exponential 1s, 2s, 4s, 8s, 16s, then
  dead-letter at retry 5 with a permanent `error` stamp.
- **D-10:** Batch size: 100 rows per drain pass. Tunable via env
  `NEON_MIRROR_BATCH_SIZE`.

### Postgres schema mirror
- **D-11:** Generate the `baran_*` DDL automatically from SQLite
  schema introspection. Mapping rules:
  - `INTEGER PRIMARY KEY AUTOINCREMENT` → `bigserial PRIMARY KEY`
  - `INTEGER` → `bigint`
  - `TEXT` → `text`
  - `REAL` → `double precision`
  - `TIMESTAMP` (TEXT in SQLite) → `text` (preserves ISO-8601 strings as-is — avoids tz parsing)
  - JSON-string columns (`*_json`) → `jsonb`
  - `CHECK` constraints copied verbatim
  - `REFERENCES <table>` → `REFERENCES baran_<table>`
  - Indexes: rebuild on the mirror tables with prefixed names.
- **D-12:** DDL emitted as `migrations/postgres/001-baran-init.sql`.
  Idempotent: every statement is `CREATE TABLE IF NOT EXISTS` etc.

### Failure semantics
- **D-13:** Any psycopg `OperationalError`, `InterfaceError`, or write
  failure → log + retry; SQLite is never aware. The originating
  request returns 200/204 as normal.
- **D-14:** On startup, the dispatcher tries to connect once. Failure
  is non-fatal — the app boots in "Neon unreachable" state. The
  dispatcher continues retrying connect in its loop.

### Backfill
- **D-15:** A one-shot script `scripts/neon_backfill.py` pushes the
  current SQLite state into the Neon `baran_*` tables before
  trigger-driven dual-write begins. Idempotent via `INSERT ... ON
  CONFLICT (pk) DO UPDATE` so re-runs are safe.
- **D-16:** Backfill order respects FK topology: parent tables before
  children (`users` → `documents_meta` → `annotations` → etc.).
- **D-17:** After backfill completes, the `_outbox` triggers are
  installed (in a migration step). This ordering prevents the
  dispatcher from racing the backfill on already-populated rows.

### Observability
- **D-18:** New admin route `GET /api/admin/mirror/health` returns
  outbox queue depth, oldest undelivered row's age, dead-letter count,
  last successful Neon write timestamp.
- **D-19:** Dispatcher writes a `system_events` row on dead-letter
  (severity `error`) and on cold-start success (severity `info`).

### Claude's Discretion
- Connection pool size and reconnect strategy (single pooled connection
  vs psycopg pool).
- Whether to use `execute_batch`, `executemany`, or `COPY FROM` for
  Neon writes (will pick based on Phase 2 perf testing).
- Exact `system_events` payload schema.
- Whether the trigger-generator Python helper lives in `scripts/` or
  `backend/migrations/helpers/` (test ergonomics decides).

</decisions>

<specifics>
## Specific Ideas

- "Outbox pattern" as it appears in *microservice* literature (Chris
  Richardson, Confluent CDC) — local event queue + async pump. This is
  the right reference, not Postgres logical replication.
- Inspired by `litestream` style for the *non-invasive* aspect, though
  litestream itself doesn't fit (it does SQLite→SQLite replication).
- The dispatcher should feel like a *vacuum process*: a background
  daemon that quietly catches up, gracefully degrades, and never
  alarms the user.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project structure & conventions
- `CLAUDE.md` — Project-wide behavioral guidelines (Think Before Coding,
  Simplicity First, Surgical Changes, Goal-Driven Execution). Phase 4
  changes must obey all four.
- `README.md` §"Architecture" — Mermaid diagram showing the existing
  SQLite + uvicorn + SSE shape. Phase 4 adds the Neon mirror branch.
- `docs/deployment.md` — Production env vars and lifespan startup
  sequence. Phase 4 adds two new env vars (`NEON_MIRROR_URL`,
  `NEON_MIRROR_BATCH_SIZE`) and one new lifespan task (dispatcher).

### Existing service-layer patterns
- `backend/annotations/service.py` — `_apply_save_inside_txn`,
  `set_complete` rich-return pattern (Phase 2). Phase 4 must not modify
  these functions; outbox capture happens via trigger.
- `backend/locks/service.py` — 90-second leased document locks.
  Triggers will capture `document_locks` mutations the same way as any
  other table.
- `backend/shared/audit.py::log_activity` — Existing audit pattern.
  Phase 4's `system_events` writes from the dispatcher follow this
  shape.

### Migration conventions
- `backend/migrations/` — Pure-SQL idempotent migration files. Phase 4
  adds at minimum two new files: one for `_outbox` + triggers, one
  documenting the Neon schema (the Postgres DDL lives outside this
  directory because it runs against a different database).

### Neon source data (already verified, May 18)
- `docs/neon-import.md` — Runbook describing the one-time read-only
  pull. Phase 4's connection / role / sslmode requirements mirror the
  practices captured there.
- `scripts/neon_import.py` — Reference for psycopg streaming + chunked
  writes. Phase 4's dispatcher will reuse this style but in the
  opposite direction.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/migrations/` — Idempotent SQL migration runner already in
  place; Phase 4 plugs in here for the `_outbox` schema.
- `backend/main.py` lifespan — already has the validation +
  migration-apply + first-admin-seed sequence; the dispatcher
  `asyncio.create_task` plugs in after migration apply.
- `psycopg[binary]` is already installed (added during the one-time
  Neon import).
- `data/db/annotations.db` already holds the 17923 documents that the
  backfill script will push to Neon `baran_documents_meta`.
- `.env.local` already holds the Neon connection string (`NEON_RO_URL`).
  Phase 4 introduces a NEW env name (`NEON_MIRROR_URL`) so the role
  used for the mirror is distinct from the read-only role used for the
  initial import.

### Established Patterns
- All multi-statement writes use `BEGIN IMMEDIATE` (see `set_complete`,
  `save_annotation`). Trigger fires AFTER each statement but rows are
  only visible post-COMMIT, so the outbox + main row commit together.
- Every audit/event log write goes through a centralized helper
  (`audit.log_activity`, `system_events`). Dispatcher dead-letter +
  cold-start events follow this pattern.
- Tests live under `tests/` (backend) and `frontend/src/.../*.test.tsx`
  (frontend). Phase 4 only touches backend; new tests live under
  `tests/test_mirror_*.py`.

### Integration Points
- `backend/main.py` — lifespan startup gets one new task. Lifespan
  shutdown gets one new graceful drain step.
- `backend/migrations/NNN-outbox-and-triggers.sql` — new migration
  file. Triggers are emitted by a script run at migration-apply time
  so they regenerate when the schema evolves.
- Every existing route stays untouched. No service-layer signatures
  change. **No frontend changes.**

</code_context>

<deferred>
## Deferred Ideas

- Per-table opt-in mirroring (currently all-or-nothing).
- Bidirectional sync — explicitly out of scope.
- Outbox archival / purge policy beyond a soft 7-day retention default.
- Postgres-side triggers or views to reshape `baran_*` data for the
  partner team.
- Replacing SQLite with Postgres entirely. The single-uvicorn-worker
  architecture is a load-bearing decision; revisiting it is a
  separate, multi-phase project.

</deferred>

---

*Phase: 04-neon-postgres-dual-write-mirror*
*Context gathered: 2026-05-18*
