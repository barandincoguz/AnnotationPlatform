"""Tests for backend/exports/service.py — build_query (Task 2),
stream_csv_rows (Task 3), stream_jsonl_objects (Task 4)."""
from datetime import date


# ---------------- build_query ----------------


def test_build_query_no_filters():
    """With format-only filters, no conditional WHERE clauses are added.
    The SQL still has a `WHERE 1=1` skeleton so future appends are uniform.
    Assertions target WHERE-clause fragments specifically (not column-name
    substring), because the SELECT always references is_completed,
    updated_at, etc. as projected columns."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(ExportFilters(format="csv", status="all"))
    assert "WHERE 1=1" in sql
    assert "AND a.is_completed = 1" not in sql       # status=all → no completion clause
    assert "AND a.updated_at >=" not in sql
    assert "AND a.updated_at <" not in sql
    assert "AND a.document_id = ?" not in sql
    assert "AND (a.last_editor_user_id" not in sql
    assert params == ()


def test_build_query_status_completed_default():
    """Default status=completed appends `AND a.is_completed = 1`."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(ExportFilters(format="csv"))
    assert "AND a.is_completed = 1" in sql
    assert params == ()


def test_build_query_status_all_omits_completion_clause():
    """Explicit status=all suppresses the is_completed WHERE clause so the
    export includes uncompleted (saved-but-not-finalized) annotations.
    The SELECT still projects a.is_completed (operators see the column);
    only the filter is dropped."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(ExportFilters(format="csv", status="all"))
    assert "AND a.is_completed = 1" not in sql
    # The column is still selected so consumers see the value:
    assert "a.is_completed" in sql


def test_build_query_from_date_filter():
    """from_date appends `AND a.updated_at >= ?` and binds the ISO string."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(
        ExportFilters(format="csv", status="all", from_date=date(2026, 4, 1))
    )
    assert "AND a.updated_at >= ?" in sql
    assert "2026-04-01" in params


def test_build_query_to_date_inclusive_end_of_day():
    """to_date uses `< date(?, '+1 day')` so '2026-04-30' includes all rows
    up to and including 2026-04-30T23:59:59."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(
        ExportFilters(format="csv", status="all", to_date=date(2026, 4, 30))
    )
    assert "AND a.updated_at < date(?, '+1 day')" in sql
    assert "2026-04-30" in params


def test_build_query_document_id_filter():
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(
        ExportFilters(format="csv", status="all", document_id="doc_42")
    )
    assert "AND a.document_id = ?" in sql
    assert "doc_42" in params


def test_build_query_user_id_matches_editor_or_completer():
    """user_id binds to BOTH last_editor_user_id AND completed_by_user_id
    in a single OR clause (so a user is included if they touched the
    annotation in any role)."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(
        ExportFilters(format="csv", status="all", user_id=42)
    )
    assert "(a.last_editor_user_id = ? OR a.completed_by_user_id = ?)" in sql
    # Same user_id bound twice
    assert params.count(42) == 2


def test_build_query_combines_multiple_filters():
    """All five conditional clauses can stack. Order matters less than
    determinism — same input → same SQL string + param tuple."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    filters = ExportFilters(
        format="csv",
        status="completed",
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 30),
        document_id="doc_42",
        user_id=42,
    )
    sql, params = build_query(filters)
    assert "is_completed = 1" in sql
    assert "updated_at >=" in sql
    assert "updated_at < date" in sql
    assert "a.document_id = ?" in sql
    assert "last_editor_user_id = ? OR a.completed_by_user_id = ?" in sql
    assert "ORDER BY a.document_id, ar.seq" in sql
    # 2 dates + 1 doc_id + 2 user_ids = 5 params
    assert len(params) == 5
