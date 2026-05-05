import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


@dataclass
class Migration:
    version: str  # e.g. "v0001"
    name: str
    up: Callable[[sqlite3.Connection], None]


SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TIMESTAMP NOT NULL
)
"""


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA_MIGRATIONS_DDL)


def applied_versions(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r["version"] for r in rows}


def apply_migrations(
    conn: sqlite3.Connection, migrations: list[Migration]
) -> list[str]:
    """Apply pending migrations in version order. Returns versions applied."""
    ensure_migrations_table(conn)
    already = applied_versions(conn)
    pending = sorted(
        [m for m in migrations if m.version not in already],
        key=lambda m: m.version,
    )
    applied = []
    for m in pending:
        m.up(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?,?,?)",
            (m.version, m.name, datetime.now(timezone.utc).isoformat()),
        )
        applied.append(m.version)
    return applied
