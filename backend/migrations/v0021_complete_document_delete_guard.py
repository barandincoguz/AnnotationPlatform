"""v0021 — protect denormalized human references on existing databases."""

import sqlite3

from backend.migrations.v0019_document_delete_guard import (
    DOCUMENT_DELETE_GUARD,
    install_document_delete_guard,
)


def up(conn: sqlite3.Connection) -> None:
    conn.execute(f"DROP TRIGGER IF EXISTS {DOCUMENT_DELETE_GUARD}")
    install_document_delete_guard(conn)
