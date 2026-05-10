"""Lifespan should emit a system_events WARN row when SESSION_SECRET is
left at a dev default. Mirrors the paket-15 production-hardening contract:
operators see the dev-default state in the audit log without the app
hard-failing local-dev or compose-default boot."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_secret(monkeypatch, tmp_path):
    """Build a clean app whose lifespan reads a monkeypatched SESSION_SECRET.

    Each test gets a fresh tmp DB so the WARN row count is deterministic.
    """
    from backend import config

    # Isolate the DB so prior runs don't contaminate the audit log scan.
    data_dir = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR",     data_dir)
    monkeypatch.setattr(config, "DB_DIR",       data_dir / "db")
    monkeypatch.setattr(config, "DB_PATH",      data_dir / "db" / "annotations.db")
    monkeypatch.setattr(config, "DOCUMENTS_DIR", data_dir / "documents")
    monkeypatch.setattr(config, "BACKUP_DIR",    data_dir / "backup")
    monkeypatch.setattr(config, "EXPORTS_DIR",   data_dir / "exports")

    return config


def _count_warn_rows(db_path) -> int:
    from backend.shared.db import connect
    conn = connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM system_events "
            "WHERE event_type='session_secret_dev_default' AND severity='warn'"
        ).fetchone()["c"]
    finally:
        conn.close()


def test_lifespan_emits_warn_when_session_secret_is_default(monkeypatch, app_with_secret):
    """The exact default from backend/config.py triggers the WARN row."""
    monkeypatch.setattr(app_with_secret, "SESSION_SECRET", "dev-secret-DO-NOT-USE-IN-PROD")
    from backend.main import app
    with TestClient(app):
        pass  # Just trigger lifespan
    assert _count_warn_rows(app_with_secret.DB_PATH) == 1


def test_lifespan_emits_warn_when_compose_default_is_used(monkeypatch, app_with_secret):
    """The compose fallback string also triggers the WARN row."""
    monkeypatch.setattr(app_with_secret, "SESSION_SECRET", "dev-secret-change-me")
    from backend.main import app
    with TestClient(app):
        pass
    assert _count_warn_rows(app_with_secret.DB_PATH) == 1


def test_lifespan_skips_warn_when_secret_is_real(monkeypatch, app_with_secret):
    """A real-looking secret leaves the WARN counter at zero."""
    monkeypatch.setattr(app_with_secret, "SESSION_SECRET",
                        "9a44e8c7f3b2d1e0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6")
    from backend.main import app
    with TestClient(app):
        pass
    assert _count_warn_rows(app_with_secret.DB_PATH) == 0
