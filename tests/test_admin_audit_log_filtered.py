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


def test_audit_log_filters_by_trace_id(client, bootstrap_admin, db_conn):
    """Trace ID filter returns only rows matching the trace_id."""
    bootstrap_admin()
    db_conn.execute(
        "INSERT INTO admin_audit_log(admin_user_id, action_type, target_kind, "
        "target_id, metadata_json, trace_id, created_at) "
        "VALUES (1, 'test_a', 'thing', '1', '{}', 'trace-aaa', datetime('now'))"
    )
    db_conn.execute(
        "INSERT INTO admin_audit_log(admin_user_id, action_type, target_kind, "
        "target_id, metadata_json, trace_id, created_at) "
        "VALUES (1, 'test_b', 'thing', '2', '{}', 'trace-bbb', datetime('now'))"
    )
    db_conn.commit()

    r = client.get("/api/admin/audit-log?trace_id=trace-aaa")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert all(it["trace_id"] == "trace-aaa" for it in body["items"])


def test_audit_log_returns_admin_username_via_join(client, bootstrap_admin, db_conn):
    """Audit items include admin_username via LEFT JOIN users."""
    bootstrap_admin()
    db_conn.execute(
        "INSERT INTO admin_audit_log(admin_user_id, action_type, target_kind, "
        "target_id, metadata_json, trace_id, created_at) "
        "VALUES (1, 'test_join', 'thing', '99', '{}', 'trace-join', datetime('now'))"
    )
    db_conn.commit()

    r = client.get("/api/admin/audit-log?trace_id=trace-join")
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert "admin_username" in item
    assert item["admin_username"] == "root"
    assert item["admin_user_id"] == 1


def test_audit_log_admin_username_null_when_admin_deleted(client, bootstrap_admin, db_conn):
    """admin_username is NULL when the admin_user_id no longer matches a user row."""
    bootstrap_admin()
    # Simulate an orphaned audit row whose admin_user_id no longer matches any
    # users.id. The FK is ON DELETE SET NULL but we want to assert the LEFT JOIN
    # behavior on a non-NULL but unmatched admin_user_id; disable FK locally so
    # the synthetic insert is accepted.
    db_conn.execute("PRAGMA foreign_keys=OFF")
    db_conn.execute(
        "INSERT INTO admin_audit_log(admin_user_id, action_type, target_kind, "
        "target_id, metadata_json, trace_id, created_at) "
        "VALUES (999, 'ghost', 'thing', '0', '{}', 'trace-ghost', datetime('now'))"
    )
    db_conn.commit()
    db_conn.execute("PRAGMA foreign_keys=ON")

    r = client.get("/api/admin/audit-log?trace_id=trace-ghost")
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["admin_username"] is None
    assert item["admin_user_id"] == 999


def test_audit_log_trace_id_and_action_combined(client, bootstrap_admin, db_conn):
    """trace_id and action filters AND-compose."""
    bootstrap_admin()
    db_conn.execute(
        "INSERT INTO admin_audit_log(admin_user_id, action_type, target_kind, "
        "target_id, metadata_json, trace_id, created_at) "
        "VALUES (1, 'wanted', 'thing', '1', '{}', 'trace-x', datetime('now'))"
    )
    db_conn.execute(
        "INSERT INTO admin_audit_log(admin_user_id, action_type, target_kind, "
        "target_id, metadata_json, trace_id, created_at) "
        "VALUES (1, 'unwanted', 'thing', '2', '{}', 'trace-x', datetime('now'))"
    )
    db_conn.commit()

    r = client.get("/api/admin/audit-log?trace_id=trace-x&action=wanted")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["action_type"] == "wanted"


def test_audit_log_trace_id_no_match_returns_empty(client, bootstrap_admin):
    bootstrap_admin()
    r = client.get("/api/admin/audit-log?trace_id=does-not-exist")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
