"""SQLite schema → baran_* Postgres DDL generator (Phase 4, D-11).

Pure function. Consumes `TableSchema` from schema_introspect and emits a
list of idempotent CREATE-TABLE/CREATE-INDEX Postgres statements.

Type mapping (D-11):
  - INTEGER PRIMARY KEY AUTOINCREMENT  → bigserial PRIMARY KEY
  - INTEGER (non-PK or non-auto PK)    → bigint
  - TEXT                               → text
  - REAL                               → double precision
  - TIMESTAMP (TEXT-stored)            → text (preserves ISO-8601, no tz parse)
  - column name ending in `_json`      → jsonb
  - CHECK constraints                  → copied verbatim
  - REFERENCES <t> → REFERENCES baran_<t>
  - composite PK                       → PRIMARY KEY (col_a, col_b)

Idempotent: every CREATE uses `IF NOT EXISTS`.

`_outbox` and `schema_migrations` are NEVER in the output (D-06 + operator
discretion).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict, deque

from backend.migrations.helpers.schema_introspect import (
    ColumnInfo,
    TableSchema,
    introspect_table,
    is_mirrored_table,
    list_project_tables,
)
from backend.quality.provenance import TRUSTED_G0_MODEL_FINGERPRINTS


_TRUSTED_PREDICTION_FINGERPRINTS_SQL = ", ".join(
    f"'{fingerprint}'" for fingerprint in sorted(TRUSTED_G0_MODEL_FINGERPRINTS)
)

PREDICTION_PROVENANCE_FUNCTION_DDL = f"""CREATE OR REPLACE FUNCTION baran_enforce_model_prediction_provenance()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.generation <> 'G0'
       OR NEW.source <> 'dqcheck_agent'
       OR COALESCE(NEW.operational_json->>'backend', '') <> 'mlx-g0'
       OR NEW.model_fingerprint !~ '^[0-9a-f]{{64}}$'
       OR NEW.model_fingerprint NOT IN ({_TRUSTED_PREDICTION_FINGERPRINTS_SQL})
       OR NEW.text_sha256 !~ '^[0-9a-f]{{64}}$'
    THEN
        RAISE EXCEPTION 'untrusted model prediction provenance';
    END IF;
    RETURN NEW;
END;
$$"""

PREDICTION_PROVENANCE_TRIGGER_DDL = """DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'baran_protect_model_prediction_provenance'
          AND tgrelid = 'baran_model_predictions'::regclass
    ) THEN
        CREATE TRIGGER baran_protect_model_prediction_provenance
        BEFORE INSERT OR UPDATE ON baran_model_predictions
        FOR EACH ROW
        EXECUTE FUNCTION baran_enforce_model_prediction_provenance();
    END IF;
END;
$$"""

PREDICTION_PROVENANCE_DDL = (
    PREDICTION_PROVENANCE_FUNCTION_DDL,
    PREDICTION_PROVENANCE_TRIGGER_DDL,
)


# ----- Type mapping --------------------------------------------------------

def _pg_type_for(col: ColumnInfo) -> str:
    """Map a single SQLite column to its Postgres type per D-11.

    Special cases:
      - INTEGER PRIMARY KEY AUTOINCREMENT  → emitted by caller as
        "bigserial PRIMARY KEY"; this helper returns "bigserial".
      - `*_json` column name             → jsonb (heuristic per Task 3 brief).
    """
    name_lower = col.name.lower()
    if col.is_autoincrement:
        return "bigserial"
    if name_lower.endswith("_json"):
        return "jsonb"
    t = col.sqlite_type.upper().strip()
    if t == "INTEGER":
        return "bigint"
    if t == "REAL":
        return "double precision"
    if t == "TIMESTAMP":
        # Preserve ISO-8601 strings as-is — no tz parsing.
        return "text"
    # TEXT, or any unknown/empty → text. SQLite's affinity is liberal; this is
    # the safe default for project columns.
    return "text"


# ----- Per-table DDL -------------------------------------------------------

def build_pg_ddl_for_table(schema: TableSchema) -> list[str]:
    """Emit the list of Postgres SQL statements creating baran_<table>.

    Always emits one `CREATE TABLE IF NOT EXISTS baran_<table>(...)` plus one
    `CREATE INDEX IF NOT EXISTS baran_<idx>(...)` per non-PK SQLite index.
    """
    mirror_name = f"baran_{schema.name}"
    column_lines: list[str] = []

    # Pre-compute FK lookup for inline-PK case: an inline PK column can carry
    # a single-column FK on the same line ("col TEXT PRIMARY KEY REFERENCES
    # documents_meta(document_id)"). For composite PKs the PK clause is a
    # trailing constraint; FKs still emit as separate constraint lines.
    fk_by_col: dict[str, list] = defaultdict(list)
    for fk in schema.foreign_keys:
        fk_by_col[fk.column].append(fk)

    composite_pk = len(schema.primary_key) > 1
    single_auto_pk = (
        not composite_pk
        and len(schema.primary_key) == 1
        and any(c.is_pk and c.is_autoincrement for c in schema.columns)
    )

    for col in schema.columns:
        pg_type = _pg_type_for(col)
        parts: list[str] = [col.name, pg_type]
        # Inline PRIMARY KEY only for single-column PK.
        if not composite_pk and col.is_pk:
            if single_auto_pk:
                # `bigserial PRIMARY KEY` (bigserial implies the sequence + NOT NULL).
                parts.append("PRIMARY KEY")
            else:
                # Non-auto single PK (e.g. TEXT PRIMARY KEY): "<col> <type> PRIMARY KEY"
                parts.append("PRIMARY KEY")
        else:
            # Non-PK column → preserve NOT NULL.
            if col.notnull:
                parts.append("NOT NULL")
        # Default value (skip for bigserial — its default is the sequence).
        if col.default is not None and not (col.is_autoincrement):
            # SQLite default values come back as the raw token (already-quoted
            # for strings). Postgres accepts the same shape for our project
            # defaults ("'[]'", "0", "1", "datetime('now')" we don't use).
            parts.append(f"DEFAULT {col.default}")
        # Inline FK only when this column is a single FK and NOT part of a
        # composite PK (the composite-PK trailing PRIMARY KEY clause comes
        # after; FK columns can still be inline because PK/FK live in
        # separate slots).
        for fk in fk_by_col.get(col.name, []):
            # A mirrored table may reference local-only operational data.
            # Omitting that FK keeps the mirror schema self-contained while
            # preserving the scalar value for analytics.
            if not is_mirrored_table(fk.ref_table):
                continue
            ref_pg = f"baran_{fk.ref_table}"
            fk_parts = [f"REFERENCES {ref_pg}({fk.ref_column})"]
            if fk.on_delete:
                fk_parts.append(f"ON DELETE {fk.on_delete}")
            if fk.on_update:
                fk_parts.append(f"ON UPDATE {fk.on_update}")
            parts.append(" ".join(fk_parts))
        column_lines.append("    " + " ".join(parts))

    # Composite PK clause.
    if composite_pk:
        pk_list = ", ".join(schema.primary_key)
        column_lines.append(f"    PRIMARY KEY ({pk_list})")

    # CHECK clauses — copied verbatim per D-11.
    for check_body in schema.checks:
        column_lines.append(f"    CHECK ({check_body})")

    body = ",\n".join(column_lines)
    create_table = (
        f"CREATE TABLE IF NOT EXISTS {mirror_name} (\n"
        f"{body}\n"
        f")"
    )

    statements: list[str] = [create_table]

    # Indexes. Strip the SQLite name's table prefix where present and prefix
    # with `baran_` (operator-readability: clear they belong to the mirror).
    for idx in schema.indexes:
        # Skip primary key auto-indexes — they're already implied by PRIMARY KEY.
        # (We already excluded sqlite_autoindex_* in introspect; the user-defined
        # `idx_*_pk` style indexes, if any, are intentional and re-emit.)
        if idx.unique and idx.columns == schema.primary_key:
            # Redundant with PRIMARY KEY — skip.
            continue
        pg_idx_name = f"baran_{idx.name}"
        unique_kw = "UNIQUE " if idx.unique else ""
        cols = ", ".join(idx.columns)
        stmt = f"CREATE {unique_kw}INDEX IF NOT EXISTS {pg_idx_name} ON {mirror_name}({cols})"
        if idx.partial_where:
            stmt += f" WHERE {idx.partial_where}"
        statements.append(stmt)

    return statements


# ----- Topological sort + full-script generator ----------------------------

def _topological_sort(schemas: dict[str, TableSchema]) -> list[str]:
    """Kahn's algorithm: parents before children (FK references).

    Raises ValueError on a cycle, listing the offending tables.
    """
    # Edge: child depends_on parent (FK target). We emit parents first.
    parents_of: dict[str, set[str]] = {t: set() for t in schemas}
    children_of: dict[str, set[str]] = {t: set() for t in schemas}
    for t, s in schemas.items():
        for fk in s.foreign_keys:
            if fk.ref_table in schemas and fk.ref_table != t:
                parents_of[t].add(fk.ref_table)
                children_of[fk.ref_table].add(t)

    # Roots: no parents.
    queue = deque(sorted(t for t in schemas if not parents_of[t]))
    out: list[str] = []
    seen_count = 0
    while queue:
        n = queue.popleft()
        out.append(n)
        seen_count += 1
        for child in sorted(children_of[n]):
            parents_of[child].discard(n)
            if not parents_of[child]:
                queue.append(child)

    if seen_count != len(schemas):
        unsorted = [t for t in schemas if t not in out]
        raise ValueError(f"FK cycle detected; unsorted tables: {sorted(unsorted)}")

    return out


def build_all_pg_ddl(conn: sqlite3.Connection) -> str:
    """Generate the full idempotent Postgres DDL script for all in-scope tables.

    Output begins with a deterministic comment block (no timestamp — kept
    stable so re-running the regen script produces byte-identical output
    against an unchanged schema). Caller is responsible for the actual file
    write.
    """
    table_names = list_project_tables(conn)
    schemas: dict[str, TableSchema] = {
        t: introspect_table(conn, t) for t in table_names
    }
    ordered = _topological_sort(schemas)

    header = (
        "-- ============================================================\n"
        "-- baran_* mirror DDL — Phase 4 generated artifact.\n"
        f"-- Source: SQLite project schema ({len(table_names)} in-scope tables).\n"
        "-- Regenerate with: python -m scripts.regen_neon_ddl\n"
        "-- Idempotent: every CREATE uses IF NOT EXISTS.\n"
        "-- ============================================================\n"
    )

    blocks: list[str] = [header]
    for t in ordered:
        statements = build_pg_ddl_for_table(schemas[t])
        block = ";\n\n".join(statements) + ";\n"
        blocks.append(block)
    if "model_predictions" in schemas:
        blocks.append(";\n\n".join(PREDICTION_PROVENANCE_DDL) + ";\n")
    blocks.append("COMMIT;\n")
    return "\n".join(blocks)
