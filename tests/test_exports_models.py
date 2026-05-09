"""Tests for backend/exports/models.py — ExportFilters query-param validation."""
import pytest
from datetime import date

from pydantic import ValidationError


def test_filters_format_required():
    """`format` is the only mandatory query param. Without it Pydantic
    rejects the request before any DB work happens."""
    from backend.exports.models import ExportFilters
    with pytest.raises(ValidationError) as exc:
        ExportFilters()
    assert "format" in str(exc.value)


def test_filters_format_rejects_invalid_value():
    """Only csv and jsonl are valid. xml/txt/null all 422."""
    from backend.exports.models import ExportFilters
    with pytest.raises(ValidationError):
        ExportFilters(format="xml")


def test_filters_status_default_completed():
    """When status is omitted, default to completed (the more selective
    filter — operator who wants 'everything' must opt in via status=all)."""
    from backend.exports.models import ExportFilters
    f = ExportFilters(format="csv")
    assert f.status == "completed"


def test_filters_from_date_after_to_date_rejected():
    """Cross-field validation: from_date must not be after to_date."""
    from backend.exports.models import ExportFilters
    with pytest.raises(ValidationError) as exc:
        ExportFilters(
            format="csv",
            from_date=date(2026, 5, 10),
            to_date=date(2026, 4, 1),
        )
    assert "from_date" in str(exc.value)


def test_filters_user_id_must_be_positive():
    """user_id is a primary key; zero/negative values can never match
    any real user. Reject at validation rather than do a wasted query."""
    from backend.exports.models import ExportFilters
    with pytest.raises(ValidationError):
        ExportFilters(format="csv", user_id=0)
    with pytest.raises(ValidationError):
        ExportFilters(format="csv", user_id=-1)
