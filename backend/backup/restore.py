"""Restore from a JSON snapshot. The DB must already have the current
schema applied (migrations) before this is called. The function does
DELETE+INSERT per table inside a single BEGIN IMMEDIATE transaction;
on any error it rolls back so the caller can decide how to recover.

Tables in the snapshot that don't exist in the current schema are
silently skipped (forward-compatible: a future table name in an old
snapshot won't break restore). Columns in the snapshot that don't
exist in the current schema are detected per-table and raise so
operators see an actionable error message rather than a SQLite
parse error."""
import json
import logging
import sqlite3
from pathlib import Path


log = logging.getLogger(__name__)


def restore_from_snapshot(db: sqlite3.Connection, snapshot_path: Path) -> dict:
    """Read snapshot JSON, DELETE+INSERT each known table inside a
    transaction. Returns {tables: {<name>: row_count}, total_rows,
    skipped_tables}.

    Raises on any error after rolling back the transaction so the caller
    can swap the DB back to the corrupt-bak file. Specifically:
      - ValueError if a snapshot row has columns that don't exist in
        the current schema (closes the column-name SQL surface and
        gives operators a clear error message).
      - sqlite3.* errors if INSERT fails for any other reason.
    """
    with open(snapshot_path, encoding="utf-8") as f:
        payload = json.load(f)

    existing_tables = {
        r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    db.execute("BEGIN IMMEDIATE")
    try:
        result_tables: dict[str, int] = {}
        skipped_tables: list[str] = []
        total = 0
        for table, rows in payload.items():
            if table not in existing_tables:
                log.warning("restore: skipping unknown table %s", table)
                skipped_tables.append(table)
                continue

            # Whitelist columns against current schema so an attacker who
            # can write the snapshot file cannot inject SQL via column names,
            # and so renamed-column drift produces a clear error.
            valid_cols = {
                r["name"] for r in db.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            }

            db.execute(f"DELETE FROM {table}")
            for row in rows:
                cols = list(row.keys())
                unknown = [c for c in cols if c not in valid_cols]
                if unknown:
                    raise ValueError(
                        f"restore: snapshot row for table {table!r} has "
                        f"unknown columns {unknown!r} (not in current schema)"
                    )
                placeholders = ",".join("?" for _ in cols)
                col_list = ",".join(cols)
                db.execute(
                    f"INSERT INTO {table}({col_list}) VALUES ({placeholders})",
                    [row[c] for c in cols],
                )
            result_tables[table] = len(rows)
            total += len(rows)
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    return {
        "tables": result_tables,
        "total_rows": total,
        "skipped_tables": skipped_tables,
    }
