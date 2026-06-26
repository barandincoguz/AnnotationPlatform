"""Transactional, streaming restore from a JSON backup snapshot."""
from __future__ import annotations

import json
import logging
import sqlite3
import gzip
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TextIO

from backend.backup.service import EXCLUDED_TABLES


log = logging.getLogger(__name__)


class _StreamingJsonReader:
    """Small incremental reader for the snapshot's top-level JSON object."""

    def __init__(self, stream: TextIO, *, chunk_size: int = 1024 * 1024):
        self.stream = stream
        self.chunk_size = chunk_size
        self.buffer = ""
        self.pos = 0
        self.eof = False
        self.decoder = json.JSONDecoder()

    def _compact(self) -> None:
        if self.pos > self.chunk_size:
            self.buffer = self.buffer[self.pos:]
            self.pos = 0

    def _fill(self) -> bool:
        if self.eof:
            return False
        self._compact()
        chunk = self.stream.read(self.chunk_size)
        if chunk == "":
            self.eof = True
            return False
        self.buffer += chunk
        return True

    def _skip_whitespace(self) -> None:
        while True:
            while self.pos < len(self.buffer) and self.buffer[self.pos].isspace():
                self.pos += 1
            if self.pos < len(self.buffer) or not self._fill():
                return

    def peek(self) -> str:
        self._skip_whitespace()
        while self.pos >= len(self.buffer):
            if not self._fill():
                raise ValueError("restore: unexpected end of JSON")
            self._skip_whitespace()
        return self.buffer[self.pos]

    def expect(self, expected: str) -> None:
        actual = self.peek()
        if actual != expected:
            raise ValueError(
                f"restore: expected {expected!r}, found {actual!r}"
            )
        self.pos += 1

    def read_value(self) -> Any:
        self._skip_whitespace()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.pos)
            except json.JSONDecodeError as exc:
                if self._fill():
                    continue
                raise ValueError(
                    f"restore: invalid JSON near character {exc.pos}: {exc.msg}"
                ) from exc
            self.pos = end
            self._compact()
            return value

    def ensure_finished(self) -> None:
        self._skip_whitespace()
        if self.pos < len(self.buffer):
            raise ValueError("restore: trailing data after top-level object")
        if self._fill():
            self._skip_whitespace()
            if self.pos < len(self.buffer):
                raise ValueError("restore: trailing data after top-level object")


@contextmanager
def _open_snapshot_text(snapshot_path: Path) -> Iterator[TextIO]:
    with open(snapshot_path, "rb") as probe:
        is_gzip = probe.read(2) == b"\x1f\x8b"
    if snapshot_path.name.endswith(".json.gz") or is_gzip:
        with gzip.open(snapshot_path, "rt", encoding="utf-8") as stream:
            yield stream
    else:
        with open(snapshot_path, encoding="utf-8") as stream:
            yield stream


def _iter_table_rows(reader: _StreamingJsonReader) -> Iterator[dict[str, Any]]:
    reader.expect("[")
    if reader.peek() == "]":
        reader.expect("]")
        return
    while True:
        row = reader.read_value()
        if not isinstance(row, dict):
            raise ValueError("restore: every table row must be a JSON object")
        yield row
        separator = reader.peek()
        if separator == ",":
            reader.expect(",")
            continue
        if separator == "]":
            reader.expect("]")
            return
        raise ValueError(
            f"restore: expected ',' or ']' after table row, found {separator!r}"
        )


def restore_from_snapshot(db: sqlite3.Connection, snapshot_path: Path) -> dict:
    """Replace snapshot tables atomically without loading the file into RAM."""
    existing_tables = {
        row["name"]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    runtime_tables = EXCLUDED_TABLES & existing_tables

    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("PRAGMA defer_foreign_keys=ON")
        # Pre-restore runtime state is invalid once durable rows are replaced.
        if "_outbox" in existing_tables:
            db.execute("DELETE FROM _outbox")

        result_tables: dict[str, int] = {}
        skipped_tables: list[str] = []
        total = 0

        with _open_snapshot_text(snapshot_path) as stream:
            reader = _StreamingJsonReader(stream)
            reader.expect("{")
            if reader.peek() != "}":
                while True:
                    table = reader.read_value()
                    if not isinstance(table, str):
                        raise ValueError(
                            "restore: top-level keys must be table-name strings"
                        )
                    reader.expect(":")

                    if table.startswith("__"):
                        reader.read_value()
                    elif table in runtime_tables:
                        for _row in _iter_table_rows(reader):
                            pass
                    elif table not in existing_tables:
                        log.warning("restore: skipping unknown table %s", table)
                        skipped_tables.append(table)
                        for _row in _iter_table_rows(reader):
                            pass
                    else:
                        valid_cols = {
                            row["name"]
                            for row in db.execute(
                                f"PRAGMA table_info({table})"
                            ).fetchall()
                        }
                        db.execute(f"DELETE FROM {table}")
                        row_count = 0
                        for row in _iter_table_rows(reader):
                            cols = list(row.keys())
                            unknown = [col for col in cols if col not in valid_cols]
                            if unknown:
                                raise ValueError(
                                    f"restore: snapshot row for table {table!r} "
                                    f"has unknown columns {unknown!r} "
                                    "(not in current schema)"
                                )
                            if not cols:
                                raise ValueError(
                                    f"restore: empty row object for table {table!r}"
                                )
                            placeholders = ",".join("?" for _ in cols)
                            col_list = ",".join(cols)
                            db.execute(
                                f"INSERT INTO {table}({col_list}) "
                                f"VALUES ({placeholders})",
                                [row[col] for col in cols],
                            )
                            row_count += 1
                        result_tables[table] = row_count
                        total += row_count

                    separator = reader.peek()
                    if separator == ",":
                        reader.expect(",")
                        continue
                    if separator == "}":
                        break
                    raise ValueError(
                        "restore: expected ',' or '}' after top-level value"
                    )
            reader.expect("}")
            reader.ensure_finished()

        # Runtime ownership and credentials never survive a restore. New
        # mirror outbox rows generated by restoring durable tables are kept.
        if "user_sessions" in existing_tables:
            db.execute("DELETE FROM user_sessions")
        if "document_locks" in existing_tables:
            db.execute("DELETE FROM document_locks")
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    return {
        "tables": result_tables,
        "total_rows": total,
        "skipped_tables": skipped_tables,
    }
