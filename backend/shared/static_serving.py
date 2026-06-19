"""Production-safe static asset and response middleware helpers."""

from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
REVALIDATE_CACHE_CONTROL = "no-cache"


class ImmutableStaticFiles(StaticFiles):
    """Serve Vite's content-hashed assets with a long immutable cache."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = IMMUTABLE_CACHE_CONTROL
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def revalidating_file_response(path: Path) -> FileResponse:
    """Serve a non-hashed public file without allowing stale deploy state."""

    return FileResponse(
        path,
        headers={
            "Cache-Control": REVALIDATE_CACHE_CONTROL,
            "X-Content-Type-Options": "nosniff",
        },
    )


class SelectiveGZipMiddleware:
    """Compress regular HTTP responses while leaving SSE unbuffered."""

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        compresslevel: int = 6,
    ) -> None:
        self.app = app
        self.gzip = GZipMiddleware(
            app,
            minimum_size=minimum_size,
            compresslevel=compresslevel,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") != "/api/events":
            await self.gzip(scope, receive, send)
            return
        await self.app(scope, receive, send)
