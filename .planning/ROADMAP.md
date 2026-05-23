# Roadmap: Annotation Platform

**Defined:** 2026-05-18 (Phase 1-3 retroactive; Phase 4 active)

## Phase List

| # | Name | Status | Goal |
|---|------|--------|------|
| 1 | Canonical workflow_state on FeedItem | Complete | Server-side 4-state classification (new/draft/review/verified) replaces frontend ternaries |
| 2 | Atomic complete + skip cleanup | Complete | Single BEGIN IMMEDIATE for save+complete+draft-delete; skip clears caller draft |
| 3 | Frontend simplify + workflow_state UI | Complete | Single-POST complete; workflow_state-based status branding; useDraft empty→DELETE; SSE annotation_completed listener |
| 4 | Neon Postgres dual-write mirror | Executed | Async outbox + dispatcher; every SQLite write also lands in partner's Neon DB under `baran_<table>` prefix |
| 5 | Pre-flight Hardening & Deploy Readiness | Complete | 12-dimension audit + 10 High fix sweep + D12 build (4 admin pages + backup restore route + dead-letter requeue + doc edits + dead-code) + restore runbook + 2 host appendices + GitHub Actions CI + wrk/Playwright/a11y validation. 27/32 gates met (4 partial waivers, 0 failed). Tag `phase-5`. |

## Phase Details

### Phase 1: Canonical workflow_state on FeedItem
**Status:** Complete
**Goal:** Replace fragile `has_annotation && !is_completed && hasDraft` ternaries with a single server-side `workflow_state` enum so the frontend stops shadowing earlier UI bugs.
**Tag:** `b536e22`
**Requirements:** (retroactive; not tracked in REQUIREMENTS.md)
**Success criteria (already met):**
1. `FeedItem.workflow_state` is one of `new | draft | review | verified` for every row.
2. `FeedItem.has_draft` reflects whether the calling user owns a draft on the doc.
3. ORDER BY `updated_at` ranks draft-only rows correctly via `COALESCE`.
4. Backend pytest +9 cases, all green.

### Phase 2: Atomic complete + skip cleanup
**Status:** Complete
**Goal:** Collapse the pre-existing frontend chain (save → complete → delete_draft) into a single `BEGIN IMMEDIATE` server-side, fixing the race where blockSaves cancelled a pending PUT and a stale `annotations.references_json` got frozen as "complete".
**Tags:** `c93fbda`, `924e4e2`
**Requirements:** (retroactive; not tracked in REQUIREMENTS.md)
**Success criteria (already met):**
1. `set_complete(references=...)` saves refs + flips flag + deletes draft in one transaction.
2. `CompleteRequest.references` is optional; `completed=False + refs` rejected at the model boundary (422).
3. First-time atomic complete (no prior row) writes both `create` and `complete_mark` version rows to preserve the chain invariant.
4. Route fires `annotation_saved` + `annotation_completed` SSE events plus the matching gamification orchestrators when the service reports `did_save` / `changed`.
5. Idempotence + `AnnotationNotFound` checks moved inside `BEGIN IMMEDIATE` (TOCTOU fix).
6. Backend pytest +13 cases, all green.

### Phase 3: Frontend simplify + workflow_state UI
**Status:** Complete
**Goal:** Consume the Phase 1+2 backend contract on the frontend; drop the legacy ternaries from the UI; collapse `handleComplete` to one round-trip.
**Tag:** `ca5555f`
**Requirements:** (retroactive; not tracked in REQUIREMENTS.md)
**Success criteria (already met):**
1. `handleComplete` issues a single `POST /complete` carrying refs in the body.
2. `DocListItem` branches on `workflow_state` (4 cases) for icon + accessible label.
3. `useDraft.debouncedSave` issues DELETE when refs go empty (autosave path only).
4. PUT/DELETE invalidate `feedKeys.all` only on 0↔non-zero draft transitions (no per-keystroke feed refetches).
5. SSE `annotation_completed` invalidates the feed (was only `annotation_saved` before).
6. Frontend vitest +8 cases (511 total), typecheck + lint clean.

### Phase 4: Neon Postgres dual-write mirror
**Status:** Executed (14 commits `1f33a53 .. 66f0986`)
**Goal:** Asynchronously mirror every SQLite write into the partner team's Neon Postgres database under `baran_<table>` prefix, with at-least-once delivery, fail-silent on Neon outage, and zero added latency on the request path.
**Requirements:** MIRROR-01 .. MIRROR-10
**Summary:** [4-SUMMARY.md](./phases/04-neon-postgres-dual-write-mirror/4-SUMMARY.md)
**Success criteria:**
1. `_outbox` table + trigger generators (**23 in-scope tables × INSERT/UPDATE/DELETE = 69 triggers**; `schema_migrations` excluded as operational metadata) capture every mutation in the same transaction as the write.
2. Async dispatcher coroutine (started in FastAPI lifespan) drains the outbox and applies each row to Neon's `baran_*` table via psycopg.
3. Neon write failure → log + retry with exponential backoff; never blocks or rolls back the SQLite write. Dead-letter after N retries (default 5) with a permanent error stamp.
4. Backfill script populates the partner Neon DB from current SQLite state (17923 docs + 37481 + 7149 denorm rows) before live dual-write begins.
5. Request latency does not increase by >5 ms p95 on existing endpoints (smoke-measured before/after).
6. Existing 872 backend + 511 frontend tests stay green. New tests cover outbox lifecycle, dispatcher retry, schema-converter unit cases, and backfill idempotency.
7. Operator-visible health surface: outbox queue depth + last-delivered-at + dead-letter count.
