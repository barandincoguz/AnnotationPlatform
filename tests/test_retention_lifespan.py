"""Smoke test verifying the retention task starts and stops cleanly with the server."""
from fastapi.testclient import TestClient
from unittest.mock import patch


def test_lifespan_starts_and_stops_retention_task(tmp_path, monkeypatch):
    """Server lifespan creates the retention task on startup and cancels it on
    shutdown without raising. Uses side_effect that calls the real start/stop
    so the task is properly created and cancelled inside the right event loop."""
    from backend import main, config
    from backend.retention import loop as retention_loop_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr(config, "DB_DIR", tmp_path / "db")
    monkeypatch.setattr(config, "DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path / "exports")

    started = []
    stopped = []
    real_start = retention_loop_mod.start
    real_stop = retention_loop_mod.stop

    def fake_start():
        started.append(True)
        return real_start()

    def fake_stop():
        stopped.append(True)
        return real_stop()

    # Patch target is `backend.main.retention_loop.start` because main.py
    # imports the module under that alias (`from backend.retention import
    # loop as retention_loop`).
    with patch("backend.main.retention_loop.start", side_effect=fake_start), \
         patch("backend.main.retention_loop.stop",  side_effect=fake_stop):
        with TestClient(main.app) as client:
            r = client.get("/api/health")
            assert r.status_code == 200
        # After exiting the with block, lifespan shutdown ran.
        assert started == [True]
        assert stopped == [True]
