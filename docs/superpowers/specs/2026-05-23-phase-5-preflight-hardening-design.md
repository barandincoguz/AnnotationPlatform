# Phase 5 — Pre-flight Hardening & Deploy Readiness — Design

**Created:** 2026-05-23
**Status:** Approved (sections 1-6) — awaiting user review of written spec
**Predecessors:** Phase 1-4 (workflow_state, atomic complete, frontend simplify, Neon mirror)
**Successor:** Phase 6 (SQLite → Neon primary cut-over, out of scope here)

---

## 1. Goal & Non-goals

### Goal

Take the artifact that emerged from Phase 1-4 — a single-instance FastAPI + SQLite WAL + React 18/TS annotation platform with an async Neon Postgres mirror — and make it production-ready for a **public, invite-gated** deployment.

Scope is an **11-dimension audit + fix sweep + host-agnostic operator runbook**. The deployment host (Hetzner / Oracle Cloud Always Free / Fly.io / etc.) is intentionally deferred; everything is defined at the container + environment-variable level. Host-specific steps live in optional appendix modules of the operator runbook.

### Non-goals

- **No new product features.** Scope is correctness + ops + security only.
- **No Phase 4 architectural change.** Mirror semantics (async one-way SQLite → Neon, fail-silent, exponential backoff, dead-letter at N retries) stay as-is.
- **No SQLite → Neon primary cut-over.** That is Phase 6 work.
- **No HF Spaces auth migration** (cookie/iframe is a structural blocker — explicitly out).
- **No multi-region or horizontal failover.** Single-instance design (workers=1, BEGIN IMMEDIATE writer) preserved.

---

## 2. Scope — 11 Audit Dimensions

Each dimension produces a severity-tagged finding file and feeds the consolidated backlog. Severities use the existing convention (Critical / High / Medium / Low / Info) from the 2026-05-17 polish sprint.

**Static vs. interactive dimensions:**

- **Static (Wave 1, parallel subagents, read-only):** D1, D2, D3, D4, D6 — code/config inspection only.
- **Interactive (Wave 3-4, run against the live container):** D5 (a11y needs browser + screen-reader), D7 (ops needs backup-loop execution), D8 (CI needs a PR), D9 (runbook needs dry-run), D10 (smoke needs built container), D11 (visual polish needs UI in browser).

| # | Dimension | Surface | Output |
|---|-----------|---------|--------|
| **D1** | Security re-audit | Phase 4 mirror code path (`backend/mirror/`); DEFER list re-evaluation; invite flow; login brute-force defense; session hygiene; CSRF/Origin allowlist correctness; secrets discipline (`.env*`, image scan); CSV/export injection; admin audit log coverage | `audit/SEC.md` |
| **D2** | Backend correctness sweep | `backend/{annotations,locks,drafts,users,training,admin,sse,mirror}` services + routes; dispatcher loop; migration runner; outbox capture race conditions; transaction boundaries; error paths | `audit/BE.md` |
| **D3** | Frontend logic sweep | `frontend/src/hooks/{useLock,useDraft,useSSE,useReferencesState}`; state machines; error UI states; `AbortController` discipline; query invalidation; race conditions | `audit/FE.md` |
| **D4** | Performance check | Phase 4 ≤5 ms p95 added-latency budget; DocList virtualized hot path under SSE invalidation storm; SSE broker under N>20 connections; outbox drain throughput; cold-boot time | `audit/PERF.md` |
| **D5** | A11y final pass | WCAG 2.1 AA target; ARIA, keyboard navigation, focus management, color contrast (Tailwind palette audit), screen-reader smoke (VoiceOver) on login + feed + AnnotateDoc + Admin | `audit/A11Y.md` |
| **D6** | Deploy config audit | Dockerfile (multi-stage, non-root user, signal handling, healthcheck); `docker-compose.yml`; `.env.production` template; `DATA_DIR` volume mount; log destination; file perms in `/data`; image layer hygiene; final image size | `audit/DEPLOY.md` |
| **D7** | Operational readiness | Backup end-to-end (snapshot → GitHub push verified); restore drill on copy; log rotation policy; monitoring surface (`/api/health`, `/api/health/db`, `/api/admin/mirror/health`); `system_events` sanity; mirror queue depth alert threshold | `audit/OPS.md` + `runbooks/restore-drill.md` |
| **D8** | CI workflow | `.github/workflows/ci.yml`: ruff + mypy (existing-error-baseline) + pytest + vitest + eslint + tsc + Dockerfile build smoke. PR-gate only; deploy stays manual until host chosen. | `.github/workflows/ci.yml` |
| **D9** | Operator runbook | Host-agnostic deploy + first-admin seed + invite seeding + rollback + restore + Neon mirror enable. Hetzner + 1 alternative (Oracle or Fly) as appendix modules. | Updated `docs/deployment.md` |
| **D10** | Smoke E2E + load | Built container → `wrk` 60s on hot endpoints + Playwright e2e 9/9 green | `audit/SMOKE.md` |
| **D11** | Frontend visual polish | Final UI sweep: empty states, error toasts, loading states, mobile breakpoint sanity, dark mode (if any), copy/typography consistency | `audit/UI.md` |

---

## 3. Phasing

Two tracks: read-only audit pass first, then severity-ordered fix waves. Each wave ends with a user-review gate.

### Wave 0 — Baseline (~1 session)

- Confirm current `pytest` + `vitest` + `tsc` + `ruff` + `eslint` all green
- Built-container smoke (`docker compose build` + 60s up + healthcheck)
- Snapshot: test counts, image size, cold-boot time, mirror queue depth, latency baseline
- Output: `audit/BASELINE.md`

### Wave 1 — Read-only Audit (~2 sessions)

- Parallel review of the **5 static dimensions** (D1, D2, D3, D4, D6) via subagent dispatch (Explore/Plan flavored). D5, D7, D9, D10, D11 require interaction with the running system and run in Wave 3 or Wave 4.
- Findings consolidated into severity-tagged backlog
- Per-dimension file: `audit/SEC.md`, `audit/BE.md`, `audit/FE.md`, `audit/PERF.md`, `audit/DEPLOY.md`
- Consolidated: `audit/BACKLOG.md` with APPLY/DEFER columns blank
- **Gate:** user reviews backlog, marks APPLY/DEFER per finding before Wave 2

### Wave 2 — Critical + High Fix Sweep (~1-2 sessions)

- Pull APPLY-Critical + APPLY-High items from backlog
- One atomic commit per finding; commit message refs finding ID
- Per fix touching Phase 4 mirror surface (`backend/mirror/*`, dispatcher, outbox triggers): run `pytest tests/mirror/` before commit
- Per fix touching frontend hooks: run relevant `vitest` files + `tsc`
- Output: commits on `main` + `audit/FIX-LOG.md` (finding → commit crosswalk)
- **Gate:** user reviews FIX-LOG.md before Wave 3

### Wave 3 — Polish + Ops (~1 session)

- D7 ops readiness: execute restore drill on copy, set up log rotation (host-agnostic config in container)
- D8 CI workflow: write `.github/workflows/ci.yml`, open one validation PR
- D9 update `docs/deployment.md`: host-agnostic core + Hetzner appendix + 1 alternative appendix
- D11 visual polish: APPLY-Medium frontend items
- Output: CI workflow committed, deployment.md refreshed, `runbooks/restore-drill.md` created
- **Gate:** user reviews runbook + CI run before Wave 4

### Wave 4 — Validation (~1 session)

- D10 smoke: built container + `wrk -t2 -c10 -d60s` on `/api/feed` + Playwright e2e 9/9
- D5 a11y: axe-core sweep + manual keyboard tour over login + feed + AnnotateDoc + Admin
- Full test re-run (backend + frontend + e2e)
- Operator-runbook dry-run: clean host → deploy → bootstrap admin → seed 1 invite → restore drill → rollback drill
- Output: `audit/SMOKE.md`, `audit/A11Y.md`, "ready" sign-off in `.planning/STATE.md`

**Total:** 5-7 sessions. Wave-end gates allow user to redirect or stop.

---

## 4. Deliverables

### Code artifacts

- `.github/workflows/ci.yml` — PR-gate CI (ruff, mypy w/ baseline, pytest, vitest, eslint, tsc, docker build smoke)
- Fix commits — atomic, per-finding, follow existing commit convention (`fix(scope): description` or `feat(scope): description`)
- `runbooks/restore-drill.md` — step-by-step restore drill with explicit STOP gates

### Doc artifacts

- `audit/BASELINE.md` — Wave 0 snapshot
- `audit/SEC.md` — D1 findings
- `audit/BE.md` — D2 findings
- `audit/FE.md` — D3 findings
- `audit/PERF.md` — D4 findings
- `audit/A11Y.md` — D5 findings
- `audit/DEPLOY.md` — D6 findings
- `audit/OPS.md` — D7 findings
- `audit/UI.md` — D11 findings
- `audit/SMOKE.md` — Wave 4 smoke + load results
- `audit/BACKLOG.md` — consolidated, severity + APPLY/DEFER verdict
- `audit/FIX-LOG.md` — Wave 2 finding → commit crosswalk
- `docs/deployment.md` — refreshed, host-agnostic core + 2 host appendix modules
- `docs/neon-mirror.md` — updated if Phase 5 touches mirror surface
- `.planning/STATE.md` — Phase 5 entry + closeout
- `.planning/ROADMAP.md` — Phase 5 row

### Process artifacts

- This spec: `docs/superpowers/specs/2026-05-23-phase-5-preflight-hardening-design.md`
- Plan (writing-plans output): `docs/superpowers/plans/2026-05-23-phase-5-preflight-hardening-plan.md`

### Convention

- Atomic commits, conventional-commit style, `phase-5` reference in commit body
- `audit/` directory is committed (permanent historical artifact, not gitignored)
- DEFER list explicit and named — feeds Phase 6 backlog

---

## 5. Success Criteria

All 26 binary gates must pass for Phase 5 "ready" sign-off.

### Correctness gates

1. `pytest` ≥ 946 pass / 0 fail (fix waves may add new tests)
2. `vitest` ≥ 511 pass / 0 fail
3. `tsc --noEmit` 0 error
4. `ruff check` 0 error
5. `eslint` 0 error / 0 warning (existing baseline-clean)
6. `mypy backend/` ≤ existing baseline error count (no regression). Skipped if mypy is not already part of the project toolchain — verified during Wave 0 baseline.
7. Playwright e2e 9/9 green against the built container

### Security gates

8. D1 audit Critical + High items are each APPLIED or DEFER + justification
9. `.env.production` template uses `<REPLACE_ME>` placeholders; production-mode env validation enforced at startup
10. `ALLOWED_ORIGINS` enforced at runtime (verified by a test exercising rejection of off-allowlist origins)
11. Bootstrap admin seed is one-shot; second boot is no-op (verified by test)
12. `/api/auth/login`, `/api/auth/register`, `/api/annotations/*/save`, `/api/drafts/*` are rate-limited (verified by test)
13. No secrets in git history, in built image, or in committed envs (grep + image-fs scan)

### Ops gates

14. `docker compose build` clean; image size ≤ baseline + 10%
15. Cold-boot to healthy (HTTP 200 on `/api/health`): ≤ 30s
16. Restore drill end-to-end on a copy of the live DB succeeds; documented
17. Backup snapshot → GitHub push → JSON dump → restore → identity check (row counts + a sample row hash per table)
18. `/api/health`, `/api/health/db`, `/api/admin/mirror/health` all return 200 with expected JSON shape
19. `system_events` has at least one `backup_success` row after Wave 4 dry-run
20. Phase 4 latency budget held: ≤5 ms p95 added latency vs. degraded-mode baseline. Measured by `wrk -t2 -c10 -d60s` against `/api/health` and `/api/feed?tab=new&limit=50`, mirroring the methodology in `.planning/phases/04-neon-postgres-dual-write-mirror/4-SUMMARY.md`.

### Doc gates

21. `docs/deployment.md` is host-agnostic + at least 2 host appendix modules (Hetzner + one alternative)
22. `runbooks/restore-drill.md` exists; executed once during Wave 3 with timestamped log
23. `docs/neon-mirror.md` reflects any Phase 5 changes to mirror surface (or marked unchanged)
24. CI workflow has run green on at least one validation PR

### A11y gates

25. `axe-core` sweep on login + feed + AnnotateDoc + Admin: 0 `critical` + 0 `serious` violations
26. Keyboard tour: tab order is logical, skip-link present and works, focus-visible ring on every interactive element

---

## 6. Risks, Mitigations, Out-of-scope

### Risks

| # | Risk | Mitigation |
|---|------|------------|
| R1 | Audit pass surfaces new Critical bug; scope explodes | Wave 1 ends with user gate; APPLY/DEFER decision is the user's |
| R2 | Fix waves break Phase 4 mirror semantics | Per-fix `pytest tests/mirror/` is mandatory; full e2e dispatcher test at end of each wave |
| R3 | CI workflow brittle on first PR (cache misconfig, secret) | Wave 3 CI only exercises public-surface jobs; secret-required jobs are skipped or stubbed |
| R4 | A11y sweep over-runs (manual keyboard tour is slow) | `axe-core` automation is primary; manual only on the 4 core flows (login + feed + AnnotateDoc + Admin) |
| R5 | Restore drill damages production data | Drill is **copy-only**; runbook has two explicit STOP gates before any DB-touching command |
| R6 | Host decision delayed → deploy slips | Spec is host-agnostic; final host can be chosen post-Wave-4 without rework |
| R7 | Bootstrap admin password rotation forgotten | Runbook flags this as a required step; consider first-login forced-rotation check (audit item, not change) |
| R8 | Backup repo PAT leak | Wave 3 audits PAT scope; recommends GitHub secret-scanning on backup repo |

### Out-of-scope (Phase 6 or later)

- SQLite → Neon primary cut-over
- HF Spaces auth migration (token-header refactor) — cookie/iframe blocker stands
- Multi-region deploy
- Password complexity rules (UX scope creep)
- Common-password dictionary load (new dependency)
- Session-token sha256-at-rest (S7 from prior polish DEFER list — broad refactor)
- Frontend bundle reorg (`lib/schemas/`, `lib/text/`) — mechanical, not polish
- DocList full virtualization rewrite — already virtualized; only memo gap addressed
- New gamification mechanics
- Email-provider integration for invite delivery — manual delivery stays Phase 5

### Explicit DEFER carry-over (from 2026-05-17 polish DEFER list, re-evaluated but not applied here)

- S7 — session-token sha256-at-rest
- Password complexity dictionary
- `__Host-` cookie prefix (breaks staging deploys)
- PAT-in-`.git/config` → git credential helper plumbing
- DocList custom-id keys reducer audit
- `lib/` directory restructure

---

## 7. References

- 2026-05-17 polish sprint: `POLISH_BACKLOG.md`, `POLISH_REPORT.md`
- Phase 4 plan + summary: `.planning/phases/04-neon-postgres-dual-write-mirror/`
- Operator runbook (current): `docs/deployment.md`
- Mirror runbook (current): `docs/neon-mirror.md`
- Project state: `.planning/STATE.md`, `.planning/ROADMAP.md`
- Baseline test counts (entering Phase 5): backend 946 pass + 3 skip; frontend 511 pass; e2e 9 pass
