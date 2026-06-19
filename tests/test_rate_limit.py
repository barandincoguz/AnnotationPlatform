"""Tests for backend/shared/rate_limit.py and its wiring into
/api/auth/login and /api/auth/register.

Covers:
  - sliding-window allows N hits then 429
  - window slides correctly (monkeypatch time.monotonic)
  - different IPs have independent buckets
  - register and login limits are independent (different namespaces)
  - 429 response carries Retry-After header
"""
from __future__ import annotations

import time

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from backend.shared.rate_limit import rate_limit, reset_for_tests


@pytest.fixture(autouse=True)
def _reset():
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.fixture
def app():
    app = FastAPI()
    throttle_a = rate_limit(namespace="ns_a", max_hits=3, window_seconds=60)
    throttle_b = rate_limit(namespace="ns_b", max_hits=3, window_seconds=60)

    @app.post("/a")
    def a(_: None = Depends(throttle_a)):
        return {"ok": "a"}

    @app.post("/b")
    def b(_: None = Depends(throttle_b)):
        return {"ok": "b"}

    @app.post("/keyed")
    def keyed(
        request: Request,
        _: None = Depends(
            rate_limit(
                namespace="ns_keyed",
                max_hits=2,
                window_seconds=60,
                key_fn=lambda r: r.headers.get("x-test-key", "default"),
            )
        ),
    ):
        return {"ok": "keyed"}

    return app


def test_allows_under_limit(app):
    with TestClient(app) as c:
        for _ in range(3):
            assert c.post("/a").status_code == 200


def test_rejects_over_limit_with_429(app):
    with TestClient(app) as c:
        for _ in range(3):
            assert c.post("/a").status_code == 200
        r = c.post("/a")
        assert r.status_code == 429
        assert r.json()["detail"]["error"] == "rate_limited"
        assert "Retry-After" in r.headers
        # Retry-After is an integer second count.
        assert int(r.headers["Retry-After"]) > 0


def test_window_slides(app, monkeypatch):
    # Drive monotonic time forwards so the deque evicts stale entries.
    fake_time = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])
    with TestClient(app) as c:
        for _ in range(3):
            assert c.post("/a").status_code == 200
        assert c.post("/a").status_code == 429
        # Jump beyond the 60s window — the bucket must drain.
        fake_time[0] += 61
        assert c.post("/a").status_code == 200


def test_namespaces_are_independent(app):
    with TestClient(app) as c:
        for _ in range(3):
            assert c.post("/a").status_code == 200
        assert c.post("/a").status_code == 429
        # /b is a different namespace and should still allow its own quota.
        for _ in range(3):
            assert c.post("/b").status_code == 200


def test_keys_are_independent(app):
    with TestClient(app) as c:
        for _ in range(2):
            assert c.post("/keyed", headers={"x-test-key": "alpha"}).status_code == 200
        # alpha exhausted
        assert c.post("/keyed", headers={"x-test-key": "alpha"}).status_code == 429
        # beta untouched
        for _ in range(2):
            assert c.post("/keyed", headers={"x-test-key": "beta"}).status_code == 200


def test_login_route_throttled(client):
    """Eleven rapid failed-login POSTs from the same IP — the eleventh
    returns 429 with Retry-After."""
    for _ in range(10):
        r = client.post(
            "/api/auth/login",
            json={"username": "ghost", "password": "wrongwrong"},
        )
        # First 10 either succeed (200) or get 401/422; what matters is
        # that they are NOT rate-limited.
        assert r.status_code != 429, f"unexpected 429 on hit {_}: {r.text}"
    final = client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": "wrongwrong"},
    )
    assert final.status_code == 429
    assert "Retry-After" in final.headers


def test_successful_logins_do_not_consume_failure_budget(client, bootstrap_admin):
    bootstrap_admin(username="admin", password="admin123")
    for _ in range(15):
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert response.status_code == 200

    for attempt in range(10):
        response = client.post(
            "/api/auth/login",
            json={"username": "ghost", "password": "wrongwrong"},
        )
        assert response.status_code == 401, f"failure {attempt} unexpectedly throttled"

    response = client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": "wrongwrong"},
    )
    assert response.status_code == 429


def test_register_route_throttled(client):
    """Six register attempts in quick succession — the sixth is throttled."""
    for i in range(5):
        client.post(
            "/api/auth/register",
            json={
                "username": f"newuser{i}",
                "password": "abcdefgh",
                "invite_code": "WRONG",
            },
        )
    r = client.post(
        "/api/auth/register",
        json={
            "username": "newuser-extra",
            "password": "abcdefgh",
            "invite_code": "WRONG",
        },
    )
    assert r.status_code == 429
