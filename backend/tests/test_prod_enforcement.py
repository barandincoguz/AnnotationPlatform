"""Tests for backend.shared.prod_enforce.enforce_production_secrets.

The function is fail-fast: in production mode it raises ProductionConfigError
listing every violation before app boot. In dev/test mode it is a no-op.
"""
import pytest

from backend.shared.prod_enforce import (
    enforce_production_secrets,
    ProductionConfigError,
)


def test_prod_rejects_default_secret(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "dev-secret-DO-NOT-USE-IN-PROD")
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    with pytest.raises(ProductionConfigError) as exc:
        enforce_production_secrets()
    assert "SESSION_SECRET" in str(exc.value)
    assert "default placeholder" in str(exc.value)


def test_prod_rejects_short_secret(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "x" * 16)
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    with pytest.raises(ProductionConfigError) as exc:
        enforce_production_secrets()
    assert "32 characters" in str(exc.value)


def test_prod_accepts_strong_secret(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "a" * 32)
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "https://github.com/example/repo.git")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "fake-pat")
    monkeypatch.setattr("backend.config.ALLOWED_ORIGINS", {"https://anotasyon.example"})
    enforce_production_secrets()  # no raise


def test_prod_accepts_wildcard_origin(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "a" * 32)
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "https://github.com/example/repo.git")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "fake-pat")
    monkeypatch.setattr("backend.config.ALLOWED_ORIGINS", {"*"})
    enforce_production_secrets()  # no raise



def test_prod_rejects_short_bootstrap_password(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "a" * 32)
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "shorty")
    with pytest.raises(ProductionConfigError) as exc:
        enforce_production_secrets()
    assert "BOOTSTRAP_ADMIN_PASSWORD" in str(exc.value)
    assert "12 characters" in str(exc.value)


def test_dev_allows_default_secret(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "development")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "dev-secret-DO-NOT-USE-IN-PROD")
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    enforce_production_secrets()  # no raise


def test_prod_rejects_no_backup_url(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "a" * 32)
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "fake-pat")
    monkeypatch.setattr("backend.config.ALLOWED_ORIGINS", {"https://anotasyon.example"})
    with pytest.raises(ProductionConfigError) as exc:
        enforce_production_secrets()
    assert "BACKUP_REPO_URL" in str(exc.value)


def test_prod_rejects_backup_url_without_pat(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "a" * 32)
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "https://github.com/o/r.git")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "")
    monkeypatch.setattr("backend.config.ALLOWED_ORIGINS", {"https://anotasyon.example"})
    with pytest.raises(ProductionConfigError) as exc:
        enforce_production_secrets()
    assert "GITHUB_PAT" in str(exc.value)


def test_prod_rejects_non_github_backup_url(monkeypatch):
    monkeypatch.setattr("backend.config.ENVIRONMENT", "production")
    monkeypatch.setattr("backend.config.SESSION_SECRET", "a" * 32)
    monkeypatch.setattr("backend.config.BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setattr("backend.config.BACKUP_REPO_URL", "https://example.com/o/r.git")
    monkeypatch.setattr("backend.config.GITHUB_PAT", "fake-pat")
    monkeypatch.setattr("backend.config.ALLOWED_ORIGINS", {"https://anotasyon.example"})
    with pytest.raises(ProductionConfigError) as exc:
        enforce_production_secrets()
    assert "github.com" in str(exc.value)
