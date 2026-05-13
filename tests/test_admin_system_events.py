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


def test_system_events_filters_by_trace_id(client, bootstrap_admin, db_conn):
    bootstrap_admin()
    db_conn.execute(
        "INSERT INTO system_events(event_type, severity, message, extra_json, "
        "trace_id, created_at) "
        "VALUES ('ev_a', 'info', 'msg-a', '{}', 'sys-trace-1', datetime('now'))"
    )
    db_conn.execute(
        "INSERT INTO system_events(event_type, severity, message, extra_json, "
        "trace_id, created_at) "
        "VALUES ('ev_b', 'info', 'msg-b', '{}', 'sys-trace-2', datetime('now'))"
    )
    db_conn.commit()

    r = client.get("/api/admin/system-events?trace_id=sys-trace-1")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["trace_id"] == "sys-trace-1"


def test_system_events_returns_trace_id_in_items(client, bootstrap_admin, db_conn):
    bootstrap_admin()
    db_conn.execute(
        "INSERT INTO system_events(event_type, severity, message, extra_json, "
        "trace_id, created_at) "
        "VALUES ('ev_present', 'info', 'with', '{}', 'sys-present', datetime('now'))"
    )
    db_conn.execute(
        "INSERT INTO system_events(event_type, severity, message, extra_json, "
        "trace_id, created_at) "
        "VALUES ('ev_null', 'info', 'without', '{}', NULL, datetime('now'))"
    )
    db_conn.commit()

    r = client.get("/api/admin/system-events?limit=200")
    items = r.json()["items"]
    by_type = {it["event_type"]: it for it in items}
    assert by_type["ev_present"]["trace_id"] == "sys-present"
    assert by_type["ev_null"]["trace_id"] is None


def test_system_events_trace_id_and_event_type_combined(client, bootstrap_admin, db_conn):
    bootstrap_admin()
    db_conn.execute(
        "INSERT INTO system_events(event_type, severity, message, extra_json, "
        "trace_id, created_at) "
        "VALUES ('wanted', 'info', '1', '{}', 't', datetime('now'))"
    )
    db_conn.execute(
        "INSERT INTO system_events(event_type, severity, message, extra_json, "
        "trace_id, created_at) "
        "VALUES ('other', 'info', '2', '{}', 't', datetime('now'))"
    )
    db_conn.commit()

    r = client.get("/api/admin/system-events?trace_id=t&event_type=wanted")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["event_type"] == "wanted"
