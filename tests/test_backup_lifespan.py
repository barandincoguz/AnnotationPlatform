"""Smoke tests verifying the backup task starts and stops cleanly with the server."""
from fastapi.testclient import TestClient
from unittest.mock import patch


def test_lifespan_starts_and_stops_backup_task(tmp_path, monkeypatch):
    """Server lifespan creates the backup task on startup and cancels it on
    shutdown without raising."""
    from backend import main, config
    from backend.backup import loop as backup_loop_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr(config, "DB_DIR", tmp_path / "db")
    monkeypatch.setattr(config, "DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path / "exports")

    started = []
    stopped = []
    real_start = backup_loop_mod.start
    real_stop = backup_loop_mod.stop

    def fake_start():
        started.append(True)
        return real_start()

    def fake_stop():
        stopped.append(True)
        return real_stop()

    with patch("backend.main.backup_loop.start", side_effect=fake_start), \
         patch("backend.main.backup_loop.stop", side_effect=fake_stop):
        with TestClient(main.app) as client:
            r = client.get("/api/health")
            assert r.status_code == 200
        # After exiting the with block, lifespan shutdown ran
        assert started == [True]
        assert stopped == [True]


def test_lifespan_logs_startup_includes_backup_task(tmp_path, monkeypatch):
    """Cosmetic-but-useful: when server starts, the existing 'startup'
    system_events row should be written. Ensures the backup task addition
    doesn't break startup."""
    from backend import main, config
    from backend.shared.db import connect

    db_path = tmp_path / "db" / "test.db"
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr(config, "DB_DIR", tmp_path / "db")
    monkeypatch.setattr(config, "DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path / "exports")

    with TestClient(main.app) as client:
        client.get("/api/health")

    # Use the captured local path; this is robust under refactors that might
    # move the assertion outside the test scope where monkeypatch is no longer active.
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM system_events WHERE event_type='startup'"
        ).fetchall()
        assert len(rows) == 1
    finally:
        conn.close()
