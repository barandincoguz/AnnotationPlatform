"""Regenerate migrations/postgres/001-baran-init.sql from a fresh SQLite schema.

The script applies every committed SQLite migration to an isolated temporary
database, then calls `build_all_pg_ddl(conn)`. It never depends on whether the
operator's local application database has already been migrated. The output is
deterministic against an unchanged migration set (no embedded timestamp), so
re-running the script without schema changes produces a byte-identical file.

Usage:
    .venv/bin/python -m scripts.regen_neon_ddl
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect
from backend.migrations.helpers.postgres_ddl import build_all_pg_ddl


OUTPUT_PATH = Path(__file__).resolve().parent.parent / "migrations" / "postgres" / "001-baran-init.sql"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="regen-neon-ddl-") as tmp:
        conn = connect(Path(tmp) / "schema.db")
        try:
            apply_migrations(conn, discover_migrations())
            ddl = build_all_pg_ddl(conn)
        finally:
            conn.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(ddl, encoding="utf-8")

    table_count = ddl.count("CREATE TABLE IF NOT EXISTS baran_")
    index_count = ddl.count("CREATE INDEX IF NOT EXISTS baran_") + ddl.count("CREATE UNIQUE INDEX IF NOT EXISTS baran_")
    print(f"OK — {table_count} tables, {index_count} indexes emitted to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
