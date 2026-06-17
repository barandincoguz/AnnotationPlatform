"""SQLite schema introspection for the Phase 4 Neon mirror (D-11).

Returns structured `TableSchema` objects assembled from PRAGMA queries plus
the original CREATE TABLE text (needed for `CHECK (...)` clauses and the
`INTEGER PRIMARY KEY AUTOINCREMENT` shape — neither of which surfaces in
`PRAGMA table_info`).

Pure functions. No I/O beyond the supplied sqlite3 connection.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


# Tables that are never mirrored (D-06 + security/operational exclusions).
_NON_PROJECT_TABLES = frozenset({
    "_outbox",
    "schema_migrations",
    "sqlite_sequence",
    # Session tokens are bearer credentials. Mirroring them would copy
    # plaintext credentials to a second database and make stale sessions
    # recoverable after an ephemeral-disk restore.
    "user_sessions",
})


@dataclass
class ColumnInfo:
    name: str
    sqlite_type: str          # raw declared type, e.g. "INTEGER", "TEXT", "TIMESTAMP"
    notnull: bool
    default: str | None
    is_pk: bool               # True if this column participates in the primary key
    is_autoincrement: bool    # True iff "INTEGER PRIMARY KEY AUTOINCREMENT" (only one column per table)


@dataclass
class ForeignKey:
    column: str
    ref_table: str
    ref_column: str
    on_delete: str | None     # e.g. "CASCADE", "SET NULL", or None for default RESTRICT
    on_update: str | None


@dataclass
class IndexInfo:
    name: str
    columns: list[str]
    unique: bool
    partial_where: str | None


@dataclass
class TableSchema:
    name: str
    columns: list[ColumnInfo]
    primary_key: list[str]                  # ordered list of PK column names (1 for single, 2+ for composite)
    foreign_keys: list[ForeignKey]
    indexes: list[IndexInfo]
    checks: list[str] = field(default_factory=list)
    create_sql: str = ""                    # original CREATE TABLE text for round-trip / autoincrement detection


def list_project_tables(conn: sqlite3.Connection) -> list[str]:
    """Return the names of in-scope tables, sorted.

    Excludes `_outbox` (D-06), `schema_migrations` (operational metadata),
    `user_sessions` (bearer credentials), and SQLite internal tables.
    """
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [r["name"] if isinstance(r, sqlite3.Row) else r[0]
            for r in rows
            if (r["name"] if isinstance(r, sqlite3.Row) else r[0]) not in _NON_PROJECT_TABLES]


def is_mirrored_table(table_name: str) -> bool:
    """Return whether a SQLite table is eligible for the Neon mirror."""
    return table_name not in _NON_PROJECT_TABLES and not table_name.startswith("sqlite_")


def _extract_checks(create_sql: str) -> list[str]:
    """Extract every top-level `CHECK (...)` body from a CREATE TABLE statement.

    Paren-matched, NOT regex — handles nested parens (e.g.
    `CHECK (severity IN ('info','warn','error'))`) correctly.
    """
    checks: list[str] = []
    i = 0
    s = create_sql
    n = len(s)
    while i < n:
        # Find next CHECK keyword (case-insensitive, must be word-boundaried).
        idx = s.lower().find("check", i)
        if idx == -1:
            break
        # Word-boundary check: char before is non-alnum, char after is whitespace or `(`.
        prev_ch = s[idx - 1] if idx > 0 else " "
        next_ch = s[idx + 5] if idx + 5 < n else ""
        if prev_ch.isalnum() or prev_ch == "_":
            i = idx + 5
            continue
        if next_ch != "(" and not next_ch.isspace():
            i = idx + 5
            continue
        # Find the opening paren.
        j = idx + 5
        while j < n and s[j].isspace():
            j += 1
        if j >= n or s[j] != "(":
            i = idx + 5
            continue
        # Paren-match.
        depth = 0
        body_start = j + 1
        k = j
        while k < n:
            c = s[k]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    checks.append(s[body_start:k].strip())
                    break
            k += 1
        i = k + 1
    return checks


def _detect_autoincrement(create_sql: str, pk_columns: list[str]) -> set[str]:
    """Return the set of column names declared `INTEGER PRIMARY KEY AUTOINCREMENT`.

    SQLite only allows AUTOINCREMENT on a single-column INTEGER PRIMARY KEY,
    so the result is at most one element. We scan the original CREATE TABLE
    text because `PRAGMA table_info` does not expose AUTOINCREMENT.
    """
    if len(pk_columns) != 1:
        return set()
    pk_col = pk_columns[0]
    # Look for the literal pattern (case-insensitive, whitespace-flexible).
    s = create_sql.lower()
    needle = "autoincrement"
    if needle not in s:
        return set()
    # Find the column definition line containing pk_col.
    # Conservative: if pk_col appears in the same logical statement segment
    # as both "primary key" and "autoincrement", classify it as auto.
    if pk_col.lower() in s and "primary key" in s and "autoincrement" in s:
        return {pk_col}
    return set()


def introspect_table(conn: sqlite3.Connection, table_name: str) -> TableSchema:
    """Build a TableSchema for `table_name` from PRAGMA + sqlite_master."""
    # Original CREATE TABLE text (for CHECK + AUTOINCREMENT detection).
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    create_sql = (row["sql"] if isinstance(row, sqlite3.Row) else row[0]) if row else ""

    # Columns + primary-key composition.
    columns: list[ColumnInfo] = []
    pk_pairs: list[tuple[int, str]] = []   # (pk-order, column-name)
    for c in conn.execute(f"PRAGMA table_info('{table_name}')").fetchall():
        if isinstance(c, sqlite3.Row):
            cname, ctype, cnotnull, cdflt, cpk = c["name"], c["type"], c["notnull"], c["dflt_value"], c["pk"]
        else:
            _cid, cname, ctype, cnotnull, cdflt, cpk = c
        if cpk and cpk > 0:
            pk_pairs.append((cpk, cname))
        columns.append(
            ColumnInfo(
                name=cname,
                sqlite_type=(ctype or "").strip(),
                notnull=bool(cnotnull),
                default=cdflt,
                is_pk=bool(cpk and cpk > 0),
                is_autoincrement=False,  # filled in below
            )
        )

    pk_pairs.sort(key=lambda p: p[0])
    primary_key = [c for _, c in pk_pairs]
    auto_set = _detect_autoincrement(create_sql, primary_key)
    for col in columns:
        if col.name in auto_set:
            col.is_autoincrement = True

    # Foreign keys.
    fks: list[ForeignKey] = []
    for f in conn.execute(f"PRAGMA foreign_key_list('{table_name}')").fetchall():
        if isinstance(f, sqlite3.Row):
            col, ref_t, ref_c = f["from"], f["table"], f["to"]
            on_del, on_upd = f["on_delete"], f["on_update"]
        else:
            _idx, _seq, ref_t, col, ref_c, on_upd, on_del, _match = f
        fks.append(ForeignKey(
            column=col,
            ref_table=ref_t,
            ref_column=ref_c,
            on_delete=(on_del or None) if (on_del and on_del.upper() != "NO ACTION") else None,
            on_update=(on_upd or None) if (on_upd and on_upd.upper() != "NO ACTION") else None,
        ))

    # Indexes — exclude SQLite-auto indexes (sqlite_autoindex_*).
    indexes: list[IndexInfo] = []
    for i in conn.execute(f"PRAGMA index_list('{table_name}')").fetchall():
        if isinstance(i, sqlite3.Row):
            iname, iuniq, iorigin = i["name"], i["unique"], i["origin"]
            ipartial = i["partial"] if "partial" in i.keys() else 0
        else:
            _seq, iname, iuniq, iorigin, ipartial = i
        if iname.startswith("sqlite_autoindex_"):
            continue
        cols = []
        for ci in conn.execute(f"PRAGMA index_info('{iname}')").fetchall():
            if isinstance(ci, sqlite3.Row):
                cols.append(ci["name"])
            else:
                cols.append(ci[2])
        # Partial-WHERE expression — extract from CREATE INDEX text in sqlite_master.
        partial_where: str | None = None
        if ipartial:
            ir = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                (iname,),
            ).fetchone()
            if ir is not None:
                idx_sql = ir["sql"] if isinstance(ir, sqlite3.Row) else ir[0]
                if idx_sql:
                    lower = idx_sql.lower()
                    where_pos = lower.find(" where ")
                    if where_pos != -1:
                        partial_where = idx_sql[where_pos + 7:].strip().rstrip(";")
        indexes.append(IndexInfo(
            name=iname,
            columns=cols,
            unique=bool(iuniq),
            partial_where=partial_where,
        ))

    checks = _extract_checks(create_sql) if create_sql else []

    return TableSchema(
        name=table_name,
        columns=columns,
        primary_key=primary_key,
        foreign_keys=fks,
        indexes=indexes,
        checks=checks,
        create_sql=create_sql or "",
    )
