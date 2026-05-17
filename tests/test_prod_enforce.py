"""Tests for backend/shared/prod_enforce.py.

prod_enforce runs at lifespan startup; misconfigured production deploys
must fail loud rather than silently. Covers: dev no-op, dev-default
SESSION_SECRET rejected, short SESSION_SECRET rejected, placeholder
admin password rejected (even when length passes), missing
ALLOWED_ORIGINS rejected.
"""
from __future__ import annotations

import pytest

from backend import config
from backend.shared.prod_enforce import (
    DEV_SESSION_SECRETS,
    ProductionConfigError,
    enforce_production_secrets,
)


@pytest.fixture
def prod(monkeypatch):
    """Default-safe production env: real secret, real password, real origin.
    Per test patches the field under inspection."""
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "SESSION_SECRET", "a" * 64)
    monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_PASSWORD", "S0lid!Random*Pass-2026")
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", {"https://anotasyon.example"})
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "")
    return monkeypatch


def test_dev_is_noop(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "development")
    monkeypatch.setattr(config, "SESSION_SECRET", "dev-secret-DO-NOT-USE-IN-PROD")
    # Should not raise even though every prod check would fail.
    enforce_production_secrets()


def test_prod_default_safe_passes(prod):
    enforce_production_secrets()


def test_dev_default_session_secret_rejected(prod):
    for secret in DEV_SESSION_SECRETS:
        prod.setattr(config, "SESSION_SECRET", secret)
        with pytest.raises(ProductionConfigError, match="SESSION_SECRET"):
            enforce_production_secrets()


def test_short_session_secret_rejected(prod):
    prod.setattr(config, "SESSION_SECRET", "x" * 31)
    with pytest.raises(ProductionConfigError, match="at least 32"):
        enforce_production_secrets()


def test_short_bootstrap_password_rejected(prod):
    prod.setattr(config, "BOOTSTRAP_ADMIN_PASSWORD", "tooshort")
    with pytest.raises(ProductionConfigError, match="at least 12"):
        enforce_production_secrets()


@pytest.mark.parametrize(
    "weak",
    [
        "admin123456789",        # 14 chars, but starts with "admin"
        "Password!1234567",
        "letmein2026-prod",
        "changeMeNowPlease",
        "Replace_Me_Now",
        "QWERTYuiop12345",
    ],
)
def test_placeholder_admin_password_rejected(prod, weak):
    prod.setattr(config, "BOOTSTRAP_ADMIN_PASSWORD", weak)
    with pytest.raises(ProductionConfigError, match="placeholder substring"):
        enforce_production_secrets()


def test_missing_allowed_origins_rejected(prod):
    prod.setattr(config, "ALLOWED_ORIGINS", set())
    with pytest.raises(ProductionConfigError, match="ALLOWED_ORIGINS"):
        enforce_production_secrets()


def test_empty_bootstrap_password_passes(prod):
    """Operator may set ENVIRONMENT=production without bootstrap creds
    (e.g. they've already seeded and removed the vars)."""
    prod.setattr(config, "BOOTSTRAP_ADMIN_PASSWORD", "")
    enforce_production_secrets()
