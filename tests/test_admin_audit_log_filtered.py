"""Audit-log endpoint with pagination + filters."""
from datetime import datetime, timedelta, timezone


def test_audit_log_returns_paginated_shape(client, bootstrap_admin):
    bootstrap_admin()
    # Create some audit entries
    for i in range(5):
        client.post("/api/admin/invite/rotate", json={"new_code": f"CODE-{i}-2026"})

    r = client.get("/api/admin/audit-log")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "has_more" in body
    assert isinstance(body["items"], list)
    assert isinstance(body["total"], int)
    assert isinstance(body["has_more"], bool)


def test_audit_log_default_limit_50(client, bootstrap_admin):
    bootstrap_admin()
    for i in range(60):
        client.post("/api/admin/invite/rotate", json={"new_code": f"CODE-{i}-2026"})

    r = client.get("/api/admin/audit-log")
    body = r.json()
    assert len(body["items"]) == 50
    assert body["has_more"] is True


def test_audit_log_offset_and_limit(client, bootstrap_admin):
    bootstrap_admin()
    for i in range(10):
        client.post("/api/admin/invite/rotate", json={"new_code": f"CODE-{i}-2026"})

    r = client.get("/api/admin/audit-log?limit=3&offset=2")
    body = r.json()
    assert len(body["items"]) == 3
    assert body["total"] >= 10
    assert body["has_more"] is True


def test_audit_log_max_limit_returns_422(client, bootstrap_admin):
    """limit > 200 should return 422 from FastAPI Query(le=200) validation."""
    bootstrap_admin()
    r = client.get("/api/admin/audit-log?limit=999")
    assert r.status_code == 422


def test_audit_log_filter_by_action(client, bootstrap_admin):
    bootstrap_admin()
    client.post("/api/admin/invite/rotate", json={"new_code": "CODE-A-2026"})

    r = client.get("/api/admin/audit-log?action=rotate_invite_code")
    body = r.json()
    assert all(item["action_type"] == "rotate_invite_code" for item in body["items"])


def test_audit_log_filter_by_admin_id(client, bootstrap_admin):
    admin_id = bootstrap_admin()
    client.post("/api/admin/invite/rotate", json={"new_code": "CODE-A-2026"})

    r = client.get(f"/api/admin/audit-log?admin_id={admin_id}")
    body = r.json()
    assert all(item["admin_user_id"] == admin_id for item in body["items"])


def test_audit_log_filter_date_range(client, bootstrap_admin):
    bootstrap_admin()
    client.post("/api/admin/invite/rotate", json={"new_code": "TODAY-1-2026"})

    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()

    r = client.get(f"/api/admin/audit-log?date_from={yesterday}&date_to={tomorrow}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1


def test_audit_log_invalid_date_returns_422(client, bootstrap_admin):
    """Malformed date_from should be rejected with 422, not silently return
    an empty result set."""
    bootstrap_admin()
    r = client.get("/api/admin/audit-log?date_from=not-a-date")
    assert r.status_code == 422

    r = client.get("/api/admin/audit-log?date_to=2026/05/08")  # wrong separator
    assert r.status_code == 422

    r = client.get("/api/admin/audit-log?date_from=2026-5-8")  # missing zero pad
    assert r.status_code == 422

    # Valid date formats still work
    r = client.get("/api/admin/audit-log?date_from=2026-05-08")
    assert r.status_code == 200


def test_audit_log_requires_admin(client, bootstrap_admin):
    # Bootstrap admin to seed invite, then logout and register as non-admin.
    bootstrap_admin()
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    r = client.get("/api/admin/audit-log")
    assert r.status_code == 404  # spec hides existence for non-admin
