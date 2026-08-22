"""Tests for the Origin/Referer CSRF middleware.

The middleware bypasses dev/test by design (see backend/shared/csrf.py
module docstring) so the bulk of the existing TestClient suite works
without per-test header plumbing. These tests force the production code
path by monkey-patching `backend.config.is_production` to return True
and exercise the allowlist directly.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config
from backend.shared.csrf import OriginCheckMiddleware


@pytest.fixture
def app(monkeypatch):
    """Minimal FastAPI app with the middleware installed and a state-changing
    POST + a safe GET route. ENVIRONMENT is patched to production so the
    middleware enforces."""
    monkeypatch.setattr(config, "is_production", lambda: True)
    monkeypatch.setattr(
        config,
        "ALLOWED_ORIGINS",
        {
            "https://allowed.example",
            "http://localhost:5173",
            "https://barandncgz72-anotasyon-platform.hf.space",
            "https://barandncgz72-anotasyon-platform.static.hf.space",
        },
    )
    app = FastAPI()
    app.add_middleware(OriginCheckMiddleware)

    @app.get("/safe")
    def safe():
        return {"ok": True}

    @app.post("/mutate")
    def mutate():
        return {"ok": True}

    @app.post("/api/internal/predictions")
    def ingest_prediction():
        return {"ok": True}

    return app


def test_get_passes_without_origin(app):
    with TestClient(app) as c:
        r = c.get("/safe")
    assert r.status_code == 200


def test_post_without_origin_or_referer_rejected(app):
    with TestClient(app) as c:
        r = c.post("/mutate")
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "origin_not_allowed"


def test_post_with_allowed_origin_passes(app):
    with TestClient(app) as c:
        r = c.post("/mutate", headers={"Origin": "https://allowed.example"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_post_with_disallowed_origin_rejected(app):
    with TestClient(app) as c:
        r = c.post("/mutate", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "origin_not_allowed"


def test_post_with_referer_fallback_passes(app):
    with TestClient(app) as c:
        r = c.post(
            "/mutate",
            headers={"Referer": "https://allowed.example/some/path?q=1"},
        )
    assert r.status_code == 200


def test_post_with_disallowed_referer_rejected(app):
    with TestClient(app) as c:
        r = c.post(
            "/mutate",
            headers={"Referer": "https://evil.example/login"},
        )
    assert r.status_code == 403


def test_origin_preferred_over_referer(app):
    """When both headers are present, Origin wins. A disallowed Origin
    with an allowed Referer (e.g. someone trying to spoof same-origin
    via Referer) is rejected."""
    with TestClient(app) as c:
        r = c.post(
            "/mutate",
            headers={
                "Origin": "https://evil.example",
                "Referer": "https://allowed.example/dashboard",
            },
        )
    assert r.status_code == 403


def test_dev_bypass(monkeypatch):
    """In non-production environments the middleware is a no-op."""
    monkeypatch.setattr(config, "is_production", lambda: False)
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", set())
    app = FastAPI()
    app.add_middleware(OriginCheckMiddleware)

    @app.post("/mutate")
    def mutate():
        return {"ok": True}

    with TestClient(app) as c:
        r = c.post("/mutate")
    assert r.status_code == 200


def test_options_passes_without_origin(app):
    """OPTIONS preflight must always succeed regardless of headers."""
    with TestClient(app) as c:
        r = c.options("/safe")
    # FastAPI returns 405 for OPTIONS on a GET-only route, but the
    # middleware doesn't reject; that's the assertion we care about.
    assert r.status_code != 403


def test_only_exact_huggingface_origins_pass(app):
    with TestClient(app) as c:
        r1 = c.post(
            "/mutate",
            headers={
                "Origin": "https://barandncgz72-anotasyon-platform.hf.space"
            },
        )
        assert r1.status_code == 200

        r2 = c.post(
            "/mutate",
            headers={"Origin": "https://random-sub.static.hf.space"},
        )
        assert r2.status_code == 403

        r3 = c.post("/mutate", headers={"Origin": "http://sub.hf.space"})
        assert r3.status_code == 403


def test_internal_bearer_route_does_not_require_browser_origin(app):
    with TestClient(app) as c:
        r = c.post("/api/internal/predictions")
    assert r.status_code == 200


def test_wildcard_origin_does_not_disable_csrf(monkeypatch):
    monkeypatch.setattr(config, "is_production", lambda: True)
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", {"*"})
    app = FastAPI()
    app.add_middleware(OriginCheckMiddleware)

    @app.post("/mutate")
    def mutate():
        return {"ok": True}

    with TestClient(app) as c:
        r = c.post("/mutate")
    assert r.status_code == 403
