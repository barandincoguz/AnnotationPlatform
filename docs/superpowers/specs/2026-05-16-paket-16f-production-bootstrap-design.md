# Paket 16f — Production Bootstrap

**Status:** APPROVED FOR PLANNING
**Date:** 2026-05-16
**Scope:** Minimal (3 day) — wire `BOOTSTRAP_ADMIN_USERNAME` + add production secret enforcement + write deployment runbook

## Context

Paket 15 shipped a working Dockerfile + docker-compose. Paket 12 shipped backup/restore. Together they cover containerization and durability. What is still missing for a production deployment:

1. **First-admin onboarding is manual.** Production operator runs `docker exec ... create-invite ...` then `... promote-admin ...` — two ad-hoc steps. `BOOTSTRAP_ADMIN_USERNAME` env var is declared in `config.py` but never read.
2. **Default `SESSION_SECRET` is unsafe.** `dev-secret-DO-NOT-USE-IN-PROD` is the default in `config.py`. A production deployment that forgets to set it boots successfully and is silently insecure.
3. **Deployment is undocumented.** No runbook, no `.env.production` template, no restore drill, no reverse proxy guidance.

Out of scope (deferred — would be Paket 16f.1 or 17): WAL-lock safety in restore CLI, production compose overlay (resource limits, log driver), CI/CD pipeline.

## Architecture

| Component | File | Type | Scope |
|---|---|---|---|
| Env config | `backend/config.py` | edit | Add `ENVIRONMENT`, `BOOTSTRAP_ADMIN_PASSWORD` |
| Boot guard | `backend/main.py` | edit | Lifespan: prod secret check + bootstrap admin seed |
| Bootstrap logic | `backend/users/service.py` | edit | `seed_bootstrap_admin(db, *, username, password)` |
| Runbook | `docs/deployment.md` | new | Full deploy walkthrough |
| Env template | `.env.example` | edit | Add new vars + production guidance |
| Bootstrap tests | `backend/tests/test_bootstrap.py` | new | 8 tests |
| Enforce tests | `backend/tests/test_prod_enforcement.py` | new | 6 tests |
| Test fixture | `backend/tests/conftest.py` | edit | Set `ENVIRONMENT=test` so existing 768 tests stay green |

## D1 — Bootstrap admin behavior (LOCKED)

**Trigger:** Lifespan startup, after migrations.

**Conditions to seed:**
1. `BOOTSTRAP_ADMIN_USERNAME` set AND `BOOTSTRAP_ADMIN_PASSWORD` set (both non-empty)
2. `users` table has zero rows where `role='admin' AND is_active=1`
3. Username not already taken by non-admin user

**Behavior on seed:**
- Insert user with: `role='admin'`, `is_active=1`, `has_passed_training=1`, `has_seen_manual=1`
- Bypass invite code requirement
- Password hashed via existing `auth.hash_password`
- Audit log entry: `action_type='bootstrap_admin_seed'`, `target_kind='user'`, `target_id=new_user_id`, `metadata_json='{"source":"lifespan"}'`
- Stderr log ONCE: `"Bootstrap admin '<username>' created (id=<id>)"`

**Idempotency:** Second boot with same env vars → no-op (admin already exists, conditions check fails silently).

**Fail-fast errors:**
- Username taken by non-admin → `RuntimeError("BOOTSTRAP_ADMIN_USERNAME='<x>' conflicts with existing non-admin user")`
- Password missing while username set → `RuntimeError("BOOTSTRAP_ADMIN_USERNAME set but BOOTSTRAP_ADMIN_PASSWORD missing")`
- Password < 12 chars in production mode → `RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must be ≥12 chars in production")`

## D2 — Production secret enforcement (LOCKED)

**Trigger:** Lifespan startup, BEFORE migrations (fail-fast at app boot).

**Detection:** `ENVIRONMENT` env var. Valid values: `development` (default), `test`, `production`. Any other value → `RuntimeError("ENVIRONMENT must be one of: development, test, production")`.

**When `ENVIRONMENT=production`, enforce all:**

| Check | Rule | On fail |
|---|---|---|
| `SESSION_SECRET` not default | `!= "dev-secret-DO-NOT-USE-IN-PROD"` | `RuntimeError`, exit |
| `SESSION_SECRET` length | `len() >= 32` | `RuntimeError`, exit |
| `BOOTSTRAP_ADMIN_PASSWORD` if set | `len() >= 12` | `RuntimeError`, exit |

**When `ENVIRONMENT=development` or `test`:** zero enforcement, existing defaults work.

**Warning (stderr, not error) in production:**
- `BACKUP_REPO_URL` empty → `"WARNING: no backup configured (BACKUP_REPO_URL empty)"`

**Error format (single block on stderr):**
```
FATAL: production mode enforcement failed:
  - SESSION_SECRET must not be the default placeholder
  - SESSION_SECRET must be at least 32 characters (current: 12)
Set ENVIRONMENT=development to disable enforcement.
```

Exit code non-zero. Docker Compose `restart: unless-stopped` will loop, but stderr makes diagnosis trivial.

## D3 — Lifespan ordering (LOCKED)

```python
@asynccontextmanager
async def lifespan(app):
    # 1. Validate env (fail-fast before any DB work)
    enforce_production_secrets()

    # 2. Ensure dirs + run migrations (existing)
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    apply_migrations(conn, discover_migrations())

    # 3. Bootstrap admin (idempotent, conditions-checked internally)
    seed_bootstrap_admin(
        conn,
        username=config.BOOTSTRAP_ADMIN_USERNAME,
        password=config.BOOTSTRAP_ADMIN_PASSWORD,
    )

    # 4. Existing startup tasks (backup loop scheduling etc.)
    ...
    yield
    # shutdown
```

## D4 — `.env.example` updates (LOCKED)

Add these vars with grouped comments:

```bash
# ---- Environment ----
# Valid: development (default), test, production
# In production: SESSION_SECRET must be set + ≥32 chars, BOOTSTRAP_ADMIN_PASSWORD must be ≥12 chars
ENVIRONMENT=development

# ---- Session ----
# Generate with: openssl rand -hex 32
SESSION_SECRET=dev-secret-DO-NOT-USE-IN-PROD
SESSION_COOKIE_NAME=anotasyon_session

# ---- Bootstrap admin (first-run only) ----
# When admins table empty AND both vars set, lifespan creates an admin user.
# After first successful seed, unset these from env (security hygiene).
BOOTSTRAP_ADMIN_USERNAME=
BOOTSTRAP_ADMIN_PASSWORD=

# ---- Backup (optional, GitHub remote) ----
BACKUP_REPO_URL=
GITHUB_PAT=
```

## D5 — Deployment runbook structure (LOCKED)

File: `docs/deployment.md`, single file ~250 lines.

Sections:

1. **Prerequisites** — Docker 24+, compose v2, disk 5GB+, optional GitHub PAT for backup
2. **Quick start** (5 steps)
   - `cp .env.example .env.production && edit`
   - Generate `SESSION_SECRET`: `openssl rand -hex 32`
   - Set `BOOTSTRAP_ADMIN_USERNAME` + `BOOTSTRAP_ADMIN_PASSWORD`
   - `ENVIRONMENT=production docker compose --env-file .env.production up -d`
   - Login at `https://host/login`, rotate bootstrap password via admin panel
3. **Env reference table** — every var: name, required?, prod-required?, example, notes
4. **First admin walkthrough** — what bootstrap does, when to unset env vars after seed
5. **Backup setup** — create empty GitHub repo, generate fine-grained PAT (contents:write only), set vars, verify first push via `system_events` log
6. **Restore drill** — `docker compose stop app` (WAL safety), `docker compose run --rm app python -m backend.cli restore-from-github`, verification queries
7. **Reverse proxy** — minimal Caddyfile + nginx snippet covering HTTPS termination + SSE WebSocket upgrade
8. **Logs + observability** — `docker compose logs -f`, `/api/health` (liveness) vs `/api/health/db` (readiness/manual)
9. **Upgrade procedure** — pull, `docker compose down`, `docker compose up -d --build`, migrations auto-run
10. **Troubleshooting** — common stderr → cause → fix table

## D6 — Test strategy (LOCKED)

**`backend/tests/test_bootstrap.py`** (8 tests):

| # | Test | Asserts |
|---|---|---|
| 1 | `test_seed_creates_admin_when_no_admin` | Empty admins + env set → admin row exists, role=admin, is_active=1, has_passed_training=1 |
| 2 | `test_seed_idempotent` | Run twice → 1 admin row, no error |
| 3 | `test_seed_skipped_when_admin_exists` | Pre-existing admin → no new user created |
| 4 | `test_seed_fails_if_username_taken_by_user` | Existing non-admin user same name → RuntimeError |
| 5 | `test_seed_skipped_when_env_missing` | Only USERNAME set, no PASSWORD → skip silently |
| 6 | `test_seed_writes_audit_log` | After seed: admin_audit_log row with action_type='bootstrap_admin_seed' |
| 7 | `test_seed_password_hashed_correctly` | Password not stored as plain, `auth.verify_password` passes |
| 8 | `test_seed_admin_can_login` | After seed: POST `/auth/login` with creds → 200 + session cookie |

**`backend/tests/test_prod_enforcement.py`** (6 tests):

| # | Test | Asserts |
|---|---|---|
| 1 | `test_prod_rejects_default_secret` | ENV=production + default secret → RuntimeError |
| 2 | `test_prod_rejects_short_secret` | ENV=production + 16-char secret → RuntimeError |
| 3 | `test_prod_accepts_strong_secret` | ENV=production + 32-char random → boot OK |
| 4 | `test_prod_rejects_short_bootstrap_password` | ENV=production + 8-char password → RuntimeError |
| 5 | `test_dev_allows_default_secret` | ENV=development → no enforcement, boot OK |
| 6 | `test_prod_warns_no_backup_url` | ENV=production + empty BACKUP_REPO_URL → stderr WARNING, boot OK |

**conftest.py impact:** Add fixture-scope env var: `monkeypatch.setenv("ENVIRONMENT", "test")` in autouse fixture so existing 768 tests stay green without manual edits.

## Acceptance criteria

- [ ] Backend tests: 768 existing + 14 new = 782/782 pass
- [ ] `ENVIRONMENT=production` + default secret → boot exits with stderr error
- [ ] `ENVIRONMENT=production` + strong secret + bootstrap vars → admin created, login works
- [ ] `ENVIRONMENT=development` (or unset) → existing behavior unchanged
- [ ] `docs/deployment.md` exists, every section populated
- [ ] `.env.example` documents all 7+ vars
- [ ] Docker rebuild succeeds, healthcheck passes
- [ ] Manual end-to-end: fresh `docker compose up` with prod env → can login → admin panel works
- [ ] No frontend changes (this paket is backend + docs only)

## Non-goals

- WAL-lock detection in restore CLI (deferred)
- Production compose overlay with resource limits (deferred)
- CI/CD pipeline (deferred)
- Multi-tenant or horizontally-scaled deploys (out of scope — SQLite single-worker by design)
- HTTPS/TLS in app (terminated at reverse proxy)
- Log aggregation / metrics export (use `docker logs` + `system_events` table)

## Risks

| Risk | Mitigation |
|---|---|
| Existing tests fail due to ENVIRONMENT default | conftest autouse fixture sets `test` |
| Bootstrap admin password leaked in logs | Only username logged, never password |
| Operator forgets to unset BOOTSTRAP_ADMIN_PASSWORD after seed | Runbook explicit; idempotency means stale env vars do nothing |
| Reverse proxy misconfig blocks SSE | Runbook includes Caddyfile + nginx examples with `proxy_buffering off` for `/api/events` |
