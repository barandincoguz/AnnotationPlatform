"""Thin psycopg wrapper for the Neon mirror (Phase 4, D-07 + D-15).

Translates per-row outbox operations into per-table baran_<table> SQL:

  INSERT/UPDATE  ->  INSERT INTO baran_<t> (...) VALUES (...)
                      ON CONFLICT (<pk_cols>) DO UPDATE
                      SET <col> = EXCLUDED.<col>, ...

  DELETE         ->  DELETE FROM baran_<t> WHERE <pk_cols>... = %s

`pk_value` is the trigger-emitted serialized PK string. For composite PKs the
trigger joins parts with '::'; this module splits and zips back against
`pk_columns_manifest` (the canonical {table -> [pk_col, ...]} map exported
from backend.migrations.helpers.trigger_generator).

Errors raised back to the dispatcher:
  - NeonTransient  -> network / connection / temporary db error; retry with backoff
  - NeonPermanent  -> schema mismatch / data shape; dead-letter immediately

Connect is lazy (first call to `apply` or explicit `connect`) so backend
startup is never blocked on Neon reachability (D-14, MIRROR-10).
"""
from __future__ import annotations

import json
import logging
from typing import Any

try:
    import psycopg
    from psycopg import errors as psycopg_errors
    _PSYCOPG_AVAILABLE = True
except ImportError:  # pragma: no cover — psycopg is a project dep
    psycopg = None  # type: ignore
    psycopg_errors = None  # type: ignore
    _PSYCOPG_AVAILABLE = False

log = logging.getLogger(__name__)


class NeonTransient(Exception):
    """Retryable error — connection lost, timeout, temp db issue."""


class NeonPermanent(Exception):
    """Non-retryable error — schema mismatch, bad payload shape, constraint violation."""


class NeonClient:
    """Thin psycopg wrapper. One long-lived connection in autocommit mode."""

    def __init__(self, dsn: str | None) -> None:
        self.dsn = dsn
        self._conn: Any | None = None  # psycopg.Connection
        self.last_status: bool | None = None  # set by apply(): True success, False failure
        self.has_connected_once: bool = False  # for cold-start detection

    # ----- lifecycle -----

    def connect(self) -> bool:
        """Try once to connect. Returns True on success, False otherwise.

        Never raises — the "Neon unreachable" boot path relies on this
        returning False so lifespan can emit a warn-severity system_event
        and continue (MIRROR-10, D-14).
        """
        if self._conn is not None:
            return True
        if not self.dsn or not _PSYCOPG_AVAILABLE:
            return False
        try:
            self._conn = psycopg.connect(self.dsn, autocommit=True)
            self.has_connected_once = True
            return True
        except Exception as exc:  # psycopg.OperationalError or anything else
            log.warning("NeonClient.connect failed: %s", exc)
            self._conn = None
            return False

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ----- apply one outbox row -----

    def apply(self, op: str, table: str, pk_value: str, payload: dict) -> None:
        """Apply one outbox operation. Raises NeonTransient or NeonPermanent on failure."""
        if not self.connect():
            self.last_status = False
            raise NeonTransient("Neon unreachable (connect failed)")

        mirror_table = f"baran_{table}"
        pk_cols = _pk_columns_for(table)
        if not pk_cols:
            raise NeonPermanent(f"no PK columns registered for table {table!r}")

        try:
            if op == "DELETE":
                sql, args = _build_delete(mirror_table, pk_cols, pk_value)
            elif op in ("INSERT", "UPDATE"):
                sql, args = _build_upsert(mirror_table, pk_cols, payload)
            else:
                raise NeonPermanent(f"unknown op {op!r}")

            cur = self._conn.cursor()  # type: ignore[union-attr]
            cur.execute(sql, args)
            cur.close()
            self.last_status = True
        except NeonPermanent:
            self.last_status = False
            raise
        except Exception as exc:
            self.last_status = False
            # Classify: psycopg.errors.* with sqlstate starting with "23" (integrity)
            # or "42" (syntax / schema) -> permanent. Network / timeout / closed -> transient.
            if _PSYCOPG_AVAILABLE and isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError)):
                # Connection died — drop it so the next attempt reconnects.
                self.close()
                raise NeonTransient(str(exc)) from exc
            sqlstate = getattr(exc, "sqlstate", None)
            if sqlstate and (sqlstate.startswith("42") or sqlstate.startswith("23")):
                raise NeonPermanent(str(exc)) from exc
            # Default: treat as transient (safer — dead-lettering on first
            # unknown error would be too aggressive).
            raise NeonTransient(str(exc)) from exc


# ----- SQL builders --------------------------------------------------------

def _pk_columns_for(table: str) -> list[str]:
    # Import here to avoid a circular module dependency at import time.
    from backend.migrations.helpers.trigger_generator import pk_columns_manifest
    cols = pk_columns_manifest.get(table)
    return list(cols) if cols else []


def _split_pk_value(pk_value: str, pk_cols: list[str]) -> list[str]:
    """Reverse the trigger's `a || '::' || b` serialization.

    For single-column PKs the value is passed through unchanged. For composite
    PKs we split on the literal '::' separator.
    """
    if len(pk_cols) == 1:
        return [pk_value]
    parts = pk_value.split("::")
    if len(parts) != len(pk_cols):
        raise NeonPermanent(
            f"pk_value {pk_value!r} has {len(parts)} parts, expected {len(pk_cols)} "
            f"for PK columns {pk_cols}"
        )
    return parts


def _serialize_value(col_name: str, value: Any) -> Any:
    """Coerce a payload value into the form psycopg should hand Postgres.

    For `*_json` columns we pass a JSON-text string and rely on the column's
    `jsonb` declared type to coerce. dict / list → json.dumps; other types
    pass through unchanged.
    """
    if col_name.endswith("_json"):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        # Already a string; trust the trigger emitted valid JSON.
        return value
    return value


def _build_upsert(mirror_table: str, pk_cols: list[str], payload: dict) -> tuple[str, list]:
    """INSERT INTO baran_<t> (cols...) VALUES (%s, %s, ...)
    ON CONFLICT (<pk_cols>) DO UPDATE SET col1 = EXCLUDED.col1, ...
    """
    cols = list(payload.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    col_list = ", ".join(cols)
    non_pk_cols = [c for c in cols if c not in set(pk_cols)]
    if non_pk_cols:
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_pk_cols)
        on_conflict = (
            f"ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET {set_clause}"
        )
    else:
        # PK-only table (rare) — fallback to DO NOTHING to remain idempotent.
        on_conflict = f"ON CONFLICT ({', '.join(pk_cols)}) DO NOTHING"
    sql = (
        f"INSERT INTO {mirror_table} ({col_list}) "
        f"VALUES ({placeholders}) "
        f"{on_conflict}"
    )
    args = [_serialize_value(c, payload[c]) for c in cols]
    return sql, args


def _build_delete(mirror_table: str, pk_cols: list[str], pk_value: str) -> tuple[str, list]:
    """DELETE FROM baran_<t> WHERE col_a = %s [AND col_b = %s ...]"""
    parts = _split_pk_value(pk_value, pk_cols)
    where = " AND ".join(f"{c} = %s" for c in pk_cols)
    sql = f"DELETE FROM {mirror_table} WHERE {where}"
    return sql, parts
