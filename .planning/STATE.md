# State

**Updated:** 2026-06-27

## Current Phase

**Phase 6** — Cross-team coordination ordering — `Complete`. 27 of 32 success gates met, 4 partial (carry-over from Phase 5, with documented Wave D progress on gate 25), 0 failed. P6-1 production blocker fixed at `ae96c82`; cross-team `document_id DESC` contract documented and enforced end-to-end. Tagged `phase-6` locally. Two originally-deferred items (P6-6 schema drift guard, P6-10 multi-user load) were re-scoped back in on follow-up and closed at `8f9fb5c` and `c1c850f`. **10 of 10** Codex findings fixed, 0 deferred. See [audit/PHASE-6-SIGNOFF.md](../audit/PHASE-6-SIGNOFF.md) for the per-finding verdict and gate evidence.

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
| 6 | Complete | Cross-team coordination ordering across all 3 feed tabs; tagged `phase-6` locally. Waves: pre-plan `4d750c7` + `08026a9` + `ad639d2`; plan `ca4328e`; Wave A `ae96c82` (P6-1 blocker fix); Wave B `b9cfdf5` (P6-2 + P6-3); Wave C `704497e` (P6-4 + P6-7); Wave D `4338fdc` + `d61bec6` + `23dfaf6` (D3 axe-core + D1 wrk + D4 counts); Wave E `810b8ea` (sign-off + tag). Follow-up: `8f9fb5c` P6-6 schema drift guard (caught real pre-existing drift — missing index from v0007 — and fixed); `c1c850f` P6-10 multi-user wrk (455 req/s on 10 sessions, 0 errors). Matches partner team (Zeynep) DB ordering `evrak_id DESC`. **10 of 10** Codex findings fixed. |

## Test Baseline (post Phase 6 Wave D)

- Backend pytest: **1155 pass / 0 fail**
- Frontend vitest: **581 pass / 581**
- Frontend typecheck: clean
- Frontend lint: clean
- e2e Playwright: **13 / 13** against auto-launched isolated backend + Vite (was 9 / 9 in Phase 5; +1 SortMenu hidden-default + dev-flag rewrite split, +3 a11y axe-core scans)
- a11y: runtime axe-core sweep over /login, /, /admin/mirror integrated in e2e (`frontend/e2e/a11y.spec.ts`); 2 scoped-out rules with documented Phase 7 deferrals (color-contrast design refresh; aria-valid-attr-value Radix React 18 useId false positive)
- ruff: 64 pre-existing errors (Phase 7 backlog; CI workflow gate is `continue-on-error: true` per W3-T3 design)
- wrk `/api/health` baseline: 5098 req/s, p99 4.14 ms (Phase 5 W4-T1; unchanged)
- wrk `/api/feed?tab=new&sort=document_id&order=desc` (Phase 6 default): **437.25 req/s**, p99 38.61 ms (+47.7% throughput vs Wave 4's legacy-default 296.04 — primary-key sort wins)
- wrk multi-user (10 distinct sessions, P6-10 follow-up via `scripts/loadtest_multiuser.sh`): **455 req/s**, p99 88.15 ms, 0 / 27 344 errors (mirror dispatcher in degraded mode)

## Live Data State

- `data/db/annotations.db` — 17923 documents (fresh Neon ETL on 2026-05-18), 0 annotations, 0 drafts, 0 users.
- `_outbox` table + 69 triggers active (migrations v0005, v0006).
- Backups: cleared 2026-05-19 after Phase 4 closeout. Canonical state lives in the partner Neon DB's `baran_*` mirror (62610 rows backfilled).

## Notes

- `.planning/` directory bootstrapped retroactively on 2026-05-18 for Phase 4 formal planning (`gsd-plan-phase` workflow). Phase 1-3 not retro-planned — they ran under the polish/Codex-review workflow with atomic commits.
- Phase 4 plan went through one revision pass (4 BLOCK + 9 FLAG → all RESOLVED → `PASS`) before execution; see `4-PLAN.md` history.
- Phase 4 was executed inline (no agent dispatch) after the GSD `/execute-phase` route proved too slow per session-level feedback.
- `docs/neon-mirror.md` is the operator runbook. The `NEON_MIRROR_URL` env var is required for live dual-write; absence leaves the dispatcher in degraded mode (local writes proceed, mirror queue accumulates).
