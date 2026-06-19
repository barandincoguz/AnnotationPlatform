from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.testclient import TestClient

from backend.shared.security_headers import (
    CONTENT_SECURITY_POLICY,
    SecurityHeadersMiddleware,
)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/api/private")
    def private():
        return JSONResponse(
            {"secret": True},
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.get("/login")
    def login():
        return HTMLResponse("<main>login</main>")

    return app


def test_api_responses_are_never_cacheable():
    response = TestClient(_app()).get("/api/private")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == (
        "camera=(), geolocation=(), microphone=()"
    )
    assert response.headers["cross-origin-opener-policy"] == "same-origin"


def test_html_responses_receive_content_security_policy():
    response = TestClient(_app()).get("/login")

    assert response.status_code == 200
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "cache-control" not in response.headers
