"""Add composite index on annotation_versions(document_id, user_id).

The O(1) EXISTS check introduced in B-01 (replace COUNT(DISTINCT user_id)
full-chain scan with an incremental increment) requires a fast lookup of
the form:

    SELECT 1 FROM annotation_versions
    WHERE document_id = ? AND user_id = ?
    LIMIT 1

The existing idx_ver_doc_time covers (document_id, created_at DESC), which
is not a covering index for user_id.  idx_ver_user_time covers (user_id,
created_at DESC) — wrong leading column for this query.  Without a
dedicated (document_id, user_id) index, SQLite must scan all version rows
for the document to evaluate the user_id predicate, defeating the O(1)
goal at long chain lengths.
"""
import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ver_doc_user "
        "ON annotation_versions(document_id, user_id)"
    )
