# Paket 15 — Docker Production-Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the existing dev-quality Docker scaffold into a production-ready, testable image: multi-stage build, non-root `appuser` (UID 1000), prod/dev deps split, liveness on `/api/health` with realistic `start_period`, tracked compose file, lifespan WARN for dev `SESSION_SECRET`, and an automated smoke test gated by docker-CLI presence.

**Architecture:** Six file-level edits + one new test file + one new requirements file + one new (or appended) README. Each task is a single atomic commit; TDD where the code is unit-testable (lifespan WARN, smoke gate); manual docker-build smoke verification where TDD doesn't apply (Dockerfile rewrite, compose changes). Final commit places `paket-15-docker` tag.

**Tech Stack:** Docker 24+, Docker Compose v2, Python 3.11-slim base, uvicorn workers=1, FastAPI 0.115, SQLite WAL, pytest 8.3 with custom marker.

**Spec:** `docs/superpowers/specs/2026-05-10-paket-15-docker-prod-design.md`

**Test runner:** `.venv/bin/python -m pytest <path> -v` (system Python lacks fastapi).

**Git config for every commit:**
```
git -c user.email=maarkval@icloud.com -c user.name=baran commit ...
```
Footer line:
```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

NEVER use `--no-verify` or `--no-gpg-sign`.

**Pyright cosmetic warnings about `backend.*` imports are expected project-wide and do not gate work.**

---

## File Structure

| File | Role | Status | Task |
|---|---|---|---|
| `requirements.txt` | Prod-only deps | Modify (slim) | T1 |
| `requirements-dev.txt` | Test/dev deps (includes prod via -r) | **Create** | T1 |
| `backend/main.py` | Lifespan adds SESSION_SECRET WARN row | Modify | T2 |
| `tests/test_session_secret_warn.py` | Lifespan-level test of the WARN logic | **Create** | T2 |
| `Dockerfile` | Multi-stage + non-root + healthcheck | Replace | T3 |
| `docker-compose.yml` | Tracked + compose-level healthcheck + image tag | Modify + `git add` | T4 |
| `.dockerignore` | Polish (deneme-dev/, annotations.db, etc.) | Replace | T5 |
| `.gitignore` | Append `annotations.db` | Modify | T5 |
| `tests/test_docker_smoke.py` | Image build + start + /api/health + UID assert | **Create** | T6 |
| `pyproject.toml` | Register `docker` pytest marker | Modify | T6 |
| `README.md` | Docker usage section | **Create** | T7 |
| Tag `paket-15-docker` | Pin final commit | — | T7 |

**Total:** 4 new files, 7 modified files, 1 git tag.

---

## Conventions for All Tasks

- **TDD strict** for T2 and T6 (the code-testable tasks).
- **Manual smoke gate** for T3, T4 (Dockerfile + compose changes): build, run, verify, cleanup.
- **Atomic commits**: one task = one commit.
- **Commit message format**: `feat(paket-15): <summary>` for substantive changes, `chore(paket-15): ...` for ignore-file polish and similar.
- **Test runner**: always `.venv/bin/python -m pytest` — bare `pytest` picks the system interpreter and fails on `import fastapi`.
- **Docker commands**: assume `docker` and `docker compose v2` on PATH. The smoke test (T6) skips cleanly when docker is absent; T3/T4 manual gates require it.
- **No `--no-verify` / `--no-gpg-sign`** on any commit.

---

## Task 1: Dependency Split

**Files:**
- Modify: `/Users/barandincoguz/Desktop/deneme/requirements.txt`
- Create: `/Users/barandincoguz/Desktop/deneme/requirements-dev.txt`

### Step 1.1: Create the dev requirements file

- [ ] Write `/Users/barandincoguz/Desktop/deneme/requirements-dev.txt`:

```
-r requirements.txt
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

The `-r requirements.txt` first line pulls prod deps; the rest are test-only.

### Step 1.2: Slim requirements.txt to prod-only

- [ ] Replace the contents of `/Users/barandincoguz/Desktop/deneme/requirements.txt` with:

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
bcrypt==4.2.0
```

### Step 1.3: Verify the dev install path still works

Run:
```
.venv/bin/pip install --dry-run -r requirements-dev.txt 2>&1 | tail -5
```

Expected: dry-run resolution succeeds, listing fastapi/uvicorn/bcrypt/pytest/pytest-asyncio/httpx as the would-install set or "already satisfied" messages. No error.

### Step 1.4: Run the full test suite to confirm no regression

Run:
```
.venv/bin/python -m pytest -x -q 2>&1 | tail -3
```

Expected: 671 tests pass (same as the paket-14b post-fix baseline). Removing pytest from `requirements.txt` doesn't break tests because pytest is still installed in `.venv` from the previous baseline install.

### Step 1.5: Commit

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  requirements.txt \
  requirements-dev.txt
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-15): split prod/dev requirements

requirements.txt now ships only the runtime dependencies (fastapi,
uvicorn, bcrypt). pytest, pytest-asyncio, and httpx move to
requirements-dev.txt, which pulls in the prod set via `-r requirements.txt`.

This is a prerequisite for the multi-stage Dockerfile in T3: the
production image will install requirements.txt only, removing test deps
from its attack surface.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: SESSION_SECRET Lifespan WARN

**Files:**
- Modify: `/Users/barandincoguz/Desktop/deneme/backend/main.py` (lifespan extension)
- Create: `/Users/barandincoguz/Desktop/deneme/tests/test_session_secret_warn.py`

### Step 2.1: Write the failing test

- [ ] Write `/Users/barandincoguz/Desktop/deneme/tests/test_session_secret_warn.py`:

```python
"""Lifespan should emit a system_events WARN row when SESSION_SECRET is
left at a dev default. Mirrors the paket-15 production-hardening contract:
operators see the dev-default state in the audit log without the app
hard-failing local-dev or compose-default boot."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_secret(monkeypatch, tmp_path):
    """Build a clean app whose lifespan reads a monkeypatched SESSION_SECRET.

    Each test gets a fresh tmp DB so the WARN row count is deterministic.
    """
    from backend import config

    # Isolate the DB so prior runs don't contaminate the audit log scan.
    data_dir = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR",     data_dir)
    monkeypatch.setattr(config, "DB_DIR",       data_dir / "db")
    monkeypatch.setattr(config, "DB_PATH",      data_dir / "db" / "annotations.db")
    monkeypatch.setattr(config, "DOCUMENTS_DIR", data_dir / "documents")
    monkeypatch.setattr(config, "BACKUP_DIR",    data_dir / "backup")
    monkeypatch.setattr(config, "EXPORTS_DIR",   data_dir / "exports")

    return config


def _count_warn_rows(db_path) -> int:
    from backend.shared.db import connect
    conn = connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM system_events "
            "WHERE event_type='session_secret_dev_default' AND severity='warn'"
        ).fetchone()["c"]
    finally:
        conn.close()


def test_lifespan_emits_warn_when_session_secret_is_default(monkeypatch, app_with_secret):
    """The exact default from backend/config.py triggers the WARN row."""
    monkeypatch.setattr(app_with_secret, "SESSION_SECRET", "dev-secret-DO-NOT-USE-IN-PROD")
    from backend.main import app
    with TestClient(app):
        pass  # Just trigger lifespan
    assert _count_warn_rows(app_with_secret.DB_PATH) == 1


def test_lifespan_emits_warn_when_compose_default_is_used(monkeypatch, app_with_secret):
    """The compose fallback string also triggers the WARN row."""
    monkeypatch.setattr(app_with_secret, "SESSION_SECRET", "dev-secret-change-me")
    from backend.main import app
    with TestClient(app):
        pass
    assert _count_warn_rows(app_with_secret.DB_PATH) == 1


def test_lifespan_skips_warn_when_secret_is_real(monkeypatch, app_with_secret):
    """A real-looking secret leaves the WARN counter at zero."""
    monkeypatch.setattr(app_with_secret, "SESSION_SECRET",
                        "9a44e8c7f3b2d1e0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6")
    from backend.main import app
    with TestClient(app):
        pass
    assert _count_warn_rows(app_with_secret.DB_PATH) == 0
```

### Step 2.2: Run test, expect FAIL

Run:
```
.venv/bin/python -m pytest tests/test_session_secret_warn.py -v
```

Expected: All 3 tests FAIL (lifespan does not yet emit the WARN row; the counter is always 0).

### Step 2.3: Implement the lifespan WARN branch

- [ ] Modify `/Users/barandincoguz/Desktop/deneme/backend/main.py`. Right above the `@asynccontextmanager` decorator on the `lifespan` function (around line 35), add the constant:

```python
DEV_SESSION_SECRETS = {
    "dev-secret-DO-NOT-USE-IN-PROD",  # backend/config.py default
    "dev-secret-change-me",            # docker-compose.yml default
}
```

Then extend the `try` block inside `lifespan` (current code around line 42-49) so it looks like:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        applied = apply_migrations(conn, discover_migrations())
        audit.log_system_event(
            conn, "startup", "info",
            message=f"app v{VERSION} started; migrations applied: {applied}",
            extra={"version": VERSION, "migrations_applied": applied},
        )
        if config.SESSION_SECRET in DEV_SESSION_SECRETS:
            audit.log_system_event(
                conn, "session_secret_dev_default", "warn",
                message="SESSION_SECRET is set to a dev default; set a real "
                        "secret via env var for production.",
            )
    finally:
        conn.close()
    # ... rest of lifespan unchanged (sweep_task, backup_task, retention_task, yield, ...) ...
```

### Step 2.4: Run test, expect PASS

Run:
```
.venv/bin/python -m pytest tests/test_session_secret_warn.py -v
```

Expected: All 3 PASS.

### Step 2.5: Run full suite to confirm no regression

Run:
```
.venv/bin/python -m pytest -x -q 2>&1 | tail -3
```

Expected: 674 tests pass (671 baseline + 3 new).

### Step 2.6: Commit

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/main.py \
  tests/test_session_secret_warn.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-15): lifespan WARN on dev SESSION_SECRET

Adds a small lifespan extension that emits a system_events WARN row
when SESSION_SECRET is left at either of the two known dev defaults
(backend/config.py fallback or the docker-compose.yml fallback).

Hard-fail was deliberately rejected: the compose default keeps local
`docker compose up` flowing for first-time setup. The WARN row is
visible via the existing /api/admin/system-events endpoint and will
surface in any admin UI as a deployment-health flag.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Dockerfile Rewrite (Multi-Stage + Non-Root)

**Files:**
- Replace: `/Users/barandincoguz/Desktop/deneme/Dockerfile`

This task has no automated test before T6 ships. Manual `docker build` + `docker run` is the gate.

### Step 3.1: Write the new Dockerfile

- [ ] Replace `/Users/barandincoguz/Desktop/deneme/Dockerfile` with:

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

# --target=/install collects all packages + console scripts under one
# directory the runtime stage copies in a single layer.
# --no-deps on the editable install is safe: pyproject.toml does NOT
# declare [project.dependencies]; all runtime deps come from requirements.txt.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --target=/install -r requirements.txt && \
    pip install --no-cache-dir --target=/install --no-deps .

# ============================================================
# Stage 2 — runtime
# Lean image, non-root, git for backup_loop's optional GitHub push,
# app code only.
# ============================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/site-packages \
    PATH=/app/site-packages/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

# Non-root user with explicit UID 1000 — predictable for host bind mounts.
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

# Apply migrations (idempotent via schema_migrations), then exec uvicorn so
# it becomes PID 1 and receives SIGTERM directly. workers=1 is explicit:
# SQLite write contention makes multi-worker counter-productive.
CMD ["sh", "-c", "python -m backend.cli migrate && exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1"]

# Liveness probe: app process up. DB issues surface via /api/health/db
# (manual/readiness use) and via system_events log rows — coupling liveness
# to DB risks transient-lock restart loops.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)" || exit 1
```

### Step 3.2: Manual smoke — build the image

Run:
```
docker build --no-cache -t anotasyon-platform:test .
```

Expected:
- Both stages complete without error.
- Final layer reports something like `naming to docker.io/library/anotasyon-platform:test`.

If the build fails, read the error message before retrying. Do NOT commit a Dockerfile that doesn't build.

### Step 3.3: Manual smoke — run + verify health

Run:
```
docker run -d --rm --name anotasyon-smoke-t3 -p 8001:8000 \
  -e SESSION_SECRET=smoke-test-secret \
  anotasyon-platform:test
sleep 35
docker ps --filter name=anotasyon-smoke-t3 --format "{{.Status}}"
```

Expected: status string contains `Up` and `(healthy)`. If it shows `(unhealthy)` or no health state after 35s, run `docker logs anotasyon-smoke-t3` to diagnose before proceeding.

### Step 3.4: Verify non-root user

Run:
```
docker exec anotasyon-smoke-t3 id -u
```

Expected: `1000`.

### Step 3.5: Verify image size sanity

Run:
```
docker images anotasyon-platform:test --format "{{.Size}}"
```

Expected: somewhere between 150 MB and 280 MB. (The exact figure varies with Docker version's wheel cache strategy; flag a >400 MB outcome as a regression worth investigating before committing.)

### Step 3.6: Cleanup

Run:
```
docker stop anotasyon-smoke-t3
docker rmi anotasyon-platform:test
```

(Expect "stopped"; image rm may fail with "image is being used by stopped container" if `--rm` hasn't drained yet — wait 1s and retry.)

### Step 3.7: Commit

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add Dockerfile
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-15): multi-stage Dockerfile + non-root + tuned healthcheck

Replaces the single-stage dev Dockerfile with a multi-stage build that
keeps build-essential and test deps out of the runtime image. Runtime
runs as appuser (UID 1000) with /data owned by the same UID. Liveness
probe uses /api/health (process-up only) with start_period=30s, sized
for the lifespan's 4-migration apply + 3 asyncio task startup.

Manual smoke gate verified locally: image builds clean from scratch,
container reports (healthy), /api/health returns 200, `id -u` == 1000.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: docker-compose.yml — Track + Harden

**Files:**
- Modify + `git add`: `/Users/barandincoguz/Desktop/deneme/docker-compose.yml`

### Step 4.1: Replace docker-compose.yml content

- [ ] Replace `/Users/barandincoguz/Desktop/deneme/docker-compose.yml` with:

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

### Step 4.2: Manual smoke — compose up + verify

Run:
```
docker compose up -d --build
sleep 35
docker compose ps --format "{{.Service}} {{.Status}}"
```

Expected: `app  Up ... (healthy)`.

If `(unhealthy)` or no health status after 35s, run `docker compose logs app | tail -50` to inspect before continuing.

### Step 4.3: Verify the WARN row was written

Run:
```
docker compose exec app sqlite3 /data/db/annotations.db \
  "SELECT event_type, severity FROM system_events WHERE event_type='session_secret_dev_default'"
```

Expected: a single row `session_secret_dev_default|warn` — confirms the lifespan branch from T2 fires under the compose default secret.

### Step 4.4: Cleanup

Run:
```
docker compose down -v
```

(`-v` removes the named volume so the next smoke run starts clean.)

### Step 4.5: Commit (with explicit `git add` because the file was previously untracked)

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add docker-compose.yml
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-15): track + harden docker-compose.yml

The compose file existed in the working tree but was never tracked.
This commit adds it to git with a hardened shape: explicit image tag,
compose-level healthcheck duplicating the Dockerfile contract for
`docker compose ps` visibility, restart=unless-stopped, named volume
for /data, and env-var passthrough for SESSION_SECRET, BACKUP_REPO_URL,
GITHUB_PAT, BOOTSTRAP_ADMIN_USERNAME, SESSION_COOKIE_NAME.

Manual smoke gate: `docker compose up -d --build` reports (healthy)
within start_period, and the lifespan WARN row from T2 is visible in
system_events under the compose default SESSION_SECRET.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Ignore-File Polish

**Files:**
- Replace: `/Users/barandincoguz/Desktop/deneme/.dockerignore`
- Modify: `/Users/barandincoguz/Desktop/deneme/.gitignore`

### Step 5.1: Replace .dockerignore

- [ ] Overwrite `/Users/barandincoguz/Desktop/deneme/.dockerignore` with:

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

# Self-ignore (defense in depth)
Dockerfile*
docker-compose*.yml
.dockerignore

# Dev artefacts
annotations.db
sensitive/
.planning/
*.log
```

### Step 5.2: Append to .gitignore

The current diff in the working tree already adds `deneme-dev/` and `sensitive`. Add one more line to `/Users/barandincoguz/Desktop/deneme/.gitignore`:

```
annotations.db
```

(Append at the end. The file's existing tail looks like `deneme-dev/\nsensitive\n`; the new line goes after `sensitive`.)

### Step 5.3: Verify the working tree no longer reports the stray annotations.db

Run:
```
git status --short 2>&1 | head -10
```

Expected: `annotations.db` no longer appears with `??` (untracked) status. The line is now ignored by the new `.gitignore` rule.

### Step 5.4: Manual smoke — rebuild and confirm the image is leaner

Run:
```
docker build --no-cache -t anotasyon-platform:t5 .
docker images anotasyon-platform:t5 --format "{{.Size}}"
docker images anotasyon-platform:test --format "{{.Size}}" 2>/dev/null
docker rmi anotasyon-platform:t5
```

Expected: t5 size ≤ test size from T3.5. (The change is small — these ignore additions strip a few MB of test fixtures and the stray `annotations.db` — but the size must not grow.)

### Step 5.5: Commit

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  .dockerignore \
  .gitignore
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
chore(paket-15): polish .dockerignore and .gitignore

.dockerignore now excludes deneme-dev/, annotations.db, sensitive/,
.planning/, *.log, and self-ignores Dockerfile / docker-compose to
avoid recursive build-context bloat. README.md added explicitly even
though *.md already covers it.

.gitignore adds annotations.db so the root-level dev artefact from
test runs no longer shows as untracked.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Smoke Test + pytest Marker

**Files:**
- Modify: `/Users/barandincoguz/Desktop/deneme/pyproject.toml` (add marker)
- Create: `/Users/barandincoguz/Desktop/deneme/tests/test_docker_smoke.py`

### Step 6.1: Register the pytest marker

- [ ] Modify `/Users/barandincoguz/Desktop/deneme/pyproject.toml`. The current `[tool.pytest.ini_options]` block is:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Replace it with:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "docker: smoke tests that require the docker CLI on PATH (slow, ~40-60s per test)",
]
```

### Step 6.2: Write the smoke test

- [ ] Create `/Users/barandincoguz/Desktop/deneme/tests/test_docker_smoke.py`:

```python
"""Docker image smoke test: build + start + /api/health + non-root assertion.

Skips when the docker CLI is absent (e.g., CI without docker-in-docker).
Default `pytest` includes these tests when docker is available; otherwise
they skip cleanly. Explicit selection: `pytest -m docker`. Exclusion:
`pytest -m "not docker"`.

Costs: image build is module-scoped (~30-60s cold, ~5s warm via layer
cache). Each test spins up a fresh container on a random host port,
waits up to 45s for /api/health to return 200, then runs its assertions.
"""
import json
import os
import shutil
import subprocess
import time
import urllib.request

import pytest

DOCKER = shutil.which("docker")
pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(DOCKER is None, reason="docker CLI not on PATH"),
]


IMAGE_TAG = "anotasyon-platform:test-smoke"


def _run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True, **kwargs)


@pytest.fixture(scope="module")
def built_image():
    """Build the image once per test module against the repo root."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    _run([DOCKER, "build", "-t", IMAGE_TAG, repo_root])
    yield IMAGE_TAG
    # Intentionally no `docker rmi` — keep the layer cache warm for the
    # next run. The image is tagged with `test-smoke`, easy to clean up
    # manually if disk pressure becomes an issue.


@pytest.fixture()
def running_container(built_image):
    """Start a fresh container on a random host port. Yield (cid, port).
    --rm + explicit `docker stop` covers cleanup even on test failure."""
    result = _run([
        DOCKER, "run", "-d", "--rm",
        "-p", "0:8000",
        "-e", "SESSION_SECRET=test-secret-smoke",
        built_image,
    ])
    cid = result.stdout.strip()
    try:
        port_out = _run([DOCKER, "port", cid, "8000"]).stdout.strip()
        # Format: "0.0.0.0:NNNNN\n[::]:NNNNN" — take the first line, then
        # the integer after the last ':'.
        first_line = port_out.splitlines()[0]
        host_port = int(first_line.rsplit(":", 1)[1])
        yield cid, host_port
    finally:
        _run([DOCKER, "stop", cid], check=False)


def _wait_healthy(port: int, timeout_s: int = 45) -> dict:
    """Poll /api/health until 200 or timeout. Returns parsed body."""
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/health", timeout=3,
            ) as r:
                if r.status == 200:
                    return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            time.sleep(1)
    raise TimeoutError(
        f"/api/health did not become ready in {timeout_s}s; last err: {last_err}"
    )


def test_image_builds_and_health_endpoint_responds(running_container):
    """End-to-end: image starts, migrations apply, app binds 8000, /api/health 200."""
    _cid, port = running_container
    body = _wait_healthy(port, timeout_s=45)
    assert body["status"] == "ok"
    assert isinstance(body.get("version"), str)
    assert body["version"]  # non-empty


def test_health_db_endpoint_reports_migrations(running_container):
    """Migrations applied on startup. /api/health/db reports counts."""
    _cid, port = running_container
    _wait_healthy(port, timeout_s=45)
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/health/db", timeout=3,
    ) as r:
        body = json.loads(r.read().decode("utf-8"))
    assert body["status"] == "ok"
    assert body["migrations_applied"] == 4  # v0001..v0004
    assert body["table_count"] >= 23


def test_container_runs_as_non_root(running_container):
    """Security baseline: PID 1 runs as appuser (UID 1000), not root."""
    cid, _port = running_container
    out = _run([DOCKER, "exec", cid, "id", "-u"]).stdout.strip()
    assert out == "1000", f"container ran as UID {out}, expected 1000 (appuser)"
```

### Step 6.3: Run the smoke test (expect PASS on a host with docker)

Run:
```
.venv/bin/python -m pytest tests/test_docker_smoke.py -v
```

Expected on a machine WITH docker: 3 PASS (slow — ~1-2 minutes total).
Expected on a machine WITHOUT docker: 3 SKIPPED with reason "docker CLI not on PATH". Either outcome is acceptable.

If the test that hits `/api/health/db` reports `table_count < 23` or `migrations_applied != 4`, run the container manually:
```
docker logs <cid>
```
and check whether `python -m backend.cli migrate` printed errors at startup. The most likely cause is a missing migration import (e.g., `v0004_trace_id` not packaged) — verify with `docker exec <cid> ls /app/backend/migrations/`.

### Step 6.4: Run the full suite to confirm no regression

Run:
```
.venv/bin/python -m pytest -x -q 2>&1 | tail -3
```

Expected: 677 tests pass (674 from T2 + 3 new smoke) on a host with docker, OR 674 pass + 3 skipped on a host without.

### Step 6.5: Commit

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  pyproject.toml \
  tests/test_docker_smoke.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-15): docker image smoke test + pytest marker

Three smoke tests run end-to-end against the actual image:
1. image builds, container starts, /api/health returns 200 within 45s
2. /api/health/db reports migrations_applied=4 (v0001..v0004) and table_count>=23
3. PID 1 runs as appuser (UID 1000), not root

Skips cleanly with `pytest.mark.skipif(docker not on PATH)` so CI
environments without docker stay green. Registered the `docker` marker
in pyproject.toml so explicit selection (`-m docker`) and exclusion
(`-m "not docker"`) work without warnings.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: README + Final Tag

**Files:**
- Create: `/Users/barandincoguz/Desktop/deneme/README.md`

### Step 7.1: Create the README

- [ ] Write `/Users/barandincoguz/Desktop/deneme/README.md`:

````markdown
# Anotasyon Platform

FastAPI-based annotation platform for legal/tax document references.
SQLite (WAL) storage, single-instance deployment.

## Development

Requires Python 3.11+ and a virtual environment in `.venv`.

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The dev DB lives under `data/db/annotations.db` (override via `DATA_DIR`).

## Docker

Build and run:

```bash
docker compose up -d --build
```

The app listens on `http://localhost:8000`. Swagger UI: `http://localhost:8000/docs`.

### Environment variables

Required for production:

- `SESSION_SECRET` — random 32+ characters. The default `dev-secret-change-me`
  is treated as dev-only and emits a WARN row in `system_events` on every
  startup. Set a real secret in production.

Optional:

- `BACKUP_REPO_URL` + `GITHUB_PAT` — enable automatic backup push to a
  GitHub repo (set both, or neither).
- `BOOTSTRAP_ADMIN_USERNAME` — username of an admin to seed on first boot.
- `SESSION_COOKIE_NAME` — defaults to `anotasyon_session`.

### Healthcheck

- Liveness: `GET /api/health` (process-up). Docker `HEALTHCHECK` uses this
  and only this — DB issues are surfaced separately to avoid restart loops
  on transient SQLite locks.
- Readiness / diagnostic: `GET /api/health/db` (returns migration + table
  counts; HTTP 500 if the DB is unreachable).

### Container user

Runs as `appuser` (UID 1000, GID 1000). When binding a host directory to
`/data`, chown it once on the host:

```bash
sudo chown -R 1000:1000 /path/to/host/data
```

### Smoke test

```bash
.venv/bin/python -m pytest tests/test_docker_smoke.py -v
```

Skips automatically when docker is not on PATH.
````

### Step 7.2: Sanity-check the README renders

Run:
```
head -30 README.md
```

Expected: the title, dev install snippet, and the start of the Docker section render as plain Markdown.

### Step 7.3: Run the full suite one final time

Run:
```
.venv/bin/python -m pytest -x -q 2>&1 | tail -3
```

Expected: 677 pass (on a docker-equipped host) or 674 pass + 3 skipped.

### Step 7.4: Commit the README

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add README.md
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
docs(paket-15): README with Docker usage section

Minimal project README covering local development install, docker compose
flow, environment variables (with SESSION_SECRET safety note), the
liveness vs readiness endpoint split, the appuser UID 1000 contract for
volume mounts, and how to run the smoke test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Step 7.5: Tag the mini-pack

Run:
```
git tag paket-15-docker
```

This is the final tag for Paket 15. After T7, the working tree should be clean.

Verify:
```
git log --oneline paket-14b-trace-id..paket-15-docker
```

Expected: the 7 task commits from this plan plus the spec commit `e0a7b1c`, the plan commit itself, and any pre-existing commits since `paket-14b-trace-id` (e.g., the paket-14 422 fix at `df02240`). The exact count is not asserted — the meaningful signal is that the 7 `feat(paket-15)` / `chore(paket-15)` / `docs(paket-15)` commits are all present in order.

---

## Verification After All Tasks

- [ ] `.venv/bin/python -m pytest -q` — 677 pass (or 674 pass + 3 skipped without docker).
- [ ] `docker build --no-cache -t anotasyon-platform:final .` — succeeds.
- [ ] `docker compose up -d --build` then `docker compose ps` shows `(healthy)` within 35s.
- [ ] `docker compose exec app id -u` reports `1000`.
- [ ] `docker compose exec app sqlite3 /data/db/annotations.db "SELECT event_type, severity FROM system_events WHERE severity='warn'"` shows the `session_secret_dev_default|warn` row (the compose default triggers it).
- [ ] `docker compose down -v` cleans up.
- [ ] `git log --oneline paket-14b-trace-id..paket-15-docker --grep="paket-15"` lists all 7 task commits (T1..T7) in order.

---

## Rollback / Recovery

Every task is one commit. Standard rollback path:

- If T2 (lifespan WARN) breaks something unexpected: `git revert <T2-sha>` — the WARN logic is isolated and rolling it back leaves the lifespan in its paket-14b state.
- If T3 (Dockerfile rewrite) builds locally but fails on a target host: `git revert <T3-sha>` restores the single-stage Dockerfile from `9b3e283`. Compose still works against the old Dockerfile.
- If T4 (compose) misbehaves: the file was previously untracked, so `git revert <T4-sha>` removes the tracked compose; the engineer can keep a local copy if needed.
- T5, T6, T7 are all additive or polish; safe to revert individually.

`paket-14b-trace-id` is the safety net: every state after that tag is reachable as a one-commit revert away from the previous task.

---

## Out of Scope (per spec §14)

- GitHub Actions CI integration (docker build + smoke test in pipeline) — separate ticket.
- Image vulnerability scan (trivy, snyk, etc.).
- Multi-arch images (amd64 + arm64).
- JSON-structured logs and `/metrics` endpoint.
- Compose memory/CPU resource limits.
- External secret management (Docker secrets, Vault).
- Reverse proxy (nginx, traefik).
- Python 3.11 → 3.13 migration (separate ticket with full suite re-run).
