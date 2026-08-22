"""v0019 — make pending scans fair and protect human work from cascades."""

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_docs_created_at "
        "ON documents_meta(created_at, document_id)"
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS protect_document_human_state_delete
        BEFORE DELETE ON documents_meta
        WHEN EXISTS (
            SELECT 1 FROM annotations WHERE document_id = OLD.document_id
        ) OR EXISTS (
            SELECT 1 FROM annotation_versions WHERE document_id = OLD.document_id
        ) OR EXISTS (
            SELECT 1 FROM annotation_audit_logs WHERE document_id = OLD.document_id
        ) OR EXISTS (
            SELECT 1 FROM drafts WHERE document_id = OLD.document_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'document has human annotation state');
        END
        """
    )
