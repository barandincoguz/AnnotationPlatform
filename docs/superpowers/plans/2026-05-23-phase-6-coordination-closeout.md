# Phase 6 — Cross-Team Coordination Closeout — PLAN

> **Status:** Plan only. Reviewed by Codex on 2026-05-23 against commit `ad639d2`. No implementation has happened against this plan yet — user gate required before execution.

**Goal:** Close the Phase 6 work (cross-team document_id DESC ordering + hidden SortMenu) safely so the platform is genuinely activation-ready. Phase 5 declared 27/32 gates met but Codex review surfaced **a production blocker introduced by the Phase 6 commits themselves** plus 5 lower-severity gaps that must close before deploy.

**Predecessor:** Phase 5 (`phase-5` tag at `237614d`) + 3 Phase 6 commits (`4d750c7`, `08026a9`, `ad639d2`).

---

## 1. Codex headline finding (verified)

`GET /api/feed` route validates `sort` via a regex literal in `backend/shuffle/routes.py:15`:

```
_SORT_PATTERN = "^(shuffle|tarih|created_at|sayi|vergi_turu|konu|difficulty|word_count|updated_at|editors_count)$"
```

`document_id` is **not** in that pattern. Frontend store v4 default (from commit `08026a9`) sends `sort=document_id&order=desc` on every feed call. Result on a real deploy: **every feed load returns HTTP 422.**

The service-layer tests added in `4d750c7` (`test_default_sort_*_tab_is_document_id_desc`) pass because they call `shuffle_service.list_feed(...)` directly, bypassing FastAPI's `Query` regex. The contract drift between the regex and the SORT_COLUMNS dict is invisible to the unit suite.

This is the single most important item in this plan. Everything else is hygiene.

---

## 2. Findings inventory (Codex + my verification pass)

Severity scale: **Blocker** (cannot deploy), **High** (must fix in Phase 6), **Medium** (Phase 6 if quick, else Phase 7), **Low** (Phase 7+).

| # | Finding | Sev | Surface | Source |
|---|---------|-----|---------|--------|
| **P6-1** | `_SORT_PATTERN` regex omits `document_id`; every feed load → 422 | **Blocker** | `backend/shuffle/routes.py:15` | Codex #1; verified by reading the file |
| **P6-2** | Playwright e2e still references SortMenu visibility (`frontend/e2e/annotation.spec.ts:51`); current default state hides it | **High** | `frontend/e2e/annotation.spec.ts` | Codex #2; verified |
| **P6-3** | SortMenu's SORT_OPTIONS list omits `document_id` even when the dev flag is on — dev users can never visually select the new default key | **Medium** | `frontend/src/components/annotation/SortMenu.tsx:42-52` | Codex #3 |
| **P6-4** | `NEON_MIRROR_URL` absent from `docs/deployment.md` env reference table; operators easily ship with the mirror silently disabled | **Medium** | `docs/deployment.md` | Codex #4 |
| **P6-5** | `audit/SIGNOFF.md` + `.planning/STATE.md` test counts stale (claim 987/525, actual 989/527) | **Low** | `audit/SIGNOFF.md`, `.planning/STATE.md` | Codex #5 |
| **P6-6** | Cross-team mirror has no automated Postgres-side schema drift check; `migrations/postgres/001-baran-init.sql` re-generation is manual per the operator runbook | **High** (ops) | `docs/neon-mirror.md` + `scripts/regen_neon_ddl.py` | Codex cross-team risk §2 |
| **P6-7** | Dispatcher is fail-silent on Neon outage; cross-team annotators can read stale rows for an indeterminate window without any operator alert | **Medium** (ops) | `backend/mirror/dispatcher.py` lifecycle | Codex cross-team risk §1 |
| **P6-8** | `localStorage.a11n.dev_sort=1` lets any browser silently break the cross-team ordering contract; no server-side enforcement | **Medium** (policy) | `frontend/src/lib/devFlags.ts` | Codex cross-team risk §5 |
| **P6-9** | Wave 4 wrk on `/api/feed` used the legacy URL without explicit Phase 6 sort param (`audit/SMOKE.md:40-43`); the 5098 req/s number was measured on a now-defunct route signature | **High** | `audit/SMOKE.md` | Codex pre-flight gap |
| **P6-10** | No multi-user live load test in Wave 4; only single-user wrk against `/api/health` is in evidence | **Medium** | `audit/SMOKE.md` | Codex pre-flight gap |

---

## 3. Plan

### Wave A — Production blocker fix (must merge before any deploy)

**A1. Add `document_id` to the route regex.** One-line change in `backend/shuffle/routes.py`:

```
_SORT_PATTERN = "^(document_id|shuffle|tarih|created_at|sayi|vergi_turu|konu|difficulty|word_count|updated_at|editors_count)$"
```

**A2. HTTP-layer tests.** Add to `tests/test_shuffle_routes.py` (or wherever feed-route tests live):
- `GET /api/feed?tab=new&sort=document_id&order=desc` → 200, item ordering matches `document_id` DESC
- Same for `tab=review` and `tab=verified`
- An invalid `sort=zzzzz` still returns 422 (regression guard on the regex itself working)

These tests would have caught the blocker. They are the structural fix.

**A3. Backfill an annotation spec for the route-vs-service contract** (lightweight): a single
parametrised test that asserts every key in `service.SORT_COLUMNS` also matches `routes._SORT_PATTERN`. Single-source-of-truth invariant.

**Exit:** A1+A2+A3 in one atomic commit. Full pytest re-run, full vitest re-run. Both green. Push.

### Wave B — Frontend test catch-up

**B1. Update `frontend/e2e/annotation.spec.ts` for Phase 6:**
- Default-state assertion: no SortMenu button visible, feed loads, first-page items are `document_id` DESC ordered.
- Dev-flag path: `await page.evaluate(() => localStorage.setItem('a11n.dev_sort', '1'))` then reload, assert button visible.
- Remove or rewrite assertions that previously depended on SortMenu being on screen.

**B2. Add `document_id` to `SortMenu` SORT_OPTIONS** with appropriate icon + label (something like `Hash` icon, label "Özelge ID"). Even though normal users never see it, the dev escape hatch is incomplete without it — a developer enabling the flag should be able to see + leave the default key.

**B3. Component test update:** `SortMenu.test.tsx` `"opens the dropdown and lists every sort option"` should now also assert the `document_id` row exists.

**Exit:** B1+B2+B3 in one atomic commit. Full vitest + tsc + eslint green. Run Playwright locally if possible (against the built container as in Phase 5 W4-T1) and confirm 9/9 still pass.

### Wave C — Operational readiness gaps

**C1. `docs/deployment.md` Phase 6 + Neon env addendum.** Add `NEON_MIRROR_URL`, `NEON_MIRROR_BATCH_SIZE`, `NEON_MIRROR_MAX_RETRIES`, `NEON_MIRROR_EMPTY_SLEEP` to the env reference table (currently §3 in the refreshed doc). Quote `docs/neon-mirror.md`'s warning that unset = silent degraded mode. Add a "Cross-team coordination" section noting:
- All annotators on this and the partner deploy must see the same feed order.
- The dev flag (`localStorage.a11n.dev_sort=1`) is for me only — never instruct an operator to set it.
- Neon mirror is one-way; partner-team reads from the partner Neon instance, not from us.

**C2. Schema drift guard.** Add a single CI step (or a `make verify-mirror-ddl` script) that runs `scripts/regen_neon_ddl.py` and asserts the diff against the committed `migrations/postgres/001-baran-init.sql` is empty. Drift = CI fails. This catches the "operator changed SQLite schema, forgot to regenerate Neon DDL" footgun.

**C3. Mirror health alert documentation.** Append a section to `runbooks/restore-drill.md` (or a sibling `runbooks/mirror-watchdog.md`): if `/api/admin/mirror/health` reports `dead_letter_count > 0` or `oldest_undelivered_age_seconds > N`, the operator should requeue (BE-10 button) and investigate. Concrete thresholds: dead-letter ≥ 1 = warn, queue depth ≥ 1000 = warn, ≥ 10000 = critical (matches the colors I already put in the UI).

**Exit:** C1+C2+C3 in one atomic commit (or two if CI step is awkward). `gh pr create` against `personal` to validate the new CI step passes.

### Wave D — Validation re-run

**D1. Rerun Wave 4 W4-T1 against `ad639d2`** with the corrected feed URL:

```
wrk -t2 -c10 -d60s --latency \
  'http://127.0.0.1:18000/api/feed?tab=new&limit=50&sort=document_id&order=desc'
```

Append to `audit/SMOKE.md` with a clear timestamp + the new commit SHA. The 5098 req/s headline from Wave 4 was on the wrong endpoint and is misleading until refreshed.

**D2. Add a multi-user load step.** Write a single `scripts/loadtest_multiuser.sh` (or extend the existing wrk invocation with a Lua script) that issues authenticated GETs for ≥10 distinct cookie sessions concurrently. Capture: p95, error count, mirror queue depth before/after. Append to `audit/SMOKE.md`. Acceptance: 0 errors, queue drains within 30 s of the load ending.

**D3. axe-core in Playwright.** Add a single `frontend/e2e/a11y.spec.ts` that runs `@axe-core/playwright` against `/login`, `/`, `/admin/mirror`. Install dep if needed (one new devDependency). The Phase 5 a11y was static-only; this closes the partial waiver on gate 25.

**D4. Update test counts.** Refresh `audit/SIGNOFF.md` and `.planning/STATE.md` with post-Phase-6 numbers (currently 989 backend / 527 frontend). Bump the "27/32 gates" line if a partial is now fully met.

**Exit:** D1-D4 across 2-3 commits. The wrk + multi-user numbers in `audit/SMOKE.md` are the new acceptance evidence.

### Wave E — Sign-off + tag

**E1.** Compose `audit/PHASE-6-SIGNOFF.md` mirroring the Phase 5 sign-off shape. Goal: 32 gates → 32 met (no partials). The previously partial gates 16/22 (restore-drill execute) and gate 25 (a11y) should now be closed by Wave D execution.

**E2.** Update `.planning/STATE.md` Current Phase → `Phase 6 — Complete` with tag.

**E3.** `git tag -a phase-6 -m "..."` + `git push personal phase-6 && git push origin phase-6`.

**Exit:** Tagged. Ready for activation discussion.

---

## 4. Out of scope for Phase 6

Stays on the Phase 7 backlog (already enumerated in `audit/SIGNOFF.md` and `audit/BACKLOG.md`):

- U2 admin broadcast, U3 leaderboard, U7 export UI, U8 gold-doc create UI, U9 quiz create UI, U10 active-locks UI
- 14 Medium APPLY-W3 audit findings (SEC-2..5, BE-9/11/12, FE-2/3/4, B-03, F-01/02, D6-001/002)
- 64 pre-existing ruff errors (mostly E402 + F841)
- A11Y-S3: Radix Dialog migration for MirrorHealthPage + RetentionPage raw modals
- Session-token sha256-at-rest (S7)
- `__Host-` cookie prefix
- Password complexity dictionary

---

## 5. Phase 6 effort estimate

| Wave | Concrete tasks | Sessions |
|------|----------------|----------|
| A — blocker fix | 1 backend file + 3 new tests + invariant | ~0.5 |
| B — frontend catch-up | 1 e2e spec + SortMenu option + 1 component test | ~0.5 |
| C — ops docs + drift guard | deployment.md edits + CI step + mirror runbook | ~0.5 |
| D — validation re-run | wrk + multi-user script + axe-core spec + count refresh | ~1 |
| E — sign-off + tag | sign-off doc + state update + tag + push | ~0.25 |
| **Total** | | **~2.5-3 sessions** |

---

## 6. Risks

- **R1 — Wave A blocker fix exposes deeper contract drift.** If the route regex differs from the service in other places (e.g. tab regex, order regex), A3's invariant test should surface them. If too many, scope creep.
- **R2 — happy-dom + axe-core compatibility.** axe-core was historically only tested under jsdom. happy-dom (switched in Phase 5 FE-1) may need its own polyfill or a fallback to running axe inside Playwright's browser context. D3 may discover this.
- **R3 — Schema drift CI step breaks on first run** because `001-baran-init.sql` was hand-edited at some point and no longer matches a fresh regeneration. Acceptable failure — investigate, fix, then guard.
- **R4 — Multi-user load test discovers SQLite WAL contention** worse than expected. Phase 4 latency budget (≤5 ms p95 added) was measured single-user. If true multi-user p99 blows past 5 ms, that's a real finding, not a stretch goal.

---

## 7. Verification at Phase 6 closeout

All five must hold to tag `phase-6`:

1. `pytest tests/` ≥ 989 pass / 0 fail; the new route-layer document_id test is in the count.
2. `vitest run` ≥ 527 + new tests pass; e2e 9/9 against built container (with the Phase 6 default-state assertions).
3. `curl -fs 'http://<host>/api/feed?tab=new&sort=document_id&order=desc'` → HTTP 200 with item 0's `document_id` lexicographically max.
4. `audit/SMOKE.md` reflects a wrk run against the actual Phase 6 feed URL on the current commit.
5. `audit/PHASE-6-SIGNOFF.md` exists with 32/32 gates met (no partial waivers carried over from Phase 5 that were in scope here).

---

## 8. Decision points (user-gated)

Before Wave A starts:

- **D1.** Accept Codex's framing of P6-1 as a blocker? (My read: yes, this is unambiguously a 100%-fail-on-deploy bug.)
- **D2.** Include P6-3 (`document_id` in SortMenu options) in Wave B, or carry to Phase 7?
- **D3.** Include P6-6 (Postgres schema drift CI guard) now, or carry to a Phase 7 mirror-hardening pass?
- **D4.** P6-10 multi-user load test — required for Phase 6 closeout, or acceptable as Phase 7?

These four decisions determine whether Phase 6 is 1.5 sessions or 3 sessions.

---

*Plan only — no code has been changed against this document yet.*
