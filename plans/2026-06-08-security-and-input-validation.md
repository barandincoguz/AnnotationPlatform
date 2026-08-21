# Security and Input Validation Implementation Plan

**Goal:** Strengthen the platform's security posture and ensure high-quality reference data through entropy checks, CSRF origin normalization, thread-safe rate limiter garbage collection, salted IP hashing, async tamper-evident logging, and smart input normalization/auto-splitting.

**Architecture:** The security middleware layer is hardened with cryptographic and thread-safe utilities, while the reference input pipeline is enhanced with identical frontend and backend normalization, validation, and auto-splitting rules.

**Design:** [thoughts/shared/designs/2026-06-08-security-and-input-validation-design.md](../designs/2026-06-08-security-and-input-validation-design.md)

---

## Dependency Graph

```
Batch 1 (parallel): 1.1, 1.2 [foundation - no deps]
Batch 2 (parallel): 2.1, 2.2, 2.3, 2.4, 2.5 [core - depends on batch 1]
Batch 3 (parallel): 3.1, 3.2 [advanced core - depends on batch 2]
Batch 4 (parallel): 4.1, 4.2 [integration - depends on batch 3]
```

---

## Batch 1: Foundation (parallel - 2 implementers)

All tasks in this batch have NO dependencies and run simultaneously.

### Task 1.1: Migration for Hash-Chaining
**File:** `backend/migrations/v0008_audit_hash_chain.py`
**Test:** `tests/test_v0008_audit_hash_chain.py`
**Depends:** none

```python
# backend/migrations/v0008_audit_hash_chain.py
"""v0008 — add hash and prev_hash columns to admin_audit_log.

Enables cryptographic tamper-evident hash-chaining of administrative audit logs.
"""
import sqlite3

SQL = """
ALTER TABLE admin_audit_log ADD COLUMN hash TEXT;
ALTER TABLE admin_audit_log ADD COLUMN prev_hash TEXT;

CREATE INDEX idx_audit_hash ON admin_audit_log(hash) WHERE hash IS NOT NULL;
"""


def up(conn: sqlite3.Connection) -> None:
    for stmt in (s.strip() for s in SQL.split(";")):
        if stmt:
            conn.execute(stmt)
```

```python
# tests/test_v0008_audit_hash_chain.py
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


def test_v0008_migration_adds_columns(db_path):
    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())
        
        # Verify columns exist in admin_audit_log
        cursor = conn.execute("PRAGMA table_info(admin_audit_log)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "hash" in columns
        assert "prev_hash" in columns
    finally:
        conn.close()
```

**Verify:** `pytest tests/test_v0008_audit_hash_chain.py`
**Commit:** `feat(audit): add migration for admin audit log hash chain columns`

---

### Task 1.2: validateReferences.ts Normalization and Auto-Splitting Helpers
**File:** `frontend/src/lib/validateReferences.ts`
**Test:** `frontend/src/lib/validateReferences.test.ts`
**Depends:** none

```typescript
// frontend/src/lib/validateReferences.ts (updated)
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

export interface ParsedReference {
  madde: string | null
  fikra: string | null
  bent: string | null
}

/**
 * Parses a complex madde input (e.g., "5/1-a") into separate fields.
 */
export function parseComplexMadde(input: string): ParsedReference | null {
  const trimmed = input.trim()
  if (!trimmed) return null
  
  if (!trimmed.includes('/') && !trimmed.includes('-')) {
    return null
  }
  
  const match = trimmed.match(/^([0-9a-zA-Z]+)(?:\/([0-9a-zA-Z]+))?(?:-([a-zA-ZçğıöşüÇĞİÖŞÜ]+))?$/)
  if (!match) {
    return null
  }
  
  return {
    madde: match[1] || null,
    fikra: match[2] || null,
    bent: match[3] || null,
  }
}

/**
 * Cleans the bent field by stripping parentheses, dots, quotes, and converting to lowercase.
 */
export function cleanBent(val: string | null): string | null {
  if (!val) return null
  const cleaned = val.replace(/^[().'"\s]+|[().'"\s]+$/g, '').toLowerCase()
  return cleaned || null
}

export function emptyReferenceItem(): ReferenceItem {
  return {
    kanun_no: null,
    kanun_ad: null,
    madde: null,
    fikra: null,
    bent: null,
    source_text: '',
  }
}

function hasAtLeastOneKanunField(r: ReferenceItem): boolean {
  const hasKanunNo = (r.kanun_no?.trim() ?? '') !== ''
  const hasKanunAd = (r.kanun_ad?.trim() ?? '') !== ''
  return hasKanunNo || hasKanunAd
}

export function isValidReference(r: ReferenceItem): boolean {
  if (!r.source_text || r.source_text.trim().length === 0) return false
  if (r.madde && (r.madde.includes('/') || r.madde.includes('-'))) {
    return false
  }
  return hasAtLeastOneKanunField(r)
}

export function areAllReferencesValid(refs: ReferenceItem[]): boolean {
  return refs.every(isValidReference)
}

export function isValidTrainingReference(r: ReferenceItem): boolean {
  return hasAtLeastOneKanunField(r)
}

export function areAllTrainingReferencesValid(refs: ReferenceItem[]): boolean {
  return refs.every(isValidTrainingReference)
}
```

```typescript
// frontend/src/lib/validateReferences.test.ts (updated/appended)
import { describe, it, expect } from 'vitest'
import {
  isValidReference,
  parseComplexMadde,
  cleanBent,
} from './validateReferences'

describe('parseComplexMadde', () => {
  it('parses full complex reference correctly', () => {
    expect(parseComplexMadde('5/1-a')).toEqual({
      madde: '5',
      fikra: '1',
      bent: 'a',
    })
  })

  it('parses Roman numerals correctly', () => {
    expect(parseComplexMadde('V/1-a')).toEqual({
      madde: 'V',
      fikra: '1',
      bent: 'a',
    })
  })

  it('parses madde and fikra only', () => {
    expect(parseComplexMadde('5/1')).toEqual({
      madde: '5',
      fikra: '1',
      bent: null,
    })
  })

  it('parses madde and bent only', () => {
    expect(parseComplexMadde('5-a')).toEqual({
      madde: '5',
      fikra: null,
      bent: 'a',
    })
  })

  it('returns null for simple madde', () => {
    expect(parseComplexMadde('5')).toBeNull()
  })

  it('returns null for invalid format', () => {
    expect(parseComplexMadde('5/1/a-b')).toBeNull()
  })
})

describe('cleanBent', () => {
  it('strips parentheses and dots', () => {
    expect(cleanBent('(a)')).toBe('a')
    expect(cleanBent('a.')).toBe('a')
    expect(cleanBent('(a).')).toBe('a')
    expect(cleanBent('"a"')).toBe('a')
  })

  it('converts to lowercase', () => {
    expect(cleanBent('A')).toBe('a')
    expect(cleanBent('(B).')).toBe('b')
  })
})

describe('isValidReference with complex madde', () => {
  it('rejects unparsed complex madde', () => {
    const ref = {
      kanun_no: '5520',
      source_text: 'metin',
      madde: '5/1-a',
      fikra: null,
      bent: null,
    }
    expect(isValidReference(ref)).toBe(false)
  })
})
```

**Verify:** `cd frontend && npm run test:run -- src/lib/validateReferences.test.ts`
**Commit:** `feat(validate): add complex reference parsing and bent cleaning helpers`

---

## Batch 2: Core Modules (parallel - 5 implementers)

All tasks in this batch depend on Batch 1 completing.

### Task 2.1: Secret Strength (Shannon Entropy)
**File:** `backend/shared/prod_enforce.py`
**Test:** `tests/test_prod_enforce.py`
**Depends:** none

```python
# backend/shared/prod_enforce.py (updated)
import sys
import math
from collections import Counter

from backend import config


DEV_SESSION_SECRETS = {
    "dev-secret-DO-NOT-USE-IN-PROD",  # backend/config.py default
    "dev-secret-change-me",            # docker-compose.yml default
}

_MIN_SESSION_SECRET_LEN = 32
_MIN_BOOTSTRAP_PASSWORD_LEN = 12

_PLACEHOLDER_PASSWORD_PATTERNS = (
    "admin",
    "password",
    "letmein",
    "changeme",
    "replace_me",
    "replaceme",
    "qwerty",
)

_TEMPLATE_PLACEHOLDER_NEEDLE = "<replace_me"


class ProductionConfigError(RuntimeError):
    """Raised when production mode is enabled but config is unsafe."""


def shannon_entropy(s: str) -> float:
    """Calculate the character-level Shannon entropy of a string."""
    if not s:
        return 0.0
    counts = Counter(s)
    total = len(s)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def enforce_production_secrets() -> None:
    """In ENVIRONMENT=production: hard-fail on any unsafe config.

    Otherwise: no-op.
    """
    if config.ENVIRONMENT != "production":
        return

    errors: list[str] = []

    if config.SESSION_SECRET in DEV_SESSION_SECRETS:
        errors.append(
            "SESSION_SECRET must not be the default placeholder "
            "(set via env var; generate with `openssl rand -hex 32`)"
        )
    elif _TEMPLATE_PLACEHOLDER_NEEDLE in config.SESSION_SECRET.lower():
        errors.append(
            "SESSION_SECRET still contains the .env.example template "
            f"placeholder ({_TEMPLATE_PLACEHOLDER_NEEDLE!r}); generate a "
            "real value via `openssl rand -hex 32`"
        )
    elif len(config.SESSION_SECRET) < _MIN_SESSION_SECRET_LEN:
        errors.append(
            f"SESSION_SECRET must be at least {_MIN_SESSION_SECRET_LEN} characters "
            f"(current: {len(config.SESSION_SECRET)})"
        )
    else:
        # Enforce minimum Shannon entropy of 3.0 bits per character
        entropy = shannon_entropy(config.SESSION_SECRET)
        if entropy < 3.0:
            errors.append(
                f"SESSION_SECRET has too low Shannon entropy ({entropy:.2f} bits/char, "
                "minimum required: 3.0). Use a cryptographically secure random string "
                "(e.g. `openssl rand -hex 32`)"
            )

    if config.BOOTSTRAP_ADMIN_PASSWORD and \
            len(config.BOOTSTRAP_ADMIN_PASSWORD) < _MIN_BOOTSTRAP_PASSWORD_LEN:
        errors.append(
            f"BOOTSTRAP_ADMIN_PASSWORD must be at least "
            f"{_MIN_BOOTSTRAP_PASSWORD_LEN} characters in production"
        )

    if config.BOOTSTRAP_ADMIN_PASSWORD:
        lowered = config.BOOTSTRAP_ADMIN_PASSWORD.lower()
        for needle in _PLACEHOLDER_PASSWORD_PATTERNS:
            if needle in lowered:
                errors.append(
                    f"BOOTSTRAP_ADMIN_PASSWORD contains a placeholder "
                    f"substring ({needle!r}); choose an un-guessable value"
                )
                break

    if not config.ALLOWED_ORIGINS:
        errors.append(
            "ALLOWED_ORIGINS must be set in production (comma-separated "
            "full origins; see backend/shared/csrf.py). Without it every "
            "state-changing request is rejected."
        )
    elif any(
        _TEMPLATE_PLACEHOLDER_NEEDLE in origin.lower()
        for origin in config.ALLOWED_ORIGINS
    ):
        errors.append(
            "ALLOWED_ORIGINS still contains the .env.example template "
            f"placeholder ({_TEMPLATE_PLACEHOLDER_NEEDLE!r}); set the real "
            "public origin (e.g. https://anotasyon.example.com)"
        )

    if errors:
        msg = "production mode enforcement failed:\n  - " + "\n  - ".join(errors)
        msg += "\nSet ENVIRONMENT=development to disable enforcement."
        raise ProductionConfigError(msg)

    if not config.BACKUP_REPO_URL:
        print(
            "WARNING: no backup configured (BACKUP_REPO_URL empty); "
            "set it for automatic GitHub backup.",
            file=sys.stderr,
        )
```

```python
# tests/test_prod_enforce.py (updated/appended)
def test_low_entropy_session_secret_rejected(prod):
    # "12345678901234567890123456789012" has entropy ~3.32, but repetitive patterns are blocked
    prod.setattr(config, "SESSION_SECRET", "a" * 32)  # Entropy is 0.0
    with pytest.raises(ProductionConfigError, match="Shannon entropy"):
        enforce_production_secrets()
```

**Verify:** `pytest tests/test_prod_enforce.py`
**Commit:** `feat(security): enforce minimum Shannon entropy check for production session secret`

---

### Task 2.2: CSRF Origin Normalization
**File:** `backend/shared/csrf.py` and `backend/config.py`
**Test:** `tests/test_csrf_normalization.py`
**Depends:** none

```python
# backend/shared/csrf.py (updated)
from __future__ import annotations

import json
from urllib.parse import urlparse

from starlette.types import ASGIApp, Receive, Scope, Send

from backend import config


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def normalize_origin(origin: str) -> str:
    """Normalize an origin string by lowercasing and stripping default ports (80/443)."""
    if not origin:
        return ""
    parsed = urlparse(origin)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if not scheme or not netloc:
        return origin.strip().lower()
    if ":" in netloc:
        host, port = netloc.rsplit(":", 1)
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host
    return f"{scheme}://{netloc}"


class OriginCheckMiddleware:
    """ASGI middleware. See module docstring for rationale."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not config.is_production():
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        if method in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        origin = headers.get("origin")
        referer = headers.get("referer")

        source = origin
        if not source and referer:
            parsed = urlparse(referer)
            if parsed.scheme and parsed.netloc:
                source = f"{parsed.scheme}://{parsed.netloc}"

        if not source or normalize_origin(source) not in config.ALLOWED_ORIGINS:
            await _reject(send, source)
            return

        await self.app(scope, receive, send)


async def _reject(send: Send, source: str | None) -> None:
    body = json.dumps(
        {
            "detail": {
                "error": "origin_not_allowed",
                "message": (
                    "missing Origin/Referer"
                    if not source
                    else "origin not in ALLOWED_ORIGINS"
                ),
            }
        }
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
```

```python
# backend/config.py (updated _parse_allowed_origins)
def _parse_allowed_origins(raw: str) -> set[str]:
    """Comma-separated → normalized set. Normalizes scheme+host+port."""
    from backend.shared.csrf import normalize_origin
    return {normalize_origin(o) for o in raw.split(",") if o.strip()}
```

```python
# tests/test_csrf_normalization.py
from backend.shared.csrf import normalize_origin


def test_normalize_origin_strips_default_ports():
    assert normalize_origin("http://localhost:80") == "http://localhost"
    assert normalize_origin("https://anotasyon.example:443") == "https://anotasyon.example"
    assert normalize_origin("http://localhost:8000") == "http://localhost:8000"


def test_normalize_origin_lowercases():
    assert normalize_origin("HTTPS://ANOTASYON.EXAMPLE") == "https://anotasyon.example"
```

**Verify:** `pytest tests/test_csrf_normalization.py`
**Commit:** `feat(csrf): normalize origins and strip default ports for CSRF matching`

---

### Task 2.3: Salted IP Hashing
**File:** `backend/shared/auth.py`
**Test:** `tests/test_auth.py`
**Depends:** none

```python
# backend/shared/auth.py (updated)
import hashlib
import secrets
import bcrypt
import hmac


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
    """HMAC-SHA256 hex digest of an IP address using SESSION_SECRET as the salt/pepper."""
    from backend import config
    key = config.SESSION_SECRET.encode("utf-8")
    return hmac.new(key, ip.encode("utf-8"), hashlib.sha256).hexdigest()
```

```python
# tests/test_auth.py (updated/appended)
def test_hash_ip_uses_salted_hmac():
    from backend.shared.auth import hash_ip
    from backend import config
    
    ip = "192.168.1.1"
    hash1 = hash_ip(ip)
    
    # Changing secret should change the hash
    config.SESSION_SECRET = "different-secret-key-for-testing-purposes"
    hash2 = hash_ip(ip)
    
    assert hash1 != hash2
    assert len(hash1) == 64
```

**Verify:** `pytest tests/test_auth.py`
**Commit:** `feat(security): transition hash_ip to salted HMAC-SHA256 using SESSION_SECRET`

---

### Task 2.4: Reference Models Validation
**File:** `backend/annotations/models.py`
**Test:** `tests/test_annotations_service.py`
**Depends:** none

```python
# backend/annotations/models.py (updated ReferenceItem)
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class ReferenceItem(BaseModel):
    kanun_no: Optional[str] = Field(default=None, max_length=64)
    kanun_ad: Optional[str] = Field(default=None, max_length=512)
    madde: Optional[str] = Field(default=None, max_length=64)
    fikra: Optional[str] = Field(default=None, max_length=64)
    bent: Optional[str] = Field(default=None, max_length=64)
    source_text: str = Field(min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def validate_madde_format(self) -> "ReferenceItem":
        if self.madde:
            # Reject if madde contains '/' or '-' which indicates a complex format that wasn't split
            if "/" in self.madde or "-" in self.madde:
                raise ValueError(
                    "Geçersiz madde formatı. Madde alanı '/' veya '-' içeremez. "
                    "Lütfen Madde, Fıkra ve Bent alanlarını ayrı ayrı doldurun."
                )
        return self
```

```python
# tests/test_annotations_service.py (updated/appended)
def test_reference_item_rejects_complex_madde():
    from pydantic import ValidationError
    from backend.annotations.models import ReferenceItem
    
    with pytest.raises(ValidationError, match="Geçersiz madde formatı"):
        ReferenceItem(
            kanun_no="5520",
            madde="5/1-a",
            source_text="test"
        )
```

**Verify:** `pytest tests/test_annotations_service.py`
**Commit:** `feat(validation): reject unparsed complex madde formats in Pydantic model`

---

### Task 2.5: Reference Diff Bent Cleaning
**File:** `backend/annotations/diff.py`
**Test:** `tests/test_annotations_diff.py`
**Depends:** none

```python
# backend/annotations/diff.py (updated)
from typing import Optional

REFERENCE_FIELDS = (
    "kanun_no", "kanun_ad", "madde", "fikra", "bent", "source_text",
)


class InvalidReference(ValueError):
    """source_text missing or empty."""


class DuplicateReference(ValueError):
    """Two refs in the same list have identical canonical keys."""


def _clean(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def clean_bent(val: Optional[str]) -> Optional[str]:
    """Strip parentheses, dots, quotes, and convert to lowercase."""
    if not val:
        return None
    s = val.strip("().'\" ").lower()
    return s if s else None


def normalize_reference(ref: dict) -> dict:
    """Return a 6-key dict with whitespace stripped, empty → None.

    Raises InvalidReference if source_text is missing or empty.
    """
    out = {f: _clean(ref.get(f)) for f in REFERENCE_FIELDS}
    if not out["source_text"]:
        raise InvalidReference("source_text is required")
    # Apply specific cleaning to the bent field
    out["bent"] = clean_bent(out["bent"])
    return out


def canonical_key(ref: dict) -> tuple:
    """Stable 6-tuple identity for set-based comparison."""
    return tuple(ref.get(f) for f in REFERENCE_FIELDS)


def normalize_references(refs: list[dict]) -> list[dict]:
    """Normalize each ref; reject the list if any two are exact duplicates.

    Order is preserved (used as `seq` for the denormalized index).
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in refs:
        n = normalize_reference(r)
        key = canonical_key(n)
        if key in seen:
            raise DuplicateReference(
                f"duplicate reference: source_text={n['source_text']!r}"
            )
        seen.add(key)
        out.append(n)
    return out


def references_diff(prev: list[dict], curr: list[dict]) -> dict:
    """Set-based symmetric difference. Returns {'added': [...], 'removed': [...]}.

    Inputs should already be normalized.
    """
    prev_map = {canonical_key(r): r for r in prev}
    curr_map = {canonical_key(r): r for r in curr}
    added_keys = curr_map.keys() - prev_map.keys()
    removed_keys = prev_map.keys() - curr_map.keys()
    return {
        "added": [curr_map[k] for k in added_keys],
        "removed": [prev_map[k] for k in removed_keys],
    }


def is_diff_zero(diff: dict) -> bool:
    return not diff["added"] and not diff["removed"]
```

```python
# tests/test_annotations_diff.py (updated/appended)
def test_normalize_reference_cleans_bent():
    from backend.annotations.diff import normalize_reference
    
    ref = {
        "kanun_no": "5520",
        "bent": "(a).",
        "source_text": "test"
    }
    normalized = normalize_reference(ref)
    assert normalized["bent"] == "a"
```

**Verify:** `pytest tests/test_annotations_diff.py`
**Commit:** `feat(validation): clean and normalize bent field on the backend`

---

## Batch 3: Advanced Core & Components (parallel - 2 implementers)

All tasks in this batch depend on Batch 2 completing.

### Task 3.1: Rate Limiter Memory Leak Cleanup
**File:** `backend/shared/rate_limit.py`
**Test:** `tests/test_rate_limit.py`
**Depends:** none

```python
# backend/shared/rate_limit.py (updated)
from __future__ import annotations

import threading
import time
import asyncio
from collections import deque
from typing import Callable, Optional

from fastapi import HTTPException, Request


# Per-namespace state. Each value is {ip: deque[float_ts]}.
_BUCKETS: dict[str, dict[str, deque[float]]] = {}
_WINDOWS: dict[str, int] = {}
_LOCK = threading.Lock()


def _bucket(namespace: str) -> dict[str, deque[float]]:
    """Get-or-create the IP→timestamps map for a namespace."""
    bucket = _BUCKETS.get(namespace)
    if bucket is None:
        with _LOCK:
            bucket = _BUCKETS.setdefault(namespace, {})
    return bucket


def reset_for_tests() -> None:
    """Drain every bucket's entries. Called from test fixtures to isolate runs."""
    with _LOCK:
        for ns_bucket in _BUCKETS.values():
            ns_bucket.clear()


async def cleanup_rate_limiter_task() -> None:
    """Periodic background task to clean up stale IP keys from rate limiter buckets."""
    while True:
        try:
            await asyncio.sleep(60)  # Run every 60 seconds
            cleanup_rate_limiter()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error in rate limiter cleanup task: {e}")


def cleanup_rate_limiter() -> None:
    """Evict keys from _BUCKETS where the deque is empty or all timestamps are older than the window."""
    now = time.monotonic()
    with _LOCK:
        for namespace, ip_buckets in list(_BUCKETS.items()):
            window = _WINDOWS.get(namespace, 3600)
            cutoff = now - window
            for ip, dq in list(ip_buckets.items()):
                while dq and dq[0] < cutoff:
                    dq.popleft()
                if not dq:
                    del ip_buckets[ip]


def rate_limit(
    *,
    namespace: str,
    max_hits: int,
    window_seconds: int,
    key_fn: Optional[Callable[[Request], str]] = None,
) -> Callable:
    """Build a FastAPI dependency that throttles based on a sliding window."""
    from backend.users.deps import get_request_ip  # local import: avoid cycle

    _WINDOWS[namespace] = window_seconds

    def _key_default(req: Request) -> str:
        ip = get_request_ip(req)
        return ip or "unknown"

    extract_key = key_fn or _key_default
    bucket = _bucket(namespace)

    def dependency(request: Request) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        key = extract_key(request)

        with _LOCK:
            dq = bucket.get(key)
            if dq is None:
                dq = deque(maxlen=max_hits + 1)
                bucket[key] = dq
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= max_hits:
                retry_after = max(1, int(dq[0] + window_seconds - now + 0.999))
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limited",
                        "message": (
                            f"too many requests; retry in ~{retry_after}s"
                        ),
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            dq.append(now)

    return dependency
```

```python
# tests/test_rate_limit.py (updated/appended)
def test_cleanup_rate_limiter_evicts_stale_keys():
    from backend.shared.rate_limit import _BUCKETS, _WINDOWS, rate_limit, cleanup_rate_limiter
    from collections import deque
    import time
    
    # Setup test bucket
    _WINDOWS["test_cleanup"] = 10
    _BUCKETS["test_cleanup"] = {
        "1.1.1.1": deque([time.monotonic() - 20]),  # Stale
        "2.2.2.2": deque([time.monotonic() - 5]),   # Active
    }
    
    cleanup_rate_limiter()
    
    assert "1.1.1.1" not in _BUCKETS["test_cleanup"]
    assert "2.2.2.2" in _BUCKETS["test_cleanup"]
```

**Verify:** `pytest tests/test_rate_limit.py`
**Commit:** `feat(rate-limit): add thread-safe background cleanup task to prevent memory leaks`

---

### Task 3.2: Async & Tamper-Evident Logging Queue
**File:** `backend/shared/audit.py`
**Test:** `tests/test_audit.py`
**Depends:** 1.1

```python
# backend/shared/audit.py (updated)
import json
import sqlite3
import uuid
import queue
import threading
import hashlib
from datetime import datetime, timezone
from typing import Optional

from backend import config

VALID_SEVERITIES = {"info", "warn", "error"}

_QUEUE: queue.Queue = queue.Queue()
_WORKER_THREAD: Optional[threading.Thread] = None
_STOP_EVENT = threading.Event()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def gen_trace_id() -> str:
    """16-char lowercase hex token (64 bits of entropy, uuid4-derived)."""
    return uuid.uuid4().hex[:16]


def start_worker() -> None:
    """Start the background daemon thread to process audit logs asynchronously."""
    global _WORKER_THREAD
    if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
        return
    _STOP_EVENT.clear()
    _WORKER_THREAD = threading.Thread(target=_worker_loop, daemon=True)
    _WORKER_THREAD.start()


def stop_worker() -> None:
    """Stop the background daemon thread and join it."""
    global _WORKER_THREAD
    if _WORKER_THREAD is None:
        return
    _STOP_EVENT.set()
    _QUEUE.put(None)  # Wake up the worker
    _WORKER_THREAD.join(timeout=5.0)
    _WORKER_THREAD = None


def _worker_loop() -> None:
    from backend.shared.db import connect
    conn = connect(config.DB_PATH)
    try:
        while not _STOP_EVENT.is_set() or not _QUEUE.empty():
            try:
                item = _QUEUE.get(timeout=1.0)
                if item is None:
                    _QUEUE.task_done()
                    continue
                
                func, args, kwargs = item
                func(conn, *args, **kwargs)
                conn.commit()
                _QUEUE.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in audit worker thread: {e}")
    finally:
        conn.close()


def _get_latest_hash(conn: sqlite3.Connection) -> Optional[str]:
    row = conn.execute("SELECT hash FROM admin_audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return row["hash"] if row else None


def _compute_hash(
    prev_hash: Optional[str],
    admin_user_id: Optional[int],
    action_type: str,
    target_kind: Optional[str],
    target_id: Optional[str],
    metadata_json: Optional[str],
    created_at: str,
    trace_id: Optional[str],
) -> str:
    parts = [
        prev_hash or "",
        str(admin_user_id) if admin_user_id is not None else "",
        action_type,
        target_kind or "",
        target_id or "",
        metadata_json or "",
        created_at,
        trace_id or ""
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _execute_log_activity(
    conn: sqlite3.Connection,
    user_id: int,
    event_type: str,
    session_id: Optional[int],
    document_id: Optional[str],
    duration_ms: Optional[int],
    extra: Optional[dict],
    created_at: str,
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
            created_at,
        ),
    )


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
    created_at = _now()
    if config.ENVIRONMENT == "test" or _WORKER_THREAD is None or not _WORKER_THREAD.is_alive():
        _execute_log_activity(conn, user_id, event_type, session_id, document_id, duration_ms, extra, created_at)
    else:
        _QUEUE.put((_execute_log_activity, (user_id, event_type, session_id, document_id, duration_ms, extra, created_at), {}))


def _execute_log_behavioral(
    conn: sqlite3.Connection,
    user_id: int,
    detector: str,
    threshold_value: Optional[float],
    actual_value: Optional[float],
    context: Optional[dict],
    created_at: str,
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
            created_at,
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
    created_at = _now()
    if config.ENVIRONMENT == "test" or _WORKER_THREAD is None or not _WORKER_THREAD.is_alive():
        _execute_log_behavioral(conn, user_id, detector, threshold_value, actual_value, context, created_at)
    else:
        _QUEUE.put((_execute_log_behavioral, (user_id, detector, threshold_value, actual_value, context, created_at), {}))


def _execute_log_admin_action(
    conn: sqlite3.Connection,
    admin_user_id: Optional[int],
    action_type: str,
    target_kind: Optional[str],
    target_id: Optional[str],
    metadata: Optional[dict],
    created_at: str,
    trace_id: Optional[str],
) -> None:
    metadata_json = json.dumps(metadata) if metadata is not None else None
    prev_hash = _get_latest_hash(conn)
    current_hash = _compute_hash(
        prev_hash, admin_user_id, action_type, target_kind, target_id, metadata_json, created_at, trace_id
    )
    conn.execute(
        """
        INSERT INTO admin_audit_log(
            admin_user_id, action_type, target_kind, target_id,
            metadata_json, created_at, trace_id, hash, prev_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            admin_user_id, action_type, target_kind, target_id,
            metadata_json,
            created_at,
            trace_id,
            current_hash,
            prev_hash,
        ),
    )


def log_admin_action(
    conn: sqlite3.Connection,
    admin_user_id: Optional[int],
    action_type: str,
    *,
    target_kind: Optional[str] = None,
    target_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    trace_id: Optional[str] = None,
) -> None:
    created_at = _now()
    if config.ENVIRONMENT == "test" or _WORKER_THREAD is None or not _WORKER_THREAD.is_alive():
        _execute_log_admin_action(conn, admin_user_id, action_type, target_kind, target_id, metadata, created_at, trace_id)
    else:
        _QUEUE.put((_execute_log_admin_action, (admin_user_id, action_type, target_kind, target_id, metadata, created_at, trace_id), {}))


def _execute_log_system_event(
    conn: sqlite3.Connection,
    event_type: str,
    severity: str,
    message: Optional[str],
    extra: Optional[dict],
    created_at: str,
    trace_id: Optional[str],
) -> None:
    conn.execute(
        """
        INSERT INTO system_events(
            event_type, severity, message, extra_json, created_at, trace_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            event_type, severity, message,
            json.dumps(extra) if extra is not None else None,
            created_at,
            trace_id,
        ),
    )


def log_system_event(
    conn: sqlite3.Connection,
    event_type: str,
    severity: str,
    *,
    message: Optional[str] = None,
    extra: Optional[dict] = None,
    trace_id: Optional[str] = None,
) -> None:
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"invalid severity: {severity!r} (must be one of {VALID_SEVERITIES})")
    created_at = _now()
    if config.ENVIRONMENT == "test" or _WORKER_THREAD is None or not _WORKER_THREAD.is_alive():
        _execute_log_system_event(conn, event_type, severity, message, extra, created_at, trace_id)
    else:
        _QUEUE.put((_execute_log_system_event, (event_type, severity, message, extra, created_at, trace_id), {}))
```

```python
# tests/test_audit.py (updated/appended)
def test_admin_audit_log_hash_chaining(db):
    from backend.shared import audit
    
    # Log first action
    audit.log_admin_action(db, admin_user_id=1, action_type="action_1")
    row1 = db.execute("SELECT * FROM admin_audit_log WHERE action_type='action_1'").fetchone()
    assert row1["hash"] is not None
    assert row1["prev_hash"] is None
    
    # Log second action
    audit.log_admin_action(db, admin_user_id=1, action_type="action_2")
    row2 = db.execute("SELECT * FROM admin_audit_log WHERE action_type='action_2'").fetchone()
    assert row2["hash"] is not None
    assert row2["prev_hash"] == row1["hash"]
```

**Verify:** `pytest tests/test_audit.py`
**Commit:** `feat(audit): implement async logging queue and tamper-evident hash-chaining`

---

## Batch 4: Integration (parallel - 2 implementers)

All tasks in this batch depend on Batch 3 completing.

### Task 4.1: Lifespan Integration for Async Logging & Rate Limiter Cleanup
**File:** `backend/main.py`
**Test:** `tests/test_audit.py`
**Depends:** 3.1, 3.2

```python
# backend/main.py (updated lifespan)
@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.validate_environment()
    enforce_production_secrets()
    config.ensure_dirs()
    
    # Start background audit worker thread
    from backend.shared.audit import start_worker, stop_worker
    start_worker()

    conn = connect(config.DB_PATH)
    try:
        applied = apply_migrations(conn, discover_migrations())
        # ... (rest of existing lifespan startup logic) ...
    finally:
        conn.close()

    # Start rate limiter cleanup task
    from backend.shared.rate_limit import cleanup_rate_limiter_task
    rate_limit_cleanup_task = asyncio.create_task(cleanup_rate_limiter_task())

    sweep_task     = locks_sweep.start(interval_seconds=60)
    backup_task    = backup_loop.start()
    retention_task = retention_loop.start()
    mirror_task    = mirror_dispatcher.start()

    yield

    # Stop rate limiter cleanup task
    rate_limit_cleanup_task.cancel()
    try:
        await rate_limit_cleanup_task
    except asyncio.CancelledError:
        pass

    locks_sweep.stop()
    try:
        await sweep_task
    except Exception:
        pass

    backup_loop.stop()
    try:
        await backup_task
    except Exception:
        pass

    retention_loop.stop()
    try:
        await retention_task
    except Exception:
        pass

    mirror_dispatcher.stop()
    try:
        await mirror_task
    except Exception:
        pass

    # Stop background audit worker thread
    stop_worker()

    conn = connect(config.DB_PATH)
    try:
        audit.log_system_event(conn, "shutdown", "info", message=f"app v{VERSION} shutting down")
    finally:
        conn.close()
```

**Verify:** `pytest tests/test_audit.py`
**Commit:** `feat(main): integrate async logging worker and rate limiter cleanup into lifespan`

---

### Task 4.2: Frontend ReferenceCard Auto-Splitting & Bent Normalization
**File:** `frontend/src/components/annotation/ReferenceCard.tsx`
**Test:** `frontend/src/components/annotation/ReferenceCard.test.tsx`
**Depends:** 1.2

```typescript
// frontend/src/components/annotation/ReferenceCard.tsx (updated)
import { X, Quote, AlertCircle, ChevronUp } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { components } from '@/api/types'
import { parseComplexMadde, cleanBent } from '@/lib/validateReferences'

type ReferenceItem = components['schemas']['ReferenceItem']

interface ReferenceCardProps {
  index: number
  value: ReferenceItem
  onChange: (next: ReferenceItem) => void
  onRemove: () => void
  disabled: boolean
  isExpanded: boolean
  onExpand: () => void
}

function set<K extends keyof ReferenceItem>(prev: ReferenceItem, key: K, v: string): ReferenceItem {
  return { ...prev, [key]: v === '' ? (key === 'source_text' ? '' : null) : v }
}

export function ReferenceCard({
  index,
  value,
  onChange,
  onRemove,
  disabled,
  isExpanded,
  onExpand,
}: ReferenceCardProps) {
  const id = (k: string) => `ref-${index}-${k}`

  const isCardInvalid = !value.source_text?.trim() || (!value.kanun_no?.trim() && !value.kanun_ad?.trim())

  if (!isExpanded) {
    const summaryParts = []
    if (value.kanun_no) summaryParts.push(`Kanun No: ${value.kanun_no}`)
    if (value.kanun_ad) summaryParts.push(value.kanun_ad)
    if (value.madde) summaryParts.push(`Md: ${value.madde}`)
    if (value.fikra) summaryParts.push(`Fık: ${value.fikra}`)
    if (value.bent) summaryParts.push(`Bnt: ${value.bent}`)

    const summaryText = summaryParts.join(' · ') || 'Yeni Boş Referans'
    const quoteSnippet = value.source_text 
      ? value.source_text.length > 45 
        ? `"${value.source_text.substring(0, 45)}..."`
        : `"${value.source_text}"`
      : 'Metinden alıntı girilmedi'

    return (
      <Card
        onClick={onExpand}
        className={cn(
          'relative overflow-hidden cursor-pointer transition-all hover:bg-secondary/15 shadow-sm border',
          isCardInvalid 
            ? 'border-destructive/30 bg-destructive/[0.01] hover:border-destructive/50' 
            : 'border-border/60 hover:border-border/80'
        )}
      >
        <span
          aria-hidden
          className={cn(
            'absolute inset-y-0 left-0 w-1',
            isCardInvalid ? 'bg-destructive/50' : 'bg-accent2/50'
          )}
        />
        <div className="flex items-center justify-between gap-3 px-3 py-2 pl-5">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span className={cn(
              'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full font-mono text-[10px] font-bold tabular-nums',
              isCardInvalid ? 'bg-destructive/10 text-destructive' : 'bg-accent2/10 text-accent2'
            )}>
              {index + 1}
            </span>
            <div className="flex flex-col min-w-0 flex-1 leading-tight">
              <span className="font-mono text-[11px] font-bold text-foreground/90 truncate">
                {summaryText}
              </span>
              <span className={cn(
                'font-serif text-[11px] italic truncate',
                isCardInvalid ? 'text-destructive/80' : 'text-muted-foreground'
              )}>
                {quoteSnippet}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {isCardInvalid && (
              <AlertCircle className="h-4 w-4 text-destructive shrink-0" aria-label="Geçersiz alanlar var" />
            )}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                onRemove()
              }}
              disabled={disabled}
              aria-label="sil"
              className="h-7 w-7 p-0 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <Card className={cn(
      'relative overflow-hidden transition-shadow hover:shadow-md border',
      isCardInvalid ? 'border-destructive/30 bg-destructive/[0.005]' : 'border-border/70'
    )}>
      <span
        aria-hidden
        className={cn(
          'absolute inset-y-0 left-0 w-1',
          isCardInvalid ? 'bg-destructive/70' : 'bg-accent2/70'
        )}
      />
      <CardContent className="space-y-5 p-5 pl-6">
        <div className="flex items-center justify-between gap-2 border-b border-border/30 pb-3">
          <button
            type="button"
            onClick={onExpand}
            className="flex items-center gap-2.5 cursor-pointer select-none group/hdr flex-1 min-w-0 text-left focus-visible:outline-none"
            title="Daraltmak için tıklayın"
          >
            <span className={cn(
              'inline-flex h-7 w-7 items-center justify-center rounded-full font-mono text-[12px] font-bold tabular-nums transition-colors',
              isCardInvalid 
                ? 'bg-destructive/15 text-destructive group-hover/hdr:bg-destructive/25' 
                : 'bg-accent2/15 text-accent2 group-hover/hdr:bg-accent2/25'
            )}>
              {index + 1}
            </span>
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground group-hover/hdr:text-foreground transition-colors truncate">
              Referans
            </span>
            <ChevronUp className="h-3.5 w-3.5 text-muted-foreground/60 group-hover/hdr:text-foreground transition-colors shrink-0" />
          </button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRemove}
            disabled={disabled}
            aria-label="sil"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <X />
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-4">
          <div className="space-y-1.5">
            <Label htmlFor={id('kanun_no')}>Kanun No</Label>
            <Input
              id={id('kanun_no')}
              value={value.kanun_no ?? ''}
              onChange={(e) => onChange(set(value, 'kanun_no', e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={id('kanun_ad')}>Kanun Adı</Label>
            <Input
              id={id('kanun_ad')}
              value={value.kanun_ad ?? ''}
              onChange={(e) => onChange(set(value, 'kanun_ad', e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={id('madde')}>Madde</Label>
            <Input
              id={id('madde')}
              value={value.madde ?? ''}
              onChange={(e) => onChange(set(value, 'madde', e.target.value))}
              onBlur={(e) => {
                const val = e.target.value
                const parsed = parseComplexMadde(val)
                if (parsed) {
                  onChange({
                    ...value,
                    madde: parsed.madde,
                    fikra: parsed.fikra || value.fikra,
                    bent: cleanBent(parsed.bent) || value.bent,
                  })
                }
              }}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={id('fikra')}>Fıkra</Label>
            <Input
              id={id('fikra')}
              value={value.fikra ?? ''}
              onChange={(e) => onChange(set(value, 'fikra', e.target.value))}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5 col-span-2">
            <Label htmlFor={id('bent')}>Bent</Label>
            <Input
              id={id('bent')}
              value={value.bent ?? ''}
              onChange={(e) => onChange(set(value, 'bent', e.target.value))}
              onBlur={(e) => {
                const cleaned = cleanBent(e.target.value)
                onChange({ ...value, bent: cleaned })
              }}
              disabled={disabled}
            />
          </div>
        </div>
        <div className={cn(
          'space-y-1.5 rounded-md border p-3',
          isCardInvalid ? 'border-destructive/20 bg-destructive/[0.02]' : 'border-accent/20 bg-accent/[0.04]'
        )}>
          <Label htmlFor={id('source')} className={cn(
            'flex items-center gap-1.5',
            isCardInvalid ? 'text-destructive' : 'text-accent'
          )}>
            <Quote aria-hidden="true" className="h-3 w-3" />
            Metinden Alıntı
          </Label>
          <Textarea
            id={id('source')}
            value={value.source_text}
            onChange={(e) => onChange({ ...value, source_text: e.target.value })}
            disabled={disabled}
            rows={3}
            required
            className={cn(
              'bg-card focus-visible:ring-1 focus-visible:ring-offset-0',
              isCardInvalid 
                ? 'border-destructive/30 focus-visible:border-destructive focus-visible:ring-destructive' 
                : 'border-accent/30 focus-visible:border-accent focus-visible:ring-accent'
            )}
          />
        </div>
      </CardContent>
    </Card>
  )
}
```

```typescript
// frontend/src/components/annotation/ReferenceCard.test.tsx (updated/appended)
it('auto-splits complex madde on blur', async () => {
  const onChange = vi.fn()
  const user = userEvent.setup()
  render(
    <ReferenceCard
      index={0}
      value={makeReferenceItem({ madde: '' })}
      onChange={onChange}
      onRemove={vi.fn()}
      disabled={false}
      isExpanded={true}
      onExpand={vi.fn()}
    />,
  )
  const input = screen.getByLabelText(/^madde$/i)
  await user.type(input, '5/1-a')
  fireEvent.blur(input)
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
    madde: '5',
    fikra: '1',
    bent: 'a',
  }))
})
```

**Verify:** `cd frontend && npm run test:run -- src/components/annotation/ReferenceCard.test.tsx`
**Commit:** `feat(ui): auto-split complex madde and clean bent on blur in ReferenceCard`
