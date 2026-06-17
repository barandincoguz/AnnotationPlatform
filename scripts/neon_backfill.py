"""One-shot SQLite → Neon Postgres backfill for Phase 4 (MIRROR-06).

Reads every row from every in-scope SQLite table in FK
topological order (parents first; reuses the postgres_ddl sort), and
INSERTs each into the corresponding baran_<table> via
`INSERT ... ON CONFLICT (<pk_cols>) DO UPDATE SET <non-pk-cols> = EXCLUDED.<col>`.

Idempotent: re-running against an already-populated Neon DB produces no
net row change (every row resolves to its current state via the upsert).

Usage:
    set -a; source .env.local; set +a
    .venv/bin/python -m scripts.neon_backfill                    # full backfill
    .venv/bin/python -m scripts.neon_backfill --dry-run          # count only
    .venv/bin/python -m scripts.neon_backfill --table users      # one table
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

from backend import config
from backend.shared.db import connect
from backend.migrations.helpers.schema_introspect import (
    introspect_table,
    list_project_tables,
)
from backend.migrations.helpers.postgres_ddl import _topological_sort


BATCH_ROWS = 500


def _pk_cols_for(table: str, sqlite_conn) -> list[str]:
    s = introspect_table(sqlite_conn, table)
    return list(s.primary_key)


def _serialize_value(col_name: str, value: Any) -> Any:
    """Match NeonClient's *_json passthrough."""
    if col_name.endswith("_json"):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return value
    return value


def _build_upsert_sql(table: str, columns: list[str], pk_cols: list[str]) -> str:
    placeholders = ", ".join(["%s"] * len(columns))
    col_list = ", ".join(columns)
    non_pk = [c for c in columns if c not in set(pk_cols)]
    if non_pk:
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_pk)
        on_conflict = f"ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET {set_clause}"
    else:
        on_conflict = f"ON CONFLICT ({', '.join(pk_cols)}) DO NOTHING"
    return (
        f"INSERT INTO baran_{table} ({col_list}) "
        f"VALUES ({placeholders}) "
        f"{on_conflict}"
    )


def _ordered_tables(sqlite_conn) -> list[str]:
    table_names = list_project_tables(sqlite_conn)
    schemas = {t: introspect_table(sqlite_conn, t) for t in table_names}
    return _topological_sort(schemas)


def backfill_table(
    sqlite_conn,
    pg_apply: Callable[[str, list], None],
    table: str,
    *,
    dry_run: bool = False,
    log: Callable[[str], None] = print,
) -> int:
    """Stream rows from SQLite → upsert into baran_<table>.

    `pg_apply(sql, values)` is the per-row writer (psycopg cursor.execute for
    production, an accumulator for tests). Returns the row count processed.
    """
    pk_cols = _pk_cols_for(table, sqlite_conn)
    rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
    total = len(rows)
    if total == 0:
        log(f"{table}: 0/0 done (empty)")
        return 0
    if dry_run:
        log(f"{table}: dry-run — {total} rows would be upserted")
        return total

    # All rows in this table share the same column ordering.
    columns = list(rows[0].keys()) if total else []
    sql = _build_upsert_sql(table, columns, pk_cols)

    done = 0
    for r in rows:
        values = [_serialize_value(c, r[c]) for c in columns]
        pg_apply(sql, values)
        done += 1
        if done % BATCH_ROWS == 0:
            log(f"{table}: {done}/{total} done")
    log(f"{table}: {done}/{total} done")
    return done


def run_backfill(
    sqlite_conn,
    pg_apply: Callable[[str, list], None],
    *,
    tables_filter: list[str] | None = None,
    dry_run: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, int]:
    """Execute the backfill across all in-scope tables (or a subset).

    Returns a {table: row_count} dict. Tables run in FK-topological order.
    """
    order = _ordered_tables(sqlite_conn)
    if tables_filter:
        order = [t for t in order if t in set(tables_filter)]
        if not order:
            raise SystemExit(f"no in-scope table matched filter {tables_filter}")
    counts: dict[str, int] = {}
    for t in order:
        counts[t] = backfill_table(sqlite_conn, pg_apply, t, dry_run=dry_run, log=log)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SQLite → Neon backfill (Phase 4)")
    parser.add_argument("--dry-run", action="store_true", help="report row counts; no writes")
    parser.add_argument("--table", action="append", default=None,
                        help="restrict to one table (may be repeated)")
    args = parser.parse_args(argv)

    sqlite_conn = connect(config.DB_PATH)
    try:
        if args.dry_run:
            counts = run_backfill(sqlite_conn, pg_apply=lambda *_: None,
                                  tables_filter=args.table, dry_run=True)
            total = sum(counts.values())
            print(f"DRY-RUN OK — {total} rows across {len(counts)} tables")
            return 0

        # Real run — open Neon via NeonClient.
        from backend.mirror.neon_client import NeonClient
        from backend.mirror import config as mirror_config
        mirror_config.reload_from_env()
        if not mirror_config.NEON_MIRROR_URL:
            print("FATAL: NEON_MIRROR_URL is not set (run `set -a; source .env.local; set +a` first)",
                  file=sys.stderr)
            return 2
        client = NeonClient(mirror_config.NEON_MIRROR_URL)
        if not client.connect():
            print("FATAL: could not connect to Neon", file=sys.stderr)
            return 2
        try:
            cursor = client._conn.cursor()  # type: ignore[union-attr]

            def _apply(sql: str, values: list) -> None:
                cursor.execute(sql, values)

            counts = run_backfill(sqlite_conn, pg_apply=_apply,
                                  tables_filter=args.table, dry_run=False)
        finally:
            client.close()

        total = sum(counts.values())
        print(f"OK — {total} rows upserted across {len(counts)} tables")
        return 0
    finally:
        sqlite_conn.close()


if __name__ == "__main__":
    sys.exit(main())
