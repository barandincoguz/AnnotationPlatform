# Paket 16f — Production Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a fresh `docker compose up` deployable to production: env-driven bootstrap admin seeded on first run, default-secret rejection in production, full deployment runbook.

**Architecture:** Three orthogonal changes in lifespan startup: (1) production-mode secret enforcement (fail-fast before DB), (2) bootstrap admin seed (idempotent, after migrations), (3) `.env.example` + `docs/deployment.md` covering ops walkthrough. No frontend changes. No schema changes.

**Tech Stack:** Python 3.11, FastAPI lifespan, sqlite3, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-05-16-paket-16f-production-bootstrap-design.md`

---

## File Structure

| File | Type | Purpose |
|---|---|---|
| `backend/config.py` | edit | Add `ENVIRONMENT`, `BOOTSTRAP_ADMIN_PASSWORD`, `is_production()` |
| `backend/main.py` | edit | Lifespan: call `enforce_production_secrets()` first, `seed_bootstrap_admin()` after migrations |
| `backend/users/service.py` | edit | Add `seed_bootstrap_admin(db, *, username, password)` |
| `backend/shared/prod_enforce.py` | create | `enforce_production_secrets()` function + `ProductionConfigError` |
| `tests/conftest.py` | edit | Set `ENVIRONMENT=test` near top (alongside `DISABLE_SPA_MOUNT`) |
| `backend/tests/test_bootstrap.py` | create | 8 tests for `seed_bootstrap_admin` |
| `backend/tests/test_prod_enforcement.py` | create | 6 tests for `enforce_production_secrets` |
| `.env.example` | edit | Add `ENVIRONMENT`, `BOOTSTRAP_ADMIN_PASSWORD` with prod guidance |
| `docs/deployment.md` | create | 10-section runbook |

**Naming note:** Existing `tests/conftest.py` has a fixture called `bootstrap_admin` (test helper that registers + direct-DB-promotes a user). Different layer. Production seed function is `seed_bootstrap_admin` to avoid collision.

---

## Task 1: Config env vars + `is_production()` helper

**Files:**
- Modify: `backend/config.py`

- [ ] **Step 1: Edit `backend/config.py` — add new vars + helper**

Append to end of file (after `SUPPORTED_EXTENSIONS`, before `def ensure_dirs`):

```python
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")

_VALID_ENVIRONMENTS = {"development", "test", "production"}


def is_production() -> bool:
    """True iff ENVIRONMENT env var is exactly 'production' (case-insensitive)."""
    return ENVIRONMENT == "production"


def validate_environment() -> None:
    """Raise RuntimeError if ENVIRONMENT is not one of the accepted values."""
    if ENVIRONMENT not in _VALID_ENVIRONMENTS:
        raise RuntimeError(
            f"ENVIRONMENT must be one of: {sorted(_VALID_ENVIRONMENTS)} "
            f"(got: {ENVIRONMENT!r})"
        )
```

- [ ] **Step 2: Commit**

```bash
git add backend/config.py
git commit -m "$(cat <<'EOF'
feat(paket-16f): config — ENVIRONMENT + BOOTSTRAP_ADMIN_PASSWORD

Adds ENVIRONMENT env var (development|test|production), is_production()
helper, validate_environment() guard, and BOOTSTRAP_ADMIN_PASSWORD env.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Conftest autouse — set `ENVIRONMENT=test`

**Files:**
- Modify: `tests/conftest.py`

The existing 768 tests must stay green. They have not set ENVIRONMENT before. Default is `development`. If we leave it that way, production-enforcement tests cannot toggle it cleanly via `monkeypatch.setenv`. Set the default to `test` in conftest, matching the existing `DISABLE_SPA_MOUNT` pattern.

- [ ] **Step 1: Edit `tests/conftest.py` — add ENVIRONMENT default near top**

Find existing line:
```python
os.environ.setdefault("DISABLE_SPA_MOUNT", "1")
```

Add directly after it:
```python
os.environ.setdefault("ENVIRONMENT", "test")
```

- [ ] **Step 2: Run full backend test suite**

Run:
```bash
.venv/bin/pytest backend/tests/ tests/ -q
```

Expected: same pass count as baseline (768 prior to this paket). Zero new failures.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "$(cat <<'EOF'
test(paket-16f): conftest — default ENVIRONMENT=test

Sets ENVIRONMENT=test via os.environ.setdefault next to the
DISABLE_SPA_MOUNT default so existing test suite cannot accidentally
trip production enforcement when added in next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `enforce_production_secrets()` (TDD)

**Files:**
- Create: `backend/shared/prod_enforce.py`
- Create: `backend/tests/test_prod_enforcement.py`
- Modify: `backend/main.py`

This task is TDD: write all 6 failing tests first, watch them fail, implement, watch them pass, then wire into lifespan and re-verify.

- [ ] **Step 1: Create `backend/tests/test_prod_enforcement.py` — all 6 tests**

```python
"""Tests for backend.shared.prod_enforce.enforce_production_secrets.

The function is fail-fast: in production mode it raises ProductionConfigError
listing every violation before app boot. In dev/test mode it is a no-op.
"""
import pytest

from backend.shared.prod_enforce import (
    enforce_production_secrets,
    ProductionConfigError,
)


def test_prod_rejects_default_secret(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "dev-secret-DO-NOT-USE-IN-PROD")
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    with pytest.raises(ProductionConfigError) as exc:
        enforce_production_secrets()
    assert "SESSION_SECRET" in str(exc.value)
    assert "default placeholder" in str(exc.value)


def test_prod_rejects_short_secret(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "x" * 16)
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    with pytest.raises(ProductionConfigError) as exc:
        enforce_production_secrets()
    assert "32 characters" in str(exc.value)


def test_prod_accepts_strong_secret(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "a" * 32)
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "https://example.com/repo.git")
    enforce_production_secrets()  # no raise


def test_prod_rejects_short_bootstrap_password(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "a" * 32)
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "shorty")
    with pytest.raises(ProductionConfigError) as exc:
        enforce_production_secrets()
    assert "BOOTSTRAP_ADMIN_PASSWORD" in str(exc.value)
    assert "12 characters" in str(exc.value)


def test_dev_allows_default_secret(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "development")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "dev-secret-DO-NOT-USE-IN-PROD")
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    enforce_production_secrets()  # no raise


def test_prod_warns_no_backup_url(monkeypatch, capsys):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "a" * 32)
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "")
    enforce_production_secrets()  # warn-only, no raise
    captured = capsys.readouterr()
    assert "no backup configured" in captured.err.lower()
```

- [ ] **Step 2: Run tests to verify all 6 fail**

Run:
```bash
.venv/bin/pytest backend/tests/test_prod_enforcement.py -v
```

Expected: 6 FAIL with `ModuleNotFoundError: No module named 'backend.shared.prod_enforce'`.

- [ ] **Step 3: Create `backend/shared/prod_enforce.py` — implementation**

```python
"""Production-mode secret enforcement.

Called from lifespan startup BEFORE DB work so misconfigured deploys
fail fast and loud (Docker Compose restart loop will keep retrying,
but stderr makes diagnosis trivial).
"""
import sys

from backend import config


_DEV_SESSION_SECRETS = {
    "dev-secret-DO-NOT-USE-IN-PROD",  # backend/config.py default
    "dev-secret-change-me",            # docker-compose.yml default
}

_MIN_SESSION_SECRET_LEN = 32
_MIN_BOOTSTRAP_PASSWORD_LEN = 12


class ProductionConfigError(RuntimeError):
    """Raised when production mode is enabled but config is unsafe."""


def enforce_production_secrets() -> None:
    """In ENVIRONMENT=production: hard-fail on any unsafe config.

    Otherwise: no-op.
    """
    if config.ENVIRONMENT != "production":
        return

    errors: list[str] = []

    if config.SESSION_SECRET in _DEV_SESSION_SECRETS:
        errors.append(
            "SESSION_SECRET must not be the default placeholder "
            "(set via env var; generate with `openssl rand -hex 32`)"
        )
    elif len(config.SESSION_SECRET) < _MIN_SESSION_SECRET_LEN:
        errors.append(
            f"SESSION_SECRET must be at least {_MIN_SESSION_SECRET_LEN} characters "
            f"(current: {len(config.SESSION_SECRET)})"
        )

    if config.BOOTSTRAP_ADMIN_PASSWORD and \
            len(config.BOOTSTRAP_ADMIN_PASSWORD) < _MIN_BOOTSTRAP_PASSWORD_LEN:
        errors.append(
            f"BOOTSTRAP_ADMIN_PASSWORD must be at least "
            f"{_MIN_BOOTSTRAP_PASSWORD_LEN} characters in production"
        )

    if errors:
        msg = "production mode enforcement failed:\n  - " + "\n  - ".join(errors)
        msg += "\nSet ENVIRONMENT=development to disable enforcement."
        raise ProductionConfigError(msg)

    # Warnings (stderr only, do not abort boot)
    if not config.BACKUP_REPO_URL:
        print(
            "WARNING: no backup configured (BACKUP_REPO_URL empty); "
            "set it for automatic GitHub backup.",
            file=sys.stderr,
        )
```

- [ ] **Step 4: Run tests to verify all 6 pass**

Run:
```bash
.venv/bin/pytest backend/tests/test_prod_enforcement.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Wire into `backend/main.py` lifespan**

In `backend/main.py`, add import near other backend imports:
```python
from backend.shared.prod_enforce import enforce_production_secrets
```

In the `lifespan` function, add `enforce_production_secrets()` as the very first line after the `async def lifespan(_app: FastAPI):` signature:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.validate_environment()
    enforce_production_secrets()
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        applied = apply_migrations(conn, discover_migrations())
        # ... rest unchanged
```

- [ ] **Step 6: Run full backend suite to verify zero regression**

Run:
```bash
.venv/bin/pytest backend/tests/ tests/ -q
```

Expected: 768 prior + 6 new = 774 PASS, 0 fail.

- [ ] **Step 7: Commit**

```bash
git add backend/shared/prod_enforce.py backend/tests/test_prod_enforcement.py backend/main.py
git commit -m "$(cat <<'EOF'
feat(paket-16f): production-mode secret enforcement

enforce_production_secrets() runs first in lifespan when
ENVIRONMENT=production: rejects default SESSION_SECRET, secrets
shorter than 32 chars, and BOOTSTRAP_ADMIN_PASSWORD shorter than
12 chars. Warns (does not fail) on missing BACKUP_REPO_URL.

Dev/test modes: no-op. 6 tests cover both branches.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `seed_bootstrap_admin()` (TDD)

**Files:**
- Modify: `backend/users/service.py` (add new function)
- Create: `backend/tests/test_bootstrap.py`
- Modify: `backend/main.py` (wire into lifespan)

- [ ] **Step 1: Create `backend/tests/test_bootstrap.py` — all 8 tests**

```python
"""Tests for backend.users.service.seed_bootstrap_admin.

Behaviour:
  - Idempotent: only seeds when no active admin exists.
  - Fails on username conflict with existing non-admin user.
  - Fails when password set is None / empty while username set.
  - Audit-logs the seed via admin_audit_log.
"""
import pytest

from backend.shared.db import connect
from backend.shared import auth
from backend.users import service
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "bootstrap.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def test_seed_creates_admin_when_no_admin(db):
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    row = db.execute(
        "SELECT username, role, is_active, has_passed_training, has_seen_manual "
        "FROM users WHERE username=?",
        ("rootadmin",),
    ).fetchone()
    assert row is not None
    assert row["role"] == "admin"
    assert row["is_active"] == 1
    assert row["has_passed_training"] == 1
    assert row["has_seen_manual"] == 1


def test_seed_idempotent(db):
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    count = db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE username=?", ("rootadmin",)
    ).fetchone()["c"]
    assert count == 1


def test_seed_skipped_when_admin_exists(db):
    db.execute(
        "INSERT INTO users(username, password_hash, role, is_active, "
        "avatar_color, created_at, updated_at) "
        "VALUES (?, ?, 'admin', 1, '#000', datetime('now'), datetime('now'))",
        ("existing_admin", auth.hash_password("anypass1234")),
    )
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    row = db.execute("SELECT 1 FROM users WHERE username=?", ("rootadmin",)).fetchone()
    assert row is None  # no new admin seeded


def test_seed_fails_if_username_taken_by_user(db):
    db.execute(
        "INSERT INTO users(username, password_hash, role, is_active, "
        "avatar_color, created_at, updated_at) "
        "VALUES (?, ?, 'user', 1, '#000', datetime('now'), datetime('now'))",
        ("rootadmin", auth.hash_password("userpass1234")),
    )
    with pytest.raises(RuntimeError) as exc:
        service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    assert "conflicts with existing non-admin user" in str(exc.value)


def test_seed_skipped_when_env_missing(db):
    # username empty → skip silently
    service.seed_bootstrap_admin(db, username="", password="strongpass1234")
    count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    assert count == 0
    # password empty → skip silently
    service.seed_bootstrap_admin(db, username="rootadmin", password="")
    count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    assert count == 0


def test_seed_writes_audit_log(db):
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    row = db.execute(
        "SELECT action_type, target_kind, metadata_json "
        "FROM admin_audit_log WHERE action_type=?",
        ("bootstrap_admin_seed",),
    ).fetchone()
    assert row is not None
    assert row["target_kind"] == "user"
    assert "lifespan" in (row["metadata_json"] or "")


def test_seed_password_hashed_correctly(db):
    service.seed_bootstrap_admin(db, username="rootadmin", password="strongpass1234")
    row = db.execute(
        "SELECT password_hash FROM users WHERE username=?", ("rootadmin",)
    ).fetchone()
    assert row["password_hash"] != "strongpass1234"  # not plaintext
    assert auth.verify_password("strongpass1234", row["password_hash"]) is True


def test_seed_admin_can_login(client, monkeypatch):
    """End-to-end: seed then login via HTTP. Uses TestClient fixture from conftest."""
    from backend.shared.db import connect
    from backend import config

    conn = connect(config.DB_PATH)
    try:
        service.seed_bootstrap_admin(conn, username="rootadmin", password="strongpass1234")
    finally:
        conn.close()

    r = client.post("/api/auth/login", json={
        "username": "rootadmin",
        "password": "strongpass1234",
    })
    assert r.status_code == 200, r.text
    # Verify role from /me
    r2 = client.get("/api/auth/me")
    assert r2.status_code == 200
    assert r2.json()["role"] == "admin"
```

- [ ] **Step 2: Run tests to verify all 8 fail**

Run:
```bash
.venv/bin/pytest backend/tests/test_bootstrap.py -v
```

Expected: 8 FAIL with `AttributeError: module 'backend.users.service' has no attribute 'seed_bootstrap_admin'`.

- [ ] **Step 3: Add `seed_bootstrap_admin` to `backend/users/service.py`**

Find the import block at the top of `backend/users/service.py`. Confirm these imports already exist (do not duplicate):
```python
from backend.shared import auth
from backend.shared import audit
```
If `audit` is not imported, add it.

Add this function at the end of the file (after `register` and `login`, before any module-level constants):

```python
def seed_bootstrap_admin(
    db: sqlite3.Connection,
    *,
    username: str,
    password: str,
) -> None:
    """Idempotent first-admin seed for production bootstrap.

    Triggered by lifespan after migrations. Behaviour:
      - Skip silently if either username or password is empty.
      - Skip silently if any active admin already exists.
      - Raise RuntimeError if username collides with an existing non-admin.
      - Otherwise: insert admin user (training+manual flags pre-set),
        log to admin_audit_log, print one stderr line.
    """
    import sys
    if not username or not password:
        return

    active_admin = db.execute(
        "SELECT 1 FROM users WHERE role='admin' AND is_active=1 LIMIT 1"
    ).fetchone()
    if active_admin is not None:
        return

    existing = db.execute(
        "SELECT id, role FROM users WHERE username=?", (username,)
    ).fetchone()
    if existing is not None and existing["role"] != "admin":
        raise RuntimeError(
            f"BOOTSTRAP_ADMIN_USERNAME={username!r} conflicts with "
            f"existing non-admin user"
        )

    now = _now()
    cur = db.execute(
        """
        INSERT INTO users(
            username, email, password_hash, role, is_active,
            has_seen_manual, has_passed_training,
            avatar_color, created_at, updated_at
        )
        VALUES (?, NULL, ?, 'admin', 1, 1, 1, ?, ?, ?)
        """,
        (
            username,
            auth.hash_password(password),
            _avatar_color_for(username),
            now, now,
        ),
    )
    user_id = cur.lastrowid
    assert user_id is not None

    db.execute(
        """
        INSERT INTO gamification_state(user_id, updated_at)
        VALUES (?, ?)
        """,
        (user_id, now),
    )

    audit.log_admin_action(
        db,
        admin_user_id=user_id,
        action_type="bootstrap_admin_seed",
        target_kind="user",
        target_id=str(user_id),
        metadata={"source": "lifespan"},
    )

    print(f"Bootstrap admin {username!r} created (id={user_id})", file=sys.stderr)
```

- [ ] **Step 4: Run tests to verify all 8 pass**

Run:
```bash
.venv/bin/pytest backend/tests/test_bootstrap.py -v
```

Expected: 8 PASS.

- [ ] **Step 5: Wire into `backend/main.py` lifespan**

Add import near other backend imports:
```python
from backend.users.service import seed_bootstrap_admin
```

In `lifespan`, immediately after `apply_migrations(...)`, add the seed call within the same `try` block (it shares the `conn`):

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.validate_environment()
    enforce_production_secrets()
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        applied = apply_migrations(conn, discover_migrations())
        seed_bootstrap_admin(
            conn,
            username=config.BOOTSTRAP_ADMIN_USERNAME,
            password=config.BOOTSTRAP_ADMIN_PASSWORD,
        )
        audit.log_system_event(
            conn, "startup", "info",
            message=f"app v{VERSION} started; migrations applied: {applied}",
            extra={"version": VERSION, "migrations_applied": applied},
        )
        # ... rest unchanged (dev-secret warning, etc.)
```

- [ ] **Step 6: Run full backend suite to verify zero regression**

Run:
```bash
.venv/bin/pytest backend/tests/ tests/ -q
```

Expected: 768 prior + 6 (Task 3) + 8 (Task 4) = 782 PASS, 0 fail.

- [ ] **Step 7: Commit**

```bash
git add backend/users/service.py backend/tests/test_bootstrap.py backend/main.py
git commit -m "$(cat <<'EOF'
feat(paket-16f): seed_bootstrap_admin in lifespan startup

seed_bootstrap_admin(db, *, username, password) creates first admin
when admins table empty AND both env vars set. Idempotent across
restarts. Refuses to overwrite an existing non-admin with same
username. Writes 'bootstrap_admin_seed' audit log entry. Skips
silently if env vars missing.

8 tests cover seed/skip/idempotent/conflict/audit/hash/login paths.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `.env.example` — document new vars

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Read current `.env.example`**

Run:
```bash
cat .env.example
```

- [ ] **Step 2: Rewrite `.env.example` with grouped sections**

Overwrite with:
```bash
# ---- Environment ----
# Valid values: development (default), test, production
# In production mode the following are enforced at startup:
#   * SESSION_SECRET must not be the default placeholder
#   * SESSION_SECRET must be at least 32 characters
#   * BOOTSTRAP_ADMIN_PASSWORD (if set) must be at least 12 characters
# Misconfigured production deploys fail fast with a single stderr block.
ENVIRONMENT=development

# ---- Data directory ----
# Defaults to <project>/data. Container mounts /data.
# DATA_DIR=/data

# ---- Session ----
# Generate a strong secret:  openssl rand -hex 32
SESSION_SECRET=dev-secret-DO-NOT-USE-IN-PROD
SESSION_COOKIE_NAME=anotasyon_session

# ---- Bootstrap admin (first-run only) ----
# When the users table has zero active admins AND both vars below are set,
# the lifespan startup creates an admin user with these credentials.
# AFTER a successful first seed, unset these from the environment (or
# rotate the password via the admin panel) for hygiene.
BOOTSTRAP_ADMIN_USERNAME=
BOOTSTRAP_ADMIN_PASSWORD=

# ---- Backup (optional, GitHub remote) ----
# When set, the backup loop pushes a JSON snapshot of the DB to a
# GitHub repo every backup window. PAT must have contents:write only.
BACKUP_REPO_URL=
GITHUB_PAT=

# ---- Tests / dev ----
# Set to 1 inside test runs to disable the SPA static mount that would
# fail when backend/static/ does not exist.
# DISABLE_SPA_MOUNT=1
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "$(cat <<'EOF'
docs(paket-16f): .env.example — ENVIRONMENT + bootstrap vars

Adds ENVIRONMENT, BOOTSTRAP_ADMIN_PASSWORD, and inline guidance for
production mode enforcement rules + first-admin seed flow.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `docs/deployment.md` — runbook

**Files:**
- Create: `docs/deployment.md`

- [ ] **Step 1: Create `docs/deployment.md` with all 10 sections**

```markdown
# Deployment Runbook — Anotasyon Platform

This is the production deployment guide. It assumes you have shell
access to a Linux host with Docker installed. The platform ships as
a single container backed by a named volume; HTTPS termination and
DNS are handled by a reverse proxy (Caddy or nginx) in front of it.

## 1. Prerequisites

| Requirement | Why |
|---|---|
| Docker 24+ with Compose v2 | Container runtime, multi-stage build |
| Linux host (Ubuntu 22.04 LTS+ recommended) | Tested base; macOS works for dev only |
| 5 GB free disk | Image + volume + backups |
| Domain name + DNS | Required for HTTPS reverse proxy |
| GitHub PAT (optional) | For off-host backup to private repo |

## 2. Quick start (5 steps)

```bash
# 1. Clone + cd into the repo
git clone <url> anotasyon && cd anotasyon

# 2. Copy + edit env template
cp .env.example .env.production
$EDITOR .env.production

# 3. Generate a strong SESSION_SECRET
openssl rand -hex 32   # paste output into SESSION_SECRET in .env.production

# 4. In .env.production, set:
#   ENVIRONMENT=production
#   BOOTSTRAP_ADMIN_USERNAME=<your-admin-username>
#   BOOTSTRAP_ADMIN_PASSWORD=<≥12 chars>

# 5. Launch
docker compose --env-file .env.production up -d
docker compose logs -f app   # watch for "Bootstrap admin '<x>' created"
```

After healthcheck passes, login at `https://<your-domain>/login` with
the username + password you set, then rotate the password from the
admin panel.

## 3. Environment reference

| Var | Required | Prod-required | Example | Notes |
|---|---|---|---|---|
| `ENVIRONMENT` | no | **yes** | `production` | Must be one of: `development`, `test`, `production` |
| `SESSION_SECRET` | yes | **yes** | `<64 hex chars>` | Must be ≥32 chars in production; never use default |
| `SESSION_COOKIE_NAME` | no | no | `anotasyon_session` | Override if running multiple instances on same host |
| `BOOTSTRAP_ADMIN_USERNAME` | no | recommended | `root` | First-admin seed; only acts when users table has no admin |
| `BOOTSTRAP_ADMIN_PASSWORD` | no | recommended | `<≥12 chars>` | Paired with the above; ≥12 chars in production |
| `BACKUP_REPO_URL` | no | recommended | `https://github.com/me/anotasyon-backup.git` | Empty → stderr WARN at boot, no backup |
| `GITHUB_PAT` | no | required if above set | `<fine-grained PAT, contents:write>` | Inject into `BACKUP_REPO_URL` clone URL at runtime |
| `DATA_DIR` | no | no | `/data` | Container default; override only for non-Docker dev |
| `DISABLE_SPA_MOUNT` | no | no | `1` | Set in tests only; do not set in prod |

## 4. First admin walkthrough

The lifespan startup looks for two conditions:
1. `users` table has zero rows with `role='admin' AND is_active=1`
2. Both `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` are set

When both hold, a single admin user is inserted with
`has_passed_training=1` and `has_seen_manual=1` (no onboarding gate),
and an entry is written to `admin_audit_log` with
`action_type='bootstrap_admin_seed'`.

After the first successful boot:
- Login at `/login` with those credentials.
- Open `/admin/users` and rotate the password (or create a new admin
  account and disable the bootstrap one).
- Remove `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD`
  from `.env.production` for hygiene. (Idempotency means leaving them
  in does nothing, but stale secrets in env are bad practice.)

## 5. Backup setup (GitHub remote)

Set up off-host snapshots so a host failure does not destroy data.

```bash
# 1. Create an empty private GitHub repo, e.g. "anotasyon-backup"

# 2. Generate a fine-grained PAT scoped to that repo only:
#    Settings → Developer settings → Personal access tokens →
#    Fine-grained tokens → New token
#    Repository access: "Only select repositories" → <your-backup-repo>
#    Permissions: Contents = Read and write
#    Copy the token immediately.

# 3. In .env.production:
BACKUP_REPO_URL=https://github.com/<you>/anotasyon-backup.git
GITHUB_PAT=github_pat_<...>

# 4. Restart
docker compose --env-file .env.production down
docker compose --env-file .env.production up -d
```

Verify the first backup landed (typically within the backup window):
```bash
docker compose exec app sqlite3 /data/db/annotations.db \
  "SELECT event_type, severity, message FROM system_events \
   WHERE event_type LIKE 'backup_%' ORDER BY id DESC LIMIT 5"
```

You should see `backup_pushed` (info severity) within a few minutes.

## 6. Restore drill

⚠️ **STOP THE APP CONTAINER FIRST.** The CLI does not currently detect
a running server's WAL lock; running restore against a hot DB risks
corruption. See `paket-16f.1` (deferred) for the planned safety
interlock.

```bash
# 1. Stop the app (WAL safety)
docker compose stop app

# 2. Run restore (interactive — prompts for confirmation)
docker compose run --rm \
  -e BACKUP_REPO_URL="$BACKUP_REPO_URL" \
  -e GITHUB_PAT="$GITHUB_PAT" \
  app python -m backend.cli restore-from-github

# 3. Verify
docker compose run --rm app sqlite3 /data/db/annotations.db \
  "SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM annotations;"

# 4. Restart
docker compose --env-file .env.production up -d
```

The pre-restore DB is renamed `corrupt-<timestamp>.db.bak` in `/data/db/`
and kept until you delete it manually.

## 7. Reverse proxy

The app listens on port 8000 in the container, mapped to host 8000 by
default. Terminate HTTPS at a proxy. Two minimal examples:

### Caddy

```caddyfile
your-domain.example.com {
  encode zstd gzip
  reverse_proxy localhost:8000 {
    flush_interval -1            # SSE: do not buffer
  }
}
```

### nginx

```nginx
server {
  listen 443 ssl http2;
  server_name your-domain.example.com;

  ssl_certificate     /etc/letsencrypt/live/your-domain.example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/your-domain.example.com/privkey.pem;

  location /api/events {       # SSE endpoint
    proxy_pass http://127.0.0.1:8000;
    proxy_buffering off;
    proxy_read_timeout 24h;
    proxy_set_header Connection '';
  }

  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

## 8. Logs and observability

```bash
docker compose logs -f app          # follow stdout/stderr
docker compose ps                    # container status + health
docker compose exec app sqlite3 /data/db/annotations.db \
  "SELECT * FROM system_events ORDER BY id DESC LIMIT 50"
```

Health endpoints:
- `GET /api/health` — liveness (200 if process up; used by Docker HEALTHCHECK)
- `GET /api/health/db` — readiness (200 if DB query succeeds; manual use)

The `system_events` table is the structured-event log for everything the
backup loop, retention loop, and lifespan do. Filter by severity:
```sql
SELECT * FROM system_events WHERE severity='error' ORDER BY id DESC LIMIT 20;
```

## 9. Upgrade procedure

```bash
cd anotasyon
git pull
docker compose down
docker compose --env-file .env.production up -d --build
docker compose logs -f app          # confirm migrations applied
```

The container runs `python -m backend.cli migrate` on every start
(idempotent — `schema_migrations` table tracks applied versions).

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Container restart-loops with `FATAL: production mode enforcement failed` | `ENVIRONMENT=production` but `SESSION_SECRET` is default or short | Generate a real secret, redeploy |
| `RuntimeError: ENVIRONMENT must be one of: [...]` | Typo (e.g. `prod`, `PROD`) | Use exactly `production` (lowercase) |
| `WARNING: no backup configured` in logs | `BACKUP_REPO_URL` empty | Either set it or accept no backup (acknowledged) |
| `Bootstrap admin '<x>' created` never appears | Either env vars missing, or an active admin already exists | Check `users` table; reset env if intentional first seed |
| Login returns 401 with correct password | Username taken by older non-admin user | Choose a different `BOOTSTRAP_ADMIN_USERNAME`, redeploy |
| SSE updates stuck / not pushing | Reverse proxy is buffering | Set `proxy_buffering off` (nginx) or `flush_interval -1` (Caddy) for `/api/events` |
| Restore says `git clone timed out` | Network / PAT scope issue | Verify `GITHUB_PAT` has `contents:write` on the backup repo |

For deeper diagnosis, the `admin_audit_log` and `system_events` tables
are the authoritative source of what the server did and when.
```

- [ ] **Step 2: Commit**

```bash
git add docs/deployment.md
git commit -m "$(cat <<'EOF'
docs(paket-16f): deployment runbook

Single-file production deployment guide covering prerequisites,
quickstart, env reference, first-admin walkthrough, backup setup,
restore drill, reverse-proxy (Caddy + nginx with SSE flushing),
logs/observability, upgrade procedure, troubleshooting table.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Acceptance + tag

**Files:**
- (no edits — verification only)

- [ ] **Step 1: Run full backend test suite**

Run:
```bash
.venv/bin/pytest backend/tests/ tests/ -q
```

Expected: 768 prior + 14 new (6 enforcement + 8 bootstrap) = 782 PASS, 0 fail.

- [ ] **Step 2: Run full frontend test suite**

Run:
```bash
cd frontend && npm test -- --run
```

Expected: 455 PASS (no frontend impact). If anything red, investigate.

- [ ] **Step 3: Lint check (backend)**

Run:
```bash
.venv/bin/python -m pyflakes backend/shared/prod_enforce.py backend/users/service.py backend/main.py
```

Expected: zero output (no findings).

- [ ] **Step 4: Manual dev-mode boot**

Run:
```bash
.venv/bin/uvicorn backend.main:app --port 8765
```

In another shell:
```bash
curl http://127.0.0.1:8765/api/health
```

Expected: `200 OK`. Kill the server with Ctrl+C.

- [ ] **Step 5: Manual production-mode failure scenario**

Run with deliberately bad config:
```bash
ENVIRONMENT=production SESSION_SECRET=dev-secret-DO-NOT-USE-IN-PROD \
  .venv/bin/uvicorn backend.main:app --port 8765
```

Expected: exits within ~1s with stderr block:
```
FATAL: production mode enforcement failed:
  - SESSION_SECRET must not be the default placeholder ...
```

- [ ] **Step 6: Manual production-mode success scenario**

Run with valid config + bootstrap, using an isolated DATA_DIR so the
real DB is untouched:
```bash
mkdir -p /tmp/16f-smoke/data
ENVIRONMENT=production \
SESSION_SECRET="$(openssl rand -hex 32)" \
BOOTSTRAP_ADMIN_USERNAME=smoketest \
BOOTSTRAP_ADMIN_PASSWORD=smoketest12345 \
DATA_DIR=/tmp/16f-smoke/data \
  .venv/bin/uvicorn backend.main:app --port 8765 &
sleep 2
curl -s http://127.0.0.1:8765/api/health
curl -s -c /tmp/16f-smoke/cookie.txt -H 'Content-Type: application/json' \
  -d '{"username":"smoketest","password":"smoketest12345"}' \
  http://127.0.0.1:8765/api/auth/login
curl -s -b /tmp/16f-smoke/cookie.txt http://127.0.0.1:8765/api/auth/me
kill %1
rm -rf /tmp/16f-smoke
```

Expected:
- Stderr contains: `Bootstrap admin 'smoketest' created (id=1)`
- Login: `200`, response includes `role: "admin"`
- `/me`: `role: "admin"`

- [ ] **Step 7: Docker rebuild + healthcheck (optional but recommended)**

```bash
docker compose build app
docker compose up -d app
sleep 30  # wait for healthcheck
docker compose ps   # column STATUS should show "(healthy)"
docker compose down
```

If `docker` is not available locally, skip — CI/host will catch it.

- [ ] **Step 8: Tag the release**

```bash
git tag paket-16f-production-bootstrap
git log --oneline -1
git tag | tail -5
```

- [ ] **Step 9: Final status report**

Report back with:
- Backend test count (expected 782)
- Frontend test count (expected 455)
- Manual smoke test outcomes
- Tag name + final commit SHA
- Any acceptance criterion that failed

---

## Self-Review Notes

**Spec coverage check:**
- D1 bootstrap behavior → Task 4
- D2 production enforcement → Task 3
- D3 lifespan ordering → Task 3 step 5 + Task 4 step 5 (in correct sequence)
- D4 `.env.example` → Task 5
- D5 deployment runbook → Task 6
- D6 test strategy → Tasks 3 + 4

**Acceptance criteria mapping:**
- 768+14 = 782 backend tests pass → Task 7 step 1
- Production default-secret rejection → Task 7 step 5
- Production happy path with admin seed → Task 7 step 6
- Dev mode unchanged → Task 7 step 4
- `docs/deployment.md` exists → Task 6
- `.env.example` documents all vars → Task 5
- Docker healthcheck → Task 7 step 7
- No frontend changes → Task 7 step 2 (455 unchanged)

**Type-consistency check:** `seed_bootstrap_admin` signature is `(db, *, username, password) -> None` everywhere (Task 4 test, implementation, lifespan wiring, plan headers). `enforce_production_secrets` is `() -> None` everywhere.

**Placeholder check:** No TBD/TODO/"similar to X"/"add appropriate handling". Each step is concrete.
