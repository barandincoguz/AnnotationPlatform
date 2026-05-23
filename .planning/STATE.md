# State

**Updated:** 2026-05-23

## Current Phase

**Phase 5** — Pre-flight Hardening & Deploy Readiness — `Complete`. 27 of 32 success gates fully met, 4 partial (waivers / operator-side), 0 failed.
See [audit/SIGNOFF.md](../audit/SIGNOFF.md) for the per-gate evidence and [audit/FIX-LOG.md](../audit/FIX-LOG.md) for the commit crosswalk.

## Active Branch

`main` (direct-to-main workflow per project preference).

## Completed Phases

| # | Status | Closeout |
|---|--------|----------|
| 1 | Complete | `b536e22` |
| 2 | Complete | `c93fbda` + Codex review fix `924e4e2` |
| 3 | Complete | `ca5555f` |
| 4 | Executed | `1f33a53 .. 66f0986` (14 commits) — wrk smoke verified in Phase 5 W4-T1 (`audit/SMOKE.md`) |
| 5 | Complete | Wave 0..4 across ~25 commits; tagged `phase-5` |

## Test Baseline (post Phase 5)

- Backend pytest: **987 pass** (was 946 + 3 skip entering Phase 5; +41 new tests across Wave 2 + Wave 2.5)
- Frontend vitest: **525 pass / 525** (was 477 / 511 entering Phase 5; FE-1 unblocked 34 + 14 new admin-page tests)
- Frontend typecheck: clean
- Frontend lint: clean
- e2e Playwright: 9 / 9 against built container (`audit/SMOKE.md`)
- ruff: 64 pre-existing errors (Phase 6 backlog; CI workflow gate is `continue-on-error: true` per W3-T3 design)
- wrk `/api/health` baseline: 5098 req/s, p99 4.14 ms (under the Phase 4 ≤5 ms budget)

## Live Data State

- `data/db/annotations.db` — 17923 documents (fresh Neon ETL on 2026-05-18), 0 annotations, 0 drafts, 0 users.
- `_outbox` table + 69 triggers active (migrations v0005, v0006).
- Backups: cleared 2026-05-19 after Phase 4 closeout. Canonical state lives in the partner Neon DB's `baran_*` mirror (62610 rows backfilled).

## Notes

- `.planning/` directory bootstrapped retroactively on 2026-05-18 for Phase 4 formal planning (`gsd-plan-phase` workflow). Phase 1-3 not retro-planned — they ran under the polish/Codex-review workflow with atomic commits.
- Phase 4 plan went through one revision pass (4 BLOCK + 9 FLAG → all RESOLVED → `PASS`) before execution; see `4-PLAN.md` history.
- Phase 4 was executed inline (no agent dispatch) after the GSD `/execute-phase` route proved too slow per session-level feedback.
- `docs/neon-mirror.md` is the operator runbook. The `NEON_MIRROR_URL` env var is required for live dual-write; absence leaves the dispatcher in degraded mode (local writes proceed, mirror queue accumulates).
