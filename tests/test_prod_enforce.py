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
    monkeypatch.setattr(config, "TRUST_FORWARDED_FOR", False)
    monkeypatch.setattr(config, "TRUSTED_PROXY_NETWORKS", ())
    monkeypatch.setattr(config, "INVALID_TRUSTED_PROXY_CIDRS", ())
    monkeypatch.setattr(config, "SPACE_ID", None, raising=False)
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


def test_placeholder_session_secret_rejected(prod):
    """An operator who copies `.env.example` verbatim leaves
    SESSION_SECRET=<REPLACE_ME_run_openssl_rand_hex_32> — 38 chars, not
    in DEV_SESSION_SECRETS — so length + identity gates pass silently.
    The dedicated template-placeholder check catches it loudly."""
    prod.setattr(config, "SESSION_SECRET", "<REPLACE_ME_run_openssl_rand_hex_32>")
    with pytest.raises(ProductionConfigError, match="template.*placeholder"):
        enforce_production_secrets()


def test_placeholder_allowed_origins_rejected(prod):
    """Same defense for ALLOWED_ORIGINS — a verbatim
    <REPLACE_ME_https_your_public_host> would be a non-empty single-element
    set that passes the truthy check, then 403s every browser request."""
    prod.setattr(config, "ALLOWED_ORIGINS", {"<REPLACE_ME_https_your_public_host>"})
    with pytest.raises(ProductionConfigError, match="template.*placeholder"):
        enforce_production_secrets()


@pytest.mark.parametrize(
    ("origin", "message"),
    [
        ("http://anotasyon.example", "must use https"),
        ("https://*.example.com", "must not contain wildcards"),
        ("https://anotasyon.example/app", "without path"),
        ("https://anotasyon.example?tenant=1", "without path"),
        ("https://user:pass@anotasyon.example", "credentials"),
        ("https://ANOTASYON.example", "canonical form"),
        ("https://anotasyon.example/", "without path"),
        ("https://anotasyon.example:bad", "invalid host or port"),
    ],
)
def test_invalid_allowed_origin_rejected(prod, origin, message):
    prod.setattr(config, "ALLOWED_ORIGINS", {origin})
    with pytest.raises(ProductionConfigError, match=message):
        enforce_production_secrets()


def test_non_default_https_port_is_allowed(prod):
    prod.setattr(config, "ALLOWED_ORIGINS", {"https://anotasyon.example:8443"})
    enforce_production_secrets()


def test_explicit_default_https_port_must_be_canonical(prod):
    prod.setattr(config, "ALLOWED_ORIGINS", {"https://anotasyon.example:443"})
    with pytest.raises(ProductionConfigError, match="canonical form"):
        enforce_production_secrets()


def test_hugging_face_runtime_also_enforces(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "development")
    monkeypatch.setattr(config, "SPACE_ID", "owner/space")
    monkeypatch.setattr(config, "SESSION_SECRET", "dev-secret-DO-NOT-USE-IN-PROD")
    monkeypatch.setattr(config, "BOOTSTRAP_ADMIN_PASSWORD", "")
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", {"https://owner-space.hf.space"})
    monkeypatch.setattr(config, "BACKUP_REPO_URL", "")
    monkeypatch.setattr(config, "INVALID_TRUSTED_PROXY_CIDRS", ())

    with pytest.raises(ProductionConfigError, match="SESSION_SECRET"):
        enforce_production_secrets()


def test_forwarded_for_trust_requires_proxy_cidrs(prod):
    prod.setattr(config, "TRUST_FORWARDED_FOR", True)
    with pytest.raises(ProductionConfigError, match="TRUSTED_PROXY_CIDRS"):
        enforce_production_secrets()


def test_invalid_proxy_cidr_rejected_even_when_trust_is_off(prod):
    prod.setattr(config, "INVALID_TRUSTED_PROXY_CIDRS", ("not-a-network",))
    with pytest.raises(ProductionConfigError, match="invalid network"):
        enforce_production_secrets()


def test_unrestricted_proxy_cidr_rejected(prod):
    from ipaddress import ip_network

    prod.setattr(config, "TRUSTED_PROXY_NETWORKS", (ip_network("0.0.0.0/0"),))
    with pytest.raises(ProductionConfigError, match="entire address family"):
        enforce_production_secrets()


def test_empty_bootstrap_password_passes(prod):
    """Operator may set ENVIRONMENT=production without bootstrap creds
    (e.g. they've already seeded and removed the vars)."""
    prod.setattr(config, "BOOTSTRAP_ADMIN_PASSWORD", "")
    enforce_production_secrets()
