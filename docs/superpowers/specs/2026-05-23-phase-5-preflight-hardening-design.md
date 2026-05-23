# Phase 5 — Pre-flight Hardening & Deploy Readiness — Design

**Created:** 2026-05-23
**Status:** D12 added 2026-05-23 after parallel subagent audit; awaiting user review of full written spec
**Predecessors:** Phase 1-4 (workflow_state, atomic complete, frontend simplify, Neon mirror)
**Successor:** Phase 6 (SQLite → Neon primary cut-over, out of scope here)

---

## 1. Goal & Non-goals

### Goal

Take the artifact that emerged from Phase 1-4 — a single-instance FastAPI + SQLite WAL + React 18/TS annotation platform with an async Neon Postgres mirror — and make it production-ready for a **public, invite-gated** deployment.

Scope is an **11-dimension audit + fix sweep + host-agnostic operator runbook**. The deployment host (Hetzner / Oracle Cloud Always Free / Fly.io / etc.) is intentionally deferred; everything is defined at the container + environment-variable level. Host-specific steps live in optional appendix modules of the operator runbook.

### Non-goals

- **No greenfield features.** New features outside the existing roadmap stay out. (Caveat: dimension D12 below completes a small set of *already-promised-but-unbuilt* features — this is closing gaps, not adding scope.)
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
- **Build dimension (Wave 2.5):** D12 — items are already inventoried by the 2026-05-23 audit, so this is a build sweep, not a discovery sweep.

---

### 2.1 D12 Inventory — Completion gaps to close in Phase 5

Discovered by 6 parallel audit subagents on 2026-05-23 (results in this commit's spec PR description). The Medium-severity items from that audit are explicitly deferred to Phase 6 (see §6).

#### Build items (4 High — new code)

| ID | Item | Surface | Effort |
|----|------|---------|--------|
| **U1** | **Backup restore HTTP route** — `restore_from_snapshot()` is fully implemented in `backend/backup/restore.py` but no route exposes it. Currently requires shell-in. | New `POST /api/admin/backup/restore` (file upload or repo-pull mode) + admin audit log entry + service-level WAL safety check (the "STOP" gate from `runbooks/restore-drill.md`) | 1 session |
| **U4** | **Mirror health admin widget** (MIRROR-09 requirement) — backend `GET /api/admin/mirror/health` exists and returns queue depth + last-delivered-at + dead-letter count; no frontend surface | New admin page or topbar widget rendering the JSON; refetch interval; alert color thresholds | 3-4h |
| **U5** | **Backup admin UI** — `POST /api/admin/backup/run-now` has no UI; operator must `curl` or shell-in | New admin route + page: "Run backup now" button, last-N backup history list (from `system_events`), backup repo URL display | 2-3h |
| **U6** | **Retention admin UI** — `GET /api/admin/retention/preview` + `POST /api/admin/retention/run-now` have no UI | New admin route + page: preview deletions, confirm-and-run, history list | 2-3h |

#### Doc-reality drift (3 — doc-only fixes)

| ID | Item | Action |
|----|------|--------|
| **DR1** | README L62 + L346 claim "scrypt password hashing"; code uses bcrypt (`requirements.txt: bcrypt==4.2.0`; `backend/shared/auth.py`) | README edit |
| **DR2** | README L39 + L57 claim "90-second document locks"; code default is 300s (`backend/locks/service.py` `DEFAULT_LOCK_EXPIRES_SECONDS = 300`, configurable via `lock.expires_seconds` site setting) | README edit (use the actual default, note configurability) |
| **DR3** | `.planning/REQUIREMENTS.md` L41-51 still marks MIRROR-01..10 as `Pending`; all 10 shipped per `4-SUMMARY.md` | Set all 10 rows to `Complete` with commit references |

#### Dead code cleanup (3 — verified-orphan removal)

| ID | Item | Action |
|----|------|--------|
| **DC1** | `frontend/src/lib/env.ts` — `env` const exported with Zod schema; no import grep hits in `frontend/src/` | Verify with one more grep (including `import.meta.env`-style indirect refs); if truly dead, delete file |
| **DC2** | Orphan table `user_badges` — created in v0001, never read or written; replaced by denormalized `badges_earned` | New migration `v0007_drop_user_badges.py`; pre-flight assertion that table is empty before drop |
| **DC3** | Orphan table `user_quiz_answers` — created in v0001, never read or written; replaced by `training_attempts` | New migration `v0007_drop_user_quiz_answers.py` (or fold into single v0007); pre-flight assertion empty |

#### Out of D12 — explicitly deferred to Phase 6 backlog

These were audit-discovered but user-deferred:

- **U2** — Admin notification broadcast (Medium)
- **U3** — Gamification leaderboard endpoint (Medium)
- **U7** — Export admin UI (Medium) — `GET /api/admin/export` lacks a UI
- **U8** — Gold Doc "create new" admin UI (Medium)
- **U9** — Quiz question "create new" admin UI (Medium)
- **U10** — Active locks list UI + missing `GET /api/locks` backend endpoint (Medium)

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
| **D12** | **Completion gaps + cleanup** | **Promised-but-unbuilt features (4 High), doc-reality drift (3), and dead code (3) discovered by 2026-05-23 audit subagents.** See §2.1 below. | `audit/COMPLETION.md` + new code |

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

### Wave 2.5 — D12 Completion Sweep (~1-2 sessions)

- **Build items (U1, U4, U5, U6):** atomic commits, one feature per commit, full test coverage for new routes + frontend pages
  - U1: write route handler + service-level WAL guard + admin audit row + tests (route + service); update `runbooks/restore-drill.md` to mention the new route as an option
  - U4: frontend page reading `/api/admin/mirror/health`; design contract: refresh interval, alert thresholds (queue depth > 1000 = warn, > 10000 = critical; dead-letter > 0 = warn)
  - U5: frontend page + history list query (from `system_events` filtered to `backup_*`)
  - U6: frontend page + preview/confirm-modal flow
- **Doc-drift items (DR1, DR2, DR3):** single doc-edit commit per file, no scope creep
- **Dead-code items (DC1, DC2, DC3):**
  - DC1: re-grep + delete file in single commit
  - DC2 + DC3: single migration `v0007` that asserts emptiness then drops both orphan tables; full test that migration is idempotent + rollback-safe
- Output: commits on `main` + `audit/COMPLETION.md` (item → commit crosswalk)
- **Gate:** user reviews COMPLETION.md + does a manual click-through of the new admin pages before Wave 3

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

**Total:** 6-9 sessions (was 5-7 before D12 added). Wave-end gates allow user to redirect or stop.

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
- `audit/COMPLETION.md` — D12 inventory + per-item commit crosswalk
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

All 32 binary gates must pass for Phase 5 "ready" sign-off (26 base + 6 D12 gates).

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

### D12 completion gates

27. `POST /api/admin/backup/restore` route exists, requires admin auth, refuses to act on a hot DB (returns 409 if WAL is open), writes an `admin_audit_log` row on success; backend + e2e tests cover both happy path and refuse path
28. Admin "Mirror health" page renders queue depth + `last_delivered_at` + dead-letter count from `/api/admin/mirror/health`; alert thresholds (warn ≥ 1000 queue, critical ≥ 10000 queue, warn ≥ 1 dead-letter) are visually distinct; component test exists
29. Admin "Backup" page calls `POST /api/admin/backup/run-now` and renders the last 20 `backup_*` `system_events`; component test exists
30. Admin "Retention" page wraps `GET /preview` + `POST /run-now` with confirm-modal; component test exists
31. README claims align with code: bcrypt (not scrypt), 300 s lock default (not 90 s), `.planning/REQUIREMENTS.md` MIRROR rows reflect Phase 4 completion
32. Migration v0007 drops `user_badges` and `user_quiz_answers` after empty-assertion; full migration suite runs idempotently end-to-end; `frontend/src/lib/env.ts` removed if truly orphan

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
| R9 | D12 Wave 2.5 surfaces deeper unbuilt features once admin UIs touch the system | New findings during Wave 2.5 are triaged at the wave gate; not auto-built. Out-of-scope items become Phase 6 backlog. |
| R10 | DC2/DC3 migration `v0007` drops a non-empty table because the empty-assertion check is incomplete | Migration must `SELECT COUNT(*) FROM <table>` and abort with a clear error before `DROP`; both tables verified empty in production data before deploy of v0007 |

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
- **U2 — Admin notification broadcast** (audit-discovered, user-deferred)
- **U3 — Gamification leaderboard endpoint** (audit-discovered, user-deferred)
- **U7 — Export admin UI** (audit-discovered, user-deferred)
- **U8 — Gold Doc "create new" admin UI** (audit-discovered, user-deferred)
- **U9 — Quiz question "create new" admin UI** (audit-discovered, user-deferred)
- **U10 — Active locks list UI + `GET /api/locks` backend** (audit-discovered, user-deferred)

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
- 2026-05-23 unbuilt-feature audit: §2.1 D12 inventory above (6 parallel subagents — backend, frontend, admin panel, docs-reality, orphan code paths, planning artifacts)
- Phase 4 plan + summary: `.planning/phases/04-neon-postgres-dual-write-mirror/`
- Operator runbook (current): `docs/deployment.md`
- Mirror runbook (current): `docs/neon-mirror.md`
- Project state: `.planning/STATE.md`, `.planning/ROADMAP.md`
- Baseline test counts (entering Phase 5): backend 946 pass + 3 skip; frontend 511 pass; e2e 9 pass
