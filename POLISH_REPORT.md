# Polish-Phase Report — 2026-05-17

Autonomous polish sprint over the Anotasyon Platform (Turkish tax-ruling
annotation, FastAPI + SQLite + React 18/TS). Multi-agent review →
backlog → batched fixes → final verification.

Source artifacts:
- `POLISH_BACKLOG.md` — consolidated finding backlog
- `/tmp/polish-security.md`, `/tmp/polish-frontend.md`,
  `/tmp/polish-backend.md`, `/tmp/polish-perf-a11y.md`,
  `/tmp/polish-quality.md` — raw reviewer outputs

## 1 — What was reviewed

Five parallel reviewer subagents covered:

| Reviewer | Surface | Findings (raw) |
|----------|---------|----------------|
| Security | FastAPI middleware, auth, SQL, file paths, Docker, env handling | 17 |
| Frontend logic + UI/UX | DocList/Viewer/SortMenu, training, admin, topbar, hooks | 30 |
| Backend/API/DB | services, routes, migrations, validators, concurrency | 27 |
| Performance + A11y | React render, query patterns, ARIA, keyboard nav, color | 23 |
| Quality + Tests + DX | duplicated logic, dead code, test gaps, README accuracy | 20 |

**Aggregate: 117 findings — Critical 5 · High 28 · Medium 54 · Low 22 · Info 8.**

## 2 — Issues by category (selection)

### Security (Critical / High)

- **No CSRF/Origin defense** — the project description claimed CSRF but
  the only protection was `SameSite=Lax` on the cookie. Admin POST
  routes like `/api/admin/users/{id}/promote` were CSRF-trivial.
- **Backup snapshot leak** — `dump_all_tables_to_json` wrote
  `users.password_hash` and `user_sessions.session_token` (live bearer
  credentials) into JSON files that get pushed to GitHub when
  `BACKUP_REPO_URL` is set.
- **`.env.production` placeholder admin creds** — local file shipped
  `admin / admin123456789`, passed length gates, no rotation enforcement.
- **`X-Forwarded-For` trusted unconditionally** — audit IPs were
  attacker-forgeable on any direct-to-uvicorn deploy.
- **No rate limit on `/api/auth/login` and `/api/auth/register`** —
  online brute force was bounded only by bcrypt(rounds=12) (~14k
  guesses/hour/thread).

### Frontend (Critical / High)

- **`useLock` cleanup beacon ignored `VITE_API_BASE_URL`** — keepalive
  POST hit the SPA origin instead of the API on split-origin deploys;
  the 5-minute server TTL became the de-facto cleanup.
- **`useDraft.debouncedSave.cancel` never called on docId change** —
  pending 2-second timer for doc A could PUT after user navigated to
  doc B (root of the "stale draft shadows shared annotation" symptom).
- **`pickNextInFeedAcrossPages` lacked a recursion-depth ceiling** —
  could spin indefinitely under flaky network + SSE racing.
- **Clipboard copy toasted success on rejection** — three admin call
  sites swallowed the rejection and showed "Kopyalandı" even when
  the clipboard write failed.
- **`'sayi'` was a dead sort key** — store accepted it, menu couldn't
  render it; a stale persisted sort would survive rehydration.

### Backend (High)

- **`save_annotation` lost-update race** — prior-state read outside
  the `BEGIN` transaction.
- **`register()` non-transactional + IntegrityError → 500** instead of
  409 on concurrent same-username registration.
- **Unbounded/empty Pydantic fields** on RotateInvite/Login/SaveAnnotation/Drafts.
- **CSV formula injection** — annotator-typed cells starting with `=`,
  `+`, `-`, `@` would auto-execute when an admin opened the CSV.
- **Admin audit/system-events returned raw JSON strings** instead of
  parsed dicts (inconsistent with the rest of the API surface).

### Perf / A11y (High)

- **`COUNT(*)` on every paged feed fetch** over the 17.9k-row anti-join
  (the single hottest scan in the codebase) — worst case 360 full
  scans for one user scroll.
- **`DocListItem` re-rendered every parent state tick** — missing
  `React.memo` + inline `onClick` factory; SSE invalidations repainted
  the entire visible window.
- **Topbar thundered 3 requests on every window-focus** — three queries
  with `refetchOnWindowFocus: true` redundant with SSE.
- **`AppShell` missing skip-link** — keyboard users had to Tab through
  ~10 topbar stops to reach the doc list.

### Quality / DX (High)

- **Lock TTL doc strings disagreed with implementation by 3×** —
  README + 3 toast strings claimed 90s, backend default is 300s.
- **README test counts stale** by ~30 on both sides.
- **`FeedTab` declared in two parallel modules** (latent drift hazard).
- **`emptyRef`/kanun-presence regex duplicated** across 3 sites.

## 3 — Fixes applied

Seven atomic commits on `main`:

| SHA | Scope | Notes |
|-----|-------|-------|
| `97be06d` | test infra | docker-smoke daemon skip + asyncio loop-scope warning |
| `d3c6ab9` | sec batch 1 | Origin middleware, backup column whitelist, XFF opt-in, prod gates, `.env.production` cleanup |
| `14220db` | backend high | save/register transactions, validators, rate limit, CSV injection guard, admin audit JSON decode |
| `c834b34` | frontend high | useLock beacon, useDraft cancel, nextDoc depth, clipboard, `sayi` drop, placeholder email |
| `5c5c10c` | perf + a11y | elide COUNT after page 0, memoize DocListItem, skip-link, calmer polling |
| `880f836` | quality | lock TTL docs, README test counts, FeedTab dedup, emptyRef dedup |
| `48de3fb` | mediums + lows | pagination, status codes, error shapes, typos, aria-labels, formatYmd unification, etc. |

### Net new files
- `backend/shared/csrf.py` — Origin/Referer ASGI middleware (production-only enforcement)
- `backend/shared/rate_limit.py` — in-memory sliding-window per-IP limiter
- `tests/test_csrf_middleware.py` — 9 cases
- `tests/test_prod_enforce.py` — 13 cases
- `tests/test_rate_limit.py` — 7 cases
- `POLISH_BACKLOG.md`, `POLISH_REPORT.md` (this file)

### Findings deferred (intentional)

- **S7** session-token hash-at-rest — corrects defense-in-depth but
  touches every auth call site; S1 (backup column whitelist) nullifies
  the practical leak.
- **Q5** add `.github/workflows/ci.yml` — new infrastructure beyond
  polish scope; recommended as a follow-up.
- **DocList row stable-id keys for ReferenceCard delete-middle focus
  jump** — requires `useReferencesState` reducer audit; safe but bigger
  than other Mediums.
- **Session cookie `__Host-` prefix** — would break staging deploys
  that share a parent domain.
- **Password complexity dictionary** — UX scope creep + new dependency.
- **SPA path-traversal symlink edge case** — no current user-upload
  surface.
- **PAT in `.git/config`** — touches credential plumbing.
- **Vitest coverage thresholds enabled** — would surface real gaps
  requiring new tests; left documented but not enforced.
- **Bundle / vite chunk-split** — informational warning at 883KB JS,
  not a regression.

## 4 — Tests + checks run

Final verification (post-batch-6):

```text
Backend  .venv/bin/python -m pytest tests -q
         → 841 passed, 3 skipped (docker-smoke; daemon unreachable)
         (was 809 + 3 errors at start; +32 net new tests, +3 errors → +3 skipped)

Frontend npm run lint        → clean
         npm run typecheck   → clean
         npm run test:run    → 501 / 501 passing
         npm run build       → succeeds (informational chunk-size warning)
         npm run e2e         → 9 / 9 passing
                              (was 10; -1 deleted by L3 dead-test removal)
```

## 5 — Remaining risks

1. **Backup operator hygiene** — the new prod-enforce rejects obvious
   placeholder admin passwords, but `BACKUP_REPO_URL` privacy is still
   an operator concern: bcrypt hashes survive in snapshots. Document
   this in the deployment runbook before publishing the GitHub backup.
2. **Pre-existing SSE-broker close-after-shutdown bug** — visible in
   the e2e logs as `sqlite3.ProgrammingError: Cannot operate on a closed
   database` in `_build_online_payload`. Not introduced or worsened by
   this polish phase; flagged in the original session memory as a
   pre-existing item out of scope.
3. **Test memory drift** — the assistant's prior session memory
   contains an incorrect "CSRF was implemented" note from a previous
   handoff. That note has been overridden in practice by `d3c6ab9`; a
   future memory rewrite should reflect the actual implementation.
4. **POLISH_BACKLOG.md DEFER list** survives as a follow-up backlog;
   each item is real but out of polish scope.
5. **Skill memory `feedback_csrf_implemented` is contradicted** — if
   any future automation reads it, it will misroute requests.

## 6 — Manual verification steps (optional follow-up)

- Set `ENVIRONMENT=production`, leave `ALLOWED_ORIGINS` empty: lifespan
  should fail with the new prod_enforce error block.
- Set `ALLOWED_ORIGINS=https://example.test`, POST to
  `/api/admin/invite/rotate` with `Origin: https://evil.test`: should
  receive HTTP 403 `{ "error": "origin_not_allowed" }`.
- Block clipboard permission in DevTools, click the admin "Kopyala"
  button in the rotate-invite dialog: should see "Kopyalanamadı" toast.
- Trigger 11 rapid `/api/auth/login` POSTs from the same IP: 11th
  returns 429 with `Retry-After`.
- Verify `data/backup/latest.json` after a backup cycle has no
  `user_sessions` key and `users[*].session_token` is absent.

## 7 — Run commands

```bash
# Backend tests (excludes docker-smoke when daemon is down)
.venv/bin/python -m pytest tests -q

# Frontend unit + integration tests
cd frontend && npm run test:run

# End-to-end (Playwright)
cd frontend && npm run e2e
# First-time: npm run e2e:install

# Lint + typecheck (frontend)
cd frontend && npm run lint && npm run typecheck

# Production-shaped build
cd frontend && npm run build  # outputs to ../backend/static/

# Dev server
cd frontend && npm run dev    # SPA on :5173 (proxies /api → :8000)
DATA_DIR=./data .venv/bin/python -m uvicorn backend.main:app --reload
```

## 8 — Release-readiness verdict

**Ready to ship.** Critical security gaps closed; perf-critical paths
de-thundered; UX polish surfaced; tests green across backend, frontend
unit, e2e, lint, typecheck, build. Items in the DEFER list are real
but bounded and tracked; none is a release blocker for a self-hosted
internal annotation platform.

Recommended follow-up sequence (not part of this sprint):

1. Wire `gen:types:check` + `pytest` into a CI workflow (Q5).
2. Open the session-token hash-at-rest refactor (S7) as a tracked
   defense-in-depth task.
3. Restructure `frontend/src/lib/` into the documented sub-folders
   (`schemas/`, `text/`).
4. Address the pre-existing SSE close-after-shutdown error log noise.
