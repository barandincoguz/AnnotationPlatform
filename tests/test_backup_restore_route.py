"""Phase 5 U1: POST /api/admin/backup/restore — uploaded snapshot restore."""
import gzip
import json
from unittest.mock import patch


def test_restore_route_replaces_db_state(client, bootstrap_admin, tmp_path):
    """Happy path: a valid snapshot replaces DB state and writes an audit row."""
    bootstrap_admin()
    snapshot = {
        "__format_version": 1,
        "users": [
            {
                "id": 1,
                "username": "alice",
                "email": None,
                "password_hash": "pbkdf2_sha256$1$test$x",
                "role": "user",
                "is_active": 1,
                "has_passed_training": 1,
                "has_seen_manual": 1,
                "avatar_color": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
    }
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps(snapshot), encoding="utf-8")
    with open(snap_path, "rb") as f:
        resp = client.post(
            "/api/admin/backup/restore",
            files={"snapshot": ("snap.json", f, "application/json")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["tables"]["users"] >= 1
    assert isinstance(body["total_rows"], int)
    assert "trace_id" in body


def test_restore_route_accepts_compressed_snapshot_upload(
    client,
    bootstrap_admin,
    tmp_path,
):
    bootstrap_admin()
    snapshot = {
        "__format_version": 1,
        "users": [
            {
                "id": 1,
                "username": "compressed",
                "email": None,
                "password_hash": "pbkdf2_sha256$1$test$x",
                "role": "user",
                "is_active": 1,
                "has_passed_training": 1,
                "has_seen_manual": 1,
                "avatar_color": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
    }
    snap_path = tmp_path / "snap.json.gz"
    snap_path.write_bytes(
        gzip.compress(json.dumps(snapshot).encode("utf-8"))
    )

    with open(snap_path, "rb") as f:
        resp = client.post(
            "/api/admin/backup/restore",
            files={"snapshot": ("snap.json.gz", f, "application/gzip")},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["tables"]["users"] == 1


def test_restore_route_writes_audit_row(client, bootstrap_admin, tmp_path):
    """Successful restore writes an admin_audit_log row with action_type=backup_restore."""
    bootstrap_admin()
    snapshot = {"__format_version": 1, "users": []}
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps(snapshot), encoding="utf-8")
    with open(snap_path, "rb") as f:
        resp = client.post(
            "/api/admin/backup/restore",
            files={"snapshot": ("snap.json", f, "application/json")},
        )
    assert resp.status_code == 200, resp.text

    from backend.shared.db import connect
    from backend import config
    db = connect(config.DB_PATH)
    try:
        row = db.execute(
            "SELECT * FROM admin_audit_log WHERE action_type='backup_restore' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        # admin_user_id is stored as None post-restore (FK-safe); trace_id carries attribution
        assert row["trace_id"] == resp.json()["trace_id"]
    finally:
        db.close()


def test_restore_route_refuses_when_wal_in_use(client, bootstrap_admin, tmp_path):
    """If WAL is busy, the route returns 409 db_busy without touching restore."""
    bootstrap_admin()
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps({"__format_version": 1, "users": []}), encoding="utf-8")
    # Patch at the routes module where the name is already bound
    with patch("backend.backup.routes.is_wal_busy", return_value=True):
        with open(snap_path, "rb") as f:
            resp = client.post(
                "/api/admin/backup/restore",
                files={"snapshot": ("snap.json", f, "application/json")},
            )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "db_busy"


def test_restore_route_requires_admin(client, seen_manual_user, tmp_path):
    """Non-admin sessions are rejected with 401/403/404."""
    seen_manual_user("bursiyer1", "INVITE-2026")
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps({"__format_version": 1}), encoding="utf-8")
    with open(snap_path, "rb") as f:
        resp = client.post(
            "/api/admin/backup/restore",
            files={"snapshot": ("snap.json", f, "application/json")},
        )
    assert resp.status_code in (401, 403, 404)


def test_restore_route_rejects_oversized_upload_and_removes_temp_file(
    client,
    bootstrap_admin,
    monkeypatch,
):
    from backend import config

    bootstrap_admin()
    monkeypatch.setattr("backend.backup.routes.MAX_RESTORE_BYTES", 32)
    before = set(config.DATA_DIR.glob("*.restore.json"))

    response = client.post(
        "/api/admin/backup/restore",
        files={
            "snapshot": (
                "large.json",
                b'{"users":[],"padding":"' + b"x" * 64 + b'"}',
                "application/json",
            ),
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "restore_too_large"
    assert set(config.DATA_DIR.glob("*.restore.json")) == before


def test_restore_route_rejects_malformed_json_as_client_error(
    client,
    bootstrap_admin,
):
    bootstrap_admin()

    response = client.post(
        "/api/admin/backup/restore",
        files={"snapshot": ("broken.json", b'{"users":[', "application/json")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "restore_invalid_snapshot"
