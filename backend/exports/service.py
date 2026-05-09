"""Annotation dataset export — pure-function service layer.

Three things here:
  1. build_query(filters) → (sql, params) for parameterized cursor execute
  2. stream_csv_rows(cursor) → Iterator[str] of CSV-encoded lines (Task 3)
  3. stream_jsonl_objects(cursor) → Iterator[str] of NDJSON-encoded lines (Task 4)

No async, no DB session state, no caller-side mutation — generators
consume a cursor passed in and yield bytes for FastAPI's
StreamingResponse to chunk to the client.
"""
import csv
import io
import json
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


def stream_csv_rows(cursor) -> Iterator[str]:
    """Yield CSV-encoded chunks from a SQLite cursor (or any iterable of
    tuples in _BASE_SELECT column order). Header is the first chunk,
    even if cursor is empty.

    Uses a per-row io.StringIO buffer + seek/truncate so memory stays
    bounded regardless of result size.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header
    writer.writerow(CSV_COLUMNS)
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate()

    for row in cursor:
        # NULL → empty string (csv writer renders None as 'None' otherwise)
        clean = tuple("" if v is None else v for v in row)
        writer.writerow(clean)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()


def stream_jsonl_objects(cursor) -> Iterator[str]:
    """Yield NDJSON-encoded annotation objects, one per line, with
    references nested as an array. Cursor MUST be ordered by
    (document_id, ref_seq) so all references of one annotation are
    contiguous; we accumulate and flush whenever document_id changes.

    Tuple field positions follow the SELECT order in _BASE_SELECT.
    """
    current_doc_id: str | None = None
    current_obj: dict | None = None

    def _flush():
        if current_obj is not None:
            return json.dumps(current_obj, ensure_ascii=False) + "\n"
        return None

    for row in cursor:
        (document_id, doc_sayi, doc_tarih, doc_konu,
         last_editor_user_id, last_editor_username, last_edited_at,
         is_completed, completed_by_user_id, completed_by_username,
         edit_count, unique_users_count,
         ref_seq, ref_kanun_no, ref_kanun_ad,
         ref_madde, ref_fikra, ref_bent, ref_source_text) = row

        if document_id != current_doc_id:
            chunk = _flush()
            if chunk is not None:
                yield chunk
            current_doc_id = document_id
            current_obj = {
                "document_id": document_id,
                "document": {
                    "sayi": doc_sayi,
                    "tarih": doc_tarih,
                    "konu": doc_konu,
                },
                "annotation": {
                    "last_editor": (
                        {"id": last_editor_user_id, "username": last_editor_username}
                        if last_editor_user_id is not None else None
                    ),
                    "last_edited_at": last_edited_at,
                    "is_completed": bool(is_completed),
                    "completed_by": (
                        {"id": completed_by_user_id, "username": completed_by_username}
                        if completed_by_user_id is not None else None
                    ),
                    "edit_count": edit_count,
                    "unique_users_count": unique_users_count,
                },
                "references": [],
            }

        # Reference is present iff the LEFT JOIN found a row.
        if ref_seq is not None:
            # current_obj is guaranteed non-None at this point: on the very
            # first iteration document_id != None triggers the conditional
            # block above which sets current_obj. Assert silences Pyright
            # and serves as a runtime tripwire if the loop logic ever
            # changes.
            assert current_obj is not None
            current_obj["references"].append({
                "seq": ref_seq,
                "kanun_no": ref_kanun_no,
                "kanun_ad": ref_kanun_ad,
                "madde": ref_madde,
                "fikra": ref_fikra,
                "bent": ref_bent,
                "source_text": ref_source_text,
            })

    chunk = _flush()
    if chunk is not None:
        yield chunk
