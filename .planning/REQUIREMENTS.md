# Requirements: Annotation Platform

**Defined:** 2026-05-18 (retroactive for Phase 1-3; v1 for Phase 4)
**Core Value:** Annotate Turkish tax rulings with structured law references; observe progress from a partner team's Neon Postgres database.

## v1 Requirements (active)

### Phase 4 — Neon Dual-Write Mirror

- [ ] **MIRROR-01**: Every SQLite INSERT/UPDATE/DELETE on a project table appends a row to a local outbox queue inside the same transaction.
- [ ] **MIRROR-02**: A background dispatcher coroutine drains outbox rows and applies them to the partner Neon Postgres database under `baran_<table_name>` table names.
- [ ] **MIRROR-03**: Partner Neon database has a mirror table for every one of the 24 project tables; types, primary keys, foreign keys, indexes, and check constraints all map faithfully (SQLite → Postgres equivalents).
- [ ] **MIRROR-04**: Neon outage (any psycopg error) MUST NOT fail or roll back the originating SQLite write. The dispatcher logs the failure, increments the row's retry count, and re-tries with backoff.
- [ ] **MIRROR-05**: Dispatcher achieves at-least-once delivery — every committed outbox row eventually reaches Neon (or lands in a dead-letter state after max retries with a permanent error stamp).
- [ ] **MIRROR-06**: A one-time backfill script populates the `baran_*` tables from the current SQLite state (17923 documents + denorms) before live dual-write begins.
- [ ] **MIRROR-07**: Request latency on existing endpoints does not increase by more than 5 ms p95 (background queue must not block the request path).
- [ ] **MIRROR-08**: Existing tests (872 backend + 511 frontend) stay green. New tests cover the outbox lifecycle (write → drain → mark delivered), retry on Neon failure, and schema-converter unit tests.
- [ ] **MIRROR-09**: A small admin / health surface exposes outbox queue depth + last-delivered-at so operators can spot a stuck dispatcher.
- [ ] **MIRROR-10**: All Neon credentials read from environment (never committed). Connection failures during boot are non-fatal — the app comes up with the dispatcher in a degraded "Neon unreachable" state.

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

| Requirement | Phase | Status |
|-------------|-------|--------|
| MIRROR-01 | Phase 4 | Pending |
| MIRROR-02 | Phase 4 | Pending |
| MIRROR-03 | Phase 4 | Pending |
| MIRROR-04 | Phase 4 | Pending |
| MIRROR-05 | Phase 4 | Pending |
| MIRROR-06 | Phase 4 | Pending |
| MIRROR-07 | Phase 4 | Pending |
| MIRROR-08 | Phase 4 | Pending |
| MIRROR-09 | Phase 4 | Pending |
| MIRROR-10 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-18*
*Last updated: 2026-05-18 — retroactive Phase 1-3 capture + Phase 4 v1*
