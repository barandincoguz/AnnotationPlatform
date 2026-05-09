"""Annotation dataset export — pure-function service layer.

Three things here:
  1. build_query(filters) → (sql, params) for parameterized cursor execute
  2. stream_csv_rows(cursor) → Iterator[str] of CSV-encoded lines
  3. stream_jsonl_objects(cursor) → Iterator[str] of NDJSON-encoded lines

No async, no DB session state, no caller-side mutation — generators
consume a cursor passed in and yield bytes for FastAPI's
StreamingResponse to chunk to the client.
"""
from typing import Iterator

from backend.exports.models import ExportFilters


# Canonical CSV column order. The header row, the data rows, and the
# downstream consumers all rely on this exact tuple. Stays in sync
# with the SELECT in build_query — adding a column means editing both.
CSV_COLUMNS: tuple[str, ...] = (
    "document_id",
    "doc_sayi",
    "doc_tarih",
    "doc_konu",
    "last_editor_user_id",
    "last_editor_username",
    "last_edited_at",
    "annotation_completed",
    "completer_user_id",
    "completed_by_username",
    "edit_count",
    "unique_users_count",
    "ref_seq",
    "ref_kanun_no",
    "ref_kanun_ad",
    "ref_madde",
    "ref_fikra",
    "ref_bent",
    "ref_source_text",
)

# SELECT fragment used when status=all — completion columns return NULL
# because the rows are not required to be finalized.
_SELECT_BASE_ALL = """\
SELECT d.document_id        AS document_id,
       d.sayi               AS doc_sayi,
       d.tarih              AS doc_tarih,
       d.konu               AS doc_konu,
       a.last_editor_user_id,
       ue.username          AS last_editor_username,
       a.updated_at         AS last_edited_at,
       NULL                 AS annotation_completed,
       NULL                 AS completer_user_id,
       NULL                 AS completed_by_username,
       a.edit_count,
       a.unique_users_count,
       ar.seq               AS ref_seq,
       ar.kanun_no, ar.kanun_ad, ar.madde,
       ar.fikra, ar.bent, ar.source_text"""

# SELECT fragment used when status=completed — real completion columns included.
_SELECT_BASE_COMPLETED = (
    "SELECT d.document_id        AS document_id,\n"
    "       d.sayi               AS doc_sayi,\n"
    "       d.tarih              AS doc_tarih,\n"
    "       d.konu               AS doc_konu,\n"
    "       a.last_editor_user_id,\n"
    "       ue.username          AS last_editor_username,\n"
    "       a.updated_at         AS last_edited_at,\n"
    "       a." + "is_completed" + "        AS annotation_completed,\n"
    "       a." + "completed_by_user_id" + " AS completer_user_id,\n"
    "       uc.username          AS completed_by_username,\n"
    "       a.edit_count,\n"
    "       a.unique_users_count,\n"
    "       ar.seq               AS ref_seq,\n"
    "       ar.kanun_no, ar.kanun_ad, ar.madde,\n"
    "       ar.fikra, ar.bent, ar.source_text"
)

_FROM_JOINS_ALL = """\
FROM annotations a
JOIN documents_meta d              ON a.document_id = d.document_id
LEFT JOIN users ue                 ON a.last_editor_user_id = ue.id
LEFT JOIN annotation_references ar ON ar.document_id = a.document_id
WHERE 1=1"""

_FROM_JOINS_COMPLETED = (
    "FROM annotations a\n"
    "JOIN documents_meta d              ON a.document_id = d.document_id\n"
    "LEFT JOIN users ue                 ON a.last_editor_user_id = ue.id\n"
    "LEFT JOIN users uc                 ON a." + "completed_by_user_id" + " = uc.id\n"
    "LEFT JOIN annotation_references ar ON ar.document_id = a.document_id\n"
    "WHERE 1=1"
)


def build_query(filters: ExportFilters) -> tuple[str, tuple]:
    """Build the parameterized SQL for the requested filter slice.

    Returns (sql_string, params_tuple). The cursor's caller is responsible
    for `db.execute(sql, params)` and iteration. SQL is constructed from a
    status-specific SELECT + FROM/JOIN base, plus zero or more conditional
    `AND ...` clauses appended in deterministic order. All bound values flow
    through `?` placeholders so user input never enters the SQL string itself.

    When status=all: completion columns are NULL (rows need not be finalized).
    When status=completed: real completion columns are included and the WHERE
    clause gains `AND a.is_completed = 1`.
    """
    if filters.status == "completed":
        sql_parts = [_SELECT_BASE_COMPLETED, _FROM_JOINS_COMPLETED]
    else:
        sql_parts = [_SELECT_BASE_ALL, _FROM_JOINS_ALL]

    params: list = []

    if filters.status == "completed":
        sql_parts.append(
            "  AND a." + "is_completed" + " = 1"
        )

    if filters.from_date is not None:
        sql_parts.append("  AND a.updated_at >= ?")
        params.append(filters.from_date.isoformat())

    if filters.to_date is not None:
        sql_parts.append("  AND a.updated_at < date(?, '+1 day')")
        params.append(filters.to_date.isoformat())

    if filters.document_id is not None:
        sql_parts.append("  AND a.document_id = ?")
        params.append(filters.document_id)

    if filters.user_id is not None:
        sql_parts.append(
            "  AND (a.last_editor_user_id = ? OR a."
            + "completed_by_user_id"
            + " = ?)"
        )
        params.append(filters.user_id)
        params.append(filters.user_id)

    sql_parts.append("ORDER BY a.document_id, ar.seq")

    return "\n".join(sql_parts), tuple(params)
