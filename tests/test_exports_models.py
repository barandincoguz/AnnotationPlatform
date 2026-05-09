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


def test_filters_format_jsonl_accepted():
    """jsonl is the second valid format (csv is tested via the default
    success path)."""
    from backend.exports.models import ExportFilters
    f = ExportFilters(format="jsonl")
    assert f.format == "jsonl"


def test_filters_status_all_accepted():
    """status='all' is the explicit-opt-in path that suppresses the
    is_completed clause in build_query (Task 2)."""
    from backend.exports.models import ExportFilters
    f = ExportFilters(format="csv", status="all")
    assert f.status == "all"


def test_filters_from_date_equal_to_date_accepted():
    """Boundary: from_date == to_date is a valid single-day window. The
    validator must use > not >= so this passes."""
    from backend.exports.models import ExportFilters
    f = ExportFilters(
        format="csv",
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 1),
    )
    assert f.from_date == f.to_date


def test_filters_document_id_accepts_string():
    """document_id is a free-form string matching annotations.document_id
    exactly. The schema imposes no length or charset constraint."""
    from backend.exports.models import ExportFilters
    f = ExportFilters(format="csv", document_id="doc_42")
    assert f.document_id == "doc_42"


def test_filters_user_id_positive_boundary_accepted():
    """user_id=1 is the smallest valid value (gt=0). Asserting the lower
    boundary protects against future regressions that might tighten the
    constraint to ge=2 or similar."""
    from backend.exports.models import ExportFilters
    f = ExportFilters(format="csv", user_id=1)
    assert f.user_id == 1
