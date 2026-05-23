# D6 Deploy Config Audit — 2026-05-23

## Findings

| ID | Sev | Area | Description | File:Line | Verdict |
|----|-----|------|-------------|-----------|---------|
| D6-001 | Medium | Image Hygiene | `__pycache__` directories present in image (65+ dirs with compiled bytecode). Inflates image size; `.pyc` files are acceptable but directories should be excluded. | `.dockerignore:2-4` | `.dockerignore` lists `__pycache__/` and `*.pyc` but pip caches compiled modules during install. Use `PYTHONDONTWRITEBYTECODE=1` (present) + layer cleanup. |
| D6-002 | Medium | Image Hygiene | Test file `test_prod_enforcement.py` present in runtime image at `/app/backend/tests/`. Tests should not be shipped; belongs only in builder or post-deploy steps. | `.dockerignore:26` | Listed but not excluded from `COPY backend/` stage. Recommend explicit exclude or separate test image. |
| D6-003 | Info | Documentation | `.env.production` template contains placeholder password `admin123456789` which contains "admin" substring. Will fail `enforce_production_secrets()` validation. Correct for template documentation, but operators must be warned. | `.env.production:11-12` | ✓ Validation enforced at startup; fails fast with clear error. Comments explain removal after first seed. |
| D6-004 | Info | Bootstrap Safety | `BOOTSTRAP_ADMIN_PASSWORD` remains in `.env.production` template after first run. Comments instruct removal but template includes creds. Documentation is clear; no code issue. | `.env.production:9-12` | ✓ Documented and enforced. Operators must follow instructions manually. |
| D6-005 | Low | Cookie Security | Session cookie `Secure` flag is conditional on `is_production()` but deployment-time reverse proxy config not validated. If `TRUST_FORWARDED_FOR=1` without HTTPS proxy, cookie can be transmitted insecure. | `backend/users/routes.py:104-111` | ✓ Flag conditionally set (`secure=config.is_production()`); trust requires operator diligence. |
| D6-006 | Info | Reverse Proxy | `X-Forwarded-For` parsing only active when `TRUST_FORWARDED_FOR=1`. Defaults to `"0"` (disabled). First client IP extracted from multi-IP list. RFC 7239 compliant. | `backend/config.py:30-34`, `backend/users/deps.py:85-89` | ✓ Safe; opt-in via env. Documented. |
| D6-007 | Low | CSRF Defense | `ALLOWED_ORIGINS` must be set in production; validation enforces this at startup. Empty set rejects all POST/PUT/PATCH/DELETE. Correct design but requires operator config. | `backend/shared/prod_enforce.py:81-86` | ✓ Enforced; fail-fast startup. Operators cannot deploy without explicit origin list. |
| D6-008 | Low | Health Check | HEALTHCHECK uses HTTP check to `/api/health` but does NOT probe `/api/health/db`. Liveness decoupled from DB state (intentional per comments). Database issues surface via manual `/api/health/db` or system logs. | `Dockerfile:82-83`, `backend/main.py:155-157, 160-174` | ✓ Intentional design. Prevents transient-lock restart loops. |
| D6-009 | Low | Shutdown Drain | Lifespan shutdown stops 4 background tasks (locks_sweep, backup_loop, retention_loop, mirror_dispatcher) and waits for each. Exceptions suppressed (pass). No explicit in-flight request drain; relies on uvicorn graceful timeout. | `backend/main.py:94-117` | ⚠ Acceptable. Background tasks stopped cleanly. Uvicorn request drain handled by runtime (worker=1, SIGTERM to PID 1). |
| D6-010 | Info | Multi-Stage Build | Builder stage installs deps with `--target=/install`, runtime copies in single layer. Code layer cached separately. Layer hygiene is good; build-essential correctly not in runtime. | `Dockerfile:7-77` | ✓ Well-structured multi-stage. |
| D6-011 | Info | Non-Root User | UID 1000, GID 1000 (appuser). Predictable for bind mounts. VOLUME `/data` owned by appuser. docker-compose mounts named volume `anotasyon_data:/data` (permissions inherited at runtime). | `Dockerfile:58-68` | ✓ Correct. |
| D6-012 | Info | Env Passthrough | docker-compose passes 9 env vars from host (all optional with fallbacks). Secrets like `SESSION_SECRET`, `GITHUB_PAT` correctly passed through, not baked into image. `.env.*` files excluded from build. | `docker-compose.yml:9-17` | ✓ Correct. |
| D6-013 | Info | Restart Policy | `restart: unless-stopped` (compose standard). Respects manual stop; auto-restarts on crash. Suitable for self-hosted. | `docker-compose.yml:18` | ✓ Appropriate. |
| D6-014 | Info | Healthcheck Duplicate | Compose healthcheck repeats Dockerfile definition (identical test, interval, timeout). Redundant but harmless; Docker compose honors this if Dockerfile omitted. | `docker-compose.yml:19-25` vs `Dockerfile:82-83` | ✓ OK. Defensive duplication; compose takes precedence anyway. |
| D6-015 | Low | PID 1 Signal Handling | Dockerfile uses `exec` in CMD to ensure uvicorn becomes PID 1 and receives SIGTERM directly. workers=1 explicit (SQLite concurrency rationale clear). | `Dockerfile:77` | ✓ Correct. |
| D6-016 | Low | Git Runtime Cost | `git` (~109 MB) included in runtime image for optional `BACKUP_REPO_URL` GitHub push. Deployments without backup still pay cost. Acknowledged as Paket 17 future work. | `Dockerfile:49-52` | ⚠ Acceptable trade-off. Document if image size critical; splitting into `.minimal` variant possible but deferred. |

## Summary

- **Critical:** 0
- **High:** 0  
- **Medium:** 2 (image hygiene: `__pycache__`, test files)
- **Low:** 5 (cookie Secure, CSRF ops, health check scope, shutdown drain, git size)
- **Info:** 9 (multi-stage, non-root, env passing, restart, healthcheck, PID1, reverse-proxy safety)

### Key Verdicts

**✓ PRODUCTION-READY** with noted hygiene improvements:

1. **Image bloat:** `__pycache__` directories inflate final image. Mitigation: Either add `RUN find /app -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true` before final stage, or ensure pip's `PYTHONDONTWRITEBYTECODE=1` (present) suppresses generation.

2. **Test leakage:** `test_prod_enforcement.py` in runtime image. Minor risk (unused code). Recommend restructuring `COPY backend/` to exclude `tests/` or post-build cleanup.

3. **Bootstrap template:** Example password will fail validation; documentation is clear and enforced at startup. No issue.

4. **Reverse proxy:** Operators MUST understand `TRUST_FORWARDED_FOR` + `ALLOWED_ORIGINS` contract. Both default-safe (disabled / rejected). Deployment runbook required.

5. **Database state:** Liveness probe decoupled from DB intentionally. Operators must monitor `/api/health/db` separately or scan system event logs for DB issues. Acceptable architecture.

All secrets (SESSION_SECRET, GITHUB_PAT, BOOTSTRAP creds) correctly excluded from image and passed via env. Dockerfile signal handling correct. Shutdown graceful (background tasks stopped, lifespan yield/exception boundary respected).

**Recommendation:** Clean `__pycache__` from image and exclude tests in next deploy cycle (low urgency; does not affect functional safety).
