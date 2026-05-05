# Paket 1 — Foundation Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modüler backend iskeletini ve veri katmanını sıfırdan kur — migration sistemi, 19 tablolu şema, shared helpers (DB, auth, audit, SSE, settings), health endpoint, CLI. Sonraki paketler (auth routes, doc ingestion, annotations) bu temele oturur.

**Architecture:** FastAPI uygulaması Docker-friendly bir tek-process. SQLite (WAL mode) ile veri katmanı, version-tracked migration sistemi (`schema_migrations` tablosu) ile şema yönetimi. Cross-cutting kaygılar (DB conn, auth helpers, event logging, SSE broker, site settings) `backend/shared/` altında modüler dosyalara ayrılır — her dosyanın tek sorumluluğu var. Domain modülleri (`users/`, `documents/`, ...) bu pakette boş bırakılır; ait oldukları paketlerde doldurulur.

**Tech Stack:** Python 3.11+, FastAPI 0.115, Uvicorn, SQLite (stdlib), bcrypt, pytest, httpx (TestClient), pytest-asyncio.

---

## Mimari Kararlar (Implementation-Critical)

- **Migration sistemi:** Auto-discovery — `backend/migrations/` altındaki `vNNNN_*.py` dosyalarındaki `up(conn)` fonksiyonu sırayla çalışır. `schema_migrations` tablosu hangi versiyonun uygulandığını takip eder. Tekrar çalıştırmak no-op (idempotent).
- **DB connection:** Her request kendi connection'ını açar (SQLite + WAL stateless). Connection helper `connect(db_path)` döner. Her connection'da `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`.
- **SSE broker:** In-memory dict (`subscribers: dict[user_id, list[Queue]]`). Bir kullanıcı çoklu sekme açabilir → çoklu queue. Single-process tasarım (Package 1 ölçeği için yeterli).
- **Settings:** Key-value JSON (`site_settings`). Typed accessor `get_int(key, default)`, `get_dict(key, default)` vb. Defaults `v0001` migration'da seed edilir.
- **Audit:** `shared/audit.py` 4 farklı event türünün tek girişi — `log_activity`, `log_behavioral`, `log_admin_action`, `log_system_event`. Doğrudan SQL insert (background queue yok, simplicity için).
- **Auth helpers:** Sadece password hash/verify ve session token generation. Routes Package 2'de.
- **CLI:** `python -m backend.cli migrate` komutu Docker entrypoint'inde çalışır.

## Dosya Yapısı

```
backend/
  __init__.py              # boş
  main.py                  # FastAPI app, lifespan, /api/health
  config.py                # path constants, env var helpers
  cli.py                   # `python -m backend.cli migrate`
  shared/
    __init__.py            # boş
    db.py                  # connect(), tx context manager
    settings.py            # site_settings typed getters/setters
    audit.py               # 4 event log entry helper
    auth.py                # bcrypt + session token
    sse.py                 # SSEBroker class
  migrations/
    __init__.py            # discover_migrations()
    runner.py              # migrate_up(), applied_versions()
    v0001_initial_schema.py  # 19 tablo + indices + defaults

tests/
  __init__.py
  conftest.py              # db, client fixtures
  test_db.py
  test_migrations.py
  test_schema.py
  test_settings.py
  test_audit.py
  test_auth.py
  test_sse.py
  test_health.py
  test_cli.py

data/
  documents/.gitkeep       # input docs (boş)

Dockerfile
docker-compose.yml
.dockerignore
.gitignore
.env.example
requirements.txt
pyproject.toml
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`, `pyproject.toml`, `.gitignore`, `.env.example`, `.dockerignore`, `backend/__init__.py`, `tests/__init__.py`, `data/documents/.gitkeep`

- [ ] **Step 1: Create `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
bcrypt==4.2.0
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "anotasyon-platform"
version = "0.1.0"
requires-python = ">=3.11"

[tool.setuptools]
packages = ["backend"]

[tool.setuptools.package-data]
backend = ["**/*.py"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.pyright]
include = ["backend", "tests"]
extraPaths = ["."]
venvPath = "."
venv = ".venv"
pythonPath = ".venv/bin/python"

[[tool.pyright.executionEnvironments]]
root = "tests"
extraPaths = [".."]
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
*.egg-info/
build/
dist/
.pytest_cache/
.venv/
venv/
.env
data/db/
data/backup/
data/documents/*
!data/documents/.gitkeep
data/exports/
.DS_Store
```

- [ ] **Step 4: Create `.dockerignore`**

```
__pycache__/
*.pyc
*.egg-info/
.venv/
.pytest_cache/
.git/
.env
data/
docs/
tests/
*.md
```

- [ ] **Step 5: Create `.env.example`**

```
# Database
DATA_DIR=/data

# Authentication
SESSION_SECRET=change-me-to-a-random-32-byte-string
SESSION_COOKIE_NAME=anotasyon_session

# GitHub Backup (optional, used in Package 12)
BACKUP_REPO_URL=
GITHUB_PAT=

# Bootstrap (Package 2)
BOOTSTRAP_ADMIN_USERNAME=
```

- [ ] **Step 6: Create empty `__init__.py` files and `.gitkeep`**

```bash
mkdir -p backend tests data/documents
touch backend/__init__.py tests/__init__.py data/documents/.gitkeep
```

- [ ] **Step 7: Create venv and install**

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

Expected: clean install, no errors.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt pyproject.toml .gitignore .dockerignore .env.example backend/ tests/ data/
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "chore: scaffold project with deps and pyproject config"
```

---

## Task 2: Config Module

**Files:**
- Create: `backend/config.py`

- [ ] **Step 1: Write `backend/config.py`**

```python
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
DB_DIR = DATA_DIR / "db"
DB_PATH = DB_DIR / "annotations.db"
DOCUMENTS_DIR = DATA_DIR / "documents"
BACKUP_DIR = DATA_DIR / "backup"
EXPORTS_DIR = DATA_DIR / "exports"

SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-secret-DO-NOT-USE-IN-PROD")
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "anotasyon_session")

BACKUP_REPO_URL = os.environ.get("BACKUP_REPO_URL", "")
GITHUB_PAT = os.environ.get("GITHUB_PAT", "")
BOOTSTRAP_ADMIN_USERNAME = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "")

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


def ensure_dirs() -> None:
    """Create all required data directories. Called from main.py lifespan."""
    for d in [DATA_DIR, DB_DIR, DOCUMENTS_DIR, BACKUP_DIR, EXPORTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 2: Smoke import**

```bash
. .venv/bin/activate
python -c "from backend import config; config.ensure_dirs(); print(config.DB_PATH)"
```

Expected: prints `/Users/.../deneme/data/db/annotations.db`, `data/db/` directory created.

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(config): add path constants and env helpers"
```

---

## Task 3: shared/db.py — Connection Helpers (TDD)

**Files:**
- Create: `backend/shared/__init__.py`, `backend/shared/db.py`, `tests/conftest.py`, `tests/test_db.py`

- [ ] **Step 1: Create `backend/shared/__init__.py` (empty)**

```bash
mkdir -p backend/shared
touch backend/shared/__init__.py
```

- [ ] **Step 2: Write `tests/conftest.py`**

```python
from pathlib import Path
import pytest


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"
```

- [ ] **Step 3: Write `tests/test_db.py` (failing)**

```python
import sqlite3
from backend.shared.db import connect


def test_connect_returns_connection(db_path):
    conn = connect(db_path)
    try:
        assert isinstance(conn, sqlite3.Connection)
    finally:
        conn.close()


def test_connect_enables_wal_mode(db_path):
    conn = connect(db_path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        conn.close()


def test_connect_enables_foreign_keys(db_path):
    conn = connect(db_path)
    try:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
    finally:
        conn.close()


def test_connect_uses_row_factory(db_path):
    conn = connect(db_path)
    try:
        conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'hi')")
        row = conn.execute("SELECT * FROM t").fetchone()
        assert row["a"] == 1
        assert row["b"] == "hi"
    finally:
        conn.close()
```

- [ ] **Step 4: Run — expect FAIL (ImportError)**

```bash
. .venv/bin/activate && pytest tests/test_db.py -v
```
Expected: `ModuleNotFoundError: backend.shared.db`.

- [ ] **Step 5: Write `backend/shared/db.py`**

```python
import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    """Open SQLite connection with WAL mode, foreign keys, Row factory.

    Caller is responsible for closing the connection.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

- [ ] **Step 6: Run — expect PASS**

```bash
pytest tests/test_db.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/shared/ tests/conftest.py tests/test_db.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(shared): add db connection helper with WAL and Row factory"
```

---

## Task 4: Migration Runner (TDD)

**Files:**
- Create: `backend/migrations/__init__.py`, `backend/migrations/runner.py`, `tests/test_migrations.py`

- [ ] **Step 1: Create migrations package**

```bash
mkdir -p backend/migrations
```

- [ ] **Step 2: Write `tests/test_migrations.py` (failing)**

```python
import sqlite3
from backend.shared.db import connect
from backend.migrations.runner import (
    Migration, ensure_migrations_table, applied_versions, apply_migrations
)


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def test_ensure_migrations_table_creates_it(db_path):
    conn = connect(db_path)
    try:
        ensure_migrations_table(conn)
        assert _has_table(conn, "schema_migrations")
    finally:
        conn.close()


def test_applied_versions_empty_initially(db_path):
    conn = connect(db_path)
    try:
        ensure_migrations_table(conn)
        assert applied_versions(conn) == set()
    finally:
        conn.close()


def test_apply_migrations_runs_pending(db_path):
    conn = connect(db_path)
    try:
        def m1(c): c.execute("CREATE TABLE m1 (x INT)")
        def m2(c): c.execute("CREATE TABLE m2 (x INT)")
        migs = [Migration("v0001", "first", m1), Migration("v0002", "second", m2)]
        applied = apply_migrations(conn, migs)
        assert applied == ["v0001", "v0002"]
        assert _has_table(conn, "m1")
        assert _has_table(conn, "m2")
        assert applied_versions(conn) == {"v0001", "v0002"}
    finally:
        conn.close()


def test_apply_migrations_idempotent(db_path):
    conn = connect(db_path)
    try:
        def m1(c): c.execute("CREATE TABLE m1 (x INT)")
        migs = [Migration("v0001", "first", m1)]
        first = apply_migrations(conn, migs)
        second = apply_migrations(conn, migs)
        assert first == ["v0001"]
        assert second == []  # already applied, no-op
    finally:
        conn.close()


def test_apply_migrations_skips_already_applied(db_path):
    conn = connect(db_path)
    try:
        def m1(c): c.execute("CREATE TABLE m1 (x INT)")
        def m2(c): c.execute("CREATE TABLE m2 (x INT)")
        apply_migrations(conn, [Migration("v0001", "first", m1)])
        applied = apply_migrations(conn, [
            Migration("v0001", "first", m1),
            Migration("v0002", "second", m2),
        ])
        assert applied == ["v0002"]
    finally:
        conn.close()
```

- [ ] **Step 3: Run — expect FAIL (ImportError)**

```bash
pytest tests/test_migrations.py -v
```

- [ ] **Step 4: Write `backend/migrations/runner.py`**

```python
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


@dataclass
class Migration:
    version: str  # e.g. "v0001"
    name: str
    up: Callable[[sqlite3.Connection], None]


SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TIMESTAMP NOT NULL
)
"""


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA_MIGRATIONS_DDL)


def applied_versions(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r["version"] for r in rows}


def apply_migrations(
    conn: sqlite3.Connection, migrations: list[Migration]
) -> list[str]:
    """Apply pending migrations in version order. Returns versions applied."""
    ensure_migrations_table(conn)
    already = applied_versions(conn)
    pending = sorted(
        [m for m in migrations if m.version not in already],
        key=lambda m: m.version,
    )
    applied = []
    for m in pending:
        m.up(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
            (m.version, m.name, datetime.now(timezone.utc).isoformat()),
        )
        applied.append(m.version)
    return applied
```

- [ ] **Step 5: Write `backend/migrations/__init__.py`**

```python
"""Auto-discover migration modules and expose collected list."""
import importlib
import pkgutil
from backend.migrations.runner import Migration


def discover_migrations() -> list[Migration]:
    """Find all v*.py modules in this package and build Migration list."""
    out = []
    for _, modname, _ in pkgutil.iter_modules(__path__):
        if not modname.startswith("v"):
            continue
        if modname == "runner":
            continue
        mod = importlib.import_module(f"backend.migrations.{modname}")
        version = modname[:5]  # 'v0001'
        name = modname[6:] if len(modname) > 5 else modname
        out.append(Migration(version=version, name=name, up=mod.up))
    return sorted(out, key=lambda m: m.version)
```

- [ ] **Step 6: Run — expect PASS**

```bash
pytest tests/test_migrations.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/migrations/ tests/test_migrations.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(migrations): add version-tracked migration runner with auto-discovery"
```

---

## Task 5: v0001 Initial Schema (19 tables + defaults)

**Files:**
- Create: `backend/migrations/v0001_initial_schema.py`, `tests/test_schema.py`

- [ ] **Step 1: Write `tests/test_schema.py` (failing)**

```python
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


EXPECTED_TABLES = {
    # Core
    "users", "invite_codes", "site_settings", "documents_meta",
    "annotations", "annotation_versions", "drafts", "document_locks",
    # Event logs
    "user_sessions", "activity_events", "behavioral_events",
    "admin_audit_log", "system_events",
    # Auxiliary
    "gamification_state", "gamification_ledger", "badges_earned",
    "training_attempts", "notifications",
    # Hybrid override (Q5)
    "training_gold_doc_overrides",
    # Migration tracking (created by runner)
    "schema_migrations",
}


def _all_tables(conn) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r["name"] for r in rows}


def test_v0001_creates_all_19_tables(db_path):
    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())
        tables = _all_tables(conn)
        missing = EXPECTED_TABLES - tables
        assert not missing, f"Missing tables: {missing}"
    finally:
        conn.close()


def test_v0001_creates_indices(db_path):
    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        index_names = {r["name"] for r in rows}
        # Spot check key indices
        for expected in [
            "idx_users_active", "idx_ver_doc_time", "idx_act_user_time",
            "idx_audit_admin_time", "idx_ledger_user_time",
        ]:
            assert expected in index_names, f"missing index: {expected}"
    finally:
        conn.close()


def test_v0001_seeds_default_settings(db_path):
    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())
        rows = conn.execute("SELECT key FROM site_settings").fetchall()
        keys = {r["key"] for r in rows}
        # Spot check several default keys exist
        for k in [
            "speed_warning.window_seconds",
            "char_limit.warn_threshold",
            "lock.expires_seconds",
            "backup.interval_seconds",
            "training.quiz_pass_threshold",
            "gamification.daily_target_docs",
            "gamification.xp_save",
        ]:
            assert k in keys, f"missing default setting: {k}"
    finally:
        conn.close()


def test_v0001_idempotent(db_path):
    conn = connect(db_path)
    try:
        first = apply_migrations(conn, discover_migrations())
        second = apply_migrations(conn, discover_migrations())
        assert first == ["v0001"]
        assert second == []
    finally:
        conn.close()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_schema.py -v
```

- [ ] **Step 3: Write `backend/migrations/v0001_initial_schema.py`**

```python
"""Initial schema: 19 tables across 4 domains + default site_settings seed."""
import json
import sqlite3
from datetime import datetime, timezone


SCHEMA_SQL = """
-- ============================================================
-- A. CORE — data of record (8 tables)
-- ============================================================

CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    email           TEXT UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
    is_active       INTEGER NOT NULL DEFAULT 1,
    has_passed_training INTEGER NOT NULL DEFAULT 0,
    has_seen_manual INTEGER NOT NULL DEFAULT 0,
    avatar_color    TEXT,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_users_active ON users(is_active);
CREATE INDEX idx_users_role ON users(role);

CREATE TABLE invite_codes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_by_admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    rotated_at      TIMESTAMP,
    created_at      TIMESTAMP NOT NULL
);
CREATE UNIQUE INDEX idx_invite_active ON invite_codes(is_active) WHERE is_active=1;

CREATE TABLE site_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMP NOT NULL,
    updated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE documents_meta (
    document_id     TEXT PRIMARY KEY,
    file_path       TEXT NOT NULL,
    word_count      INTEGER NOT NULL,
    sentence_count  INTEGER NOT NULL,
    text_density    REAL NOT NULL,
    estimated_difficulty TEXT NOT NULL CHECK(estimated_difficulty IN ('Kolay','Orta','Zor')),
    ozelge_no       TEXT,
    topic_category  TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_docs_difficulty ON documents_meta(estimated_difficulty);
CREATE INDEX idx_docs_topic ON documents_meta(topic_category);
CREATE INDEX idx_docs_ozelge ON documents_meta(ozelge_no);

CREATE TABLE annotations (
    document_id     TEXT PRIMARY KEY REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    question_1      TEXT,
    question_2      TEXT,
    question_3      TEXT,
    is_completed    INTEGER NOT NULL DEFAULT 0,
    last_editor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    completed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    edit_count      INTEGER NOT NULL DEFAULT 0,
    unique_users_count INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_ann_completed ON annotations(is_completed);
CREATE INDEX idx_ann_editor ON annotations(last_editor_user_id);

CREATE TABLE annotation_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     TEXT NOT NULL REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    question_1      TEXT,
    question_2      TEXT,
    question_3      TEXT,
    diff_from_previous TEXT,
    is_diff_zero    INTEGER NOT NULL DEFAULT 0,
    action          TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_ver_doc_time ON annotation_versions(document_id, created_at DESC);
CREATE INDEX idx_ver_user_time ON annotation_versions(user_id, created_at DESC);
CREATE INDEX idx_ver_diff_zero ON annotation_versions(is_diff_zero);

CREATE TABLE drafts (
    document_id     TEXT NOT NULL REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_1      TEXT,
    question_2      TEXT,
    question_3      TEXT,
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (document_id, user_id)
);

CREATE TABLE document_locks (
    document_id     TEXT PRIMARY KEY REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    acquired_at     TIMESTAMP NOT NULL,
    last_heartbeat  TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_lock_user ON document_locks(user_id);
CREATE INDEX idx_lock_expires ON document_locks(expires_at);

-- ============================================================
-- B. EVENT LOGS — append-only (5 tables)
-- ============================================================

CREATE TABLE user_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token   TEXT NOT NULL,
    ip_hash         TEXT,
    user_agent      TEXT,
    started_at      TIMESTAMP NOT NULL,
    ended_at        TIMESTAMP,
    last_activity_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_session_user_active ON user_sessions(user_id, ended_at);
CREATE INDEX idx_session_token ON user_sessions(session_token);

CREATE TABLE activity_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    session_id      INTEGER REFERENCES user_sessions(id) ON DELETE SET NULL,
    event_type      TEXT NOT NULL,
    document_id     TEXT,
    duration_ms     INTEGER,
    extra_json      TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_act_user_time ON activity_events(user_id, created_at DESC);
CREATE INDEX idx_act_doc_time ON activity_events(document_id, created_at DESC);
CREATE INDEX idx_act_type_time ON activity_events(event_type, created_at DESC);

CREATE TABLE behavioral_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    detector        TEXT NOT NULL,
    threshold_value REAL,
    actual_value    REAL,
    context_json    TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_beh_user_time ON behavioral_events(user_id, created_at DESC);
CREATE INDEX idx_beh_detector ON behavioral_events(detector);

CREATE TABLE admin_audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    action_type     TEXT NOT NULL,
    target_kind     TEXT,
    target_id       TEXT,
    metadata_json   TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_audit_admin_time ON admin_audit_log(admin_user_id, created_at DESC);
CREATE INDEX idx_audit_action ON admin_audit_log(action_type);

CREATE TABLE system_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK(severity IN ('info','warn','error')),
    message         TEXT,
    extra_json      TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_sys_severity_time ON system_events(severity, created_at DESC);
CREATE INDEX idx_sys_type ON system_events(event_type);

-- ============================================================
-- C. AUXILIARY (5 tables)
-- ============================================================

CREATE TABLE gamification_state (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    total_xp        INTEGER NOT NULL DEFAULT 0,
    current_streak_days INTEGER NOT NULL DEFAULT 0,
    longest_streak_days INTEGER NOT NULL DEFAULT 0,
    last_active_date TEXT,
    today_save_count INTEGER NOT NULL DEFAULT 0,
    today_complete_count INTEGER NOT NULL DEFAULT 0,
    today_review_count INTEGER NOT NULL DEFAULT 0,
    today_skip_count INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP NOT NULL
);

CREATE TABLE gamification_ledger (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    delta_xp        INTEGER NOT NULL,
    reason          TEXT NOT NULL,
    related_doc_id  TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_ledger_user_time ON gamification_ledger(user_id, created_at DESC);

CREATE TABLE badges_earned (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge_id        TEXT NOT NULL,
    earned_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (user_id, badge_id)
);

CREATE TABLE training_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    attempt_number  INTEGER NOT NULL,
    quiz_score      INTEGER NOT NULL,
    quiz_total      INTEGER NOT NULL,
    annotation_pass_count INTEGER NOT NULL,
    annotation_total INTEGER NOT NULL,
    annotation_details_json TEXT,
    passed          INTEGER NOT NULL,
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP NOT NULL
);
CREATE INDEX idx_train_user ON training_attempts(user_id);

CREATE TABLE notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT,
    data_json       TEXT,
    is_read         INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_notif_user_unread ON notifications(user_id, is_read);

-- ============================================================
-- D. HYBRID OVERRIDE (Q5 resolution)
-- ============================================================

CREATE TABLE training_gold_doc_overrides (
    gold_id         TEXT PRIMARY KEY,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    content         TEXT,
    expected_concepts TEXT,
    min_concept_count INTEGER,
    source          TEXT NOT NULL CHECK(source IN ('override','custom')),
    created_by_admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
"""


DEFAULT_SETTINGS: dict[str, tuple[object, str]] = {
    # Speed warning
    "speed_warning.window_seconds": (300, "Hız uyarısı için zaman penceresi (saniye)"),
    "speed_warning.max_saves_in_window": (5, "Pencerede izin verilen max save sayısı"),
    "speed_warning.min_seconds_per_doc": (30, "Bir dokümanda minimum kalma süresi"),
    "speed_warning.min_words_for_min_seconds": (100, "Yukarıdaki kuralın geçerli olduğu min kelime sayısı"),
    # Char limit
    "char_limit.warn_threshold": (300, "Soru başına turuncu uyarı eşiği"),
    "char_limit.alert_threshold": (600, "Soru başına kırmızı uyarı eşiği"),
    # Lock
    "lock.expires_seconds": (300, "Doküman kilidi idle timeout (saniye)"),
    "lock.heartbeat_interval_seconds": (30, "Frontend heartbeat sıklığı"),
    # Backup
    "backup.interval_seconds": (600, "GitHub backup sıklığı (10dk)"),
    # Training
    "training.quiz_pass_threshold": (4, "5 sorudan en az kaç doğru gerekli"),
    "training.annotation_pass_threshold": (2, "3 gold doc'tan en az kaç pass gerekli"),
    "training.max_attempts": (3, "Toplam deneme hakkı"),
    # Gamification
    "gamification.daily_target_docs": (20, "Günlük hedef doc sayısı"),
    "gamification.xp_save": (1, "Sakla başına XP"),
    "gamification.xp_complete": (5, "Tamamlandı işaretle başına XP"),
    "gamification.xp_review": (2, "Review (mevcut annotation düzenle) başına XP"),
    "gamification.xp_review_kept": (3, "Review'in sonraki kullanıcı tarafından korunması bonusu"),
    "gamification.xp_training_pass": (50, "Training pass one-time bonus"),
    "gamification.good_reviewer.min_reviews": (20, "Good Reviewer rozeti min review sayısı"),
    "gamification.good_reviewer.min_kept": (15, "Good Reviewer min korunmuş review sayısı"),
}


def _seed_default_settings(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for key, (value, description) in DEFAULT_SETTINGS.items():
        conn.execute(
            """
            INSERT INTO site_settings(key, value, description, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (key, json.dumps(value), description, now),
        )


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    _seed_default_settings(conn)
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_schema.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/v0001_initial_schema.py tests/test_schema.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(migrations): add v0001 initial schema with 19 tables and default settings"
```

---

## Task 6: shared/settings.py — Typed Accessors (TDD)

**Files:**
- Create: `backend/shared/settings.py`, `tests/test_settings.py`

- [ ] **Step 1: Write `tests/test_settings.py`**

```python
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared import settings as S


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def test_get_int_returns_seeded_default(db):
    assert S.get_int(db, "speed_warning.window_seconds") == 300


def test_get_int_missing_uses_default(db):
    assert S.get_int(db, "no.such.key", default=42) == 42


def test_get_int_missing_no_default_raises(db):
    with pytest.raises(KeyError):
        S.get_int(db, "no.such.key")


def test_set_persists_value(db):
    S.set_value(db, "test.key", 123, updated_by_user_id=None)
    assert S.get_int(db, "test.key") == 123


def test_set_overwrites_existing(db):
    S.set_value(db, "speed_warning.window_seconds", 600, None)
    assert S.get_int(db, "speed_warning.window_seconds") == 600


def test_get_dict_returns_dict(db):
    S.set_value(db, "test.dict", {"a": 1, "b": [2, 3]}, None)
    assert S.get_dict(db, "test.dict") == {"a": 1, "b": [2, 3]}


def test_get_str(db):
    S.set_value(db, "test.str", "hello", None)
    assert S.get_str(db, "test.str") == "hello"


def test_get_float(db):
    S.set_value(db, "test.float", 3.14, None)
    assert S.get_float(db, "test.float") == 3.14


def test_get_all_returns_dict(db):
    all_settings = S.get_all(db)
    assert "gamification.xp_save" in all_settings
    assert all_settings["gamification.xp_save"] == 1
```

- [ ] **Step 2: Run — expect FAIL (ImportError)**

```bash
pytest tests/test_settings.py -v
```

- [ ] **Step 3: Write `backend/shared/settings.py`**

```python
"""Typed key-value access to site_settings table."""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

_MISSING = object()


def _get_raw(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM site_settings WHERE key=?", (key,)
    ).fetchone()
    return row["value"] if row else None


def get_str(conn, key: str, default: Any = _MISSING) -> str:
    raw = _get_raw(conn, key)
    if raw is None:
        if default is _MISSING:
            raise KeyError(key)
        return default
    parsed = json.loads(raw)
    if not isinstance(parsed, str):
        raise TypeError(f"setting {key} is not a string: {type(parsed).__name__}")
    return parsed


def get_int(conn, key: str, default: Any = _MISSING) -> int:
    raw = _get_raw(conn, key)
    if raw is None:
        if default is _MISSING:
            raise KeyError(key)
        return default
    parsed = json.loads(raw)
    if not isinstance(parsed, (int, float)) or isinstance(parsed, bool):
        raise TypeError(f"setting {key} is not numeric: {type(parsed).__name__}")
    return int(parsed)


def get_float(conn, key: str, default: Any = _MISSING) -> float:
    raw = _get_raw(conn, key)
    if raw is None:
        if default is _MISSING:
            raise KeyError(key)
        return default
    parsed = json.loads(raw)
    if not isinstance(parsed, (int, float)):
        raise TypeError(f"setting {key} is not numeric: {type(parsed).__name__}")
    return float(parsed)


def get_dict(conn, key: str, default: Any = _MISSING) -> dict:
    raw = _get_raw(conn, key)
    if raw is None:
        if default is _MISSING:
            raise KeyError(key)
        return default
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise TypeError(f"setting {key} is not a dict")
    return parsed


def get_all(conn) -> dict[str, Any]:
    rows = conn.execute("SELECT key, value FROM site_settings").fetchall()
    return {r["key"]: json.loads(r["value"]) for r in rows}


def set_value(
    conn: sqlite3.Connection,
    key: str,
    value: Any,
    updated_by_user_id: Optional[int],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO site_settings(key, value, updated_at, updated_by_user_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at,
            updated_by_user_id=excluded.updated_by_user_id
        """,
        (key, json.dumps(value), now, updated_by_user_id),
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_settings.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/shared/settings.py tests/test_settings.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(shared): add typed site_settings accessors"
```

---

## Task 7: shared/audit.py — Event Logging (TDD)

**Files:**
- Create: `backend/shared/audit.py`, `tests/test_audit.py`

- [ ] **Step 1: Write `tests/test_audit.py`**

```python
import json
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared import audit


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    # Seed a test user (FK target)
    conn.execute(
        "INSERT INTO users(id, username, password_hash, created_at, updated_at) VALUES (1, 'tester', 'x', datetime('now'), datetime('now'))"
    )
    yield conn
    conn.close()


def test_log_activity_inserts_row(db):
    audit.log_activity(db, user_id=1, event_type="save", document_id="doc_001", duration_ms=4500)
    rows = db.execute("SELECT * FROM activity_events").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "save"
    assert rows[0]["user_id"] == 1
    assert rows[0]["document_id"] == "doc_001"
    assert rows[0]["duration_ms"] == 4500


def test_log_activity_with_extra(db):
    audit.log_activity(db, user_id=1, event_type="open_doc",
                       document_id="doc_001", extra={"from": "review_tab"})
    row = db.execute("SELECT extra_json FROM activity_events").fetchone()
    assert json.loads(row["extra_json"]) == {"from": "review_tab"}


def test_log_behavioral_inserts(db):
    audit.log_behavioral(db, user_id=1, detector="speed_warning",
                          threshold_value=5.0, actual_value=7.0,
                          context={"recent": 7})
    row = db.execute("SELECT * FROM behavioral_events").fetchone()
    assert row["detector"] == "speed_warning"
    assert row["threshold_value"] == 5.0
    assert row["actual_value"] == 7.0


def test_log_admin_action_inserts(db):
    audit.log_admin_action(db, admin_user_id=1, action_type="promote_admin",
                           target_kind="user", target_id="42",
                           metadata={"reason": "trust"})
    row = db.execute("SELECT * FROM admin_audit_log").fetchone()
    assert row["action_type"] == "promote_admin"
    assert row["target_id"] == "42"


def test_log_system_event_inserts(db):
    audit.log_system_event(db, event_type="backup_complete",
                            severity="info", message="OK")
    row = db.execute("SELECT * FROM system_events").fetchone()
    assert row["event_type"] == "backup_complete"
    assert row["severity"] == "info"


def test_log_system_event_invalid_severity(db):
    with pytest.raises(ValueError):
        audit.log_system_event(db, event_type="x", severity="bogus")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_audit.py -v
```

- [ ] **Step 3: Write `backend/shared/audit.py`**

```python
"""Single entry point for all event logging.

Four log channels:
- activity_events: high-frequency user actions (save, skip, open_doc, ...)
- behavioral_events: trigger-based detectors (speed warning, char limit, ...)
- admin_audit_log: sensitive admin operations (immutable record)
- system_events: backup/sync/error logs (sysadmin)
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

VALID_SEVERITIES = {"info", "warn", "error"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_activity(
    conn: sqlite3.Connection,
    user_id: int,
    event_type: str,
    *,
    session_id: Optional[int] = None,
    document_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    extra: Optional[dict] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO activity_events(
            user_id, session_id, event_type, document_id,
            duration_ms, extra_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, session_id, event_type, document_id,
            duration_ms,
            json.dumps(extra) if extra is not None else None,
            _now(),
        ),
    )


def log_behavioral(
    conn: sqlite3.Connection,
    user_id: int,
    detector: str,
    *,
    threshold_value: Optional[float] = None,
    actual_value: Optional[float] = None,
    context: Optional[dict] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO behavioral_events(
            user_id, detector, threshold_value, actual_value,
            context_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, detector, threshold_value, actual_value,
            json.dumps(context) if context is not None else None,
            _now(),
        ),
    )


def log_admin_action(
    conn: sqlite3.Connection,
    admin_user_id: int,
    action_type: str,
    *,
    target_kind: Optional[str] = None,
    target_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO admin_audit_log(
            admin_user_id, action_type, target_kind, target_id,
            metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            admin_user_id, action_type, target_kind, target_id,
            json.dumps(metadata) if metadata is not None else None,
            _now(),
        ),
    )


def log_system_event(
    conn: sqlite3.Connection,
    event_type: str,
    severity: str,
    *,
    message: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"invalid severity: {severity!r} (must be one of {VALID_SEVERITIES})")
    conn.execute(
        """
        INSERT INTO system_events(
            event_type, severity, message, extra_json, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            event_type, severity, message,
            json.dumps(extra) if extra is not None else None,
            _now(),
        ),
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_audit.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/shared/audit.py tests/test_audit.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(shared): add unified event logging entry points"
```

---

## Task 8: shared/auth.py — Password & Session Helpers (TDD)

**Files:**
- Create: `backend/shared/auth.py`, `tests/test_auth.py`

- [ ] **Step 1: Write `tests/test_auth.py`**

```python
from backend.shared import auth


def test_hash_password_returns_bytes_or_str_hash():
    h = auth.hash_password("hunter2")
    assert isinstance(h, str)
    assert h != "hunter2"
    assert h.startswith("$2b$")


def test_hash_password_unique_per_call():
    """bcrypt salts each hash."""
    h1 = auth.hash_password("hunter2")
    h2 = auth.hash_password("hunter2")
    assert h1 != h2


def test_verify_password_correct():
    h = auth.hash_password("hunter2")
    assert auth.verify_password("hunter2", h) is True


def test_verify_password_wrong():
    h = auth.hash_password("hunter2")
    assert auth.verify_password("WRONG", h) is False


def test_verify_password_handles_invalid_hash():
    """Garbage hash should return False, not crash."""
    assert auth.verify_password("any", "not-a-valid-hash") is False


def test_generate_session_token_length():
    t = auth.generate_session_token()
    assert isinstance(t, str)
    assert len(t) >= 32  # urlsafe base64 of 32 bytes ~ 43 chars


def test_generate_session_token_unique():
    tokens = {auth.generate_session_token() for _ in range(100)}
    assert len(tokens) == 100


def test_hash_ip_returns_64_char_hex():
    h = auth.hash_ip("203.0.113.7")
    assert len(h) == 64  # SHA-256 hex
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_ip_deterministic():
    assert auth.hash_ip("1.2.3.4") == auth.hash_ip("1.2.3.4")


def test_hash_ip_different_inputs():
    assert auth.hash_ip("1.2.3.4") != auth.hash_ip("1.2.3.5")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_auth.py -v
```

- [ ] **Step 3: Write `backend/shared/auth.py`**

```python
"""Password hashing, session token generation, IP hashing.

Routes and session storage live in `backend/users/` (Package 2).
"""
import hashlib
import secrets
import bcrypt


def hash_password(plain: str) -> str:
    """Hash a password using bcrypt (work factor 12)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time password verification. Returns False on any error."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def generate_session_token() -> str:
    """URL-safe random token (43 chars from 32 random bytes)."""
    return secrets.token_urlsafe(32)


def hash_ip(ip: str) -> str:
    """SHA-256 hex digest of an IP address. Used for privacy-preserving session logging."""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_auth.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/shared/auth.py tests/test_auth.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(shared): add bcrypt password hashing, session tokens, IP hashing"
```

---

## Task 9: shared/sse.py — Pub/Sub Broker (TDD with async)

**Files:**
- Create: `backend/shared/sse.py`, `tests/test_sse.py`

- [ ] **Step 1: Write `tests/test_sse.py`**

```python
import asyncio
import pytest
from backend.shared.sse import SSEBroker, SSEEvent


@pytest.mark.asyncio
async def test_subscriber_receives_personal_event():
    broker = SSEBroker()
    queue = broker.subscribe(user_id=1)
    await broker.publish_to([1], "badge_unlocked", {"badge_id": "first_annotation"})
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event.event_type == "badge_unlocked"
    assert event.data == {"badge_id": "first_annotation"}


@pytest.mark.asyncio
async def test_other_user_does_not_receive_personal_event():
    broker = SSEBroker()
    q1 = broker.subscribe(user_id=1)
    q2 = broker.subscribe(user_id=2)
    await broker.publish_to([1], "badge_unlocked", {"x": 1})
    await asyncio.wait_for(q1.get(), timeout=1.0)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q2.get(), timeout=0.2)


@pytest.mark.asyncio
async def test_broadcast_reaches_all_users():
    broker = SSEBroker()
    q1 = broker.subscribe(user_id=1)
    q2 = broker.subscribe(user_id=2)
    await broker.publish_broadcast("lock_acquired", {"document_id": "doc_1"})
    e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert e1.event_type == "lock_acquired"
    assert e2.event_type == "lock_acquired"


@pytest.mark.asyncio
async def test_user_can_have_multiple_queues_one_per_tab():
    broker = SSEBroker()
    q_tab1 = broker.subscribe(user_id=1)
    q_tab2 = broker.subscribe(user_id=1)
    await broker.publish_to([1], "speed_warning", {"msg": "slow"})
    e1 = await asyncio.wait_for(q_tab1.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q_tab2.get(), timeout=1.0)
    assert e1.data == {"msg": "slow"}
    assert e2.data == {"msg": "slow"}


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    broker = SSEBroker()
    queue = broker.subscribe(user_id=1)
    broker.unsubscribe(user_id=1, queue=queue)
    await broker.publish_to([1], "x", {})
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.2)


@pytest.mark.asyncio
async def test_online_users_returns_user_ids_with_subscribers():
    broker = SSEBroker()
    broker.subscribe(user_id=1)
    broker.subscribe(user_id=2)
    broker.subscribe(user_id=2)  # second tab
    assert broker.online_user_ids() == {1, 2}


@pytest.mark.asyncio
async def test_unsubscribe_last_queue_removes_user_from_online():
    broker = SSEBroker()
    queue = broker.subscribe(user_id=1)
    assert 1 in broker.online_user_ids()
    broker.unsubscribe(1, queue)
    assert 1 not in broker.online_user_ids()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_sse.py -v
```

- [ ] **Step 3: Write `backend/shared/sse.py`**

```python
"""In-memory SSE pub/sub broker.

A user can have multiple subscriber queues (multiple browser tabs).
Single-process design — fine for Package 1 scale (2-30 users).

Three publish modes:
- publish_to(user_ids, ...): personal events to specific users
- publish_broadcast(...): all online users
- publish_to_others(except_user, ...): everyone except one user (for own actions)
"""
import asyncio
from dataclasses import dataclass
from typing import Iterable


@dataclass
class SSEEvent:
    event_type: str
    data: dict


class SSEBroker:
    def __init__(self) -> None:
        self._subscribers: dict[int, list[asyncio.Queue]] = {}

    def subscribe(self, user_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(user_id, []).append(queue)
        return queue

    def unsubscribe(self, user_id: int, queue: asyncio.Queue) -> None:
        queues = self._subscribers.get(user_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues and user_id in self._subscribers:
            del self._subscribers[user_id]

    def online_user_ids(self) -> set[int]:
        return set(self._subscribers.keys())

    async def publish_to(
        self, user_ids: Iterable[int], event_type: str, data: dict
    ) -> None:
        event = SSEEvent(event_type=event_type, data=data)
        for uid in user_ids:
            for q in list(self._subscribers.get(uid, [])):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Slow consumer — drop
                    pass

    async def publish_broadcast(self, event_type: str, data: dict) -> None:
        await self.publish_to(self._subscribers.keys(), event_type, data)

    async def publish_to_others(
        self, except_user_id: int, event_type: str, data: dict
    ) -> None:
        targets = [uid for uid in self._subscribers if uid != except_user_id]
        await self.publish_to(targets, event_type, data)


# Module-level singleton (FastAPI app uses this)
broker = SSEBroker()
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_sse.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/shared/sse.py tests/test_sse.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(shared): add in-memory SSE pub/sub broker"
```

---

## Task 10: main.py — FastAPI App + Health Endpoint (TDD)

**Files:**
- Create: `backend/main.py`, `tests/test_health.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Modify `tests/conftest.py` — add client fixture**

```python
from pathlib import Path
import pytest


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """FastAPI TestClient with isolated DATA_DIR / DB."""
    from fastapi.testclient import TestClient
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("backend.config.DB_DIR", tmp_path / "db")
    monkeypatch.setattr("backend.config.DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr("backend.config.DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr("backend.config.BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr("backend.config.EXPORTS_DIR", tmp_path / "exports")
    from backend.main import app
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 2: Write `tests/test_health.py`**

```python
def test_health_returns_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_app_runs_migrations_on_startup(client):
    # If migrations didn't run, the schema_migrations table won't exist.
    r = client.get("/api/health/db")
    assert r.status_code == 200
    body = r.json()
    assert body["migrations_applied"] >= 1
    assert body["table_count"] >= 19  # 19 + schema_migrations
```

- [ ] **Step 3: Run — expect FAIL**

```bash
pytest tests/test_health.py -v
```

- [ ] **Step 4: Write `backend/main.py`**

```python
"""FastAPI application entry point.

On startup:
  1. Ensure data directories exist
  2. Apply pending migrations
  3. Log startup system event

Domain routers (users, documents, ...) are mounted in their respective packages.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI

from backend import config
from backend.shared.db import connect
from backend.shared import audit
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations

VERSION = "0.1.0"


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
    finally:
        conn.close()
    yield
    # Shutdown — log clean exit
    conn = connect(config.DB_PATH)
    try:
        audit.log_system_event(conn, "shutdown", "info", message=f"app v{VERSION} shutting down")
    finally:
        conn.close()


app = FastAPI(title="Anotasyon Platform", version=VERSION, lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": VERSION}


@app.get("/api/health/db")
def health_db():
    conn = connect(config.DB_PATH)
    try:
        migrations_count = conn.execute("SELECT COUNT(*) AS c FROM schema_migrations").fetchone()["c"]
        tables_count = conn.execute(
            "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()["c"]
    finally:
        conn.close()
    return {
        "status": "ok",
        "migrations_applied": migrations_count,
        "table_count": tables_count,
    }
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/test_health.py -v
```

- [ ] **Step 6: Manual smoke test**

```bash
. .venv/bin/activate
uvicorn backend.main:app --port 8765 &
sleep 2
curl -s http://localhost:8765/api/health
echo
curl -s http://localhost:8765/api/health/db
echo
kill %1
```

Expected:
```
{"status":"ok","version":"0.1.0"}
{"status":"ok","migrations_applied":1,"table_count":20}
```

- [ ] **Step 7: Commit**

```bash
git add backend/main.py tests/conftest.py tests/test_health.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(main): add FastAPI app with lifespan migrations and health endpoints"
```

---

## Task 11: CLI — `python -m backend.cli migrate` (TDD)

**Files:**
- Create: `backend/cli.py`, `backend/__main__.py`, `tests/test_cli.py`

- [ ] **Step 1: Write `tests/test_cli.py`**

```python
import subprocess
import sys
from pathlib import Path


def test_cli_migrate_runs_on_empty_dir(tmp_path: Path):
    env = {
        "DATA_DIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
    }
    result = subprocess.run(
        [sys.executable, "-m", "backend.cli", "migrate"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "v0001" in result.stdout
    assert (tmp_path / "db" / "annotations.db").exists()


def test_cli_migrate_idempotent(tmp_path: Path):
    env = {
        "DATA_DIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
    }
    # First run
    subprocess.run(
        [sys.executable, "-m", "backend.cli", "migrate"],
        capture_output=True, text=True, env=env, check=True,
    )
    # Second run: no migrations to apply
    result = subprocess.run(
        [sys.executable, "-m", "backend.cli", "migrate"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0
    assert "no pending" in result.stdout.lower() or "0 applied" in result.stdout.lower()


def test_cli_unknown_command_returns_nonzero(tmp_path: Path):
    env = {
        "DATA_DIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
    }
    result = subprocess.run(
        [sys.executable, "-m", "backend.cli", "bogus-command"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_cli.py -v
```

- [ ] **Step 3: Write `backend/cli.py`**

```python
"""Command-line interface.

Usage:
  python -m backend.cli migrate
"""
import argparse
import sys

from backend import config
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


def cmd_migrate(_args) -> int:
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        applied = apply_migrations(conn, discover_migrations())
    finally:
        conn.close()
    if applied:
        print(f"Applied {len(applied)} migrations: {', '.join(applied)}")
    else:
        print("No pending migrations.")
    return 0


COMMANDS = {
    "migrate": cmd_migrate,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backend.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply pending DB migrations")

    args = parser.parse_args(argv)
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.error(f"unknown command: {args.command}")
        return 2
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Write `backend/__main__.py`**

```python
"""Allow `python -m backend.cli ...` invocation.

This file is intentionally minimal — see backend/cli.py for the actual logic.
"""
from backend.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/test_cli.py -v
```

- [ ] **Step 6: Manual smoke test**

```bash
rm -rf /tmp/cli-test
mkdir -p /tmp/cli-test
DATA_DIR=/tmp/cli-test python -m backend.cli migrate
DATA_DIR=/tmp/cli-test python -m backend.cli migrate  # second time — no-op
```

Expected:
```
Applied 1 migrations: v0001
No pending migrations.
```

- [ ] **Step 7: Commit**

```bash
git add backend/cli.py backend/__main__.py tests/test_cli.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(cli): add migrate subcommand"
```

---

## Task 12: Docker Setup

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps for bcrypt (uses libffi)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python deps first for layer caching
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Application
COPY backend/ ./backend/

# Editable install so `python -m backend.cli` works
RUN pip install --no-cache-dir -e .

# Data volume mount point
VOLUME ["/data"]
ENV DATA_DIR=/data

EXPOSE 8000

# Apply migrations then start uvicorn
CMD ["sh", "-c", "python -m backend.cli migrate && uvicorn backend.main:app --host 0.0.0.0 --port 8000"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" || exit 1
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - anotasyon_data:/data
    environment:
      - DATA_DIR=/data
      - SESSION_SECRET=${SESSION_SECRET:-dev-secret-change-me}
      - SESSION_COOKIE_NAME=anotasyon_session
      - BACKUP_REPO_URL=${BACKUP_REPO_URL:-}
      - GITHUB_PAT=${GITHUB_PAT:-}
      - BOOTSTRAP_ADMIN_USERNAME=${BOOTSTRAP_ADMIN_USERNAME:-}
    restart: unless-stopped

volumes:
  anotasyon_data:
```

- [ ] **Step 3: Build the image**

```bash
docker build -t anotasyon:dev .
```

Expected: build succeeds, ~200MB image.

- [ ] **Step 4: Run a smoke test**

```bash
docker run --rm -d -p 8765:8000 --name anotasyon-smoke anotasyon:dev
sleep 5
curl -s http://localhost:8765/api/health
echo
curl -s http://localhost:8765/api/health/db
echo
docker stop anotasyon-smoke
```

Expected:
```
{"status":"ok","version":"0.1.0"}
{"status":"ok","migrations_applied":1,"table_count":20}
```

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(docker): add Dockerfile and docker-compose for deployment"
```

---

## Task 13: End-to-End Verification

**Files:**
- None (manual verification)

- [ ] **Step 1: Full test suite**

```bash
. .venv/bin/activate
pytest tests/ -v
```

Expected: All tests pass. Approximate count: 50+ tests across 8 test files.

- [ ] **Step 2: Cold-start integration check**

```bash
rm -rf /tmp/cold-start
mkdir -p /tmp/cold-start
DATA_DIR=/tmp/cold-start python -m backend.cli migrate
ls /tmp/cold-start/db/
DATA_DIR=/tmp/cold-start uvicorn backend.main:app --port 8765 &
sleep 2
curl -s http://localhost:8765/api/health/db
kill %1
```

Expected:
- `annotations.db` created
- `migrations_applied: 1`
- `table_count: 20` (19 schema + `schema_migrations`)

- [ ] **Step 3: Verify settings seeded**

```bash
DATA_DIR=/tmp/cold-start python -c "
from backend.shared.db import connect
from backend.config import DB_PATH
from backend.shared import settings as S
conn = connect(DB_PATH)
print('Default settings:')
for k, v in sorted(S.get_all(conn).items()):
    print(f'  {k} = {v}')
conn.close()
"
```

Expected: 20 default settings printed (speed_warning.*, char_limit.*, lock.*, backup.*, training.*, gamification.*).

- [ ] **Step 4: Audit log spot check**

```bash
DATA_DIR=/tmp/cold-start python -c "
from backend.shared.db import connect
from backend.config import DB_PATH
conn = connect(DB_PATH)
rows = conn.execute('SELECT * FROM system_events ORDER BY id').fetchall()
for r in rows:
    print(r['event_type'], r['severity'], r['message'])
conn.close()
"
```

Expected: At least 1 `startup` event from the lifespan call.

- [ ] **Step 5: Final review checklist**

Verify:
- [ ] All 19 spec tables present (Q5 hybrid table included)
- [ ] All 20 default site_settings seeded
- [ ] `shared/db.py`, `shared/settings.py`, `shared/audit.py`, `shared/auth.py`, `shared/sse.py` complete
- [ ] Migration system idempotent
- [ ] Health endpoint reports correct migration + table counts
- [ ] CLI works (`python -m backend.cli migrate`)
- [ ] Docker image builds and runs
- [ ] Test count: 50+ tests, all passing

If any item fails, create a follow-up task with the specific failure.

- [ ] **Step 6: Tag the milestone**

```bash
git tag -a paket-1-foundation -m "Paket 1 — Foundation Refactor complete"
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Implementing task |
|---|---|
| Modüler folder yapısı | Task 1, 2 (skeleton) — domain folders deferred to their packages |
| Migration sistemi v0→v1 | Task 4, 5 |
| 19 tablonun DDL'i | Task 5 |
| `shared/db.py` | Task 3 |
| `shared/settings.py` | Task 6 |
| `shared/audit.py` | Task 7 |
| `shared/auth.py` (helpers only) | Task 8 |
| `shared/sse.py` | Task 9 |
| Default site_settings seed | Task 5 (bundled in v0001) |
| Health endpoint | Task 10 |
| CLI migrate | Task 11 |
| Docker | Task 12 |
| Test infrastructure (conftest, fixtures) | Task 3, 10 |
| Q5 hybrid table | Task 5 (`training_gold_doc_overrides`) |

**2. Placeholder scan:** None. Every step has concrete code or commands.

**3. Type/method consistency:**
- `connect(db_path: Path) → sqlite3.Connection` — used in tasks 3, 4, 5, 6, 7, 10, 11
- `Migration(version, name, up)` — defined in 4, used in 4, 5
- `apply_migrations(conn, migrations) → list[str]` — defined in 4, used in 4, 5, 6, 7, 10, 11
- `discover_migrations() → list[Migration]` — defined in 4, used in 5, 6, 7, 10, 11
- Settings getters: `get_int`, `get_str`, `get_float`, `get_dict`, `get_all`, `set_value` — all consistent
- Audit functions: keyword-only after positional required — consistent
- `SSEBroker.subscribe / unsubscribe / publish_to / publish_broadcast / publish_to_others` — consistent

**Known compromise — Pyright IDE warnings:** The previous session encountered persistent Pyright "Import could not be resolved" warnings even with editable install. The `pyproject.toml` config mitigates most cases via `extraPaths` + `executionEnvironments`. If warnings persist in this session, they are cosmetic only — runtime and tests pass.
