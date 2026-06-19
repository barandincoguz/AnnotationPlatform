"""SQLite trigger generator for the Phase 4 outbox capture (MIRROR-01).

Produces one `CREATE TRIGGER IF NOT EXISTS` per (in-scope table, op) pair —
22 tables × 3 ops = **66 triggers**. Each trigger body INSERTs a single
`_outbox` row carrying the JSON-encoded payload, the pk_value string per
D-03, and the operation type.

Key conventions:
  - Trigger name: `_outbox_<table>_<ins|upd|del>` (deterministic).
  - Payload: `json_object('col_a', NEW.col_a, ...)` for INSERT/UPDATE,
             `json_object('col_a', OLD.col_a, ...)` for DELETE.
  - pk_value: `CAST(NEW.<col> AS TEXT)` for single PK,
              `NEW.col_a || '::' || NEW.col_b` for composite PK.
  - created_at: `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` (ISO-8601 UTC).
  - All triggers idempotent (`IF NOT EXISTS`).
  - NO `--` line comments inside trigger bodies (the runner's `_split_sql`
    strips them and would break trigger SQL).

Also exports `pk_columns_manifest`: the canonical map of in-scope table
name → ordered list of primary-key column names. Consumed by:
  - the NeonClient upsert SQL (Task 7),
  - the dispatcher (Task 8),
  - the backfill script (Task 11)
for `ON CONFLICT (<pk_cols>) DO UPDATE`.
"""
from __future__ import annotations

import sqlite3
from functools import lru_cache

from backend.migrations.helpers.schema_introspect import (
    TableSchema,
    introspect_table,
    list_project_tables,
)

OUTBOX_EXCLUDED_TABLES = frozenset({
    "user_sessions",
    "document_locks",
    "system_events",
})


# ----- Per-op trigger SQL --------------------------------------------------

_OP_TOKEN = {
    "INSERT": ("ins", "NEW"),
    "UPDATE": ("upd", "NEW"),
    "DELETE": ("del", "OLD"),
}


def _pk_value_expr(schema: TableSchema, ref: str) -> str:
    """Build the `pk_value` SQL expression for one row reference (NEW / OLD).

    Single-column PK -> `CAST(NEW.<col> AS TEXT)`.
    Composite PK    -> `NEW.col_a || '::' || NEW.col_b` (concat each cast to TEXT
                       by SQLite's implicit `||` operator, which coerces to TEXT).
    """
    pk_cols = schema.primary_key
    if not pk_cols:
        raise ValueError(f"table {schema.name!r} has no primary key — cannot generate trigger")
    if len(pk_cols) == 1:
        return f"CAST({ref}.{pk_cols[0]} AS TEXT)"
    # Composite: cast each piece to TEXT explicitly and join with '::'.
    parts = [f"CAST({ref}.{c} AS TEXT)" for c in pk_cols]
    return " || '::' || ".join(parts)


def _payload_expr(schema: TableSchema, ref: str) -> str:
    """`json_object('col_a', NEW.col_a, 'col_b', NEW.col_b, ...)` over every column."""
    parts: list[str] = []
    for col in schema.columns:
        parts.append(f"'{col.name}'")
        # Session rows are local-only bearer credentials. Nulling this
        # reference keeps activity events mirrorable during rolling upgrades
        # without requiring a remote session row.
        if schema.name == "activity_events" and col.name == "session_id":
            parts.append("NULL")
        else:
            parts.append(f"{ref}.{col.name}")
    return f"json_object({', '.join(parts)})"


def build_triggers_for_table(schema: TableSchema) -> list[str]:
    """Return 3 CREATE TRIGGER statements (INSERT, UPDATE, DELETE) for one table."""
    out: list[str] = []
    for op in ("INSERT", "UPDATE", "DELETE"):
        suffix, ref = _OP_TOKEN[op]
        trigger_name = f"_outbox_{schema.name}_{suffix}"
        when = {"INSERT": "AFTER INSERT", "UPDATE": "AFTER UPDATE", "DELETE": "AFTER DELETE"}[op]
        pk_expr = _pk_value_expr(schema, ref)
        payload_expr = _payload_expr(schema, ref)
        stmt = (
            f"CREATE TRIGGER IF NOT EXISTS {trigger_name} "
            f"{when} ON {schema.name} "
            f"BEGIN "
            f"INSERT INTO _outbox(table_name, op, pk_value, payload_json, created_at) "
            f"VALUES ("
            f"'{schema.name}', '{op}', {pk_expr}, {payload_expr}, "
            f"strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
            f"); "
            f"END"
        )
        out.append(stmt)
    return out


# ----- Aggregate over all in-scope tables ----------------------------------

def _collect_schemas(conn: sqlite3.Connection) -> list[TableSchema]:
    return [
        introspect_table(conn, table)
        for table in list_project_tables(conn)
        if table not in OUTBOX_EXCLUDED_TABLES
    ]


def build_all_triggers(conn: sqlite3.Connection) -> list[str]:
    """Return the full ordered list of trigger CREATE statements.

    Result length is exactly **66** (22 tables × 3 ops) under the
    canonical project schema.
    """
    out: list[str] = []
    for schema in _collect_schemas(conn):
        out.extend(build_triggers_for_table(schema))
    return out


# ----- pk_columns_manifest (first-class export, lazy-loaded) ---------------

_MANIFEST_CACHE: dict[str, list[str]] | None = None


def build_pk_columns_manifest(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Build the {table → [pk_col, ...]} map from the supplied SQLite connection.

    Consumed by NeonClient (Task 7), dispatcher (Task 8), backfill (Task 11)
    to emit correct `ON CONFLICT (<pk_cols>) DO UPDATE ...` per table.
    """
    return {s.name: list(s.primary_key) for s in _collect_schemas(conn)}


def pk_columns_manifest_for(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Cached variant: compute once per process, keyed off the conn's DB path.

    The dispatcher / backfill / NeonClient call this on the hot path; we
    don't want to re-introspect every table per outbox row. Cache lives at
    module scope; resets via `_reset_manifest_cache()` for tests.
    """
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is None:
        _MANIFEST_CACHE = build_pk_columns_manifest(conn)
    return _MANIFEST_CACHE


def _reset_manifest_cache() -> None:
    """Test-only: clear the module-level cache between fresh in-memory DBs."""
    global _MANIFEST_CACHE
    _MANIFEST_CACHE = None


# Module-level lazy proxy. Importable as `pk_columns_manifest` but only
# materializes against the live `config.DB_PATH` on first access.
class _ManifestProxy(dict):
    """Read-only-ish dict that loads on first access via the project DB.

    Importers that already have a connection should prefer
    `build_pk_columns_manifest(conn)` (explicit) — this proxy exists for
    legacy / convenience call sites.
    """
    def _ensure_loaded(self) -> None:
        if not super().__len__():
            from backend.shared.db import connect
            from backend import config
            conn = connect(config.DB_PATH)
            try:
                for k, v in build_pk_columns_manifest(conn).items():
                    dict.__setitem__(self, k, v)
            finally:
                conn.close()

    def __getitem__(self, k):
        self._ensure_loaded()
        return super().__getitem__(k)

    def __contains__(self, k):  # type: ignore[override]
        self._ensure_loaded()
        return super().__contains__(k)

    def __len__(self):  # type: ignore[override]
        self._ensure_loaded()
        return super().__len__()

    def keys(self):  # type: ignore[override]
        self._ensure_loaded()
        return super().keys()

    def items(self):  # type: ignore[override]
        self._ensure_loaded()
        return super().items()

    def get(self, k, default=None):
        self._ensure_loaded()
        return super().get(k, default)


pk_columns_manifest = _ManifestProxy()
