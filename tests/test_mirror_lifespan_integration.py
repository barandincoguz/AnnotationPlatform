"""Lifespan integration for the Phase 4 dispatcher (Task 10).

Boots the FastAPI app via TestClient with NEON_MIRROR_URL unset and
asserts:
  - startup succeeds (no exceptions),
  - _outbox + 63 triggers exist after migrations applied,
  - a system_events 'neon_mirror_unreachable' row is emitted on warn,
  - the dispatcher task is alive,
  - on shutdown the dispatcher stops cleanly.

Also verifies the negative case: an unreachable NEON_MIRROR_URL still
yields a successful boot (the dispatcher's first connect() returns False
without raising — MIRROR-10, D-14).
"""
from __future__ import annotations

import pytest

from backend.shared.db import connect
from backend import config


@pytest.fixture(autouse=True)
def _reset_dispatcher_state():
    """Make sure each test starts with fresh dispatcher module state."""
    from backend.mirror import dispatcher as d
    d._cold_start_emitted = False
    d.last_status = None
    d.last_delivered_at = None
    yield


def test_lifespan_starts_with_no_neon_url(client, monkeypatch):
    """NEON_MIRROR_URL unset → boot succeeds, warn-severity event emitted."""
    # NB: client fixture has already started the app. We need to ensure the
    # env is clean BEFORE the TestClient context entered — `client` is
    # function-scoped so this monkeypatch must run before client materialization.
    # In practice the test env never sets NEON_MIRROR_URL, so the default
    # path is exactly the degraded boot.
    conn = connect(config.DB_PATH)
    try:
        # _outbox exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_outbox'"
        ).fetchone()
        assert row is not None
        # 66 triggers (22 mirrored tables × 3 ops, after adding annotation_audit_logs in v0017)
        trig = conn.execute(
            "SELECT count(*) AS c FROM sqlite_master "
            "WHERE type='trigger' AND name LIKE '_outbox_%'"
        ).fetchone()
        assert trig["c"] == 66
        # warn event recorded
        events = conn.execute(
            "SELECT * FROM system_events WHERE event_type='neon_mirror_unreachable'"
        ).fetchall()
        assert len(events) == 1, events
        assert events[0]["severity"] == "warn"
    finally:
        conn.close()

    # Dispatcher task is alive.
    from backend.mirror import dispatcher
    assert dispatcher.is_alive()


def test_lifespan_starts_with_unreachable_neon_url(tmp_path, monkeypatch):
    """An invalid NEON_MIRROR_URL should still allow boot (degraded mode).

    The dispatcher's initial connect() returns False without raising.
    """
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("backend.config.DB_DIR", tmp_path / "db")
    monkeypatch.setattr("backend.config.DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr("backend.config.DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr("backend.config.BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr("backend.config.EXPORTS_DIR", tmp_path / "exports")
    # Point at an unreachable DSN: Neon won't be there in the test env.
    monkeypatch.setenv("NEON_MIRROR_URL", "postgresql://no:no@127.0.0.1:1/no?sslmode=disable")

    # Import the app fresh so the lifespan sees the new env.
    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as c:
        # health endpoint still works
        r = c.get("/api/health")
        assert r.status_code == 200
        # dispatcher is alive
        from backend.mirror import dispatcher
        assert dispatcher.is_alive()

    # After context exit (lifespan shutdown) the dispatcher task is done.
    from backend.mirror import dispatcher
    assert not dispatcher.is_alive()


def test_lifespan_dispatcher_handle_exposed(client):
    """The dispatcher module exposes is_alive() and get_neon_client()."""
    from backend.mirror import dispatcher
    assert dispatcher.is_alive() is True
    # Neon client created lazily; should be a NeonClient instance
    nc = dispatcher.get_neon_client()
    assert nc is not None
