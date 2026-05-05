import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    """Open SQLite connection with WAL mode, foreign keys, Row factory.

    Caller is responsible for closing the connection.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
