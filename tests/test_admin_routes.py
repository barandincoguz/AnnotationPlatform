def test_admin_can_list_users(client, bootstrap_admin):
    bootstrap_admin()
    r = client.get("/api/admin/users")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1


def test_non_admin_gets_404_on_admin_routes(client, bootstrap_admin):
    bootstrap_admin()
    # Logout, register new normal user
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    r = client.get("/api/admin/users")
    assert r.status_code == 404  # spec hides existence


def test_admin_promotes_user(client, bootstrap_admin):
    bootstrap_admin()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "BURSIYER-2026",
    })
    # Find alice's id
    r = client.get("/api/admin/users")
    alice = next(u for u in r.json()["users"] if u["username"] == "alice")
    promote = client.post(f"/api/admin/users/{alice['id']}/promote")
    assert promote.status_code == 200
    r2 = client.get("/api/admin/users")
    alice2 = next(u for u in r2.json()["users"] if u["username"] == "alice")
    assert alice2["role"] == "admin"


def test_admin_cannot_demote_last_admin(client, bootstrap_admin):
    bootstrap_admin()
    r = client.get("/api/admin/users")
    me = next(u for u in r.json()["users"] if u["username"] == "root")
    demote = client.post(f"/api/admin/users/{me['id']}/demote")
    # Polish-phase M2: state-invariant rejection now returns 409 with a
    # `last_admin_protection` error code, matching the project's
    # `{error, message}` shape.
    assert demote.status_code == 409
    assert demote.json()["detail"]["error"] == "last_admin_protection"


def test_admin_disable_user(client, bootstrap_admin):
    bootstrap_admin()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "BURSIYER-2026",
    })
    r = client.get("/api/admin/users")
    alice = next(u for u in r.json()["users"] if u["username"] == "alice")
    dis = client.post(f"/api/admin/users/{alice['id']}/disable")
    assert dis.status_code == 200


def test_admin_rotate_invite_code(client, bootstrap_admin):
    bootstrap_admin()
    r = client.post("/api/admin/invite/rotate", json={"new_code": "NEW-CODE-2026"})
    assert r.status_code == 200
    body = r.json()
    assert body["new_code"] == "NEW-CODE-2026"


def test_admin_audit_log_endpoint_returns_actions(client, bootstrap_admin):
    bootstrap_admin()
    # The new RotateInviteRequest validator enforces an 8-char minimum
    # (security: rotating to a short code makes registration trivially
    # guessable). The original "X-2026" failed the validator silently,
    # producing zero audit rows.
    client.post("/api/admin/invite/rotate", json={"new_code": "XPSTRY26"})
    r = client.get("/api/admin/audit-log")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "has_more" in body
    assert any(e["action_type"] == "rotate_invite_code" for e in body["items"])


def test_user_admin_actions_carry_trace_id(client, bootstrap_admin):
    """Group B audit-only: trace_id populated on audit row for ALL 5 user admin actions.
    Each action is asserted to succeed (200) so every plumbing path is exercised — a
    regression in any one of the 5 service.<fn>(..., trace_id=...) propagations would
    fail this test rather than silently skip an unverified branch."""
    bootstrap_admin()
    # Register a target user
    client.post("/api/auth/register", json={
        "username": "trace_target", "password": "password123", "invite_code": "BURSIYER-2026",
    })
    r = client.get("/api/admin/users")
    target = next(u for u in r.json()["users"] if u["username"] == "trace_target")
    target_id = target["id"]

    # 1. Promote — fresh non-admin target → must 200
    r = client.post(f"/api/admin/users/{target_id}/promote")
    assert r.status_code == 200, r.text
    # 2. Demote — now 2 admins (root + trace_target), so last-admin guardrail is OK
    r = client.post(f"/api/admin/users/{target_id}/demote")
    assert r.status_code == 200, r.text
    # 3. Disable — trace_target is now a regular user
    r = client.post(f"/api/admin/users/{target_id}/disable")
    assert r.status_code == 200, r.text
    # 4. Enable
    r = client.post(f"/api/admin/users/{target_id}/enable")
    assert r.status_code == 200, r.text
    # 5. Rotate invite
    r = client.post("/api/admin/invite/rotate", json={"new_code": "TRACE-TEST-T5A"})
    assert r.status_code == 200, r.text

    from backend.shared.db import connect
    from backend import config
    db = connect(config.DB_PATH)
    try:
        # Assert each of the 5 action types produced a row with a 16-char trace_id —
        # a regression in any single service-level propagation would now fail with
        # an action-specific message rather than passing on a 4-of-5 partial.
        for action_type in (
            "promote_admin", "demote_admin",
            "disable_user", "enable_user",
            "rotate_invite_code",
        ):
            row = db.execute(
                "SELECT trace_id FROM admin_audit_log "
                "WHERE action_type=? ORDER BY id DESC LIMIT 1",
                (action_type,),
            ).fetchone()
            assert row is not None, f"no audit row for {action_type}"
            assert isinstance(row["trace_id"], str), (
                f"{action_type} has trace_id={row['trace_id']!r}"
            )
            assert len(row["trace_id"]) == 16, (
                f"{action_type} trace_id len={len(row['trace_id'])}"
            )
    finally:
        db.close()


def test_bootstrap_admin_fixture_is_idempotent(client, bootstrap_admin):
    """The fixture uses INSERT OR IGNORE on the BURSIYER-2026 invite code so
    it can be called multiple times in a single test (e.g. to seed two admins)
    without IntegrityError on the second insert. Without OR IGNORE, the second
    call would crash before the second register, masking real test failures."""
    admin1 = bootstrap_admin(username="root1", password="rootpass1")
    admin2 = bootstrap_admin(username="root2", password="rootpass2")
    assert admin1 != admin2
    # Sanity-check both admins exist
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT username, role FROM users WHERE id IN (?, ?)",
            (admin1, admin2),
        ).fetchall()
    finally:
        conn.close()
    assert {r["username"] for r in rows} == {"root1", "root2"}
    assert all(r["role"] == "admin" for r in rows)
