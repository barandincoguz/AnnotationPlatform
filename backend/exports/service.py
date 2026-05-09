"""Annotation dataset export — pure-function service layer.

Three things here:
  1. build_query(filters) → (sql, params) for parameterized cursor execute
  2. stream_csv_rows(cursor) → Iterator[str] of CSV-encoded lines (Task 3)
  3. stream_jsonl_objects(cursor) → Iterator[str] of NDJSON-encoded lines (Task 4)

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
    "is_completed",
    "completed_by_user_id",
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


_BASE_SELECT = """\
SELECT d.document_id  AS document_id,
       d.sayi         AS doc_sayi,
       d.tarih        AS doc_tarih,
       d.konu         AS doc_konu,
       a.last_editor_user_id,
       ue.username    AS last_editor_username,
       a.updated_at   AS last_edited_at,
       a.is_completed,
       a.completed_by_user_id,
       uc.username    AS completed_by_username,
       a.edit_count,
       a.unique_users_count,
       ar.seq         AS ref_seq,
       ar.kanun_no, ar.kanun_ad, ar.madde, ar.fikra, ar.bent, ar.source_text
FROM annotations a
JOIN documents_meta d           ON a.document_id = d.document_id
LEFT JOIN users ue              ON a.last_editor_user_id = ue.id
LEFT JOIN users uc              ON a.completed_by_user_id = uc.id
LEFT JOIN annotation_references ar ON ar.document_id = a.document_id
WHERE 1=1"""


def build_query(filters: ExportFilters) -> tuple[str, tuple]:
    """Build the parameterized SQL for the requested filter slice.

    Returns (sql_string, params_tuple). The cursor's caller is responsible
    for `db.execute(sql, params)` and iteration. SQL is constructed from a
    fixed _BASE_SELECT plus zero or more conditional `AND ...` clauses
    appended in deterministic order; all bound values flow through `?`
    placeholders so user input never enters the SQL string itself.

    The SELECT always returns the same column shape (CSV_COLUMNS contract);
    the conditional WHERE clauses just narrow which rows match.
    """
    sql_parts = [_BASE_SELECT]
    params: list = []

    if filters.status == "completed":
        sql_parts.append("  AND a.is_completed = 1")

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
            "  AND (a.last_editor_user_id = ? OR a.completed_by_user_id = ?)"
        )
        params.append(filters.user_id)
        params.append(filters.user_id)

    sql_parts.append("ORDER BY a.document_id, ar.seq")

    return "\n".join(sql_parts), tuple(params)
