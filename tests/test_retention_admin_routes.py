"""Tests for backend/retention/routes.py — admin retention HTTP endpoints."""
import json

import pytest


def test_run_now_admin_only(client, passed_user):
    """A non-admin gets 404 (require_admin existence-hide pattern, not
    401, because revealing 'admin endpoint exists' to non-admins is the
    threat model we're guarding against)."""
    r = client.post("/api/admin/retention/run-now")
    assert r.status_code == 404


def test_run_now_returns_purged_counts(client, bootstrap_admin):
    """Admin sees {ok, purged: {table: count}, total} on success."""
    bootstrap_admin()
    r = client.post("/api/admin/retention/run-now")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "purged" in body
    assert "total" in body
    # All six policy tables present in purged dict (kill-switched ones are 0).
    assert set(body["purged"].keys()) == {
        "behavioral_events", "activity_events", "system_events",
        "user_sessions", "notifications", "drafts",
    }


def test_run_now_writes_admin_audit_log_row(client, bootstrap_admin):
    """admin_audit_log captures the manual trigger."""
    bootstrap_admin()
    client.post("/api/admin/retention/run-now")

    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        row = conn.execute(
            "SELECT action_type, target_kind, metadata_json FROM admin_audit_log "
            "WHERE action_type='retention_run_now' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["target_kind"] == "retention"
    meta = json.loads(row["metadata_json"])
    assert "total" in meta
    assert "by_table" in meta


def test_run_now_returns_500_on_internal_failure(client, bootstrap_admin, monkeypatch):
    """If run_purge raises, return 500 with structured error detail."""
    bootstrap_admin()
    from backend.retention import routes as retention_routes
    monkeypatch.setattr(
        retention_routes, "run_purge",
        lambda db: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    r = client.post("/api/admin/retention/run-now")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"]["error"] == "retention_failed"
    assert "boom" in body["detail"]["message"]


def test_preview_admin_only(client, passed_user):
    """Same existence-hide as run-now: non-admin gets 404, not 401."""
    r = client.get("/api/admin/retention/preview")
    assert r.status_code == 404


def test_preview_returns_dry_run_counts(client, bootstrap_admin):
    """Preview returns rows_to_purge, total, policy without modifying DB."""
    bootstrap_admin()
    r = client.get("/api/admin/retention/preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rows_to_purge" in body
    assert "total" in body
    assert "policy" in body
    assert isinstance(body["policy"], list)
    assert len(body["policy"]) == 6  # all six tables represented
    for p in body["policy"]:
        assert {"table", "days", "cutoff_iso"} <= set(p.keys())
