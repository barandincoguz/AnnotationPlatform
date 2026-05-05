import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.users import service


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    # Seed an active invite code
    conn.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
        ("BURSIYER-2026",),
    )
    yield conn
    conn.close()


def test_register_creates_user_and_gamification_state(db):
    user_id = service.register(
        db, username="alice", password="password123",
        invite_code="BURSIYER-2026", email="alice@example.com",
    )
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    assert user["username"] == "alice"
    assert user["email"] == "alice@example.com"
    assert user["role"] == "user"
    assert user["is_active"] == 1
    assert user["has_seen_manual"] == 0
    assert user["has_passed_training"] == 0
    assert user["avatar_color"] is not None  # auto-assigned
    assert user["password_hash"].startswith("$2b$")

    state = db.execute(
        "SELECT * FROM gamification_state WHERE user_id=?", (user_id,)
    ).fetchone()
    assert state is not None
    assert state["total_xp"] == 0


def test_register_invalid_invite_code_raises(db):
    with pytest.raises(service.InvalidInviteCode):
        service.register(db, username="alice", password="password123",
                         invite_code="WRONG-CODE", email=None)


def test_register_inactive_invite_code_raises(db):
    db.execute("UPDATE invite_codes SET is_active=0 WHERE code=?", ("BURSIYER-2026",))
    with pytest.raises(service.InvalidInviteCode):
        service.register(db, username="alice", password="password123",
                         invite_code="BURSIYER-2026", email=None)


def test_register_duplicate_username_raises(db):
    service.register(db, username="alice", password="pw_alice99",
                     invite_code="BURSIYER-2026", email=None)
    with pytest.raises(service.UsernameTaken):
        service.register(db, username="alice", password="pw_alice22",
                         invite_code="BURSIYER-2026", email=None)


def test_register_duplicate_email_raises(db):
    service.register(db, username="alice", password="pw_alice99",
                     invite_code="BURSIYER-2026", email="shared@x.com")
    with pytest.raises(service.EmailTaken):
        service.register(db, username="bob", password="pw_bob123",
                         invite_code="BURSIYER-2026", email="shared@x.com")


def test_register_avatar_color_deterministic_from_username():
    """Same username → same color across calls."""
    color1 = service._avatar_color_for("alice")
    color2 = service._avatar_color_for("alice")
    assert color1 == color2
    color3 = service._avatar_color_for("bob")
    assert color3 != color1  # different username, likely different color


def test_register_password_too_short_raises(db):
    """Service accepts validated input — Pydantic enforces length, but service should also gate."""
    with pytest.raises(service.InvalidPassword):
        service.register(db, username="alice", password="short",
                         invite_code="BURSIYER-2026", email=None)


def test_login_correct_credentials_creates_session(db):
    uid = service.register(db, username="alice", password="password123",
                            invite_code="BURSIYER-2026", email=None)
    token = service.login(db, username="alice", password="password123",
                           ip="1.2.3.4", user_agent="curl/8.0")
    assert isinstance(token, str)
    assert len(token) >= 32

    sess = db.execute("SELECT * FROM user_sessions WHERE session_token=?", (token,)).fetchone()
    assert sess["user_id"] == uid
    assert sess["ended_at"] is None
    assert sess["ip_hash"] is not None
    assert sess["user_agent"] == "curl/8.0"


def test_login_wrong_password_raises(db):
    service.register(db, username="alice", password="password123",
                      invite_code="BURSIYER-2026", email=None)
    with pytest.raises(service.InvalidCredentials):
        service.login(db, username="alice", password="WRONG", ip="1.2.3.4")


def test_login_unknown_user_raises(db):
    with pytest.raises(service.InvalidCredentials):
        service.login(db, username="ghost", password="anything", ip="1.2.3.4")


def test_login_disabled_user_raises(db):
    uid = service.register(db, username="alice", password="password123",
                            invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET is_active=0 WHERE id=?", (uid,))
    with pytest.raises(service.UserDisabled):
        service.login(db, username="alice", password="password123", ip="1.2.3.4")


def test_logout_ends_session(db):
    service.register(db, username="alice", password="password123",
                      invite_code="BURSIYER-2026", email=None)
    token = service.login(db, username="alice", password="password123", ip="1.2.3.4")
    service.logout(db, session_token=token)
    sess = db.execute("SELECT ended_at FROM user_sessions WHERE session_token=?", (token,)).fetchone()
    assert sess["ended_at"] is not None


def test_get_user_by_session_returns_user(db):
    uid = service.register(db, username="alice", password="password123",
                            invite_code="BURSIYER-2026", email=None)
    token = service.login(db, username="alice", password="password123", ip="1.2.3.4")
    user = service.get_user_by_session(db, session_token=token)
    assert user is not None
    assert user["id"] == uid
    assert user["username"] == "alice"


def test_get_user_by_session_unknown_token_returns_none(db):
    assert service.get_user_by_session(db, session_token="bogus") is None


def test_get_user_by_session_after_logout_returns_none(db):
    service.register(db, username="alice", password="password123",
                      invite_code="BURSIYER-2026", email=None)
    token = service.login(db, username="alice", password="password123", ip="1.2.3.4")
    service.logout(db, session_token=token)
    assert service.get_user_by_session(db, session_token=token) is None


def test_promote_user_to_admin_writes_audit(db):
    admin_uid = service.register(db, username="admin1", password="admin12345",
                                  invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin_uid,))
    target_uid = service.register(db, username="alice", password="password123",
                                   invite_code="BURSIYER-2026", email=None)

    service.promote_admin(db, admin_user_id=admin_uid, target_user_id=target_uid)

    user = db.execute("SELECT role FROM users WHERE id=?", (target_uid,)).fetchone()
    assert user["role"] == "admin"

    audit_row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='promote_admin'"
    ).fetchone()
    assert audit_row is not None
    assert audit_row["admin_user_id"] == admin_uid
    assert audit_row["target_id"] == str(target_uid)


def test_demote_admin_to_user(db):
    admin1 = service.register(db, username="admin1", password="adminpass1",
                               invite_code="BURSIYER-2026", email=None)
    admin2 = service.register(db, username="admin2", password="adminpass2",
                               invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id IN (?,?)", (admin1, admin2))

    service.demote_admin(db, admin_user_id=admin1, target_user_id=admin2)

    user = db.execute("SELECT role FROM users WHERE id=?", (admin2,)).fetchone()
    assert user["role"] == "user"


def test_demote_last_admin_raises(db):
    admin_uid = service.register(db, username="admin1", password="adminpass1",
                                  invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin_uid,))

    with pytest.raises(service.LastAdminCannotBeRemoved):
        service.demote_admin(db, admin_user_id=admin_uid, target_user_id=admin_uid)


def test_disable_user_sets_inactive(db):
    admin = service.register(db, username="admin1", password="adminpass1",
                              invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin,))
    target = service.register(db, username="alice", password="password123",
                               invite_code="BURSIYER-2026", email=None)

    service.disable_user(db, admin_user_id=admin, target_user_id=target)

    row = db.execute("SELECT is_active FROM users WHERE id=?", (target,)).fetchone()
    assert row["is_active"] == 0


def test_disable_last_admin_raises(db):
    admin = service.register(db, username="admin1", password="adminpass1",
                              invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin,))
    with pytest.raises(service.LastAdminCannotBeRemoved):
        service.disable_user(db, admin_user_id=admin, target_user_id=admin)


def test_enable_user_restores_active(db):
    admin = service.register(db, username="admin1", password="adminpass1",
                              invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin,))
    target = service.register(db, username="alice", password="password123",
                               invite_code="BURSIYER-2026", email=None)
    service.disable_user(db, admin_user_id=admin, target_user_id=target)
    service.enable_user(db, admin_user_id=admin, target_user_id=target)
    row = db.execute("SELECT is_active FROM users WHERE id=?", (target,)).fetchone()
    assert row["is_active"] == 1


def test_rotate_invite_code_deactivates_old_and_creates_new(db):
    admin = service.register(db, username="admin1", password="adminpass1",
                              invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id=?", (admin,))

    new_code = service.rotate_invite_code(db, admin_user_id=admin, new_code="NEW-2026")

    assert new_code == "NEW-2026"
    rows = db.execute(
        "SELECT code, is_active FROM invite_codes ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["code"] == "BURSIYER-2026"
    assert rows[0]["is_active"] == 0
    assert rows[1]["code"] == "NEW-2026"
    assert rows[1]["is_active"] == 1


def test_count_active_admins(db):
    a1 = service.register(db, username="admin1", password="adminpass1",
                          invite_code="BURSIYER-2026", email=None)
    a2 = service.register(db, username="admin2", password="adminpass2",
                          invite_code="BURSIYER-2026", email=None)
    db.execute("UPDATE users SET role='admin' WHERE id IN (?,?)", (a1, a2))
    assert service.count_active_admins(db) == 2
    db.execute("UPDATE users SET is_active=0 WHERE id=?", (a1,))
    assert service.count_active_admins(db) == 1
