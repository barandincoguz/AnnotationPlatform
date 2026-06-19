import pytest

from backend import config


def test_validate_environment_rejects_non_positive_session_lifetime(
    monkeypatch,
):
    monkeypatch.setattr(config, "SESSION_MAX_AGE_SECONDS", 0)
    monkeypatch.setattr(config, "SESSION_MAX_AGE_SECONDS_RAW", "0")

    with pytest.raises(RuntimeError, match="SESSION_MAX_AGE_SECONDS"):
        config.validate_environment()


def test_validate_environment_rejects_invalid_cookie_samesite(monkeypatch):
    monkeypatch.setattr(config, "SESSION_COOKIE_SAMESITE", "invalid")

    with pytest.raises(RuntimeError, match="SESSION_COOKIE_SAMESITE"):
        config.validate_environment()
