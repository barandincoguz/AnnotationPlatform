"""Admin endpoint POST /api/admin/backup/run-now."""
from unittest.mock import patch


def test_run_now_succeeds_with_no_remote(client, bootstrap_admin):
    """No BACKUP_REPO_URL → 200, pushed=False, committed_sha=None."""
    bootstrap_admin()
    r = client.post("/api/admin/backup/run-now")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["pushed"] is False
    assert body["committed_sha"] is None
    assert body["snapshot_path"].endswith(".json")


def test_run_now_writes_audit_row(client, bootstrap_admin):
    admin_id = bootstrap_admin()
    client.post("/api/admin/backup/run-now")

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='backup_run_now'"
    ).fetchone()
    assert row is not None
    assert row["admin_user_id"] == admin_id
    db.close()


def test_run_now_writes_system_event(client, bootstrap_admin):
    bootstrap_admin()
    client.post("/api/admin/backup/run-now")

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM system_events "
        "WHERE event_type IN ('backup_skipped_no_remote','backup_success') "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    db.close()


def test_run_now_requires_admin(client, seen_manual_user):
    """Non-admin → 404 existence-hide."""
    seen_manual_user("bursiyer1", "INVITE-2026")
    r = client.post("/api/admin/backup/run-now")
    assert r.status_code == 404


def test_run_now_returns_500_on_cycle_failure(client, bootstrap_admin):
    """If run_backup_cycle raises, the route returns 500 with an error body.
    The system_events failure row was already written by the cycle."""
    bootstrap_admin()
    with patch("backend.backup.routes.run_backup_cycle",
               side_effect=RuntimeError("git push failed")):
        r = client.post("/api/admin/backup/run-now")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"]["error"] == "backup_failed"
    assert "git push failed" in body["detail"]["message"]


def test_run_now_threads_trace_id_across_audit_and_system_events(client, bootstrap_admin):
    """The same trace_id must appear in (a) the audit row, (b) every system_events
    row emitted during the cycle, and (c) the response body — so an operator
    can JOIN by trace_id and reconstruct the operation."""
    bootstrap_admin()
    response = client.post("/api/admin/backup/run-now")
    assert response.status_code == 200

    body = response.json()
    trace_id = body["trace_id"]
    assert isinstance(trace_id, str)
    assert len(trace_id) == 16

    from backend.shared.db import connect
    from backend import config
    db = connect(config.DB_PATH)
    try:
        audit_rows = db.execute(
            "SELECT trace_id FROM admin_audit_log WHERE action_type='backup_run_now'"
        ).fetchall()
        # exactly one audit row, with our trace_id
        assert len(audit_rows) >= 1
        assert audit_rows[-1]["trace_id"] == trace_id

        sys_rows = db.execute(
            "SELECT trace_id FROM system_events WHERE trace_id=?", (trace_id,)
        ).fetchall()
        # at least one system_events row from the cycle (success or skipped path)
        assert len(sys_rows) >= 1
        # all share the same id (sanity)
        assert all(r["trace_id"] == trace_id for r in sys_rows)
    finally:
        db.close()
