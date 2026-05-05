from pathlib import Path
import pytest


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """FastAPI TestClient with isolated DATA_DIR / DB."""
    from fastapi.testclient import TestClient
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("backend.config.DB_DIR", tmp_path / "db")
    monkeypatch.setattr("backend.config.DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr("backend.config.DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr("backend.config.BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr("backend.config.EXPORTS_DIR", tmp_path / "exports")
    from backend.main import app
    with TestClient(app) as c:
        yield c
