"""ASGI request-body limit enforced before FastAPI parses JSON payloads."""

from __future__ import annotations

import json
from collections.abc import Mapping

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _BodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        path_max_bytes: Mapping[str, int] | None = None,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if any(limit <= 0 for limit in (path_max_bytes or {}).values()):
            raise ValueError("path limits must be positive")
        self.app = app
        self.max_bytes = max_bytes
        self.path_max_bytes = dict(path_max_bytes or {})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = self.path_max_bytes.get(str(scope.get("path", "")), self.max_bytes)
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        raw_length = headers.get("content-length")
        if raw_length is not None:
            try:
                if int(raw_length) > max_bytes:
                    await _reject(send, max_bytes)
                    return
            except ValueError:
                pass

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            await _reject(send, max_bytes)


async def _reject(send: Send, max_bytes: int) -> None:
    body = json.dumps(
        {
            "detail": {
                "error": "request_body_too_large",
                "max_bytes": max_bytes,
            }
        }
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
