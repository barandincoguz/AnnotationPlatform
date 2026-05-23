"""Phase 5 BE-5 + BE-6: users/service.py multi-step mutations must be transactional.

BE-5: demote_admin() and disable_user() check count_active_admins() then UPDATE
      in two separate autocommit statements — concurrent demotions of different
      admins when exactly two admins remain can both pass the guard.

BE-6: rotate_invite_code() deactivates all codes then inserts a new one across
      two separate statements — a registration request in the gap sees no valid
      invite code.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.users import service as users_service


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_db(tmp_path: Path):
    """Single migrated connection to an on-disk test DB (used for structural tests)."""
    db_path = tmp_path / "users_test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


@pytest.fixture
def two_dbs(tmp_path: Path):
    """Two independent connections to the SAME on-disk DB — simulates two request threads."""
    db_path = tmp_path / "users_race.db"

    conn_a = connect(db_path)
    apply_migrations(conn_a, discover_migrations())

    conn_b = connect(db_path)

    yield conn_a, conn_b

    conn_a.close()
    conn_b.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = "2026-01-01T00:00:00+00:00"


def _seed_admin(conn, user_id: int, username: str) -> None:
    """Insert an active admin user row directly (no invite needed)."""
    conn.execute(
        "INSERT INTO users(id, username, email, password_hash, role, is_active, "
        "avatar_color, created_at, updated_at) "
        "VALUES (?, ?, NULL, '$2b$12$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', "
        "'admin', 1, '#3b82f6', ?, ?)",
        (user_id, username, _NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO gamification_state(user_id, updated_at) VALUES (?, ?)",
        (user_id, _NOW),
    )


# ---------------------------------------------------------------------------
# BE-5: demote_admin — concurrent race
# ---------------------------------------------------------------------------


def test_concurrent_demote_admin_preserves_at_least_one_admin(tmp_path):
    """BE-5: two concurrent demotions of different admins when exactly two
    admins remain must NOT both succeed. The second must raise
    LastAdminCannotBeRemoved and exactly one active admin must survive."""
    db_path = tmp_path / "demote_race.db"

    # Bootstrap the schema and seed two admins using one connection.
    setup = connect(db_path)
    apply_migrations(setup, discover_migrations())
    _seed_admin(setup, 1, "admin_a")
    _seed_admin(setup, 2, "admin_b")
    setup.close()

    errors: list[tuple[int, Exception]] = []
    barrier = threading.Barrier(2)

    def worker(uid: int, other_uid: int) -> None:
        conn = connect(db_path)
        try:
            barrier.wait()
            # admin demotes the other admin
            users_service.demote_admin(conn, admin_user_id=uid, target_user_id=other_uid)
        except Exception as exc:
            errors.append((uid, exc))
        finally:
            conn.close()

    t1 = threading.Thread(target=worker, args=(1, 2))
    t2 = threading.Thread(target=worker, args=(2, 1))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Exactly one demotion must succeed; the other must have raised
    # LastAdminCannotBeRemoved.
    assert len(errors) == 1, f"expected exactly 1 error, got {errors}"
    _, err = errors[0]
    assert isinstance(err, users_service.LastAdminCannotBeRemoved), (
        f"unexpected exception: {err!r}"
    )

    # Active-admin count must be exactly 1, not 0.
    verify = connect(db_path)
    remaining = verify.execute(
        "SELECT COUNT(*) AS c FROM users WHERE role='admin' AND is_active=1"
    ).fetchone()["c"]
    verify.close()
    assert remaining == 1, f"expected 1 active admin, got {remaining}"


def test_demote_admin_is_transactional_structural(fresh_db):
    """BE-5: count_active_admins SELECT and the UPDATE must both execute inside
    one BEGIN IMMEDIATE … COMMIT transaction."""
    _seed_admin(fresh_db, 1, "admin_a")
    _seed_admin(fresh_db, 2, "admin_b")

    calls: list[str] = []

    class _TraceConn:
        def __getattr__(self, name):
            return getattr(fresh_db, name)

        def execute(self, stmt, *args, **kw):
            first = stmt.strip().split()[0].upper()
            if first in ("BEGIN", "COMMIT", "ROLLBACK", "SELECT", "UPDATE", "INSERT", "DELETE"):
                calls.append(first)
            return fresh_db.execute(stmt, *args, **kw)

        def commit(self):
            calls.append("COMMIT")
            return fresh_db.commit()

        def rollback(self):
            calls.append("ROLLBACK")
            return fresh_db.rollback()

    users_service.demote_admin(_TraceConn(), admin_user_id=1, target_user_id=2)

    assert "BEGIN" in calls, f"demote_admin did not BEGIN a transaction: {calls}"
    begin_idx = calls.index("BEGIN")
    post_begin = calls[begin_idx + 1:]
    assert "COMMIT" in post_begin, f"demote_admin did not COMMIT: {calls}"
    commit_idx = post_begin.index("COMMIT")
    inside = post_begin[:commit_idx]
    assert "SELECT" in inside, (
        f"count_active_admins SELECT ran outside the transaction: {calls}"
    )
    assert "UPDATE" in inside, (
        f"demote_admin UPDATE ran outside the transaction: {calls}"
    )


# ---------------------------------------------------------------------------
# BE-5: disable_user — concurrent race for admin targets
# ---------------------------------------------------------------------------


def test_disable_user_concurrent_with_two_admins_preserves_one(tmp_path):
    """BE-5 (mirror): same race shape for disable_user on admin users.
    Two concurrent disable calls targeting different admins when exactly two
    admins exist must not leave zero active admins."""
    db_path = tmp_path / "disable_race.db"

    setup = connect(db_path)
    apply_migrations(setup, discover_migrations())
    _seed_admin(setup, 1, "admin_a")
    _seed_admin(setup, 2, "admin_b")
    setup.close()

    errors: list[tuple[int, Exception]] = []
    barrier = threading.Barrier(2)

    def worker(uid: int, target_uid: int) -> None:
        conn = connect(db_path)
        try:
            barrier.wait()
            users_service.disable_user(conn, admin_user_id=uid, target_user_id=target_uid)
        except Exception as exc:
            errors.append((uid, exc))
        finally:
            conn.close()

    t1 = threading.Thread(target=worker, args=(1, 2))
    t2 = threading.Thread(target=worker, args=(2, 1))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert len(errors) == 1, f"expected exactly 1 error, got {errors}"
    _, err = errors[0]
    assert isinstance(err, users_service.LastAdminCannotBeRemoved), (
        f"unexpected exception: {err!r}"
    )

    verify = connect(db_path)
    remaining = verify.execute(
        "SELECT COUNT(*) AS c FROM users WHERE role='admin' AND is_active=1"
    ).fetchone()["c"]
    verify.close()
    assert remaining >= 1, f"expected at least 1 active admin, got {remaining}"


def test_disable_user_is_transactional_structural(fresh_db):
    """BE-5: count_active_admins SELECT and the UPDATE inside disable_user must
    both execute inside one BEGIN IMMEDIATE … COMMIT transaction."""
    _seed_admin(fresh_db, 1, "admin_a")
    _seed_admin(fresh_db, 2, "admin_b")

    calls: list[str] = []

    class _TraceConn:
        def __getattr__(self, name):
            return getattr(fresh_db, name)

        def execute(self, stmt, *args, **kw):
            first = stmt.strip().split()[0].upper()
            if first in ("BEGIN", "COMMIT", "ROLLBACK", "SELECT", "UPDATE", "INSERT", "DELETE"):
                calls.append(first)
            return fresh_db.execute(stmt, *args, **kw)

        def commit(self):
            calls.append("COMMIT")
            return fresh_db.commit()

        def rollback(self):
            calls.append("ROLLBACK")
            return fresh_db.rollback()

    users_service.disable_user(_TraceConn(), admin_user_id=1, target_user_id=2)

    assert "BEGIN" in calls, f"disable_user did not BEGIN a transaction: {calls}"
    begin_idx = calls.index("BEGIN")
    post_begin = calls[begin_idx + 1:]
    assert "COMMIT" in post_begin, f"disable_user did not COMMIT: {calls}"
    commit_idx = post_begin.index("COMMIT")
    inside = post_begin[:commit_idx]
    assert "SELECT" in inside, (
        f"count_active_admins SELECT ran outside the transaction: {calls}"
    )
    assert "UPDATE" in inside, (
        f"disable_user UPDATE ran outside the transaction: {calls}"
    )


# ---------------------------------------------------------------------------
# BE-6: rotate_invite_code — structural transactionality
# ---------------------------------------------------------------------------


def test_rotate_invite_code_is_transactional(fresh_db):
    """BE-6: the UPDATE-deactivate and the INSERT-new inside rotate_invite_code
    must both execute inside one BEGIN IMMEDIATE … COMMIT transaction so a
    concurrent registration in the gap cannot see zero active codes."""
    _seed_admin(fresh_db, 1, "admin_a")
    # Seed a starting invite code
    fresh_db.execute(
        "INSERT INTO invite_codes(code, is_active, created_by_admin_id, created_at) "
        "VALUES ('OLD-CODE', 1, 1, ?)",
        (_NOW,),
    )

    calls: list[str] = []

    class _TraceConn:
        def __getattr__(self, name):
            return getattr(fresh_db, name)

        def execute(self, stmt, *args, **kw):
            first = stmt.strip().split()[0].upper()
            if first in ("BEGIN", "COMMIT", "ROLLBACK", "UPDATE", "INSERT", "SELECT", "DELETE"):
                calls.append(first)
            return fresh_db.execute(stmt, *args, **kw)

        def commit(self):
            calls.append("COMMIT")
            return fresh_db.commit()

        def rollback(self):
            calls.append("ROLLBACK")
            return fresh_db.rollback()

    users_service.rotate_invite_code(_TraceConn(), admin_user_id=1, new_code="NEW-2026")

    assert "BEGIN" in calls, f"rotate_invite_code did not BEGIN a transaction: {calls}"
    begin_idx = calls.index("BEGIN")
    post_begin = calls[begin_idx + 1:]
    assert "COMMIT" in post_begin, f"rotate_invite_code did not COMMIT: {calls}"
    commit_idx = post_begin.index("COMMIT")
    inside = post_begin[:commit_idx]
    assert "UPDATE" in inside and "INSERT" in inside, (
        f"rotate_invite_code UPDATE+INSERT not inside transaction: {calls}"
    )
