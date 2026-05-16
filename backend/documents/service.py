"""Document ingestion + listing + reading.

Ingestion is upsert: same evrakOid replaces metadata + ref tables.
Listing returns summary view (no pdf_text). get_document returns full row.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.documents.parser import parse_document, ParseError


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
            print(f"WARN: skipping item[{idx}]: {e}")
            continue
        meta = parsed["meta"]
        _upsert_meta(db, meta)
        _replace_kanun_refs(db, meta["document_id"], parsed["kanun_refs"])
        _replace_bkk_refs(db, meta["document_id"], parsed["bkk_refs"])
        count += 1
        if total > 1000 and (count % 1000 == 0):
            print(f"  ingested {count}/{total} ({skipped} skipped)")
    if skipped:
        print(f"  total skipped: {skipped}")
    return count


def ingest_directory(db: sqlite3.Connection, dir_path: Path) -> int:
    total = 0
    for path in sorted(Path(dir_path).glob("*.json")):
        try:
            total += ingest_file(db, path)
        except ParseError as e:
            print(f"WARN: skipping {path.name}: {e}")
    return total


def list_documents(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        f"SELECT {', '.join(SUMMARY_COLUMNS)} FROM documents_meta ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_document(db: sqlite3.Connection, document_id: str) -> Optional[dict]:
    row = db.execute(
        "SELECT * FROM documents_meta WHERE document_id=?", (document_id,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)
