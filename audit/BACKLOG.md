# Phase 5 Audit Backlog — 2026-05-23

**Source:** Wave 1 read-only audit, 5 dimensions (D1 sec, D2 BE, D3 FE, D4 perf, D6 deploy).

**Counts:** 0 Critical · 10 High · 14 Medium · 20 Low · 28 Info = **72 findings**.

**User action required:** Fill `Verdict` per row before Wave 2 starts.

Valid verdicts:
- `APPLY-W2` — fix in Wave 2 (default for Critical + High that aren't features)
- `APPLY-W2.5-ADD` — adds to D12 build scope (only for clearly-missing features that aren't already in D12)
- `APPLY-W3` — apply during polish/ops wave
- `DEFER` — Phase 6 backlog (add one-line reason)
- `INFO-NO-ACTION` — leave as-is

---

## High Severity (10)

| ID | Dim | Area | Description | File:Line | Verdict |
|----|-----|------|-------------|-----------|---------|
| SEC-1 | D1 | mirror/neon_client | Postgres SQL identifiers (`baran_{table}`, columns, PK) interpolated unquoted via f-strings; no `psycopg.sql.Identifier`. Not exploitable via HTTP today but unsafe if column names ever leak attacker control. | `backend/mirror/neon_client.py:96,181,184-186,192,203-204` | |
| BE-1 | D2 | locks/service | `heartbeat()` reads + writes without transaction; concurrent `acquire()` can swap owner mid-flight, heartbeat refreshes wrong owner's expiry. | `backend/locks/service.py:149-166` | |
| BE-2 | D2 | locks/service | `sweep_expired()` SELECT then DELETE without wrapping txn; race vs concurrent `heartbeat()` can delete lock the holder still believes active → spurious `NotLockHolder` on next heartbeat. | `backend/locks/service.py:186-195` | |
| BE-3 | D2 | annotations/service | `save_annotation()` + `set_complete()` check lock ownership BEFORE `BEGIN IMMEDIATE`; `BEGIN IMMEDIATE` does not re-verify ownership. TOCTOU — guard is advisory only. | `backend/annotations/service.py:212-226,392-395` | |
| BE-4 | D2 | training/service | `submit_quiz`/`submit_annotation` + `finalize_if_complete` have no transaction wrapper; two concurrent submits for different gold_ids race the `annotation_details_json` UPDATE → last-writer-wins clobber, one result silently lost. | `backend/training/service.py:313-358,361-444` | |
| BE-5 | D2 | users/service | `demote_admin`/`disable_user` `count_active_admins()` then UPDATE in two autocommit statements; two concurrent demotions when 2 admins remain can both pass `<=1` guard → leave zero active admins. | `backend/users/service.py:272-293,296-316` | |
| BE-6 | D2 | users/service | `rotate_invite_code()` deactivates all codes then INSERTs new one in two statements; concurrent registration in the gap finds no valid code → `InvalidInviteCode` despite freshly issued code. | `backend/users/service.py:340-362` | |
| FE-1 | D3 | vitest/jsdom | jsdom/undici AbortSignal cross-realm incompatibility breaks 34 vitest tests across 7 files. Root: openapi-fetch passes an undici-realm AbortSignal into jsdom's fetch, which fails `instanceof` check. Fix direction: switch `environment: 'happy-dom'` OR adjust `vitest.config.ts` to bridge realms. | `frontend/vite.config.ts` + 7 affected test files | |
| B-01 | D4 | annotations/service | `_count_unique_users()` N+1 COUNT inside every save; full version-chain rescan. Adds +15-20ms per save at 100+ versions. | `backend/annotations/service.py:102-107` | |
| B-02 | D4 | mirror/dispatcher | Concurrent-dispatcher safety unverified; two instances would both drain same rows → lost rows / duplicate applies. No advisory lock or single-instance enforcement. | `backend/mirror/dispatcher.py:170-189` | |

## Medium Severity (14)

| ID | Dim | Area | Description | File:Line | Verdict |
|----|-----|------|-------------|-----------|---------|
| SEC-2 | D1 | mirror/neon_client | `NeonClient.connect` logs raw `psycopg.OperationalError`; on some psycopg3 builds the exception string includes DSN host/user/database. | `backend/mirror/neon_client.py:76` | |
| SEC-3 | D1 | secrets | `.env.production` ships with live `admin`/`admin123456789` values; placeholder-blocker catches it but file should use `<REPLACE_ME>` like `.env.example`. | `.env.production:11-12` | |
| SEC-4 | D1 | secrets | `.env.local` retains live Neon credentials that the file's own comment marks as compromised. Gitignored + never committed but persists on disk. | `.env.local:12-16` | |
| SEC-5 | D1 | csrf | `OriginCheckMiddleware` bypassed when `ENVIRONMENT != "production"`; staging deploy set to `development` silently disables CSRF. No `staging` value supported. | `backend/shared/csrf.py:56-58` | |
| BE-9 | D2 | mirror/dispatcher | At-least-once delivery semantics undocumented; crash between `neon.apply()` success and `_mark_delivered` commit → duplicate send on restart. | `backend/mirror/dispatcher.py:113-136,175-191` | |
| BE-10 | D2 | mirror/dispatcher | Dead-lettered rows (`retry_count >= max_retries`) have no operator re-queue path. No admin endpoint, CLI, or documented SQL. Permanent mirror divergence after retry exhaustion. | `backend/mirror/dispatcher.py:62-78` | |
| BE-11 | D2 | backup/service | f-string interpolation of `{table}` in restore_from_snapshot; whitelisted today, but if `col_list` ever sees attacker-controlled column names through future code paths, surface is broad. | `backend/backup/service.py:46-72`, `backend/backup/restore.py:63-88` | |
| BE-12 | D2 | migrations/runner | `applied_versions()` read outside per-migration `BEGIN IMMEDIATE`; concurrent dual-boot can crash on schema_migrations PK collision. | `backend/migrations/runner.py:45-68` | |
| FE-2 | D3 | useLock | Heartbeat POST has no `AbortController.signal`; dangling fetch on every release/route-change. Accumulates across navigations. | `frontend/src/hooks/useLock.ts:85-107` | |
| FE-3 | D3 | useLock | `release()` doesn't set `cancelledRef.current = true` before await; tight race with effect cleanup beacon under strict-mode double-invoke. | `frontend/src/hooks/useLock.ts:153-172` | |
| FE-4 | D3 | useSSE | `onerror` invalidates `feedKeys.all` + `usersKeys.online()` on every CONNECTING transition with no debounce → unthrottled refetch storm on flaky link. | `frontend/src/hooks/useSSE.ts:32-39` | |
| B-03 | D4 | shuffle/feed COUNT | New-tab feed COUNT(*) anti-join scans ~17.9k rows on first page; already mitigated via offset>0 return-None; flagged for Wave 4 load test observation only. | `backend/shuffle/service.py:338-356` | |
| F-01 | D4 | auth/me | `refetchOnWindowFocus: true` + `staleTime: 60s` triggers a full `/api/auth/me` on every tab return; cumulative across N tabs. SSE already dispatches role/perm changes. | `frontend/src/api/queries/auth.ts:22` | |
| F-02 | D4 | polling | notifications 60s + users 60s polling fallbacks + `refetchOnWindowFocus: true` add ~120 req/hr per idle user. Intentional SSE-drop safety; observation only. | `frontend/src/api/queries/notifications.ts:32,46`, `frontend/src/api/queries/users.ts:23` | |
| D6-001 | D6 | docker image | `__pycache__` directories present in runtime image (65+ dirs). Inflates image size. `.dockerignore` lists pattern but pip caches them during install. | `Dockerfile + .dockerignore:2-4` | |
| D6-002 | D6 | docker image | `test_prod_enforcement.py` present in runtime at `/app/backend/tests/`. Tests should not ship. | `Dockerfile (COPY backend/ stage)` | |

## Low Severity (20)

| ID | Dim | Area | Description | File:Line | Verdict |
|----|-----|------|-------------|-----------|---------|
| SEC-6 | D1 | brute-force | Rate limiter in-memory per-IP single-process; multi-worker deploy multiplies budget. No horizontal scale today. | `backend/shared/rate_limit.py:1-17`, `backend/users/routes.py:29-38` | |
| SEC-7 | D1 | brute-force | `/api/auth/logout` POST has no rate limit; unauth caller can pollute access logs. Idempotent + cheap. | `backend/users/routes.py:115-125` | |
| SEC-8 | D1 | mirror/config | `NEON_MIRROR_URL` cached at import; runtime rotation requires `reload_from_env()` which has no production guard. | `backend/mirror/config.py:45-53` | |
| SEC-9 | D1 | csrf | OriginCheckMiddleware uses `latin-1` decode without `errors=`; crafted non-latin-1 Origin header raises UnicodeDecodeError → 500 instead of 403. | `backend/shared/csrf.py:68` | |
| BE-7 | D2 | users/service | `login()` INSERT session row as autocommit; if INSERT fails after `generate_session_token()` returned, user gets unusable cookie + persistent 401. | `backend/users/service.py:167-202` | |
| BE-13 | D2 | users/service | `promote_admin`/`enable_user` no-op when already in target state but still write audit row → misleading log entries. | `backend/users/service.py:251-269,319-337` | |
| BE-15 | D2 | training/service | `start_attempt()` COUNT-then-INSERT race; concurrent calls produce duplicate `attempt_number`. | `backend/training/service.py:237-281` | |
| BE-16 | D2 | sse/routes | `_stream_for_user` holds `db` connection open for entire SSE lifetime (hours). Used once for `_build_online_payload`; should be closed after. | `backend/sse/routes.py:58-106` | |
| BE-17 | D2 | locks/service | `get_lock()` does DELETE as side effect (expired sweep); read-intent call performs write. Surprising semantics; not broadcast as SSE event. | `backend/locks/service.py:72-82` | |
| FE-6 | D3 | sse handlers | `lockHandlers.ts` + `feedHandlers.ts` use raw `['feed']` literal instead of `feedKeys.all`; drift hazard. | `frontend/src/hooks/sse/lockHandlers.ts:37,48`, `frontend/src/hooks/sse/feedHandlers.ts:18` | |
| FE-7 | D3 | useReferencesState | `hydrated: hydratedRef.current` returned at render time; not a reactive signal. Field name misleading. No UI regression today (callers use `refs.list` instead). | `frontend/src/hooks/useReferencesState.ts:122` | |
| FE-8 | D3 | annotateStore | No `onRehydrateStorage` validator; unknown persisted `SortKey` from stale tab → 422 on backend → broken feed until reload. | `frontend/src/stores/annotateStore.ts:77-96` | |
| FE-9 | D3 | trainingStore | `migrate` pass-through pattern brittle for future v1→v2 bump; current v1→v1 no-op correct. | `frontend/src/stores/trainingStore.ts:134-137` | |
| FE-10 | D3 | DocList | `useEffect` lists whole `virtualizer` object in deps; new ref every render → effect fires on every tick (same class as the `feed` object bug already fixed). IS_TEST guard prevents test OOM. | `frontend/src/components/annotation/DocList.tsx:46-54` | |
| B-04 | D4 | annotations/service | `_count_unique_users()` runs every save even when result is 1 or unchanged. +5ms write latency. | `backend/annotations/service.py:156` | |
| D6-005 | D6 | cookie | `Secure` flag conditional on `is_production()`; if `TRUST_FORWARDED_FOR=1` set without HTTPS proxy, cookie transmits insecure. Operator diligence required. | `backend/users/routes.py:104-111` | |
| D6-007 | D6 | csrf ops | `ALLOWED_ORIGINS` enforced at startup; deploy requires explicit origin list. Documented + fail-fast. | `backend/shared/prod_enforce.py:81-86` | |
| D6-008 | D6 | healthcheck | HEALTHCHECK probes `/api/health` only (not `/api/health/db`); intentional to avoid transient-lock restart loops. | `Dockerfile:82-83`, `backend/main.py:155-174` | |
| D6-009 | D6 | shutdown | Lifespan shutdown stops background tasks but no explicit in-flight request drain; relies on uvicorn graceful timeout. | `backend/main.py:94-117` | |
| D6-015 | D6 | PID 1 | Dockerfile `exec` ensures uvicorn becomes PID 1 with direct SIGTERM. workers=1 explicit. | `Dockerfile:77` | |
| D6-016 | D6 | image size | `git` (~109 MB) in runtime image for optional `BACKUP_REPO_URL` push; deployments without backup still pay cost. Acknowledged Paket 17 deferred. | `Dockerfile:49-52` | |

## Info Severity (28)

| ID | Dim | Area | Description | File:Line | Verdict |
|----|-----|------|-------------|-----------|---------|
| SEC-10 | D1 | mirror/neon_client | `NeonClient.dsn` public attribute; `repr()` would leak. No current serialization path. | `backend/mirror/neon_client.py:52-53` | |
| SEC-11 | D1 | exports | JSONL export confirmed clean (no `password_hash`/`session_token`). | `backend/exports/service.py:46-66` | |
| SEC-12 | D1 | exports | CSV injection guard OWASP-compliant. Confirmed clean. | `backend/exports/service.py:117-133` | |
| SEC-13 | D1 | admin-audit | 13 sampled admin routes all call `log_admin_action` correctly. | multiple | |
| BE-8 | D2 | training/service | `finalize_if_complete` dual early-exit logic non-obvious but correct on both pass + fail paths. | `backend/training/service.py:361-381` | |
| BE-14 | D2 | annotations/service | `_count_unique_users` ordering dependency (INSERT first, then COUNT) subtle but correct under SQLite serialization. | `backend/annotations/service.py:143-179` | |
| BE-18 | D2 | shared/auth | bcrypt work factor 12 appropriate; constant-time compare; `secrets.token_urlsafe(32)` correct. SHA-256 IP hashing is weak pseudonymisation (known). | `backend/shared/auth.py:1-31` | |
| BE-19 | D2 | sse/broker | `publish_to` drops full queues (maxsize=100); cleanup correctly guarded. No connection leaks. | `backend/shared/sse.py:41-76` | |
| BE-20 | D2 | backup/restore | `PRAGMA defer_foreign_keys=ON` correct; `user_sessions` clear at end is documented. | `backend/backup/restore.py:48-100` | |
| FE-5 | D3 | useSSE | `meId` dep correctly re-registers listeners on login change. Intentional. | `frontend/src/hooks/useSSE.ts:20-21` | |
| FE-11 | D3 | useDraft | `deleteMutation` no signal; intentional per comment (mutation API + abort + rev pattern incompatibility). | `frontend/src/hooks/useDraft.ts:192-213` | |
| FE-12 | D3 | App.tsx | No admin route slot reserved for future Notifications admin; scope note for Wave 2.5 alignment. | `frontend/src/App.tsx:121-131` | |
| FE-13 | D3 | notifications | `useNotificationsHistory` has `refetchOnWindowFocus: true`, `useUnreadNotifications` doesn't; asymmetry uncommented. | `frontend/src/api/queries/notifications.ts:15-48` | |
| F-04 | D4 | feed query | `staleTime: 30_000` appropriate; SSE drives invalidation. Well-tuned. | `frontend/src/api/queries/feed.ts:60` | |
| S-01 | D4 | sse broker | Queue maxsize=100 acceptable for 2-30 users; bump to 500 only at 100+ concurrent. | `backend/shared/sse.py:27` | |
| D-01 | D4 | dispatcher config | Batch 100 + 0.1s inter-batch + 5s empty-sleep + 1s→16s backoff appropriate. | `backend/mirror/config.py:36-42` | |
| D6-003 | D6 | env template | `.env.production` placeholder "admin" substring fails `enforce_production_secrets()` validation. Documented. | `.env.production:11-12` | |
| D6-004 | D6 | bootstrap | `BOOTSTRAP_ADMIN_PASSWORD` remains in template after first run; comments instruct removal. Documented. | `.env.production:9-12` | |
| D6-006 | D6 | reverse-proxy | `X-Forwarded-For` parsing opt-in via `TRUST_FORWARDED_FOR=1`, defaults disabled. RFC 7239 compliant. | `backend/config.py:30-34`, `backend/users/deps.py:85-89` | |
| D6-010 | D6 | multi-stage build | Builder `--target=/install`; runtime single-layer copy. Layer hygiene good. | `Dockerfile:7-77` | |
| D6-011 | D6 | non-root user | UID 1000 / GID 1000 (appuser); predictable for bind mounts. | `Dockerfile:58-68` | |
| D6-012 | D6 | env passthrough | 9 env vars from host, all optional with fallbacks. Secrets correctly passed not baked. | `docker-compose.yml:9-17` | |
| D6-013 | D6 | restart policy | `restart: unless-stopped` appropriate self-hosted. | `docker-compose.yml:18` | |
| D6-014 | D6 | healthcheck | Compose healthcheck duplicates Dockerfile; defensive, harmless. | `docker-compose.yml:19-25` vs `Dockerfile:82-83` | |

## DEFER list re-evaluation (2026-05-17 polish)

Verdict context only; no new findings here. From `audit/SEC.md`:

| Original ID | Current re-eval | Verdict |
|-------------|-----------------|---------|
| S7 (session token sha256 at rest) | S1 fix (no token leak in backup) slightly raises relative weight, but threat model unchanged | DEFER still valid; phase-6 if read replicas added |
| Q5 (CI workflow) | No `.github/workflows/` yet; expanded surface (Phase 4 mirror + 69 triggers) | Phase 5 W3 covers this (D8) |
| Bundle reorg `lib/schemas/` | No change | DEFER — mechanical |
| `__Host-` cookie prefix | No change | DEFER — staging concern unchanged |
| Password complexity rules | 8-char min in place; no dictionary | DEFER — UX scope |
| Common-password dictionary | Not implemented | DEFER — new dependency |
| SPA path-traversal symlink | No upload surface added | DEFER — N/A |
| PAT in `.git/config` | `GITHUB_PAT` from env only | DEFER — operator-education item |
| Vitest coverage thresholds | No change | DEFER |
| DocList full virtualization | Not a security item | DEFER |
| Custom-id keys reducer audit | Not a security item | DEFER |
| `lib/` restructure | Not a security item | DEFER |

---

## Summary

| Sev | Count |
|-----|-------|
| Critical | 0 |
| High | 10 |
| Medium | 14 |
| Low | 20 |
| Info | 28 |
| **Total** | **72** |

### High-priority themes

1. **Multi-step writes without `BEGIN IMMEDIATE`** (5 of 10 High): BE-1, BE-2, BE-3, BE-4, BE-5, BE-6 — locks heartbeat/sweep, annotation lock re-verify, training submit/finalize, admin demotion guard, invite rotation. The dominant bug class. All race-driven, all serious under multi-user concurrent load.

2. **Test infra blocker** (1 of 10): FE-1 — 34 vitest tests fail because of jsdom/undici AbortSignal cross-realm bug. Fix likely 1 commit (`environment: 'happy-dom'` or vitest config bridge).

3. **Mirror surface gaps** (3 of 10): SEC-1 (identifier quoting), B-02 (dispatcher concurrency), BE-10 (dead-letter re-queue path missing). Phase 4 close-out gaps.

4. **N+1 query in save path** (1 of 10): B-01 — `_count_unique_users` rescans full version chain per save.

### Wave 2 default recommendation (for user override)

If you APPLY-W2 all 10 High items, Wave 2 = approximately 10 atomic fix commits.
- 6 transaction-boundary fixes (BE-1, BE-2, BE-3, BE-4, BE-5, BE-6) — similar structure; could batch into ~3 commits.
- 1 test infra fix (FE-1) — 1 commit, unblocks 34 tests.
- 1 SQL quoting fix (SEC-1) — 1 commit.
- 1 dispatcher concurrency fix (B-02) — 1 commit + advisory lock or single-instance enforcement.
- 1 dead-letter re-queue (BE-10) — could be APPLY-W2.5 since it adds a new admin endpoint (not just a fix).
- 1 denorm refactor (B-01) — 1 commit if cached field path, more if schema migration.

Wave 2.5 is a clean candidate for BE-10 (operator surface) — the fix is "add an endpoint", which is the D12 shape.
