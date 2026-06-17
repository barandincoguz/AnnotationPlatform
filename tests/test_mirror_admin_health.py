"""Tests for `backend/mirror/health.py::collect_health` + the
`GET /api/admin/mirror/health` route.

The health computation is a pure function over a SQLite connection, so
most tests drive `collect_health(conn)` directly so HTTP authentication and
unrelated application writes do not affect queue assertions.
The HTTP layer is covered separately by an auth gate test and a shape
test.
"""
from datetime import datetime, timedelta, timezone

from backend.shared.db import connect
from backend import config
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.mirror import dispatcher as mirror_dispatcher
from backend.mirror import config as mirror_config
from backend.mirror.health import collect_health


def _bootstrap_db(db_path):
    """Apply all migrations onto a clean tmp DB so `_outbox` exists."""
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    return conn


def _make_admin(client):
    """Register a user, promote to admin, log them in, return the user dict."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("ADMIN-MIRROR-INV",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": "mirror_boss", "password": "password123",
        "invite_code": "ADMIN-MIRROR-INV", "email": "mirror_boss@example.com",
    })
    assert r.status_code == 201, r.text
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
        "username": "mirror_boss", "password": "password123",
    })
    assert r.status_code == 200
    return user


def _reset_dispatcher_module_state():
    """Other suites don't touch these globals, but the health function
    reads them so per-test determinism requires a clean slate."""
    mirror_dispatcher._task = None
    mirror_dispatcher.last_status = None
    mirror_dispatcher.last_delivered_at = None


# === Unit-level (collect_health directly; no HTTP, no session writes) ===

def test_collect_health_empty_queue(db_path):
    """No outbox rows → queue_depth=0, dead=0, oldest_age=None,
    last_delivered=None, dispatcher_alive=False (no task), neon_reachable=None."""
    _reset_dispatcher_module_state()
    conn = _bootstrap_db(db_path)
    try:
        conn.execute("DELETE FROM _outbox")
        conn.commit()
        body = collect_health(conn)
    finally:
        conn.close()
    assert body == {
        "queue_depth": 0,
        "dead_letter_count": 0,
        "oldest_undelivered_age_seconds": None,
        "last_delivered_at": None,
        "dispatcher_alive": False,
        "neon_reachable": None,
    }


def test_collect_health_one_pending_row(db_path):
    """One undelivered row created 30s ago → queue_depth=1, dead=0,
    oldest_age ≈ 30s, last_delivered=None."""
    _reset_dispatcher_module_state()
    conn = _bootstrap_db(db_path)
    try:
        conn.execute("DELETE FROM _outbox")
        past = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        conn.execute(
            "INSERT INTO _outbox(table_name, op, pk_value, payload_json, "
            "created_at, retry_count) VALUES (?, ?, ?, ?, ?, ?)",
            ("users", "INSERT", "1", '{"id": 1}', past, 0),
        )
        conn.commit()
        body = collect_health(conn)
    finally:
        conn.close()
    assert body["queue_depth"] == 1
    assert body["dead_letter_count"] == 0
    assert body["oldest_undelivered_age_seconds"] is not None
    assert body["oldest_undelivered_age_seconds"] >= 29.0  # ≈30s, 1s clock fudge


def test_collect_health_dead_letter_excluded_from_queue_depth(db_path):
    """retry_count >= MAX_RETRIES → counted as dead-letter, NOT in queue_depth."""
    _reset_dispatcher_module_state()
    conn = _bootstrap_db(db_path)
    try:
        conn.execute("DELETE FROM _outbox")
        conn.execute(
            "INSERT INTO _outbox(table_name, op, pk_value, payload_json, "
            "created_at, error, retry_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "users", "INSERT", "1", '{"id": 1}',
                datetime.now(timezone.utc).isoformat(),
                "permanent: bad data",
                mirror_config.MAX_RETRIES,
            ),
        )
        conn.commit()
        body = collect_health(conn)
    finally:
        conn.close()
    assert body["queue_depth"] == 0
    assert body["dead_letter_count"] == 1


def test_collect_health_last_delivered_falls_back_to_outbox_when_module_none(db_path):
    """When the dispatcher hasn't run yet (module-level last_delivered_at is
    None) but a historical delivered row exists, collect_health falls back
    to `MAX(delivered_at)` from the table."""
    _reset_dispatcher_module_state()
    conn = _bootstrap_db(db_path)
    try:
        conn.execute("DELETE FROM _outbox")
        delivered = "2026-05-18T22:00:00+00:00"
        conn.execute(
            "INSERT INTO _outbox(table_name, op, pk_value, payload_json, "
            "created_at, delivered_at, retry_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "users", "INSERT", "1", '{"id": 1}',
                datetime.now(timezone.utc).isoformat(),
                delivered, 0,
            ),
        )
        conn.commit()
        body = collect_health(conn)
    finally:
        conn.close()
    assert body["last_delivered_at"] == delivered


def test_collect_health_neon_reachable_reflects_dispatcher_last_status(db_path):
    """Ergonomic field: True/False mirror dispatcher.last_status; None means
    "never attempted" rather than asserting reachability either way."""
    _reset_dispatcher_module_state()
    conn = _bootstrap_db(db_path)
    try:
        conn.execute("DELETE FROM _outbox")
        conn.commit()
        # last_status None → neon_reachable None
        assert collect_health(conn)["neon_reachable"] is None
        # True → True
        mirror_dispatcher.last_status = True
        assert collect_health(conn)["neon_reachable"] is True
        # False → False
        mirror_dispatcher.last_status = False
        assert collect_health(conn)["neon_reachable"] is False
    finally:
        conn.close()
        _reset_dispatcher_module_state()


# === HTTP layer (auth gate + shape stability) ===

def test_health_endpoint_requires_auth(client):
    r = client.get("/api/admin/mirror/health")
    assert r.status_code == 401


def test_health_endpoint_non_admin_404(passed_user):
    # require_admin returns 404 (hides existence) per backend/users/deps.py.
    r = passed_user["client"].get("/api/admin/mirror/health")
    assert r.status_code == 404


def test_health_endpoint_admin_returns_stable_shape(client):
    """The HTTP body must always carry exactly these keys (operator
    dashboards key off them). Catches accidental renames during future
    refactors. We don't assert numeric values here — the session
    middleware writes outbox rows on every request, so queue counts
    are inherently flaky at the HTTP layer; collect_health unit
    tests above cover the math."""
    _make_admin(client)
    r = client.get("/api/admin/mirror/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "queue_depth",
        "dead_letter_count",
        "oldest_undelivered_age_seconds",
        "last_delivered_at",
        "dispatcher_alive",
        "neon_reachable",
    }
    # Numeric fields are well-typed integers; floats can be None or float.
    assert isinstance(body["queue_depth"], int)
    assert isinstance(body["dead_letter_count"], int)
    assert isinstance(body["dispatcher_alive"], bool)
