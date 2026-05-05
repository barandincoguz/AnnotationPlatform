"""Typed key-value access to site_settings table."""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

_MISSING = object()


def _get_raw(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM site_settings WHERE key=?", (key,)
    ).fetchone()
    return row["value"] if row else None


def get_str(conn, key: str, default: Any = _MISSING) -> str:
    raw = _get_raw(conn, key)
    if raw is None:
        if default is _MISSING:
            raise KeyError(key)
        return default
    parsed = json.loads(raw)
    if not isinstance(parsed, str):
        raise TypeError(f"setting {key} is not a string: {type(parsed).__name__}")
    return parsed


def get_int(conn, key: str, default: Any = _MISSING) -> int:
    raw = _get_raw(conn, key)
    if raw is None:
        if default is _MISSING:
            raise KeyError(key)
        return default
    parsed = json.loads(raw)
    if not isinstance(parsed, (int, float)) or isinstance(parsed, bool):
        raise TypeError(f"setting {key} is not numeric: {type(parsed).__name__}")
    return int(parsed)


def get_float(conn, key: str, default: Any = _MISSING) -> float:
    raw = _get_raw(conn, key)
    if raw is None:
        if default is _MISSING:
            raise KeyError(key)
        return default
    parsed = json.loads(raw)
    if not isinstance(parsed, (int, float)):
        raise TypeError(f"setting {key} is not numeric: {type(parsed).__name__}")
    return float(parsed)


def get_dict(conn, key: str, default: Any = _MISSING) -> dict:
    raw = _get_raw(conn, key)
    if raw is None:
        if default is _MISSING:
            raise KeyError(key)
        return default
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise TypeError(f"setting {key} is not a dict")
    return parsed


def get_all(conn) -> dict[str, Any]:
    rows = conn.execute("SELECT key, value FROM site_settings").fetchall()
    return {r["key"]: json.loads(r["value"]) for r in rows}


def set_value(
    conn: sqlite3.Connection,
    key: str,
    value: Any,
    updated_by_user_id: Optional[int],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO site_settings(key, value, updated_at, updated_by_user_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at,
            updated_by_user_id=excluded.updated_by_user_id
        """,
        (key, json.dumps(value), now, updated_by_user_id),
    )
