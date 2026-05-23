"""TDD for SEC-1: NeonClient SQL builders must use psycopg.sql.Identifier
composables for table and column name identifiers — not f-string interpolation.

These tests directly exercise _build_upsert and _build_delete (the SQL builder
helpers) rather than routing through apply(), so they work without a live Neon
connection and are independent of dispatcher fixtures.
"""
from __future__ import annotations

import pytest
from psycopg import sql as pg_sql

from backend.mirror.neon_client import _build_delete, _build_upsert


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _as_str(query) -> str:
    """Return the SQL string representation of a Composed/Composable.

    Works whether the object is already a str (pre-fix, expected to fail these
    tests) or a psycopg.sql.Composed (post-fix).
    """
    if isinstance(query, str):
        return query
    # Composable.as_string() needs a connection for dialect; use a dummy
    # placeholder-compatible dialect via mogrify is not available without a
    # connection. Instead rely on str() which on psycopg3 Composed objects
    # renders the template with placeholder tokens intact — enough for
    # structural inspection.
    return str(query)


# ---------------------------------------------------------------------------
# SEC-1 core invariant: builders must return psycopg.sql.Composed, not str
# ---------------------------------------------------------------------------


def test_build_upsert_returns_composed_not_str():
    """_build_upsert must return a psycopg.sql.Composed, not a plain string."""
    query, args = _build_upsert("baran_users", ["id"], {"id": 1, "username": "alice"})
    assert isinstance(query, pg_sql.Composed), (
        f"_build_upsert returned {type(query).__name__!r}; "
        "expected psycopg.sql.Composed (sql.Identifier-based)"
    )


def test_build_delete_returns_composed_not_str():
    """_build_delete must return a psycopg.sql.Composed, not a plain string."""
    query, args = _build_delete("baran_users", ["id"], "42")
    assert isinstance(query, pg_sql.Composed), (
        f"_build_delete returned {type(query).__name__!r}; "
        "expected psycopg.sql.Composed (sql.Identifier-based)"
    )


# ---------------------------------------------------------------------------
# Identifier quoting: special characters in column names must not produce
# broken SQL (they should be double-quoted by psycopg.sql.Identifier).
# ---------------------------------------------------------------------------


def test_upsert_column_with_double_quote_is_safely_quoted():
    """A column name containing a double-quote must be handled by Identifier
    (which will double the quote inside the delimiters) — NOT produce raw
    f-string output that breaks SQL parsing.
    """
    # psycopg.sql.Identifier doubles embedded quotes: col"name → "col""name"
    tricky_col = 'col"name'
    query, args = _build_upsert("baran_users", ["id"], {"id": 1, tricky_col: "val"})
    assert isinstance(query, pg_sql.Composed), (
        "f-string path still active — _build_upsert returned str, not Composed"
    )
    # The rendered SQL must double-quote the identifier, not embed a raw "
    rendered = query.as_string(None)  # psycopg3: as_string(None) works for Identifiers
    assert '"col""name"' in rendered, (
        f"Identifier did not double-quote the embedded quote; rendered:\n{rendered}"
    )


def test_delete_pk_col_with_semicolon_is_safely_quoted():
    """A PK column name containing ';' must be double-quoted by Identifier,
    not interpolated raw into the WHERE clause.
    """
    evil_col = "id; DROP TABLE users; --"
    query, args = _build_delete("baran_users", [evil_col], "1")
    assert isinstance(query, pg_sql.Composed), (
        "f-string path still active — _build_delete returned str, not Composed"
    )
    rendered = query.as_string(None)
    # The rendered SQL must wrap the identifier in double-quotes.
    assert '"id; DROP TABLE users; --"' in rendered, (
        f"Identifier did not quote the evil column name; rendered:\n{rendered}"
    )
    # Must NOT appear as raw (unquoted) text in the SQL string.
    assert "DROP TABLE" not in rendered.replace('"id; DROP TABLE users; --"', ""), (
        "Unquoted injection text escaped into the SQL string"
    )


def test_upsert_do_nothing_on_pk_only_table_returns_composed():
    """PK-only table (DO NOTHING path) must also return Composed."""
    query, args = _build_upsert("baran_pk_only", ["id"], {"id": 99})
    assert isinstance(query, pg_sql.Composed), (
        f"DO-NOTHING branch returned {type(query).__name__!r}, not Composed"
    )


def test_build_upsert_composite_pk_returns_composed():
    """Composite-PK upsert (drafts pattern) must return Composed."""
    query, args = _build_upsert(
        "baran_drafts",
        ["document_id", "user_id"],
        {"document_id": "d1", "user_id": 7, "references_json": "[]"},
    )
    assert isinstance(query, pg_sql.Composed)


def test_build_delete_composite_pk_returns_composed():
    """Composite-PK delete must return Composed."""
    query, args = _build_delete("baran_drafts", ["document_id", "user_id"], "d1::7")
    assert isinstance(query, pg_sql.Composed)
