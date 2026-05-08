"""GET /api/admin/system-events — pagination + filters."""
from datetime import datetime, timezone


def _seed_event(event_type: str, severity: str = "info", message: str = "test"):
    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    db.execute(
        "INSERT INTO system_events(event_type, severity, message, created_at) "
        "VALUES (?, ?, ?, ?)",
        (event_type, severity, message, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    db.close()


def test_system_events_returns_paginated_shape(client, bootstrap_admin):
    bootstrap_admin()
    for i in range(5):
        _seed_event(f"event_{i}", "info")

    r = client.get("/api/admin/system-events")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "has_more" in body


def test_filter_by_event_type(client, bootstrap_admin):
    bootstrap_admin()
    _seed_event("training_pass", "info")
    _seed_event("lock_force_release", "warn")

    r = client.get("/api/admin/system-events?event_type=training_pass")
    body = r.json()
    assert all(item["event_type"] == "training_pass" for item in body["items"])


def test_filter_by_severity(client, bootstrap_admin):
    bootstrap_admin()
    _seed_event("ev_a", "info")
    _seed_event("ev_b", "warn")
    _seed_event("ev_c", "error")

    r = client.get("/api/admin/system-events?severity=error")
    body = r.json()
    assert all(item["severity"] == "error" for item in body["items"])


def test_default_limit_50(client, bootstrap_admin):
    bootstrap_admin()
    for i in range(60):
        _seed_event(f"e_{i}")

    r = client.get("/api/admin/system-events")
    body = r.json()
    assert len(body["items"]) == 50
    assert body["has_more"] is True


def test_invalid_date_returns_422(client, bootstrap_admin):
    bootstrap_admin()
    r = client.get("/api/admin/system-events?date_from=not-a-date")
    assert r.status_code == 422
    r = client.get("/api/admin/system-events?date_to=2026/05/08")
    assert r.status_code == 422


def test_system_events_requires_admin(client, bootstrap_admin):
    # Bootstrap admin to seed invite, then logout and register as non-admin.
    bootstrap_admin()
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    r = client.get("/api/admin/system-events")
    assert r.status_code == 404  # spec hides existence for non-admin
