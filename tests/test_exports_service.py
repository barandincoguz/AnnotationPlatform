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


# ---------------- stream_csv_rows ----------------


def _fake_row(**kwargs):
    """Helper: produces a tuple matching the SELECT column order in
    build_query. Defaults are non-empty for required fields, NULL for
    nullable ones. Override only what the test cares about."""
    defaults = {
        "document_id": "doc_42",
        "doc_sayi": 1234,
        "doc_tarih": "20260101",
        "doc_konu": "Test özelge",
        "last_editor_user_id": 42,
        "last_editor_username": "ahmet",
        "last_edited_at": "2026-04-15T10:30:00+00:00",
        "is_completed": 1,
        "completed_by_user_id": 42,
        "completed_by_username": "ahmet",
        "edit_count": 3,
        "unique_users_count": 2,
        "ref_seq": 0,
        "ref_kanun_no": "5520",
        "ref_kanun_ad": "Kurumlar Vergisi Kanunu",
        "ref_madde": "30",
        "ref_fikra": "2",
        "ref_bent": "a",
        "ref_source_text": "madde 30/2-a",
    }
    defaults.update(kwargs)
    # Match the SELECT order from _BASE_SELECT
    result = (
        defaults["document_id"], defaults["doc_sayi"], defaults["doc_tarih"],
        defaults["doc_konu"], defaults["last_editor_user_id"],
        defaults["last_editor_username"], defaults["last_edited_at"],
        defaults["is_completed"], defaults["completed_by_user_id"],
        defaults["completed_by_username"], defaults["edit_count"],
        defaults["unique_users_count"], defaults["ref_seq"],
        defaults["ref_kanun_no"], defaults["ref_kanun_ad"],
        defaults["ref_madde"], defaults["ref_fikra"], defaults["ref_bent"],
        defaults["ref_source_text"],
    )
    # Guard against silent short-tuples if _BASE_SELECT ever gains a column.
    from backend.exports.service import CSV_COLUMNS
    assert len(result) == len(CSV_COLUMNS), (
        f"_fake_row produces {len(result)} fields but CSV_COLUMNS has "
        f"{len(CSV_COLUMNS)} — update the helper's tuple to match the SELECT."
    )
    return result


def test_stream_csv_rows_emits_header_first():
    """Header row is the FIRST yielded chunk, regardless of data presence."""
    from backend.exports.service import stream_csv_rows, CSV_COLUMNS
    chunks = list(stream_csv_rows(iter([])))  # zero data rows
    assert chunks[0].startswith(",".join(CSV_COLUMNS))
    assert chunks[0].endswith("\r\n") or chunks[0].endswith("\n")
    assert len(chunks) == 1  # only header


def test_stream_csv_rows_one_row_per_reference():
    """Two reference rows for the same document → 2 CSV data lines, all
    fields except ref_* repeated exactly."""
    from backend.exports.service import stream_csv_rows
    rows = [
        _fake_row(ref_seq=0, ref_kanun_no="5520", ref_madde="30"),
        _fake_row(ref_seq=1, ref_kanun_no="5901", ref_madde="91"),
    ]
    out = "".join(stream_csv_rows(iter(rows)))
    lines = out.strip().split("\n")
    assert len(lines) == 3  # header + 2 data
    assert "5520" in lines[1]
    assert "5901" in lines[2]
    # Same document_id + last_editor on both data rows
    assert "doc_42" in lines[1] and "doc_42" in lines[2]
    assert "ahmet" in lines[1] and "ahmet" in lines[2]


def test_stream_csv_rows_zero_reference_annotation_emits_one_row_with_nulls():
    """An annotation with no references comes back as a single row with
    LEFT JOIN producing NULL for ar.* — verify those land as empty cells,
    not the literal 'None' or 'null'."""
    from backend.exports.service import stream_csv_rows
    row = _fake_row(
        ref_seq=None, ref_kanun_no=None, ref_kanun_ad=None,
        ref_madde=None, ref_fikra=None, ref_bent=None, ref_source_text=None,
    )
    out = "".join(stream_csv_rows(iter([row])))
    lines = out.strip().split("\n")
    assert len(lines) == 2  # header + 1 row
    # 7 trailing ref_* fields are NULL → 7 trailing commas exactly:
    # ref_seq, ref_kanun_no, ref_kanun_ad, ref_madde, ref_fikra, ref_bent, ref_source_text
    assert lines[1].rstrip().endswith(",,,,,,,")
    assert "None" not in lines[1]
    assert "null" not in lines[1]


def test_stream_csv_rows_escapes_special_chars():
    """Source text containing quotes, commas, and newlines must be
    RFC 4180-escaped: wrapped in double quotes, embedded quotes doubled.
    Otherwise downstream Excel/pandas parsers misalign columns."""
    from backend.exports.service import stream_csv_rows
    tricky = 'has "quotes", commas, and\nnewlines'
    row = _fake_row(ref_source_text=tricky)
    out = "".join(stream_csv_rows(iter([row])))
    # The dangerous cell must be quoted with internal quotes doubled.
    assert '"has ""quotes"", commas, and\nnewlines"' in out


# ---------------- stream_jsonl_objects ----------------


def test_stream_jsonl_objects_one_per_annotation():
    """Each contiguous group of cursor rows with the same document_id
    yields exactly one JSON line."""
    from backend.exports.service import stream_jsonl_objects
    import json
    rows = [
        _fake_row(document_id="doc_a", ref_seq=0, ref_kanun_no="A"),
        _fake_row(document_id="doc_a", ref_seq=1, ref_kanun_no="B"),
        _fake_row(document_id="doc_b", ref_seq=0, ref_kanun_no="C"),
    ]
    lines = list(stream_jsonl_objects(iter(rows)))
    assert len(lines) == 2
    obj_a = json.loads(lines[0])
    obj_b = json.loads(lines[1])
    assert obj_a["document_id"] == "doc_a"
    assert obj_b["document_id"] == "doc_b"


def test_stream_jsonl_objects_groups_references_per_annotation():
    """One JSON line for doc_a contains BOTH its references in order.
    The references list must be sorted by ref_seq."""
    from backend.exports.service import stream_jsonl_objects
    import json
    rows = [
        _fake_row(document_id="doc_a", ref_seq=0, ref_kanun_no="5520"),
        _fake_row(document_id="doc_a", ref_seq=1, ref_kanun_no="5901"),
    ]
    lines = list(stream_jsonl_objects(iter(rows)))
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert len(obj["references"]) == 2
    assert obj["references"][0]["kanun_no"] == "5520"
    assert obj["references"][1]["kanun_no"] == "5901"


def test_stream_jsonl_objects_empty_references_array():
    """An annotation with zero references produces a row where ref_seq
    and ref_kanun_no are NULL (LEFT JOIN miss). The JSONL must emit
    `references: []`, not omit the field and not put a single null
    entry."""
    from backend.exports.service import stream_jsonl_objects
    import json
    row = _fake_row(
        document_id="doc_a",
        ref_seq=None, ref_kanun_no=None, ref_kanun_ad=None,
        ref_madde=None, ref_fikra=None, ref_bent=None, ref_source_text=None,
    )
    lines = list(stream_jsonl_objects(iter([row])))
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["references"] == []


def test_stream_jsonl_handles_turkish_chars():
    """ensure_ascii=False so 'özelge' stays readable as 'özelge', not
    escaped to '\\u00f6zelge'. Critical for downstream readability and
    common-sense file size."""
    from backend.exports.service import stream_jsonl_objects
    row = _fake_row(doc_konu="Türkçe özelge başlık")
    lines = list(stream_jsonl_objects(iter([row])))
    assert "ö" in lines[0] and "ü" in lines[0]
    assert "\\u00" not in lines[0]
