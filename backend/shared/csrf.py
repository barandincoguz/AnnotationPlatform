"""Origin/Referer middleware — CSRF defense for state-changing requests.

Why this exists:
    Session auth lives in a `SameSite=Lax` cookie. SameSite=Lax still sends
    the cookie on top-level navigations (e.g. attacker page submits a
    `<form method=POST>` to our admin endpoint), so a logged-in admin
    visiting any malicious page can be forced to perform privileged
    actions like rotating the invite code or promoting users — every
    admin POST route accepts a path-only payload (no body schema), making
    them ideal CSRF targets.

What it does:
    Rejects POST/PUT/PATCH/DELETE requests whose Origin (or Referer
    fallback) is not in `config.ALLOWED_ORIGINS`. GET/HEAD/OPTIONS pass
    through. The middleware sits before the routers so every router is
    protected without per-route opt-in.

Production-only by design:
    Dev (`ENVIRONMENT=development`) and tests (`ENVIRONMENT=test`)
    bypass the check. The TestClient does not set Origin, and adding it
    to every existing test would be noisy. Dedicated tests in
    `tests/test_csrf_middleware.py` exercise the production path
    directly by monkey-patching ENVIRONMENT.

Operator setup:
    Set `ALLOWED_ORIGINS` to a comma-separated allowlist of full origins
    (scheme + host + port). Example:
        ALLOWED_ORIGINS=https://anotasyon.example.com
"""
from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

from starlette.types import ASGIApp, Receive, Scope, Send

from backend import config

log = logging.getLogger(__name__)


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class OriginCheckMiddleware:
    """ASGI middleware. See module docstring for rationale."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Bypass in dev/test so the existing test suite and `npm run dev`
        # work unchanged. Production must set ALLOWED_ORIGINS.
        if not config.is_production():
            await self.app(scope, receive, send)
            return

        # Service-to-service routes authenticate with a bearer token and do
        # not consume the browser session cookie, so CSRF does not apply.
        if str(scope.get("path", "")).startswith("/api/internal/"):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        if method in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        # Headers in ASGI are tuple(bytes, bytes). Decode once.
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

        is_allowed = False
        if source:
            is_allowed = source in config.ALLOWED_ORIGINS

        if not is_allowed:
            log.warning(
                "CSRF check failed: source %s is not in ALLOWED_ORIGINS %s",
                source,
                config.ALLOWED_ORIGINS,
            )
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
