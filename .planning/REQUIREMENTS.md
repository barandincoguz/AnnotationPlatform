# Requirements: Annotation Platform

**Defined:** 2026-05-18 (retroactive for Phase 1-3; v1 for Phase 4)
**Core Value:** Annotate Turkish tax rulings with structured law references; observe progress from a partner team's Neon Postgres database.

## v1 Requirements (active)

### Phase 4 — Neon Dual-Write Mirror

- [x] **MIRROR-01**: Every SQLite INSERT/UPDATE/DELETE on a project table appends a row to a local outbox queue inside the same transaction.
- [x] **MIRROR-02**: A background dispatcher coroutine drains outbox rows and applies them to the partner Neon Postgres database under `baran_<table_name>` table names.
- [x] **MIRROR-03**: Partner Neon database has a mirror table for every one of the 24 project tables; types, primary keys, foreign keys, indexes, and check constraints all map faithfully (SQLite → Postgres equivalents).
- [x] **MIRROR-04**: Neon outage (any psycopg error) MUST NOT fail or roll back the originating SQLite write. The dispatcher logs the failure, increments the row's retry count, and re-tries with backoff.
- [x] **MIRROR-05**: Dispatcher achieves at-least-once delivery — every committed outbox row eventually reaches Neon (or lands in a dead-letter state after max retries with a permanent error stamp).
- [x] **MIRROR-06**: A one-time backfill script populates the `baran_*` tables from the current SQLite state (17923 documents + denorms) before live dual-write begins.
- [x] **MIRROR-07**: Request latency on existing endpoints does not increase by more than 5 ms p95 (background queue must not block the request path).
- [x] **MIRROR-08**: Existing tests (872 backend + 511 frontend) stay green. New tests cover the outbox lifecycle (write → drain → mark delivered), retry on Neon failure, and schema-converter unit tests.
- [x] **MIRROR-09**: A small admin / health surface exposes outbox queue depth + last-delivered-at so operators can spot a stuck dispatcher.
- [x] **MIRROR-10**: All Neon credentials read from environment (never committed). Connection failures during boot are non-fatal — the app comes up with the dispatcher in a degraded "Neon unreachable" state.

## v2 Requirements (deferred)

| ID | Description | Reason for deferral |
|----|-------------|---------------------|
| MIRROR-V2-01 | Bidirectional sync (Neon → SQLite) | Out of scope; requires conflict-resolution semantics |
| MIRROR-V2-02 | Outbox purge / archival policy beyond 7 days | Tackle once production volume is known |
| MIRROR-V2-03 | Per-table opt-in for mirroring (currently all-or-nothing) | YAGNI for now |

## Out of Scope

| Feature | Reason |
|---------|--------|
| Postgres becoming primary | SQLite + single-worker is a load-bearing architectural choice (single source of truth, BEGIN IMMEDIATE semantics) |
| 2-phase commit / XA | Adds operational complexity disproportionate to the audit-mirror use case |
| Schema-drift auto-migration on Neon | Phase 4 ships a one-shot DDL; future SQLite migrations need a manual Neon counterpart |
| Mirror coverage for `_outbox` itself | Outbox is a local-only operational table |

## Traceability

| Requirement | Phase | Status | Notes |
|-------------|-------|--------|-------|
| MIRROR-01 | Phase 4 | Complete | outbox schema `1f33a53` |
| MIRROR-02 | Phase 4 | Complete | dispatcher core `d8be3c1`, lifespan wire `e5d6d8f` |
| MIRROR-03 | Phase 4 | Complete | baran-init.sql `1c1e005`, triggers `e358f36` |
| MIRROR-04 | Phase 4 | Complete | retry + backoff `b4cc384` |
| MIRROR-05 | Phase 4 | Complete | dead-letter `b4cc384` (Phase 5 BE-10 adds operator requeue) |
| MIRROR-06 | Phase 4 | Complete | backfill script `25d271b` |
| MIRROR-07 | Phase 4 | Complete | latency guard test `3c765f4`, wrk smoke `9fb4a17` |
| MIRROR-08 | Phase 4 | Complete | e2e + soft latency guard `3c765f4` |
| MIRROR-09 | Phase 4 | Complete | admin health endpoint `abca27f`, Phase 5 admin UI `ac22ceb` |
| MIRROR-10 | Phase 4 | Complete | lifespan integration + degraded boot `e5d6d8f` |

**Coverage:**
- v1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-18*
*Last updated: 2026-05-18 — retroactive Phase 1-3 capture + Phase 4 v1*
