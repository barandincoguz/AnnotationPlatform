"""Automated SQLite -> Neon Postgres schema synchronization (auto-migrations).

Ensures that the partner Neon Postgres database schema (baran_* tables) is
automatically kept in sync with the local SQLite schema on startup.
"""
import logging
import re
import sqlite3
import psycopg

from backend.migrations.helpers.schema_introspect import list_project_tables, introspect_table
from backend.migrations.helpers.postgres_ddl import build_pg_ddl_for_table, _pg_type_for

log = logging.getLogger(__name__)


def sync_postgres_schema(sqlite_conn: sqlite3.Connection, pg_dsn: str) -> None:
    """Introspect SQLite schema and Neon Postgres database, and automatically
    apply missing tables, columns, and indexes to Postgres.
    """
    log.info("Postgres schema sync: starting database schema check against Neon...")
    try:
        with psycopg.connect(pg_dsn) as pg_conn:
            with pg_conn.cursor() as pg_cur:
                # 1. Fetch existing tables and columns on Postgres
                pg_cur.execute(
                    """
                    SELECT table_name, column_name 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' AND table_name LIKE 'baran_%'
                    """
                )
                pg_cols = pg_cur.fetchall()
                pg_schema: dict[str, set[str]] = {}
                for table, col in pg_cols:
                    pg_schema.setdefault(table.lower(), set()).add(col.lower())

                # Fetch all existing indexes on Postgres to avoid duplicate index errors
                pg_cur.execute(
                    """
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE schemaname = 'public' AND tablename LIKE 'baran_%'
                    """
                )
                pg_indexes = {row[0].lower() for row in pg_cur.fetchall()}

                # 2. Introspect SQLite project tables and compare
                tables = list_project_tables(sqlite_conn)
                for t in tables:
                    sqlite_schema = introspect_table(sqlite_conn, t)
                    pg_table_name = f"baran_{t}".lower()

                    if pg_table_name not in pg_schema:
                        # Table does not exist on Postgres. Create it!
                        log.info("Postgres schema sync: table %s is missing. Creating...", pg_table_name)
                        statements = build_pg_ddl_for_table(sqlite_schema)
                        for stmt in statements:
                            pg_cur.execute(stmt)
                        log.info("Postgres schema sync: table %s created successfully.", pg_table_name)
                    else:
                        # Table exists. Check for missing columns.
                        existing_cols = pg_schema[pg_table_name]
                        statements = build_pg_ddl_for_table(sqlite_schema)
                        
                        for col in sqlite_schema.columns:
                            if col.name.lower() not in existing_cols:
                                pg_type = _pg_type_for(col)
                                alter_stmt = f"ALTER TABLE {pg_table_name} ADD COLUMN {col.name} {pg_type}"
                                if col.default is not None and not col.is_autoincrement:
                                    alter_stmt += f" DEFAULT {col.default}"
                                log.info("Postgres schema sync: column %s is missing in %s. Altering...", col.name, pg_table_name)
                                pg_cur.execute(alter_stmt)
                                
                        # Check for missing indexes
                        # build_pg_ddl_for_table emits the table creation statement as the first item,
                        # and then all index creation statements as subsequent items.
                        for stmt in statements[1:]:
                            match = re.search(r"INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)\s+ON", stmt, re.IGNORECASE)
                            if match:
                                idx_name = match.group(1).lower()
                                if idx_name not in pg_indexes:
                                    log.info("Postgres schema sync: index %s is missing. Creating...", idx_name)
                                    pg_cur.execute(stmt)
                                    
            pg_conn.commit()
            log.info("Postgres schema sync: successfully completed!")
    except Exception as e:
        log.exception("Postgres schema sync: failed to run auto-migration: %s", e)
        print(f"Postgres schema sync: failed to run auto-migration: {e}")
