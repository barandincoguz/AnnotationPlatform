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
