# Paket 15 — Docker Production-Hardening

**Status:** DESIGN APPROVED — ready for plan
**Date:** 2026-05-10
**Depends on:** Paket 1-14 + Paket 14b (entire backend feature set)
**Tag at end:** `paket-15-docker`

---

## 1. Problem

A `Dockerfile` and `docker-compose.yml` were scaffolded at commit `9b3e283` ("feat(docker): add Dockerfile and docker-compose for deployment") but never advanced past dev-quality. The current setup runs the app but has several production gaps:

- `docker-compose.yml` is **untracked** in git (working-tree artefact only).
- `requirements.txt` mixes prod and test dependencies — `pytest`, `pytest-asyncio`, `httpx` ship inside the production image.
- Single-stage build leaves build tools (`build-essential` would be needed for any wheel rebuild) and the editable install layer in the runtime image.
- Container runs as **root** — no UID/GID isolation.
- `HEALTHCHECK` `start_period=10s` is too tight for a startup that runs 4 migrations, spins up 3 asyncio background loops, and initializes SQLite WAL.
- No automated smoke test confirms the image builds, starts, applies migrations, and responds to `/api/health`.
- No safety signal when `SESSION_SECRET` is left at a dev default in production.
- `.dockerignore` / `.gitignore` miss several dev artefacts (`deneme-dev/`, `annotations.db`, `.planning/`, `sensitive/`).

**Goal:** harden the existing Docker scaffold to a production-ready, testable artifact; ship it as Paket 15 with a clean tag.

---

## 2. Scope (locked)

**IN scope:**

- Rewrite `Dockerfile` as multi-stage (builder + runtime) with non-root `appuser` (UID 1000).
- Split `requirements.txt` into prod and dev variants.
- Update healthcheck: liveness probes `/api/health` (process-up), `start_period=30s`.
- Track `docker-compose.yml` in git with hardened env + compose-level healthcheck.
- Add `tests/test_docker_smoke.py` exercising build + start + health + non-root assertion. Skip when `docker` CLI is absent.
- Add `SESSION_SECRET` dev-default detection in lifespan startup → `system_events` WARN row.
- Polish `.dockerignore` and `.gitignore`.
- Add a minimal README Docker section.

**OUT of scope (defer to Paket 17 or later):**

- GitHub Actions CI integration (docker build + smoke test in pipeline).
- Image vulnerability scanning (trivy, snyk, etc.).
- Multi-arch images (amd64 + arm64).
- JSON-structured logs / `/metrics` endpoint / Prometheus.
- Compose memory/CPU resource limits.
- External secret management (Docker secrets, Vault).
- Reverse proxy (nginx, traefik) — host-side or shipped with frontend (Paket 16).
- Python base upgrade 3.11 → 3.13 (separate migration with smoke test).

---

## 3. Locked Decisions

| Decision | Choice | Why |
|---|---|---|
| Base image | `python:3.11-slim` | Codex consult: 3.13 upgrade is its own work; FastAPI 0.115 + bcrypt + SQLite already stable on 3.11. |
| Build pattern | Multi-stage (builder + runtime) | Keeps `build-essential` and intermediate artefacts out of the runtime image. |
| User | Non-root `appuser` (UID 1000, GID 1000) | Security baseline; explicit UID for predictable volume permissions. |
| Workers | `uvicorn --workers 1` (explicit) | SQLite write contention: multi-worker introduces lock thrashing under load. |
| Healthcheck endpoint | `/api/health` (process-up only) | Codex consult: liveness should not couple to DB state; a transient SQLite lock should not trigger restart-loop. `/api/health/db` remains available for readiness/diagnostic use (manual or future K8s readiness probe). |
| `start_period` | 30s | Codex consult: covers 4-migration apply + 3 asyncio task spawn + WAL init with margin against false-unhealthy on a cold host. |
| Deps split | `requirements.txt` (prod) + `requirements-dev.txt` (test) | Removes `pytest`, `pytest-asyncio`, `httpx` from the runtime image; prod image is leaner and has smaller attack surface. |
| `SESSION_SECRET` safety | Log `system_events` WARN on dev-default detection at startup | Hard-fail would break compose `up` for local development (compose default is `dev-secret-change-me`). WARN gives operators a visible signal in the existing `/api/admin/system-events` viewer without blocking dev. |
| `docker-compose.yml` | Track in git | Currently untracked; shipping artefact. |
| Smoke test gate | `pytest tests/test_docker_smoke.py` with `docker`-presence skip | Runs locally on dev machines; skips cleanly in environments without docker (e.g., basic CI). |

---

## 4. Dockerfile

**File:** `Dockerfile`

```dockerfile
# ============================================================
# Stage 1 — builder
# Installs Python deps into an isolated target dir we can copy from.
# build-essential is here as a fallback for any wheel that needs to
# compile from source; it never reaches the runtime image.
# ============================================================
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
COPY backend/ ./backend/

# --target=/install: place all packages + console scripts under a single
# directory so the runtime stage can COPY one tree. --no-deps on the
# editable install is safe because all runtime deps come from
# requirements.txt (pyproject.toml does not declare [project.dependencies]).
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --target=/install -r requirements.txt && \
    pip install --no-cache-dir --target=/install --no-deps .

# ============================================================
# Stage 2 — runtime
# Lean image, non-root, git for backup_loop push, app code only.
# ============================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/site-packages \
    PATH=/app/site-packages/bin:$PATH

# git is a runtime dependency: backup_loop's optional GitHub push uses it.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

# Non-root user with explicit UID 1000. Volume permissions are predictable
# on host bind mounts — operators chown the host dir to 1000:1000 once.
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home --shell /bin/bash appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /install /app/site-packages
COPY --chown=appuser:appuser backend/ /app/backend/

RUN mkdir -p /data && chown appuser:appuser /data
VOLUME ["/data"]
ENV DATA_DIR=/data

USER appuser

EXPOSE 8000

# Apply migrations (idempotent via schema_migrations gate), then exec
# uvicorn so it becomes PID 1 and receives SIGTERM directly. workers=1
# is explicit: SQLite write contention makes multi-worker counter-productive.
CMD ["sh", "-c", "python -m backend.cli migrate && exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1"]

# Liveness probe: app process up. DB issues are surfaced via
# /api/health/db (manual/readiness use) and via system_events log rows —
# coupling liveness to DB risks transient-lock restart loops.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)" || exit 1
```

---

## 5. docker-compose.yml (track + harden)

**File:** `docker-compose.yml` (currently untracked — `git add` in implementation).

```yaml
services:
  app:
    build: .
    image: anotasyon-platform:latest
    ports:
      - "8000:8000"
    volumes:
      - anotasyon_data:/data
    environment:
      - DATA_DIR=/data
      - SESSION_SECRET=${SESSION_SECRET:-dev-secret-change-me}
      - SESSION_COOKIE_NAME=${SESSION_COOKIE_NAME:-anotasyon_session}
      - BACKUP_REPO_URL=${BACKUP_REPO_URL:-}
      - GITHUB_PAT=${GITHUB_PAT:-}
      - BOOTSTRAP_ADMIN_USERNAME=${BOOTSTRAP_ADMIN_USERNAME:-}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"]
      interval: 30s
      timeout: 5s
      start_period: 30s
      retries: 3

volumes:
  anotasyon_data:
```

The compose-level healthcheck duplicates the Dockerfile directive but is explicit so `docker compose ps` and `--filter health=...` reflect the intended contract without inheritance ambiguity.

---

## 6. Lifespan SESSION_SECRET Safety

**File:** `backend/main.py` — extend the lifespan startup block.

```python
DEV_SESSION_SECRETS = {
    "dev-secret-DO-NOT-USE-IN-PROD",  # backend/config.py default
    "dev-secret-change-me",            # docker-compose.yml default
}

# Inside the existing lifespan() async function, after the existing
# audit.log_system_event(conn, "startup", ...) call:
if config.SESSION_SECRET in DEV_SESSION_SECRETS:
    audit.log_system_event(
        conn, "session_secret_dev_default", "warn",
        message="SESSION_SECRET is set to a dev default; set a real "
                "secret via env var for production.",
    )
```

**Why WARN, not hard-fail:** the compose file ships with `dev-secret-change-me` as the fallback so `docker compose up` works out of the box for local development. A hard-fail would force every dev environment to set an env var before first run, hurting onboarding. The WARN row appears in `/api/admin/system-events` (visible to operators) and will surface in any future admin UI as a deployment-health flag.

---

## 7. Dependency Split

**File:** `requirements.txt` (prod only)

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
bcrypt==4.2.0
```

**File:** `requirements-dev.txt` (new — test deps)

```
-r requirements.txt
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

Dev install:

```bash
.venv/bin/pip install -r requirements-dev.txt
```

(The `-r requirements.txt` first line pulls prod deps automatically.)

---

## 8. Ignore-File Polish

**File:** `.dockerignore` — replace contents with:

```
# Python build artefacts
__pycache__/
*.pyc
*.pyo
*.egg-info/

# Virtualenvs and tooling caches
.venv/
venv/
.pytest_cache/

# Git internals
.git/
.gitignore

# Local env files
.env
.env.*

# Data dirs (mounted at runtime, never baked into image)
data/
deneme-dev/

# Docs and tests do not belong in the production image
docs/
tests/
*.md
README.md

# Self-ignore (defense in depth against recursive context bloat)
Dockerfile*
docker-compose*.yml
.dockerignore

# Dev artefacts
annotations.db
sensitive/
.planning/
*.log
```

**File:** `.gitignore` — append one line (the existing working-tree diff adds `deneme-dev/` and `sensitive`; T1 of the plan adds `annotations.db`):

```
annotations.db
```

---

## 9. Tests

**File:** `tests/test_docker_smoke.py` (new)

Three tests, all marked `@pytest.mark.docker`. Skip cleanly when `docker` is absent from `PATH`.

1. **`test_image_builds_and_health_endpoint_responds`** — builds the image (module-scoped fixture), starts a container on a random host port, polls `/api/health` until 200 or 45s timeout, asserts `body["status"] == "ok"` and a non-empty `version` field.
2. **`test_health_db_endpoint_reports_migrations`** — same container start, polls `/api/health`, then hits `/api/health/db`, asserts `migrations_applied == 4` (v0001..v0004) and `table_count >= 23`.
3. **`test_container_runs_as_non_root`** — `docker exec <cid> id -u` returns `1000`, confirming the `appuser` USER directive took effect.

Each test uses a fresh container via a function-scoped fixture that calls `docker run -d --rm -p 0:8000 -e SESSION_SECRET=test-secret-smoke ...` and discovers the host port via `docker port`. Image build is module-scoped to amortize cost (~30-60s cold, ~5s warm).

**File:** `pyproject.toml` — register the new marker:

```toml
[tool.pytest.ini_options]
# existing fields ...
markers = [
    "docker: smoke tests that require docker CLI on PATH (slow, ~40-60s per test).",
]
```

**Run modes:**

- Default `pytest`: smoke tests run if `docker` is present, skip otherwise — no separate flag needed.
- Explicit selection: `pytest -m docker` or `pytest tests/test_docker_smoke.py`.
- Skip in fast feedback loops: `pytest -m "not docker"`.

---

## 10. README Docker Section

**File:** `README.md` — add a Docker section (or create the file if missing — implementation checks).

```markdown
## Docker

Build and run:

\`\`\`bash
docker compose up -d --build
\`\`\`

The app listens on `http://localhost:8000`.

### Environment variables

Required:

- `SESSION_SECRET` — random 32+ characters. Default `dev-secret-change-me` is treated as dev-only and emits a WARN row in `system_events` on startup.

Optional:

- `BACKUP_REPO_URL` + `GITHUB_PAT` — enable automatic backup to a GitHub repo. Both must be set together; either alone is ignored.
- `BOOTSTRAP_ADMIN_USERNAME` — username of an admin to seed on first boot (one-shot).
- `SESSION_COOKIE_NAME` — defaults to `anotasyon_session`.

### Healthcheck

- Liveness: `GET /api/health` (process-up). Docker `HEALTHCHECK` uses this.
- Readiness / diagnostic: `GET /api/health/db` (returns migration + table counts; surfaces SQLite errors).

### Container user

Runs as `appuser` (UID 1000). When binding a host directory to `/data`, chown it once:

\`\`\`bash
sudo chown -R 1000:1000 /path/to/host/data
\`\`\`

### Smoke test

\`\`\`bash
.venv/bin/python -m pytest tests/test_docker_smoke.py -v
\`\`\`
```

---

## 11. Edge Cases

**Build fails on minimal apt sources** — `build-essential` and `git` come from the default Debian Trixie repos baked into `python:3.11-slim`. If the host has a corporate apt mirror that rejects `bullseye-backports` or similar, the build fails fast at the `apt-get install` step. No silent corruption.

**Volume permission deadlock** — addressed in §4: the `chown appuser:appuser /data` runs **before** `USER appuser` and `VOLUME ["/data"]`, so the directory ownership is captured by the image. Named volumes initialize from this state on first use. Host bind mounts require operator-side chown (documented in README §10).

**SIGTERM handling** — `exec uvicorn` replaces the `sh -c` parent in CMD, making uvicorn PID 1. Docker's `docker stop` sends SIGTERM to PID 1, which uvicorn handles cleanly via its own signal handlers (graceful shutdown of the asyncio loop). Without `exec`, sh would intercept SIGTERM, send it to nothing, and require the 10s default kill timeout to escalate to SIGKILL.

**`pip install --no-deps .` risk** — would silently miss runtime deps if `pyproject.toml` declared `[project.dependencies]`. Verified: `pyproject.toml` does NOT declare them — all runtime deps come through `requirements.txt`. Safe today; if `[project.dependencies]` is ever added, the editable install must drop `--no-deps`.

**Smoke test on host with running app on port 8000** — the smoke test fixture publishes the container on `0:8000` (random host port), so it never collides with a developer's running uvicorn.

**Healthcheck during cold start** — the first 30s after `docker run` are inside `start_period`. Docker reports the container as `starting`, not `unhealthy`, regardless of healthcheck failures. Restart policies do not fire during `start_period`.

**docker-compose `dev-secret-change-me` and the WARN row** — on every container restart, the WARN row appears again (lifespan runs each time). This is intentional: persistent visibility for operators who haven't yet set a real secret.

---

## 12. Test Plan

### Smoke (new file)

- `test_image_builds_and_health_endpoint_responds`
- `test_health_db_endpoint_reports_migrations`
- `test_container_runs_as_non_root`

### Existing tests (must remain green)

- All 671 existing tests pass with no changes — none of them depend on Docker.
- `test_audit.py` already covers `audit.log_system_event(severity="warn", ...)`; the new `session_secret_dev_default` event uses the same helper, no new audit-helper test needed.

### Manual smoke gate (implementation phase)

```bash
# Build from scratch (no cache, full path validation)
docker build --no-cache -t anotasyon-platform:test .

# Inspect image size — sanity check on multi-stage gains
docker images anotasyon-platform:test

# Run + verify healthcheck reports "healthy" within ~45s
docker run -d --name test -p 8001:8000 -e SESSION_SECRET=smoke anotasyon-platform:test
sleep 45
docker ps --filter name=test --format "{{.Status}}"  # expect "Up ... (healthy)"
docker inspect test --format "{{.Config.User}}"      # expect "appuser"

# Cleanup
docker stop test
```

### Pyright cosmetic

Same project-wide cosmetic Pyright warnings about `backend.*` imports apply. Not gating.

---

## 13. Implementation Estimate

| Element | Files | Notes |
|---|---|---|
| Dockerfile rewrite | `Dockerfile` | Multi-stage + non-root + healthcheck + comments |
| Compose update + git track | `docker-compose.yml` | Compose-level healthcheck + image tag |
| Deps split | `requirements.txt`, `requirements-dev.txt` (new) | Test deps moved out |
| Lifespan WARN | `backend/main.py` | ~7 added lines |
| Ignore polish | `.dockerignore`, `.gitignore` | Additive |
| Smoke tests | `tests/test_docker_smoke.py` (new), `pyproject.toml` marker | 3 tests + pytest marker |
| README | `README.md` (new or append) | Docker section |

Estimated: **6-7 atomic commits**, single-day implementation including a manual `docker build` + `docker run` smoke gate during the Dockerfile commit.

---

## 14. Out-of-Spec / Deferred

- **GitHub Actions CI integration** — building the image + running the smoke test in CI requires either docker-in-docker or a self-hosted runner. Worth a dedicated paket once the smoke test is mature.
- **Vulnerability scanning** — `trivy image anotasyon-platform:latest` should run before any external release. Out of scope for first ship.
- **Multi-arch images** — `docker buildx build --platform linux/amd64,linux/arm64` requires `buildx` setup and a manifest registry. Single-platform until there is a real deployment target on arm64.
- **JSON logs / `/metrics`** — observability concerns of a later phase; the current `system_events` stream covers what an operator needs day-one.
- **Compose memory/CPU limits** — deployment-environment specific; ship limits in the operator's compose override, not the shipped compose file.
- **Python 3.11 → 3.13 migration** — separate ticket; should include re-running the full suite under 3.13 and confirming bcrypt + asyncio + sqlite3 stdlib parity. The dev environment is already on 3.13.3.
