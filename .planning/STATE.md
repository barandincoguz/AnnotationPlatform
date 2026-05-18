# State

**Updated:** 2026-05-19

## Current Phase

**Phase 4** — Neon Postgres dual-write mirror — `Executed` (14/14 tasks shipped).
See [4-SUMMARY.md](./phases/04-neon-postgres-dual-write-mirror/4-SUMMARY.md) for the per-commit breakdown.

## Active Branch

`main` (direct-to-main workflow per project preference).

## Completed Phases

| # | Status | Closeout |
|---|--------|----------|
| 1 | Complete | `b536e22` |
| 2 | Complete | `c93fbda` + Codex review fix `924e4e2` |
| 3 | Complete | `ca5555f` |
| 4 | Executed | `1f33a53 .. 66f0986` (14 commits) — pending operator-run wrk/hey + tag |

## Test Baseline

- Backend pytest: **946 pass + 3 skip** (was 872 + 3 entering Phase 4; +74 mirror tests)
- Frontend vitest: 511 pass / 511 (untouched by Phase 4)
- Frontend typecheck: clean
- Frontend lint: clean
- e2e Playwright: 9 / 9

## Live Data State

- `data/db/annotations.db` — 17923 documents (fresh Neon ETL on 2026-05-18), 0 annotations, 0 drafts, 0 users.
- `_outbox` table + 69 triggers active (migrations v0005, v0006).
- Backups under `data/db/annotations.db.bak-*` (pre-clean-restart snapshots).

## Notes

- `.planning/` directory bootstrapped retroactively on 2026-05-18 for Phase 4 formal planning (`gsd-plan-phase` workflow). Phase 1-3 not retro-planned — they ran under the polish/Codex-review workflow with atomic commits.
- Phase 4 plan went through one revision pass (4 BLOCK + 9 FLAG → all RESOLVED → `PASS`) before execution; see `4-PLAN.md` history.
- Phase 4 was executed inline (no agent dispatch) after the GSD `/execute-phase` route proved too slow per session-level feedback.
- `docs/neon-mirror.md` is the operator runbook. The `NEON_MIRROR_URL` env var is required for live dual-write; absence leaves the dispatcher in degraded mode (local writes proceed, mirror queue accumulates).
