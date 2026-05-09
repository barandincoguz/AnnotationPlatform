"""Admin force-release endpoint + SSE reason='admin_force' field."""


def test_force_release_deletes_lock(client, ingest_doc, bootstrap_admin, seen_manual_passed_user):
    admin_id = bootstrap_admin()
    other_id = seen_manual_passed_user("bursiyer1", "INVITE-2026")
    ingest_doc("doc-A")
    # bursiyer1 acquires a lock first
    r = client.post("/api/locks/doc-A/acquire")
    assert r.status_code == 200, r.text
    # Switch to admin
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})
    r = client.post("/api/locks/doc-A/admin/force-release")
    assert r.status_code == 200, r.text

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute("SELECT * FROM document_locks WHERE document_id='doc-A'").fetchone()
    assert row is None
    db.close()


def test_force_release_writes_audit(client, ingest_doc, bootstrap_admin, seen_manual_passed_user):
    admin_id = bootstrap_admin()
    user_id = seen_manual_passed_user("bursiyer1", "INVITE-2026")
    ingest_doc("doc-B")
    client.post("/api/locks/doc-B/acquire")
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    r = client.post("/api/locks/doc-B/admin/force-release")
    assert r.status_code == 200, r.text

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='lock_force_release' AND target_id='doc-B'"
    ).fetchone()
    assert row is not None
    assert row["admin_user_id"] == admin_id
    db.close()


def test_force_release_no_lock_returns_404(client, bootstrap_admin):
    bootstrap_admin()
    r = client.post("/api/locks/doc-doesnotexist/admin/force-release")
    assert r.status_code == 404


def test_force_release_publishes_lock_released_with_reason(
    client, ingest_doc, bootstrap_admin, seen_manual_passed_user,
):
    """Direct SSE event capture by patching the broker."""
    admin_id = bootstrap_admin()
    user_id = seen_manual_passed_user("bursiyer1", "INVITE-2026")
    ingest_doc("doc-C")
    client.post("/api/locks/doc-C/acquire")
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    captured = []
    from backend.shared.sse import broker as sse_broker
    orig_publish = sse_broker.publish_broadcast

    async def capture(event_type: str, data: dict):
        captured.append((event_type, data))
        await orig_publish(event_type, data)

    sse_broker.publish_broadcast = capture
    try:
        r = client.post("/api/locks/doc-C/admin/force-release")
        assert r.status_code == 200, r.text
    finally:
        sse_broker.publish_broadcast = orig_publish

    released = [(t, d) for t, d in captured if t == "lock_released"]
    assert len(released) == 1
    assert released[0][1]["reason"] == "admin_force"
    assert released[0][1]["document_id"] == "doc-C"


def test_force_release_requires_admin(client, seen_manual_passed_user):
    user_id = seen_manual_passed_user("bursiyer1", "INVITE-2026")
    # bursiyer1 is logged in (not admin)
    r = client.post("/api/locks/doc-X/admin/force-release")
    assert r.status_code == 404  # existence-hide


def test_user_release_publishes_reason_user_release(client, ingest_doc, seen_manual_passed_user):
    """Regression: existing user-driven release now carries reason='user_release'."""
    user_id = seen_manual_passed_user("bursiyer1", "INVITE-2026")
    ingest_doc("doc-D")
    client.post("/api/locks/doc-D/acquire")

    captured = []
    from backend.shared.sse import broker as sse_broker
    orig_publish = sse_broker.publish_broadcast

    async def capture(event_type, data):
        captured.append((event_type, data))
        await orig_publish(event_type, data)

    sse_broker.publish_broadcast = capture
    try:
        r = client.post("/api/locks/doc-D/release")
        assert r.status_code == 200
    finally:
        sse_broker.publish_broadcast = orig_publish

    released = [(t, d) for t, d in captured if t == "lock_released"]
    assert len(released) == 1
    assert released[0][1]["reason"] == "user_release"


def test_force_release_audit_row_carries_trace_id(
    client, ingest_doc, bootstrap_admin, seen_manual_passed_user
):
    """Group B audit-only: trace_id present on the audit row, no
    system_events follow-up. Operator can grep system_events by trace_id
    and correctly find zero rows."""
    bootstrap_admin()
    seen_manual_passed_user("bursiyer1", "INVITE-2026")
    ingest_doc("doc-trace-fr")
    # bursiyer1 is logged in after seen_manual_passed_user — acquire as them
    client.post("/api/locks/doc-trace-fr/acquire")
    # Switch to admin
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    r = client.post("/api/locks/doc-trace-fr/admin/force-release")
    assert r.status_code == 200, r.text

    from backend.shared.db import connect
    from backend import config
    db = connect(config.DB_PATH)
    try:
        row = db.execute(
            "SELECT trace_id FROM admin_audit_log "
            "WHERE action_type='lock_force_release' AND target_id=? "
            "ORDER BY id DESC LIMIT 1",
            ("doc-trace-fr",),
        ).fetchone()
        assert row is not None
        assert isinstance(row["trace_id"], str)
        assert len(row["trace_id"]) == 16

        # No system_events for this trace_id (force-release is audit-only)
        sys_rows = db.execute(
            "SELECT * FROM system_events WHERE trace_id=?", (row["trace_id"],)
        ).fetchall()
        assert len(sys_rows) == 0
    finally:
        db.close()
