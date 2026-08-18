"""Document ingestion + listing + reading.

Ingestion is upsert: same evrakOid replaces metadata + ref tables.
Listing returns summary view (no pdf_text). get_document returns full row.
"""
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.documents.parser import parse_document, ParseError


log = logging.getLogger(__name__)


META_COLUMNS = [
    "document_id", "file_path",
    "sayi", "tarih", "basvuru_tarihi", "vergi_donemi",
    "konu", "vergi_turu", "mukellefiyet_turu",
    "pdf_text", "html_text",
    "word_count", "sentence_count", "text_density", "estimated_difficulty",
    "topic_category", "created_at",
]

SUMMARY_COLUMNS = [
    "document_id", "sayi", "tarih", "basvuru_tarihi", "vergi_donemi",
    "konu", "vergi_turu", "mukellefiyet_turu",
    "word_count", "sentence_count", "text_density", "estimated_difficulty",
    "topic_category", "created_at",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _upsert_meta(db: sqlite3.Connection, meta: dict) -> None:
    now = _now()
    cols = META_COLUMNS
    placeholders = ", ".join("?" for _ in cols)
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "document_id" and c != "created_at")

    # A cached model prediction (backend.quality.service) is only meaningful
    # against the exact text it was computed from. If this upsert is about to
    # change pdf_text, drop that prediction so the document falls back into
    # pending_documents' "no prediction" set naturally instead of relying on
    # a stale-text rescan there.
    existing = db.execute(
        "SELECT pdf_text FROM documents_meta WHERE document_id=?",
        (meta["document_id"],),
    ).fetchone()
    if existing is not None and existing["pdf_text"] != meta.get("pdf_text"):
        db.execute(
            "DELETE FROM model_predictions WHERE document_id=?",
            (meta["document_id"],),
        )

    sql = f"""
        INSERT INTO documents_meta({", ".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(document_id) DO UPDATE SET {update_clause}
    """
    values = [meta.get(c) for c in cols[:-1]] + [now]
    db.execute(sql, values)


def _replace_kanun_refs(db: sqlite3.Connection, document_id: str, refs: list[dict]) -> None:
    db.execute("DELETE FROM document_kanun_refs WHERE document_id=?", (document_id,))
    for r in refs:
        db.execute(
            "INSERT INTO document_kanun_refs(document_id, seq, kanun_kodu, kanun_maddesi, kanun_maddesi_turu) VALUES (?,?,?,?,?)",
            (document_id, r["seq"], r["kanun_kodu"], r["kanun_maddesi"], r["kanun_maddesi_turu"]),
        )


def _replace_bkk_refs(db: sqlite3.Connection, document_id: str, refs: list[dict]) -> None:
    db.execute("DELETE FROM document_bkk_refs WHERE document_id=?", (document_id,))
    for r in refs:
        db.execute(
            "INSERT INTO document_bkk_refs(document_id, seq, turu, kanun_kodu, madde_no) VALUES (?,?,?,?,?)",
            (document_id, r["seq"], r["turu"], r["kanun_kodu"], r["madde_no"]),
        )


def ingest_file(db: sqlite3.Connection, path: Path) -> int:
    """Ingest a JSON file (single doc or array of docs). Returns # docs ingested.

    Per-item ParseErrors are logged and skipped so a single bad record cannot
    abort a bulk import. Progress is reported every 1000 docs for large files.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else [raw]
    total = len(items)
    count = 0
    skipped = 0
    for idx, item in enumerate(items):
        try:
            parsed = parse_document(item, file_path=str(path))
        except ParseError as e:
            skipped += 1
            # Was `print(...)` which hit stdout and interleaved with
            # FastAPI request logs. Now flows through the standard
            # logging pipeline so operator filters on .WARNING actually
            # catch these messages.
            log.warning("skipping item[%s] in %s: %s", idx, path.name, e)
            continue
        meta = parsed["meta"]
        _upsert_meta(db, meta)
        _replace_kanun_refs(db, meta["document_id"], parsed["kanun_refs"])
        _replace_bkk_refs(db, meta["document_id"], parsed["bkk_refs"])
        count += 1
        if total > 1000 and (count % 1000 == 0):
            log.info("ingested %s/%s (%s skipped)", count, total, skipped)
    if skipped:
        log.info("total skipped: %s", skipped)
    return count


def ingest_directory(db: sqlite3.Connection, dir_path: Path) -> int:
    total = 0
    for path in sorted(Path(dir_path).glob("*.json")):
        try:
            total += ingest_file(db, path)
        except ParseError as e:
            log.warning("skipping %s: %s", path.name, e)
    return total


def list_documents(
    db: sqlite3.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Paginated SELECT — returns (rows, total).

    Without a cap, calling this at production scale (~17.9k rows) emits
    a multi-MB response on every request. Other feeds cap at MAX_LIMIT=200;
    this helper does the same. Total is returned via a separate COUNT(*)
    so the frontend can show "M of N" and drive pagination without a
    second round-trip.
    """
    rows = db.execute(
        f"SELECT {', '.join(SUMMARY_COLUMNS)} FROM documents_meta "
        f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    total = db.execute(
        "SELECT COUNT(*) AS c FROM documents_meta"
    ).fetchone()["c"]
    return [dict(r) for r in rows], total


def get_document(db: sqlite3.Connection, document_id: str) -> Optional[dict]:
    """Return a document's full meta row plus its kanun + bkk reference
    lists (joined and ordered by ingest seq)."""
    row = db.execute(
        "SELECT * FROM documents_meta WHERE document_id=?", (document_id,)
    ).fetchone()
    if row is None:
        return None
    out = dict(row)
    out["kanun_refs"] = [
        dict(r)
        for r in db.execute(
            "SELECT seq, kanun_kodu, kanun_maddesi, kanun_maddesi_turu "
            "FROM document_kanun_refs WHERE document_id=? ORDER BY seq ASC",
            (document_id,),
        ).fetchall()
    ]
    out["bkk_refs"] = [
        dict(r)
        for r in db.execute(
            "SELECT seq, turu, kanun_kodu, madde_no "
            "FROM document_bkk_refs WHERE document_id=? ORDER BY seq ASC",
            (document_id,),
        ).fetchall()
    ]
    return out
