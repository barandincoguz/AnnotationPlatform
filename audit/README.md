# Audit artifacts — historical record

**Do not use these files as live project documentation.**

The `audit/` directory is a frozen snapshot of the Phase 5 pre-flight hardening
audit (2026-05-23) and the Phase 6 coordination closeout (2026-05-24). Test
counts, gate statuses, and backlog verdicts reflect the codebase **at seal
time**, not the current `main` branch.

## For current truth, use instead

| Topic | Live source |
|-------|-------------|
| Test counts | Root `README.md` → Tests (run pytest / vitest for live numbers) |
| Production deploy | `docs/deployment.md` |
| Security / perf findings (historical) | `audit/SEC.md`, `audit/PERF.md` — read with date context |
| Open backlog items | `audit/BACKLOG.md` — many items may already be fixed; verify in code |
| Phase gate sign-off | `audit/SIGNOFF.md`, `audit/PHASE-6-SIGNOFF.md` — sealed records only |

## File index

| File | Contents | Sealed |
|------|----------|--------|
| `SIGNOFF.md` | Phase 5 — 32 gates, 27/32 met | 2026-05-23 |
| `PHASE-6-SIGNOFF.md` | Phase 6 — coordination ordering, P6-1 blocker fix | 2026-05-24 |
| `BACKLOG.md` | 72 findings from Wave 1 audit (verdicts required before Wave 2) | 2026-05-23 |
| `FIX-LOG.md` | Wave 2 applied fixes | 2026-05-23 |
| `COMPLETION.md` | D12 completion-gaps crosswalk | 2026-05-23 |
| `BASELINE.md` | Pre-audit baseline metrics | 2026-05-23 |
| `SEC.md` / `BE.md` / `FE.md` / `PERF.md` / `DEPLOY.md` | Dimension audit reports | 2026-05-23 |
| `SMOKE.md` / `A11Y.md` | Wave 4 validation evidence | 2026-05-23 (+ Phase 6 append) |

## Test count drift (expected)

| Suite | Phase 6 seal (2026-05-24) | Current main (2026-07-07) |
|-------|----------------------------|---------------------------|
| Backend pytest | 1004 | **1179** |
| Frontend vitest | 527 | **596** |
| Playwright e2e | 13 | **14** |

Drift is normal as features land post-`phase-6` (e.g. feedback system,
statistics rollup indexes). Never copy seal-time numbers into user-facing docs
without re-running the suites.
