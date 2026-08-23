"""v0019 — make pending scans fair and protect human work from cascades."""

import sqlite3


DOCUMENT_DELETE_GUARD = "protect_document_human_state_delete"


def install_document_delete_guard(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TRIGGER IF NOT EXISTS {DOCUMENT_DELETE_GUARD}
        BEFORE DELETE ON documents_meta
        WHEN EXISTS (
            SELECT 1 FROM annotations WHERE document_id = OLD.document_id
        ) OR EXISTS (
            SELECT 1 FROM annotation_versions WHERE document_id = OLD.document_id
        ) OR EXISTS (
            SELECT 1 FROM annotation_audit_logs WHERE document_id = OLD.document_id
        ) OR EXISTS (
            SELECT 1 FROM drafts WHERE document_id = OLD.document_id
        ) OR EXISTS (
            SELECT 1 FROM annotation_references WHERE document_id = OLD.document_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'document has human annotation state');
        END
        """
    )


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_docs_created_at "
        "ON documents_meta(created_at, document_id)"
    )
    install_document_delete_guard(conn)
