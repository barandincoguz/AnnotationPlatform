"""Central browser and cache-safety headers for every HTTP response."""
from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend import config

_FRAME_ANCESTORS = "'self' https://huggingface.co" if config.SPACE_ID else "'none'"

CONTENT_SECURITY_POLICY = (
    "base-uri 'self'; "
    "object-src 'none'; "
    f"frame-ancestors {_FRAME_ANCESTORS}; "
    "form-action 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data:"
)


class SecurityHeadersMiddleware:
    """Apply defense-in-depth headers and prevent API response caching."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                if not config.SPACE_ID:
                    headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Permissions-Policy"] = (
                    "camera=(), geolocation=(), microphone=()"
                )
                headers["Cross-Origin-Opener-Policy"] = "same-origin"

                if path.startswith("/api/"):
                    headers["Cache-Control"] = "no-store"

                content_type = headers.get("content-type", "")
                if content_type.lower().startswith("text/html"):
                    headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY

            await send(message)

        await self.app(scope, receive, send_with_headers)
