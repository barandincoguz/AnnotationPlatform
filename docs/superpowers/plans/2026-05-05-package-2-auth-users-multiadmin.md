# Paket 2 — Auth + Users + Multi-Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Davet kodu ile kayıt + login/logout + session yönetimi + user CRUD + multi-admin (manuel bootstrap, promote/demote, son-admin guardrail) + admin audit log + has_seen_manual ve has_passed_training gating endpoint'leri. Routes tarafından kullanılan auth middleware. Sonraki tüm paketler bu auth katmanına yaslanacak.

**Architecture:** Session cookie-based auth (HttpOnly + SameSite=Lax + Secure flag prod'da). Session token'lar DB'de `user_sessions` tablosunda saklanır (ekstra revoke yetkisi için), browser cookie sadece opaque token taşır. Bcrypt parola hash. Davet kodu paylaşılır birden fazla bursiyer aynı kodla register olabilir; admin rotate eder. Multi-admin: ilk admin manuel CLI ile DB'ye eklenir; mevcut admin'ler başkasını promote/demote eder; son aktif admin demote edilemez. Tüm sensitive admin action'ları `admin_audit_log`'a yazılır.

**Tech Stack:** FastAPI dependencies (Depends), `Cookie` parametresi, `Response.set_cookie`, bcrypt (Paket 1'deki shared/auth.py), pytest + httpx TestClient, monkeypatch fixture'lar.

---

## Mimari Kararlar (Implementation-Critical)

- **Session cookie:** Adı `anotasyon_session` (config), HttpOnly, SameSite=Lax, Path=/, Max-Age=30 gün, Secure flag environment'tan (`SESSION_COOKIE_SECURE=1` prod'da)
- **Token'lar:** `secrets.token_urlsafe(32)` — 43 karakter URL-safe random; ham token cookie'de, hash değil (DB'de aynısı saklanır, lookup için)
- **Session expiry:** Sliding window — her HTTP request'te `last_activity_at` güncellenir; `last_activity_at` 30 günden eskiyse expired sayılır ve auto-logout
- **IP hashing:** `shared.auth.hash_ip()` ile session log'a kaydedilir, ham IP saklanmaz
- **Davet kodu:** Tek aktif satır olur (`UNIQUE INDEX ... WHERE is_active=1`); rotate işlemi eski satırı `is_active=0` yapıp yeni satır insert eder
- **Bootstrap CLI:** `python -m backend.cli promote-admin <username>` — sadece kullanıcı kaydı varsa çalışır; ilk admin'i sistem admin'i bu komut ile manuel atar
- **Last-admin guardrail:** Demote/disable işlemi öncesinde aktif admin sayısı sayılır; son admin'se 400 döner
- **Soft delete:** User `is_active=0` olur, kayıtları korunur; login'de `is_active=0` ise 401
- **Audit:** Her admin action `shared/audit.log_admin_action` çağrısı ile loglanır
- **Auth middleware:** `Depends(get_current_user)` ve `Depends(require_admin)` reusable dependency'ler — sonraki paketler import eder
- **`/api/me/seen-manual`:** Bursiyerin "Anladım" dediğini işler — has_seen_manual=True

## Dosya Yapısı

```
backend/users/
├── __init__.py
├── models.py            # Pydantic request/response modelleri
├── service.py           # iş mantığı (register, login, logout, promote, demote, ...)
├── routes.py            # /api/auth/*, /api/users/*, /api/me/*
└── deps.py              # FastAPI dependencies: get_current_user, require_admin

backend/cli.py           # MODIFIED: promote-admin, demote-admin, rotate-invite, create-invite komutları eklenir

backend/main.py          # MODIFIED: users router mount edilir

tests/
├── test_users_service.py
├── test_auth_routes.py
├── test_admin_routes.py
└── test_cli_admin.py
```

---

## Task 1: Pydantic Models + Routes Skeleton (TDD)

**Files:**
- Create: `backend/users/__init__.py`, `backend/users/models.py`, `backend/users/routes.py`, `tests/test_auth_routes.py`
- Modify: `backend/main.py` (router mount)

- [ ] **Step 1: Create users package**

```bash
mkdir -p backend/users
touch backend/users/__init__.py
```

- [ ] **Step 2: Write `backend/users/models.py`**

```python
"""Pydantic request/response models for auth + users."""
from typing import Optional, Literal
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    invite_code: str
    email: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: Optional[str]
    role: Literal["user", "admin"]
    is_active: bool
    has_passed_training: bool
    has_seen_manual: bool
    avatar_color: Optional[str]
    created_at: str


class UsersListResponse(BaseModel):
    users: list[UserOut]
    total: int


class OkResponse(BaseModel):
    ok: bool = True
```

- [ ] **Step 3: Write skeletal `backend/users/routes.py`**

```python
"""Auth + user routes. Implementations come in subsequent tasks."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["users"])

# Endpoints implemented in tasks 2-7
```

- [ ] **Step 4: Modify `backend/main.py` to mount router**

Show full updated file (additions only — keep all existing code; add the import + include_router below):

```python
"""FastAPI application entry point.
... (unchanged docstring) ..."""
from contextlib import asynccontextmanager
from fastapi import FastAPI

from backend import config
from backend.shared.db import connect
from backend.shared import audit
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.users.routes import router as users_router

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
    conn = connect(config.DB_PATH)
    try:
        audit.log_system_event(conn, "shutdown", "info", message=f"app v{VERSION} shutting down")
    finally:
        conn.close()


app = FastAPI(title="Anotasyon Platform", version=VERSION, lifespan=lifespan)
app.include_router(users_router)


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

- [ ] **Step 5: Write `tests/test_auth_routes.py` (sanity test)**

```python
def test_app_imports_users_router(client):
    """Smoke: app boots after mounting users router."""
    r = client.get("/api/health")
    assert r.status_code == 200
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
. .venv/bin/activate && pytest tests/test_auth_routes.py -v
pytest tests/ -q
```

Expected: 51 tests pass (50 + 1 new).

- [ ] **Step 7: Commit**

```bash
git add backend/users/ backend/main.py tests/test_auth_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(users): scaffold users package with router skeleton and pydantic models"
```

---

## Task 2: User Service — Register (TDD)

**Files:**
- Create: `backend/users/service.py`, `tests/test_users_service.py`

- [ ] **Step 1: Write `tests/test_users_service.py` — register tests**

```python
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.users import service


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    # Seed an active invite code
    conn.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
        ("BURSIYER-2026",),
    )
    yield conn
    conn.close()


def test_register_creates_user_and_gamification_state(db):
    user_id = service.register(
        db, username="alice", password="password123",
        invite_code="BURSIYER-2026", email="alice@example.com",
    )
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    assert user["username"] == "alice"
    assert user["email"] == "alice@example.com"
    assert user["role"] == "user"
    assert user["is_active"] == 1
    assert user["has_seen_manual"] == 0
    assert user["has_passed_training"] == 0
    assert user["avatar_color"] is not None  # auto-assigned
    assert user["password_hash"].startswith("$2b$")

    state = db.execute(
        "SELECT * FROM gamification_state WHERE user_id=?", (user_id,)
    ).fetchone()
    assert state is not None
    assert state["total_xp"] == 0


def test_register_invalid_invite_code_raises(db):
    with pytest.raises(service.InvalidInviteCode):
        service.register(db, username="alice", password="password123",
                         invite_code="WRONG-CODE", email=None)


def test_register_inactive_invite_code_raises(db):
    db.execute("UPDATE invite_codes SET is_active=0 WHERE code=?", ("BURSIYER-2026",))
    with pytest.raises(service.InvalidInviteCode):
        service.register(db, username="alice", password="password123",
                         invite_code="BURSIYER-2026", email=None)


def test_register_duplicate_username_raises(db):
    service.register(db, username="alice", password="pw_alice99",
                     invite_code="BURSIYER-2026", email=None)
    with pytest.raises(service.UsernameTaken):
        service.register(db, username="alice", password="pw_alice22",
                         invite_code="BURSIYER-2026", email=None)


def test_register_duplicate_email_raises(db):
    service.register(db, username="alice", password="pw_alice99",
                     invite_code="BURSIYER-2026", email="shared@x.com")
    with pytest.raises(service.EmailTaken):
        service.register(db, username="bob", password="pw_bob123",
                         invite_code="BURSIYER-2026", email="shared@x.com")


def test_register_avatar_color_deterministic_from_username(db):
    """Same username → same color across calls."""
    color1 = service._avatar_color_for("alice")
    color2 = service._avatar_color_for("alice")
    assert color1 == color2
    color3 = service._avatar_color_for("bob")
    assert color3 != color1  # different username, likely different color


def test_register_password_too_short_raises(db):
    """Service accepts validated input — Pydantic enforces length, but service should also gate."""
    with pytest.raises(service.InvalidPassword):
        service.register(db, username="alice", password="short",
                         invite_code="BURSIYER-2026", email=None)
```

- [ ] **Step 2: Run — expect FAIL (no service module)**

```bash
pytest tests/test_users_service.py -v
```

- [ ] **Step 3: Write `backend/users/service.py`**

```python
"""User service: register, login, logout, admin operations.

Custom exceptions are caught by route handlers and mapped to HTTP errors.
"""
import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.shared import auth, audit


# === Exception types ===
class UsersServiceError(Exception):
    """Base class for user-related errors."""


class InvalidInviteCode(UsersServiceError):
    pass


class UsernameTaken(UsersServiceError):
    pass


class EmailTaken(UsersServiceError):
    pass


class InvalidPassword(UsersServiceError):
    pass


class UserNotFound(UsersServiceError):
    pass


class InvalidCredentials(UsersServiceError):
    pass


class UserDisabled(UsersServiceError):
    pass


class NotAdmin(UsersServiceError):
    pass


class LastAdminCannotBeRemoved(UsersServiceError):
    pass


# === Constants ===
AVATAR_PALETTE = [
    "#ef4444", "#f97316", "#eab308", "#22c55e",
    "#10b981", "#06b6d4", "#3b82f6", "#6366f1",
    "#a855f7", "#ec4899", "#f43f5e", "#84cc16",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _avatar_color_for(username: str) -> str:
    """Deterministic color from username (SHA-256 hash → palette index)."""
    h = hashlib.sha256(username.lower().encode("utf-8")).hexdigest()
    idx = int(h, 16) % len(AVATAR_PALETTE)
    return AVATAR_PALETTE[idx]


def _check_active_invite(db: sqlite3.Connection, code: str) -> None:
    row = db.execute(
        "SELECT id FROM invite_codes WHERE code=? AND is_active=1", (code,)
    ).fetchone()
    if row is None:
        raise InvalidInviteCode("invite code not recognized or inactive")


def register(
    db: sqlite3.Connection,
    *,
    username: str,
    password: str,
    invite_code: str,
    email: Optional[str],
) -> int:
    """Register a new bursiyer. Returns new user_id."""
    if len(password) < 8:
        raise InvalidPassword("password must be at least 8 characters")

    _check_active_invite(db, invite_code)

    # Username uniqueness
    if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        raise UsernameTaken(f"username '{username}' already exists")

    if email and db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise EmailTaken(f"email '{email}' already registered")

    now = _now()
    cur = db.execute(
        """
        INSERT INTO users(username, email, password_hash, role, is_active,
                          avatar_color, created_at, updated_at)
        VALUES (?, ?, ?, 'user', 1, ?, ?, ?)
        """,
        (
            username, email,
            auth.hash_password(password),
            _avatar_color_for(username),
            now, now,
        ),
    )
    user_id = cur.lastrowid
    assert user_id is not None  # AUTOINCREMENT

    # Initialize gamification state
    db.execute(
        """
        INSERT INTO gamification_state(user_id, updated_at)
        VALUES (?, ?)
        """,
        (user_id, now),
    )

    return user_id
```

- [ ] **Step 4: Run — expect ALL PASS**

```bash
pytest tests/test_users_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/users/service.py tests/test_users_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(users): register service with invite code validation and avatar color"
```

---

## Task 3: User Service — Login + Sessions (TDD)

**Files:**
- Modify: `backend/users/service.py`, `tests/test_users_service.py`

- [ ] **Step 1: Add login tests to `tests/test_users_service.py`**

```python
def test_login_correct_credentials_creates_session(db):
    uid = service.register(db, username="alice", password="password123",
                            invite_code="BURSIYER-2026", email=None)
    token = service.login(db, username="alice", password="password123",
                           ip="1.2.3.4", user_agent="curl/8.0")
    assert isinstance(token, str)
    assert len(token) >= 32

    sess = db.execute("SELECT * FROM user_sessions WHERE session_token=?", (token,)).fetchone()
    assert sess["user_id"] == uid
    assert sess["ended_at"] is None
    assert sess["ip_hash"] is not None
    assert sess["user_agent"] == "curl/8.0"


def test_login_wrong_password_raises(db):
    service.register(db, username="alice", password="password123",
                      invite_code="BURSIYER-2026", email=None)
    with pytest.raises(service.InvalidCredentials):
        service.login(db, username="alice", password="WRONG", ip="1.2.3.4")


def test_login_unknown_user_raises(db):
    with pytest.raises(service.InvalidCredentials):
        service.login(db, username="ghost", password="anything", ip="1.2.3.4")


def test_login_disabled_user_raises(db):
    uid = service.register(db, username="alice", password="password123",
                            invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET is_active=0 WHERE id=?", (uid,))
    with pytest.raises(service.UserDisabled):
        service.login(db, username="alice", password="password123", ip="1.2.3.4")


def test_logout_ends_session(db):
    service.register(db, username="alice", password="password123",
                      invite_code="BURSIYER-2026", email=None)
    token = service.login(db, username="alice", password="password123", ip="1.2.3.4")
    service.logout(db, session_token=token)
    sess = db.execute("SELECT ended_at FROM user_sessions WHERE session_token=?", (token,)).fetchone()
    assert sess["ended_at"] is not None


def test_get_user_by_session_returns_user(db):
    uid = service.register(db, username="alice", password="password123",
                            invite_code="BURSIYER-2026", email=None)
    token = service.login(db, username="alice", password="password123", ip="1.2.3.4")
    user = service.get_user_by_session(db, session_token=token)
    assert user is not None
    assert user["id"] == uid
    assert user["username"] == "alice"


def test_get_user_by_session_unknown_token_returns_none(db):
    assert service.get_user_by_session(db, session_token="bogus") is None


def test_get_user_by_session_after_logout_returns_none(db):
    service.register(db, username="alice", password="password123",
                      invite_code="BURSIYER-2026", email=None)
    token = service.login(db, username="alice", password="password123", ip="1.2.3.4")
    service.logout(db, session_token=token)
    assert service.get_user_by_session(db, session_token=token) is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_users_service.py -v
```

- [ ] **Step 3: Add to `backend/users/service.py`**

```python
def login(
    db: sqlite3.Connection,
    *,
    username: str,
    password: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """Verify credentials and create a session. Returns session token."""
    user = db.execute(
        "SELECT * FROM users WHERE username=?", (username,)
    ).fetchone()
    if user is None:
        raise InvalidCredentials("invalid username or password")
    if not auth.verify_password(password, user["password_hash"]):
        raise InvalidCredentials("invalid username or password")
    if user["is_active"] != 1:
        raise UserDisabled("user account is disabled")

    token = auth.generate_session_token()
    now = _now()
    db.execute(
        """
        INSERT INTO user_sessions(
            user_id, session_token, ip_hash, user_agent,
            started_at, last_activity_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user["id"], token,
            auth.hash_ip(ip) if ip else None,
            user_agent,
            now, now,
        ),
    )
    return token


def logout(db: sqlite3.Connection, *, session_token: str) -> None:
    db.execute(
        "UPDATE user_sessions SET ended_at=? WHERE session_token=? AND ended_at IS NULL",
        (_now(), session_token),
    )


def get_user_by_session(
    db: sqlite3.Connection, *, session_token: str
) -> Optional[sqlite3.Row]:
    """Return user row if session is active, else None.

    Also updates last_activity_at as side effect (sliding window).
    """
    row = db.execute(
        """
        SELECT u.*, s.id AS session_id
        FROM user_sessions s JOIN users u ON s.user_id = u.id
        WHERE s.session_token = ?
          AND s.ended_at IS NULL
          AND u.is_active = 1
        """,
        (session_token,),
    ).fetchone()
    if row is None:
        return None
    db.execute(
        "UPDATE user_sessions SET last_activity_at=? WHERE id=?",
        (_now(), row["session_id"]),
    )
    return row
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_users_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/users/service.py tests/test_users_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(users): add login/logout with session tokens and IP hashing"
```

---

## Task 4: FastAPI Dependencies (`get_current_user`, `require_admin`) (TDD)

**Files:**
- Create: `backend/users/deps.py`

- [ ] **Step 1: Write `backend/users/deps.py`**

```python
"""FastAPI dependencies for auth and authorization.

Used by every route in subsequent packages:
  @router.get("/api/feed", dependencies=[Depends(require_seen_manual)])
  def feed(user: dict = Depends(get_current_user)): ...
"""
import sqlite3
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status

from backend import config
from backend.shared.db import connect
from backend.users import service


def get_db() -> sqlite3.Connection:
    """Yield-based DB connection — called per-request."""
    conn = connect(config.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(
    db: sqlite3.Connection = Depends(get_db),
    session_token: Optional[str] = Cookie(None, alias=config.SESSION_COOKIE_NAME),
) -> sqlite3.Row:
    """Resolve current user from session cookie. 401 if not authenticated."""
    if not session_token:
        raise HTTPException(status_code=401, detail="not authenticated")
    user = service.get_user_by_session(db, session_token=session_token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    return user


def get_current_user_optional(
    db: sqlite3.Connection = Depends(get_db),
    session_token: Optional[str] = Cookie(None, alias=config.SESSION_COOKIE_NAME),
) -> Optional[sqlite3.Row]:
    """Like get_current_user but returns None instead of 401."""
    if not session_token:
        return None
    return service.get_user_by_session(db, session_token=session_token)


def require_admin(user: sqlite3.Row = Depends(get_current_user)) -> sqlite3.Row:
    """403 if not admin. Use as additional dependency on admin routes."""
    if user["role"] != "admin":
        raise HTTPException(status_code=404, detail="not found")  # hide existence per spec
    return user


def require_seen_manual(user: sqlite3.Row = Depends(get_current_user)) -> sqlite3.Row:
    """409 if user hasn't seen the help manual yet (frontend redirects to /help)."""
    if user["has_seen_manual"] != 1:
        raise HTTPException(
            status_code=409,
            detail={"error": "manual_not_seen", "message": "user must view /help first"},
        )
    return user


def require_passed_training(user: sqlite3.Row = Depends(require_seen_manual)) -> sqlite3.Row:
    """409 if user hasn't passed the training gate."""
    if user["has_passed_training"] != 1:
        raise HTTPException(
            status_code=409,
            detail={"error": "training_not_passed", "message": "user must complete training"},
        )
    return user


def get_request_ip(request: Request) -> Optional[str]:
    """Extract client IP from request, honoring X-Forwarded-For if behind proxy."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None
```

- [ ] **Step 2: Smoke import**

```bash
. .venv/bin/activate && python -c "from backend.users.deps import get_current_user, require_admin; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/users/deps.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(users): add reusable auth/role dependencies for FastAPI routes"
```

---

## Task 5: Auth Routes — register, login, logout, /me (TDD)

**Files:**
- Modify: `backend/users/routes.py`, `tests/test_auth_routes.py`

- [ ] **Step 1: Add auth route tests to `tests/test_auth_routes.py`**

Replace the smoke test with a full set:

```python
import pytest


@pytest.fixture
def seeded_client(client):
    """Client with one active invite code seeded."""
    # Seed via test client by making a direct DB call through monkeypatched config
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("BURSIYER-2026",),
        )
    finally:
        conn.close()
    return client


def test_register_creates_user(seeded_client):
    r = seeded_client.post("/api/auth/register", json={
        "username": "alice",
        "password": "password123",
        "invite_code": "BURSIYER-2026",
        "email": "alice@example.com",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["username"] == "alice"
    assert body["role"] == "user"


def test_register_invalid_invite_code_returns_403(seeded_client):
    r = seeded_client.post("/api/auth/register", json={
        "username": "alice",
        "password": "password123",
        "invite_code": "WRONG",
    })
    assert r.status_code == 403


def test_register_short_password_returns_422(seeded_client):
    r = seeded_client.post("/api/auth/register", json={
        "username": "alice",
        "password": "short",
        "invite_code": "BURSIYER-2026",
    })
    assert r.status_code == 422  # Pydantic validation


def test_register_duplicate_username_returns_409(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    r = seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "different123",
        "invite_code": "BURSIYER-2026",
    })
    assert r.status_code == 409


def test_login_sets_session_cookie(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    r = seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })
    assert r.status_code == 200
    assert "anotasyon_session" in r.cookies


def test_login_wrong_password_returns_401(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    r = seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "WRONG",
    })
    assert r.status_code == 401


def test_me_returns_current_user(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })
    r = seeded_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_me_unauthenticated_returns_401(seeded_client):
    r = seeded_client.get("/api/auth/me")
    assert r.status_code == 401


def test_logout_clears_session(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })
    r = seeded_client.post("/api/auth/logout")
    assert r.status_code == 200
    # Session should now be invalid
    r2 = seeded_client.get("/api/auth/me")
    assert r2.status_code == 401
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_auth_routes.py -v
```

- [ ] **Step 3: Update `backend/users/routes.py`**

```python
"""Auth + user routes."""
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from backend import config
from backend.users import service
from backend.users.deps import (
    get_db, get_current_user, get_request_ip, require_admin
)
from backend.users.models import (
    RegisterRequest, LoginRequest, UserOut, UsersListResponse, OkResponse,
)

router = APIRouter(prefix="/api", tags=["users"])


def _user_to_out(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "has_passed_training": bool(row["has_passed_training"]),
        "has_seen_manual": bool(row["has_seen_manual"]),
        "avatar_color": row["avatar_color"],
        "created_at": row["created_at"],
    }


@router.post("/auth/register", response_model=UserOut, status_code=201)
def register(
    payload: RegisterRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    try:
        user_id = service.register(
            db,
            username=payload.username,
            password=payload.password,
            invite_code=payload.invite_code,
            email=payload.email,
        )
    except service.InvalidInviteCode as e:
        raise HTTPException(status_code=403, detail=str(e))
    except service.UsernameTaken as e:
        raise HTTPException(status_code=409, detail=str(e))
    except service.EmailTaken as e:
        raise HTTPException(status_code=409, detail=str(e))
    except service.InvalidPassword as e:
        raise HTTPException(status_code=422, detail=str(e))

    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _user_to_out(user)


@router.post("/auth/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: sqlite3.Connection = Depends(get_db),
):
    try:
        token = service.login(
            db,
            username=payload.username,
            password=payload.password,
            ip=get_request_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except service.InvalidCredentials as e:
        raise HTTPException(status_code=401, detail=str(e))
    except service.UserDisabled as e:
        raise HTTPException(status_code=401, detail=str(e))

    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 60 * 60,  # 30 days
        secure=False,  # set true behind HTTPS in prod via env
        path="/",
    )
    return {"ok": True}


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: sqlite3.Connection = Depends(get_db),
):
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if token:
        service.logout(db, session_token=token)
    response.delete_cookie(config.SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me", response_model=UserOut)
def me(user: sqlite3.Row = Depends(get_current_user)):
    return _user_to_out(user)
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_auth_routes.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/users/routes.py tests/test_auth_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(users): add register/login/logout/me HTTP routes with session cookie"
```

---

## Task 6: Manual Gating + Training Status Endpoints (TDD)

**Files:**
- Modify: `backend/users/routes.py`, `tests/test_auth_routes.py`

- [ ] **Step 1: Add gating tests**

```python
def test_seen_manual_endpoint_sets_flag(seeded_client):
    seeded_client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    seeded_client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })
    r = seeded_client.post("/api/me/seen-manual")
    assert r.status_code == 200

    me = seeded_client.get("/api/auth/me").json()
    assert me["has_seen_manual"] is True


def test_seen_manual_unauthenticated_returns_401(seeded_client):
    r = seeded_client.post("/api/me/seen-manual")
    assert r.status_code == 401
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_auth_routes.py -v
```

- [ ] **Step 3: Add to `backend/users/routes.py`**

```python
@router.post("/me/seen-manual", response_model=OkResponse)
def seen_manual(
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    db.execute(
        "UPDATE users SET has_seen_manual=1, updated_at=datetime('now') WHERE id=?",
        (user["id"],),
    )
    return {"ok": True}
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_auth_routes.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/users/routes.py tests/test_auth_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(users): add /api/me/seen-manual endpoint for first-time gating"
```

---

## Task 7: Admin Service — Promote, Demote, Disable, Enable, Rotate Invite (TDD)

**Files:**
- Modify: `backend/users/service.py`, `tests/test_users_service.py`

- [ ] **Step 1: Add admin service tests**

```python
def test_promote_user_to_admin_writes_audit(db):
    admin_uid = service.register(db, username="admin1", password="admin12345",
                                  invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin_uid,))
    target_uid = service.register(db, username="alice", password="password123",
                                   invite_code="BURSIYER-2026", email=None)

    service.promote_admin(db, admin_user_id=admin_uid, target_user_id=target_uid)

    user = db.execute("SELECT role FROM users WHERE id=?", (target_uid,)).fetchone()
    assert user["role"] == "admin"

    audit_row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='promote_admin'"
    ).fetchone()
    assert audit_row is not None
    assert audit_row["admin_user_id"] == admin_uid
    assert audit_row["target_id"] == str(target_uid)


def test_demote_admin_to_user(db):
    admin1 = service.register(db, username="admin1", password="adminpass1",
                               invite_code="BURSIYER-2026", email=None)
    admin2 = service.register(db, username="admin2", password="adminpass2",
                               invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id IN (?,?)", (admin1, admin2))

    service.demote_admin(db, admin_user_id=admin1, target_user_id=admin2)

    user = db.execute("SELECT role FROM users WHERE id=?", (admin2,)).fetchone()
    assert user["role"] == "user"


def test_demote_last_admin_raises(db):
    admin_uid = service.register(db, username="admin1", password="adminpass1",
                                  invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin_uid,))

    with pytest.raises(service.LastAdminCannotBeRemoved):
        service.demote_admin(db, admin_user_id=admin_uid, target_user_id=admin_uid)


def test_disable_user_sets_inactive(db):
    admin = service.register(db, username="admin1", password="adminpass1",
                              invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin,))
    target = service.register(db, username="alice", password="password123",
                               invite_code="BURSIYER-2026", email=None)

    service.disable_user(db, admin_user_id=admin, target_user_id=target)

    row = db.execute("SELECT is_active FROM users WHERE id=?", (target,)).fetchone()
    assert row["is_active"] == 0


def test_disable_last_admin_raises(db):
    admin = service.register(db, username="admin1", password="adminpass1",
                              invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin,))
    with pytest.raises(service.LastAdminCannotBeRemoved):
        service.disable_user(db, admin_user_id=admin, target_user_id=admin)


def test_enable_user_restores_active(db):
    admin = service.register(db, username="admin1", password="adminpass1",
                              invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin,))
    target = service.register(db, username="alice", password="password123",
                               invite_code="BURSIYER-2026", email=None)
    service.disable_user(db, admin_user_id=admin, target_user_id=target)
    service.enable_user(db, admin_user_id=admin, target_user_id=target)
    row = db.execute("SELECT is_active FROM users WHERE id=?", (target,)).fetchone()
    assert row["is_active"] == 1


def test_rotate_invite_code_deactivates_old_and_creates_new(db):
    admin = service.register(db, username="admin1", password="adminpass1",
                              invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin,))

    new_code = service.rotate_invite_code(db, admin_user_id=admin, new_code="NEW-2026")

    assert new_code == "NEW-2026"
    rows = db.execute(
        "SELECT code, is_active FROM invite_codes ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["code"] == "BURSIYER-2026"
    assert rows[0]["is_active"] == 0
    assert rows[1]["code"] == "NEW-2026"
    assert rows[1]["is_active"] == 1


def test_count_active_admins(db):
    a1 = service.register(db, username="admin1", password="adminpass1",
                          invite_code="BURSIYER-2026", email=None)
    a2 = service.register(db, username="admin2", password="adminpass2",
                          invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id IN (?,?)", (a1, a2))
    assert service.count_active_admins(db) == 2
    db.execute("UPDATE users SET is_active=0 WHERE id=?", (a1,))
    assert service.count_active_admins(db) == 1
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_users_service.py -v
```

- [ ] **Step 3: Add to `backend/users/service.py`**

```python
def count_active_admins(db: sqlite3.Connection) -> int:
    return db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE role='admin' AND is_active=1"
    ).fetchone()["c"]


def _ensure_admin(db: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if user is None or user["role"] != "admin" or user["is_active"] != 1:
        raise NotAdmin(f"user {user_id} is not an active admin")
    return user


def promote_admin(
    db: sqlite3.Connection, *, admin_user_id: int, target_user_id: int
) -> None:
    _ensure_admin(db, admin_user_id)
    target = db.execute(
        "SELECT * FROM users WHERE id=?", (target_user_id,)
    ).fetchone()
    if target is None:
        raise UserNotFound(f"user {target_user_id} not found")
    db.execute(
        "UPDATE users SET role='admin', updated_at=? WHERE id=?",
        (_now(), target_user_id),
    )
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="promote_admin",
        target_kind="user", target_id=str(target_user_id),
    )


def demote_admin(
    db: sqlite3.Connection, *, admin_user_id: int, target_user_id: int
) -> None:
    _ensure_admin(db, admin_user_id)
    target = db.execute(
        "SELECT * FROM users WHERE id=?", (target_user_id,)
    ).fetchone()
    if target is None or target["role"] != "admin":
        raise UserNotFound(f"user {target_user_id} is not an admin")
    # Last-admin guardrail
    if count_active_admins(db) <= 1:
        raise LastAdminCannotBeRemoved("cannot demote the last active admin")
    db.execute(
        "UPDATE users SET role='user', updated_at=? WHERE id=?",
        (_now(), target_user_id),
    )
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="demote_admin",
        target_kind="user", target_id=str(target_user_id),
    )


def disable_user(
    db: sqlite3.Connection, *, admin_user_id: int, target_user_id: int
) -> None:
    _ensure_admin(db, admin_user_id)
    target = db.execute(
        "SELECT * FROM users WHERE id=?", (target_user_id,)
    ).fetchone()
    if target is None:
        raise UserNotFound(f"user {target_user_id} not found")
    if target["role"] == "admin" and count_active_admins(db) <= 1:
        raise LastAdminCannotBeRemoved("cannot disable the last active admin")
    db.execute(
        "UPDATE users SET is_active=0, updated_at=? WHERE id=?",
        (_now(), target_user_id),
    )
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="disable_user",
        target_kind="user", target_id=str(target_user_id),
    )


def enable_user(
    db: sqlite3.Connection, *, admin_user_id: int, target_user_id: int
) -> None:
    _ensure_admin(db, admin_user_id)
    db.execute(
        "UPDATE users SET is_active=1, updated_at=? WHERE id=?",
        (_now(), target_user_id),
    )
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="enable_user",
        target_kind="user", target_id=str(target_user_id),
    )


def rotate_invite_code(
    db: sqlite3.Connection, *, admin_user_id: int, new_code: str
) -> str:
    _ensure_admin(db, admin_user_id)
    now = _now()
    db.execute(
        "UPDATE invite_codes SET is_active=0, rotated_at=? WHERE is_active=1",
        (now,),
    )
    db.execute(
        """
        INSERT INTO invite_codes(code, is_active, created_by_admin_id, created_at)
        VALUES (?, 1, ?, ?)
        """,
        (new_code, admin_user_id, now),
    )
    audit.log_admin_action(
        db, admin_user_id=admin_user_id, action_type="rotate_invite_code",
        target_kind="invite", target_id=new_code,
    )
    return new_code
```

- [ ] **Step 4: Run — expect ALL PASS**

```bash
pytest tests/test_users_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/users/service.py tests/test_users_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(users): add admin operations (promote/demote/disable/enable/rotate-invite) with last-admin guard"
```

---

## Task 8: Admin Routes (TDD)

**Files:**
- Modify: `backend/users/routes.py`, Create: `tests/test_admin_routes.py`

- [ ] **Step 1: Write `tests/test_admin_routes.py`**

```python
import pytest


def _bootstrap_admin(client, username="root", password="rootpass1"):
    """Register a user and promote to admin via direct DB write (simulating CLI)."""
    from backend.shared.db import connect
    from backend import config
    # Seed invite code
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("BURSIYER-2026",),
        )
    finally:
        conn.close()
    # Register
    client.post("/api/auth/register", json={
        "username": username, "password": password, "invite_code": "BURSIYER-2026",
    })
    # Promote via direct DB
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE users SET role='admin' WHERE username=?", (username,))
    finally:
        conn.close()
    # Login
    client.post("/api/auth/login", json={"username": username, "password": password})


def test_admin_can_list_users(client):
    _bootstrap_admin(client)
    r = client.get("/api/admin/users")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1


def test_non_admin_gets_404_on_admin_routes(client):
    _bootstrap_admin(client)
    # Logout, register new normal user
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    r = client.get("/api/admin/users")
    assert r.status_code == 404  # spec hides existence


def test_admin_promotes_user(client):
    _bootstrap_admin(client)
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "BURSIYER-2026",
    })
    # Find alice's id
    r = client.get("/api/admin/users")
    alice = next(u for u in r.json()["users"] if u["username"] == "alice")
    promote = client.post(f"/api/admin/users/{alice['id']}/promote")
    assert promote.status_code == 200
    r2 = client.get("/api/admin/users")
    alice2 = next(u for u in r2.json()["users"] if u["username"] == "alice")
    assert alice2["role"] == "admin"


def test_admin_cannot_demote_last_admin(client):
    _bootstrap_admin(client)
    r = client.get("/api/admin/users")
    me = next(u for u in r.json()["users"] if u["username"] == "root")
    demote = client.post(f"/api/admin/users/{me['id']}/demote")
    assert demote.status_code == 400


def test_admin_disable_user(client):
    _bootstrap_admin(client)
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "BURSIYER-2026",
    })
    r = client.get("/api/admin/users")
    alice = next(u for u in r.json()["users"] if u["username"] == "alice")
    dis = client.post(f"/api/admin/users/{alice['id']}/disable")
    assert dis.status_code == 200


def test_admin_rotate_invite_code(client):
    _bootstrap_admin(client)
    r = client.post("/api/admin/invite/rotate", json={"new_code": "NEW-CODE-2026"})
    assert r.status_code == 200
    body = r.json()
    assert body["new_code"] == "NEW-CODE-2026"


def test_admin_audit_log_endpoint_returns_actions(client):
    _bootstrap_admin(client)
    client.post("/api/admin/invite/rotate", json={"new_code": "X-2026"})
    r = client.get("/api/admin/audit-log")
    assert r.status_code == 200
    body = r.json()
    assert any(e["action_type"] == "rotate_invite_code" for e in body["events"])
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_admin_routes.py -v
```

- [ ] **Step 3: Add admin routes to `backend/users/routes.py`**

Append to the file (after existing routes):

```python
from pydantic import BaseModel as _BaseModel


class RotateInviteRequest(_BaseModel):
    new_code: str


@router.get("/admin/users", response_model=UsersListResponse)
def list_users(
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    rows = db.execute(
        "SELECT * FROM users ORDER BY id"
    ).fetchall()
    users = [_user_to_out(r) for r in rows]
    return {"users": users, "total": len(users)}


@router.post("/admin/users/{user_id}/promote", response_model=OkResponse)
def admin_promote(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    try:
        service.promote_admin(db, admin_user_id=admin["id"], target_user_id=user_id)
    except service.UserNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.post("/admin/users/{user_id}/demote", response_model=OkResponse)
def admin_demote(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    try:
        service.demote_admin(db, admin_user_id=admin["id"], target_user_id=user_id)
    except service.UserNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except service.LastAdminCannotBeRemoved as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/admin/users/{user_id}/disable", response_model=OkResponse)
def admin_disable(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    try:
        service.disable_user(db, admin_user_id=admin["id"], target_user_id=user_id)
    except service.UserNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except service.LastAdminCannotBeRemoved as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/admin/users/{user_id}/enable", response_model=OkResponse)
def admin_enable(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    try:
        service.enable_user(db, admin_user_id=admin["id"], target_user_id=user_id)
    except service.UserNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.post("/admin/invite/rotate")
def admin_rotate_invite(
    payload: RotateInviteRequest,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    new_code = service.rotate_invite_code(
        db, admin_user_id=admin["id"], new_code=payload.new_code
    )
    return {"ok": True, "new_code": new_code}


@router.get("/admin/audit-log")
def admin_audit_log(
    limit: int = 100,
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    rows = db.execute(
        "SELECT * FROM admin_audit_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    events = [
        {
            "id": r["id"],
            "admin_user_id": r["admin_user_id"],
            "action_type": r["action_type"],
            "target_kind": r["target_kind"],
            "target_id": r["target_id"],
            "metadata": r["metadata_json"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {"events": events}
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_admin_routes.py -v
pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/users/routes.py tests/test_admin_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(admin): add admin routes for user mgmt, invite rotate, audit log"
```

---

## Task 9: CLI Admin Commands (TDD)

**Files:**
- Modify: `backend/cli.py`, Create: `tests/test_cli_admin.py`

- [ ] **Step 1: Write `tests/test_cli_admin.py`**

```python
import subprocess
import sqlite3
import sys
from pathlib import Path


def _run_cli(tmp_path: Path, *args) -> subprocess.CompletedProcess:
    env = {
        "DATA_DIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
    }
    return subprocess.run(
        [sys.executable, "-m", "backend.cli", *args],
        capture_output=True, text=True, env=env,
    )


def _seed_invite_and_user(tmp_path: Path, username="root"):
    """Apply migrations, seed invite, register a user."""
    _run_cli(tmp_path, "migrate")
    db = sqlite3.connect(str(tmp_path / "db" / "annotations.db"))
    db.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
        ("BURSIYER-2026",),
    )
    # Insert user directly (bcrypt hash any value, since we just need the row)
    db.execute(
        """INSERT INTO users(username, password_hash, role, is_active, avatar_color,
                              created_at, updated_at)
           VALUES (?, '$2b$12$bogushash', 'user', 1, '#000000', datetime('now'), datetime('now'))""",
        (username,),
    )
    db.execute(
        "INSERT INTO gamification_state(user_id, updated_at) VALUES ((SELECT id FROM users WHERE username=?), datetime('now'))",
        (username,),
    )
    db.commit()
    db.close()


def test_cli_promote_admin_promotes_existing_user(tmp_path):
    _seed_invite_and_user(tmp_path, "root")
    result = _run_cli(tmp_path, "promote-admin", "root")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "promoted" in result.stdout.lower() or "admin" in result.stdout.lower()
    db = sqlite3.connect(str(tmp_path / "db" / "annotations.db"))
    row = db.execute("SELECT role FROM users WHERE username=?", ("root",)).fetchone()
    db.close()
    assert row[0] == "admin"


def test_cli_promote_admin_unknown_user_fails(tmp_path):
    _run_cli(tmp_path, "migrate")
    result = _run_cli(tmp_path, "promote-admin", "ghost")
    assert result.returncode != 0


def test_cli_create_invite_creates_active_code(tmp_path):
    _run_cli(tmp_path, "migrate")
    result = _run_cli(tmp_path, "create-invite", "FIRST-CODE-2026")
    assert result.returncode == 0, result.stderr
    db = sqlite3.connect(str(tmp_path / "db" / "annotations.db"))
    row = db.execute(
        "SELECT code, is_active FROM invite_codes WHERE code=?", ("FIRST-CODE-2026",)
    ).fetchone()
    db.close()
    assert row is not None
    assert row[1] == 1
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_cli_admin.py -v
```

- [ ] **Step 3: Modify `backend/cli.py`** — add new subcommands

Replace the existing file with:

```python
"""Command-line interface.

Usage:
  python -m backend.cli migrate
  python -m backend.cli promote-admin <username>
  python -m backend.cli demote-admin <username>
  python -m backend.cli create-invite <code>
  python -m backend.cli rotate-invite <new_code>
"""
import argparse
import sys
from datetime import datetime, timezone

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


def cmd_promote_admin(args) -> int:
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        apply_migrations(conn, discover_migrations())
        row = conn.execute("SELECT id FROM users WHERE username=?", (args.username,)).fetchone()
        if row is None:
            print(f"ERROR: user '{args.username}' not found", file=sys.stderr)
            return 2
        conn.execute(
            "UPDATE users SET role='admin', updated_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        # Audit (admin_user_id is the user themselves for bootstrap)
        conn.execute(
            """
            INSERT INTO admin_audit_log(admin_user_id, action_type, target_kind, target_id, metadata_json, created_at)
            VALUES (?, 'promote_admin_cli', 'user', ?, ?, ?)
            """,
            (
                row["id"], str(row["id"]),
                '{"source":"cli"}',
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    finally:
        conn.close()
    print(f"User '{args.username}' promoted to admin.")
    return 0


def cmd_demote_admin(args) -> int:
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        apply_migrations(conn, discover_migrations())
        row = conn.execute(
            "SELECT id, role FROM users WHERE username=?", (args.username,)
        ).fetchone()
        if row is None:
            print(f"ERROR: user '{args.username}' not found", file=sys.stderr)
            return 2
        if row["role"] != "admin":
            print(f"ERROR: user '{args.username}' is not an admin", file=sys.stderr)
            return 3
        active_admins = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role='admin' AND is_active=1"
        ).fetchone()["c"]
        if active_admins <= 1:
            print("ERROR: cannot demote the last active admin", file=sys.stderr)
            return 4
        conn.execute(
            "UPDATE users SET role='user', updated_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        conn.execute(
            """
            INSERT INTO admin_audit_log(admin_user_id, action_type, target_kind, target_id, metadata_json, created_at)
            VALUES (?, 'demote_admin_cli', 'user', ?, ?, ?)
            """,
            (
                row["id"], str(row["id"]),
                '{"source":"cli"}',
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    finally:
        conn.close()
    print(f"User '{args.username}' demoted to user.")
    return 0


def cmd_create_invite(args) -> int:
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        apply_migrations(conn, discover_migrations())
        # Deactivate existing active code (if any) — only one can be active
        conn.execute(
            "UPDATE invite_codes SET is_active=0, rotated_at=? WHERE is_active=1",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?, 1, ?)",
            (args.code, datetime.now(timezone.utc).isoformat()),
        )
    finally:
        conn.close()
    print(f"Invite code '{args.code}' created and activated.")
    return 0


def cmd_rotate_invite(args) -> int:
    return cmd_create_invite(args)  # same logic


COMMANDS = {
    "migrate": cmd_migrate,
    "promote-admin": cmd_promote_admin,
    "demote-admin": cmd_demote_admin,
    "create-invite": cmd_create_invite,
    "rotate-invite": cmd_rotate_invite,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backend.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply pending DB migrations")

    p_promote = sub.add_parser("promote-admin", help="Promote a user to admin")
    p_promote.add_argument("username")

    p_demote = sub.add_parser("demote-admin", help="Demote an admin to user")
    p_demote.add_argument("username")

    p_create = sub.add_parser("create-invite", help="Create / replace active invite code")
    p_create.add_argument("code")

    p_rotate = sub.add_parser("rotate-invite", help="Rotate active invite code")
    p_rotate.add_argument("code")

    args = parser.parse_args(argv)
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.error(f"unknown command: {args.command}")  # raises SystemExit
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_cli_admin.py -v
```

- [ ] **Step 5: Manual smoke test**

```bash
rm -rf /tmp/cli-admin-test
mkdir -p /tmp/cli-admin-test
. .venv/bin/activate
DATA_DIR=/tmp/cli-admin-test python -m backend.cli migrate
DATA_DIR=/tmp/cli-admin-test python -m backend.cli create-invite "BURSIYER-2026"
echo "---"
DATA_DIR=/tmp/cli-admin-test sqlite3 /tmp/cli-admin-test/db/annotations.db "SELECT code, is_active FROM invite_codes"
```

Expected: invite created and active.

- [ ] **Step 6: Commit**

```bash
git add backend/cli.py tests/test_cli_admin.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(cli): add promote-admin, demote-admin, create-invite, rotate-invite commands"
```

---

## Task 10: End-to-End Verification

**Files:** None (manual verification)

- [ ] **Step 1: Full test suite**

```bash
. .venv/bin/activate
pytest tests/ -v
```

Expected: ~80 tests pass (50 from Paket 1 + ~30 from Paket 2).

- [ ] **Step 2: Cold-start E2E flow simulation**

```bash
rm -rf /tmp/p2-e2e
mkdir -p /tmp/p2-e2e
DATA_DIR=/tmp/p2-e2e python -m backend.cli migrate
DATA_DIR=/tmp/p2-e2e python -m backend.cli create-invite "BURSIYER-2026"

# Start server
lsof -ti:8765 | xargs kill -9 2>/dev/null
DATA_DIR=/tmp/p2-e2e uvicorn backend.main:app --port 8765 --log-level error &
sleep 2

echo "=== 1. Register ==="
curl -s -c /tmp/p2-cookies.txt -X POST http://localhost:8765/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin1","password":"adminpass1","invite_code":"BURSIYER-2026"}'
echo

echo "=== 2. Login ==="
curl -s -c /tmp/p2-cookies.txt -X POST http://localhost:8765/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin1","password":"adminpass1"}'
echo

echo "=== 3. Auth/me before admin promotion (should be role=user) ==="
curl -s -b /tmp/p2-cookies.txt http://localhost:8765/api/auth/me
echo

echo "=== 4. Promote via CLI (simulating bootstrap) ==="
DATA_DIR=/tmp/p2-e2e python -m backend.cli promote-admin admin1

echo "=== 5. Re-login and check admin role ==="
curl -s -c /tmp/p2-cookies.txt -X POST http://localhost:8765/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin1","password":"adminpass1"}'
curl -s -b /tmp/p2-cookies.txt http://localhost:8765/api/auth/me
echo

echo "=== 6. List all users (admin endpoint) ==="
curl -s -b /tmp/p2-cookies.txt http://localhost:8765/api/admin/users
echo

echo "=== 7. Mark manual seen ==="
curl -s -b /tmp/p2-cookies.txt -X POST http://localhost:8765/api/me/seen-manual
echo
curl -s -b /tmp/p2-cookies.txt http://localhost:8765/api/auth/me
echo

echo "=== 8. Logout ==="
curl -s -b /tmp/p2-cookies.txt -X POST http://localhost:8765/api/auth/logout
echo
curl -s -b /tmp/p2-cookies.txt http://localhost:8765/api/auth/me  # should 401
echo

kill %1 2>/dev/null
```

Expected output: all 200/201 responses except step 8 second curl which is 401.

- [ ] **Step 3: Verify audit log**

```bash
sqlite3 /tmp/p2-e2e/db/annotations.db "SELECT action_type, target_id FROM admin_audit_log ORDER BY id"
```

Expected: at least `promote_admin_cli` entry from CLI use.

- [ ] **Step 4: Final review checklist**

Verify:
- [ ] All paket-1 tests still pass (50)
- [ ] All paket-2 tests pass (~30)
- [ ] /api/auth/{register,login,logout,me} all work
- [ ] /api/me/seen-manual sets has_seen_manual=true
- [ ] /api/admin/users requires admin role (404 for non-admin)
- [ ] Last-admin guard prevents losing last admin
- [ ] Session cookie HttpOnly + SameSite=Lax
- [ ] CLI promote-admin / create-invite / rotate-invite work

If any item fails, create follow-up task with specific failure.

- [ ] **Step 5: Tag the milestone**

```bash
git tag -a paket-2-auth -m "Paket 2 — Auth + Users + Multi-Admin complete"
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Implementing task |
|---|---|
| Davet kodu (paylaşılır, rotate edilebilir) | T2 register check, T7 rotate, T9 CLI |
| Bcrypt password | T2 (uses shared/auth.py from Paket 1) |
| Session cookie | T5 (set_cookie HttpOnly+SameSite) |
| Multi-admin + son-admin guard | T7 service, T8 routes, T9 CLI |
| Soft delete | T7 disable_user (is_active=0) |
| Audit log | T7 service writes via shared/audit |
| Reusable deps (get_current_user, require_admin, require_seen_manual, require_passed_training) | T4 |
| /api/me/seen-manual gating | T6 |
| Manuel CLI bootstrap | T9 promote-admin |
| Avatar color (deterministic from username) | T2 _avatar_color_for |
| Gamification_state initialized on register | T2 |

**2. Placeholder scan:** None. Every step has concrete code.

**3. Type/method consistency:**
- `service.register/login/logout/get_user_by_session/promote_admin/demote_admin/disable_user/enable_user/rotate_invite_code/count_active_admins` — all defined and used consistently
- `Exception types`: `InvalidInviteCode`, `UsernameTaken`, `EmailTaken`, `InvalidPassword`, `UserNotFound`, `InvalidCredentials`, `UserDisabled`, `NotAdmin`, `LastAdminCannotBeRemoved` — referenced consistently in tests, service, and route handlers
- `_user_to_out` — consistent shape for user serialization
- `get_db`, `get_current_user`, `require_admin`, `require_seen_manual`, `require_passed_training`, `get_request_ip` — deps consistent

**Known compromises:**
- `Secure` cookie flag is hardcoded `False` — should be from env var in prod (TODO before HTTPS deploy; tracked in Paket 15 deployment task)
- CLI `promote-admin` uses self-as-admin in audit log (since it's bootstrap, no prior admin exists). Acceptable for first-time use.
- 30-day session timeout via Max-Age cookie. DB-side expiry (`last_activity_at` cleanup) deferred to a later retention/cleanup job (Paket 13).
