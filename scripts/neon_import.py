"""Neon Postgres → JSON ETL for the one-time özelge import.

Pulls rows from the source `documents` table (read-only role expected),
shapes each row into the project's canonical ingest JSON contract
(see `backend/documents/parser.py`), and writes chunked files into
`data/import-neon/` ready for `ingest_directory`.

Source schema (verified 2026-05-18):
    documents
      evrak_id           varchar(64), NOT NULL, UNIQUE  → evrakOid
      display_text       text, NOT NULL                  → pdfText
      raw_metadata_json  jsonb, nullable                 → other fields
                                                          (already shaped
                                                           with the parser's
                                                           expected keys)
    17923 rows total; 17523 carry a non-null raw_metadata_json. The
    remaining 400 ingest with sparse metadata (parser accepts NULLs
    on every optional field).

Usage:
    set -a; source .env.local; set +a
    .venv/bin/python -m scripts.neon_import --limit 50          # pilot
    .venv/bin/python -m scripts.neon_import                     # full run
    .venv/bin/python -m scripts.neon_import --out custom/dir

Output:
    data/import-neon/neon-00000.json
    data/import-neon/neon-00001.json
    ...
    Each file is an array of records, chunk size 1000 (configurable).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
from typing import Any

import psycopg


CHUNK_DEFAULT = 1000
DEFAULT_OUT = pathlib.Path("data/import-neon")

# Keys our parser knows about. Anything else in raw_metadata_json
# (`cetvel`, `mevcutIslem`, etc.) is dropped silently — parser.get()
# would ignore them anyway, but stripping keeps the JSON tidy.
PARSER_KEYS = {
    "evrakOid",
    "pdfText",
    "htmlText",
    "sayi",
    "tarih",
    "basvuruTarihi",
    "vergiTuru",
    "vergiDonemi",
    "konu",
    "mukellefiyetTuru",
    "kanunBilgileri",
    "bkkTebligSirkuBilgileri",
}


def shape_row(evrak_id: str, display_text: str, raw_meta: dict | None) -> dict[str, Any]:
    """Combine table columns + JSONB metadata into the ingest contract.

    `evrak_id` and `display_text` come from the table (NOT NULL, 100%
    coverage). `raw_meta` may be None for the 400/17923 rows that
    arrived without enriched metadata — those still produce a valid
    sparse record.
    """
    meta = {k: v for k, v in (raw_meta or {}).items() if k in PARSER_KEYS}
    # Canonicalize the required fields from table columns. Source
    # may also store evrakOid inside raw_meta — table column wins
    # because it's the indexed unique key.
    meta["evrakOid"] = evrak_id
    meta["pdfText"] = display_text
    return meta


def export(
    conn_url: str,
    *,
    out_dir: pathlib.Path,
    chunk_size: int = CHUNK_DEFAULT,
    limit: int | None = None,
) -> tuple[int, int]:
    """Stream rows from Neon, write JSON chunks. Returns (rows, files)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Two fixed SQL forms keep psycopg's Pyright stub happy
    # (LiteralString requirement on `cursor.execute`) without giving
    # up the pilot-mode LIMIT. The LIMIT value rides as a bound
    # parameter, so it can't smuggle SQL anywhere.
    base_sql = (
        "SELECT evrak_id, display_text, raw_metadata_json "
        "FROM documents ORDER BY id"
    )
    limited_sql = base_sql + " LIMIT %s"

    rows_total = 0
    files_total = 0
    batch: list[dict[str, Any]] = []
    started = time.time()

    with psycopg.connect(conn_url) as conn:
        # Server-side named cursor → rows stream in chunks instead of
        # loading 69 MB into client memory.
        with conn.cursor(name="ozelge_export") as cur:
            cur.itersize = chunk_size
            if limit is not None:
                cur.execute(limited_sql, (int(limit),))
            else:
                cur.execute(base_sql)
            for evrak_id, display_text, raw_meta in cur:
                rows_total += 1
                if not evrak_id or not display_text:
                    # Defensive — both are NOT NULL in the source, so
                    # this branch should never fire. Log + skip if it
                    # ever does so the importer doesn't write garbage.
                    print(
                        f"  warn: row {rows_total} missing required col "
                        f"(evrak_id={bool(evrak_id)}, "
                        f"display_text={bool(display_text)}), skipped",
                        file=sys.stderr,
                    )
                    continue
                batch.append(shape_row(evrak_id, display_text, raw_meta))
                if len(batch) >= chunk_size:
                    _flush(out_dir, files_total, batch)
                    files_total += 1
                    batch.clear()
                    if files_total % 5 == 0:
                        elapsed = time.time() - started
                        rate = rows_total / max(elapsed, 0.001)
                        print(
                            f"  progress: {rows_total} rows, "
                            f"{files_total} files, {rate:.0f} rows/s"
                        )
            if batch:
                _flush(out_dir, files_total, batch)
                files_total += 1

    return rows_total, files_total


def _flush(out_dir: pathlib.Path, idx: int, batch: list[dict[str, Any]]) -> None:
    """Write one chunk to disk. Compact JSON keeps file sizes near
    the average row size; pretty-printing would inflate disk usage
    without aiding the import pipeline."""
    path = out_dir / f"neon-{idx:05d}.json"
    path.write_text(
        json.dumps(batch, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Neon → JSON ETL for özelge import")
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=DEFAULT_OUT,
        help=f"Output directory (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--chunk",
        type=int,
        default=CHUNK_DEFAULT,
        help=f"Rows per output file (default: {CHUNK_DEFAULT})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Pull at most N rows (use for pilot runs).",
    )
    args = parser.parse_args(argv)

    conn_url = os.environ.get("NEON_RO_URL")
    if not conn_url:
        print("error: NEON_RO_URL not set (source .env.local first)", file=sys.stderr)
        return 2

    started = time.time()
    rows, files = export(
        conn_url,
        out_dir=args.out,
        chunk_size=args.chunk,
        limit=args.limit,
    )
    elapsed = time.time() - started
    print(
        f"done: wrote {rows} rows to {files} files in "
        f"{args.out}/ ({elapsed:.1f}s, {rows / max(elapsed, 0.001):.0f} rows/s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
