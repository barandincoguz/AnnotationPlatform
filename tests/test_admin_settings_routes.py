"""HTTP tests for admin settings endpoints."""
import json

from backend.shared.db import connect
from backend import config


def _make_admin(client):
    """Register a user, promote to admin, log them in, return the user dict."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("ADMIN-INV",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": "boss", "password": "password123",
        "invite_code": "ADMIN-INV", "email": "boss@example.com",
    })
    assert r.status_code == 201
    user = r.json()
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET role='admin', has_seen_manual=1, has_passed_training=1 WHERE id=?",
            (user["id"],),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/login", json={
        "username": "boss", "password": "password123",
    })
    assert r.status_code == 200
    return user


def test_get_settings_requires_auth(client):
    r = client.get("/api/admin/settings")
    assert r.status_code == 401


def test_get_settings_non_admin_404(passed_user):
    r = passed_user["client"].get("/api/admin/settings")
    # require_admin returns 404 to hide existence (per backend/users/deps.py:52)
    assert r.status_code == 404


def test_get_settings_returns_seeded_keys(client):
    _make_admin(client)
    r = client.get("/api/admin/settings")
    assert r.status_code == 200
    data = r.json()
    # Some seeded keys present
    assert "speed_warning.window_seconds" in data
    assert data["speed_warning.window_seconds"] == 300
    assert data["char_limit.warn_threshold"] == 300
    assert data["char_limit.alert_threshold"] == 600


def test_put_settings_requires_auth(client):
    r = client.put("/api/admin/settings/speed_warning.window_seconds", json={"value": 600})
    assert r.status_code == 401


def test_put_settings_non_admin_404(passed_user):
    r = passed_user["client"].put(
        "/api/admin/settings/speed_warning.window_seconds", json={"value": 600},
    )
    assert r.status_code == 404


def test_put_unknown_key_404(client):
    _make_admin(client)
    r = client.put("/api/admin/settings/no.such.key", json={"value": 1})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_setting_key"


def test_put_persists_int_value(client):
    _make_admin(client)
    r = client.put(
        "/api/admin/settings/speed_warning.window_seconds", json={"value": 600},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["key"] == "speed_warning.window_seconds"
    assert data["value"] == 600

    # Round-trip: GET sees the new value
    r = client.get("/api/admin/settings")
    assert r.json()["speed_warning.window_seconds"] == 600


def test_put_type_mismatch_int_to_string_422(client):
    _make_admin(client)
    r = client.put(
        "/api/admin/settings/speed_warning.window_seconds", json={"value": "abc"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "type_mismatch"


def test_put_type_mismatch_int_to_dict_422(client):
    _make_admin(client)
    r = client.put(
        "/api/admin/settings/char_limit.warn_threshold",
        json={"value": {"foo": "bar"}},
    )
    assert r.status_code == 422


def test_put_type_mismatch_bool_int_either_direction(client):
    """Locks the bool-before-int ordering in _python_type_label. Without this
    test, a future reorder of the isinstance checks would silently treat
    bool as int and vice-versa (because isinstance(True, int) == True)."""
    _make_admin(client)
    # int-typed key (window_seconds=300) — PUT with bool should be rejected
    r = client.put(
        "/api/admin/settings/speed_warning.window_seconds", json={"value": True},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "type_mismatch"
    assert r.json()["detail"]["expected"] == "int"
    assert r.json()["detail"]["got"] == "bool"

    # bool-typed key (planted) — PUT with int should be rejected
    conn = connect(config.DB_PATH)
    try:
        from backend.shared import settings as S
        S.set_value(conn, "test.bool_key", True, updated_by_user_id=None)
    finally:
        conn.close()
    r = client.put("/api/admin/settings/test.bool_key", json={"value": 1})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "type_mismatch"
    assert r.json()["detail"]["expected"] == "bool"
    assert r.json()["detail"]["got"] == "int"


def test_put_audit_log_written(client):
    admin = _make_admin(client)
    r = client.put(
        "/api/admin/settings/speed_warning.window_seconds", json={"value": 1200},
    )
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT admin_user_id, action_type, target_kind, target_id, metadata_json
            FROM admin_audit_log
            WHERE action_type='settings_update'
            ORDER BY id DESC LIMIT 1
            """,
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["admin_user_id"] == admin["id"]
    assert row["target_kind"] == "setting"
    assert row["target_id"] == "speed_warning.window_seconds"
    metadata = json.loads(row["metadata_json"])
    assert metadata["old_value"] == 300
    assert metadata["new_value"] == 1200


def test_put_same_value_still_audited(client):
    """Idempotent PUT (no-op write) is still recorded in admin_audit_log so the
    audit trail captures every admin attempt, not just behaviorally distinct ones."""
    _make_admin(client)
    r = client.put(
        "/api/admin/settings/speed_warning.window_seconds", json={"value": 300},
    )
    assert r.status_code == 200
    conn = connect(config.DB_PATH)
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM admin_audit_log WHERE action_type='settings_update'"
        ).fetchone()["c"]
    finally:
        conn.close()
    assert count == 1
