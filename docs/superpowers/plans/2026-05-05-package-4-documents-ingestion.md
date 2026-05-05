# Paket 4 — Documents Metadata + Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Özelge JSON dosyalarını okuyup `documents_meta` + `document_kanun_refs` + `document_bkk_refs` tablolarına yükleyen ingestion pipeline kur. Doküman listeme/getirme API'si (`GET /api/documents`, `GET /api/documents/{id}`) bu paketin çıktısı. Annotation logic Paket 5'te.

**Architecture:** Source JSON dosyaları `data/documents/*.json` klasöründen okunur. Her JSON tek özelge içerir. Ingest CLI (`python -m backend.cli ingest <path>`) tüm dosyaları tarar, parser deserializer ile DB'ye yazar. Word_count/sentence_count/text_density/estimated_difficulty `pdf_text`'ten hesaplanır. Source kanunBilgileri/bkkTebligSirkuBilgileri **metadata olarak saklanır** ama annotation UI'a sızmaz.

**Tech Stack:** Python stdlib (`json`, `pathlib`), FastAPI auth deps (Paket 2'den), pytest.

---

## Mimari Kararlar

- **Format:** Source = tek JSON file = tek özelge ya da JSON array içinde N özelge — her ikisi destekleniyor
- **Idempotent ingest:** Aynı `evrakOid`'i ikinci kez ingest etmek upsert (UPDATE eski metadata)
- **kanun_refs/bkk_refs upsert:** İlgili doküman için eski satırlar silinir, yeni listeden tekrar yazılır
- **Word/sentence count:** `pdf_text` üzerinden hesaplanır (`htmlText` UI render için ayrı)
- **Difficulty thresholds:** `site_settings`'de admin-configurable (defaults: <500 Kolay, 500-2000 Orta, >=2000 Zor)
- **API auth:** `get_current_user` (paket 2 deps'i), `has_seen_manual` GEREKMİYOR (henüz training de gerekmiyor — bu temel listeleme)
- **Topic_category:** Bu pakette doldurulmaz; Paket 11 admin paneli ile ya da Paket 5 ingestion override ile

## Dosya Yapısı

```
backend/documents/
├── __init__.py            # boş
├── models.py              # Pydantic response modelleri
├── service.py             # ingestion + listing + reading
├── parser.py              # JSON → DB row transformations
├── metrics.py             # word_count, sentence_count, text_density, difficulty
└── routes.py              # GET /api/documents, /api/documents/{id}

backend/cli.py             # MODIFIED: ingest subcommand eklenir

tests/
├── test_documents_metrics.py
├── test_documents_parser.py
├── test_documents_service.py
└── test_documents_routes.py
```

---

## Task 1: Metrics Module (TDD)

**Files:**
- Create: `backend/documents/__init__.py`, `backend/documents/metrics.py`, `tests/test_documents_metrics.py`

- [ ] **Step 1: Create package**

```bash
mkdir -p backend/documents
touch backend/documents/__init__.py
```

- [ ] **Step 2: Write `tests/test_documents_metrics.py`**

```python
from backend.documents.metrics import (
    word_count, sentence_count, text_density,
    classify_difficulty,
)


def test_word_count_simple():
    assert word_count("hello world foo") == 3


def test_word_count_empty():
    assert word_count("") == 0


def test_word_count_turkish():
    assert word_count("Ali ve Veli okula gitti.") == 5


def test_sentence_count_periods():
    assert sentence_count("Bu bir cümle. Bu da bir cümle.") == 2


def test_sentence_count_with_question_and_exclamation():
    assert sentence_count("Niye? Çünkü öyle! Ve ayrıca.") == 3


def test_sentence_count_zero_raises_to_one_via_density_helper():
    """text_density(words, 0) should treat sentence_count as 1 to avoid div by zero."""
    assert text_density(50, 0) == 50.0


def test_text_density_normal():
    assert text_density(100, 5) == 20.0


def test_text_density_rounded_one_decimal():
    assert text_density(100, 7) == 14.3


def test_classify_difficulty_kolay():
    assert classify_difficulty(499, kolay_max=500, orta_max=2000) == "Kolay"


def test_classify_difficulty_orta():
    assert classify_difficulty(1500, kolay_max=500, orta_max=2000) == "Orta"


def test_classify_difficulty_zor():
    assert classify_difficulty(3500, kolay_max=500, orta_max=2000) == "Zor"


def test_classify_difficulty_at_boundary_kolay():
    assert classify_difficulty(500, kolay_max=500, orta_max=2000) == "Orta"


def test_classify_difficulty_at_boundary_zor():
    assert classify_difficulty(2000, kolay_max=500, orta_max=2000) == "Zor"
```

- [ ] **Step 3: Run — expect FAIL (ImportError)**

```bash
. .venv/bin/activate && pytest tests/test_documents_metrics.py -v
```

- [ ] **Step 4: Write `backend/documents/metrics.py`**

```python
"""Text metrics + difficulty classification.

All metrics are computed from `pdf_text` only. They run on document ingest
and are stored in `documents_meta`. Used by the UI to show difficulty badge,
by training to pick balanced gold docs, and by analytics.
"""
from typing import Literal


def word_count(text: str) -> int:
    """Whitespace-split word count."""
    return len(text.split())


def sentence_count(text: str) -> int:
    """Count sentence-terminating punctuation. Min 1 if any text exists."""
    if not text:
        return 0
    count = text.count(".") + text.count("?") + text.count("!")
    return max(count, 1) if text.strip() else 0


def text_density(words: int, sentences: int) -> float:
    """Average words per sentence. Returns 0 for empty input."""
    if words == 0:
        return 0.0
    safe_sentences = sentences if sentences > 0 else 1
    return round(words / safe_sentences, 1)


def classify_difficulty(
    words: int,
    *,
    kolay_max: int = 500,
    orta_max: int = 2000,
) -> Literal["Kolay", "Orta", "Zor"]:
    """Classify by word count. Thresholds are admin-configurable via site_settings."""
    if words < kolay_max:
        return "Kolay"
    if words < orta_max:
        return "Orta"
    return "Zor"
```

- [ ] **Step 5: Run — expect ALL 12 PASS**

```bash
pytest tests/test_documents_metrics.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/documents/__init__.py backend/documents/metrics.py tests/test_documents_metrics.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(documents): add text metrics and difficulty classification"
```

---

## Task 2: JSON Parser (TDD)

**Files:**
- Create: `backend/documents/parser.py`, `tests/test_documents_parser.py`

- [ ] **Step 1: Write `tests/test_documents_parser.py`**

```python
from backend.documents.parser import parse_document, ParseError
import pytest


SAMPLE_DOC = {
    "evrakOid": "1hmkqodt0v1d55",
    "sayi": 24,
    "tarih": "20260123",
    "basvuruTarihi": "20250604",
    "vergiTuru": "0001",
    "vergiDonemi": "01/2025-12/2025",
    "konu": "Kiraya verilen gayrimenkulün vergilendirilmesi",
    "pdfText": "Bu bir test pdf metnidir. İçinde birkaç cümle var.",
    "htmlText": "<p>html version</p>",
    "kanunBilgileri": [
        {"kanunMaddesi": "37", "kanunKodu": "193 - GELİR VERGİSİ KANUNU", "kanunMaddesiTuru": "ASIL"},
        {"kanunMaddesi": "70", "kanunKodu": "193 - GELİR VERGİSİ KANUNU", "kanunMaddesiTuru": "ASIL"},
    ],
    "bkkTebligSirkuBilgileri": [
        {"turu": "TEBLİĞ", "kanunKodu": "193 - GELİR VERGİSİ KANUNU", "maddeNo": "325"},
    ],
}


def test_parse_extracts_evrakoid_as_document_id():
    parsed = parse_document(SAMPLE_DOC, file_path="/data/sample.json")
    assert parsed["meta"]["document_id"] == "1hmkqodt0v1d55"
    assert parsed["meta"]["file_path"] == "/data/sample.json"


def test_parse_copies_json_fields():
    parsed = parse_document(SAMPLE_DOC, file_path="/x.json")
    m = parsed["meta"]
    assert m["sayi"] == 24
    assert m["tarih"] == "20260123"
    assert m["basvuru_tarihi"] == "20250604"
    assert m["vergi_donemi"] == "01/2025-12/2025"
    assert m["vergi_turu"] == "0001"
    assert m["konu"] == "Kiraya verilen gayrimenkulün vergilendirilmesi"
    assert m["pdf_text"].startswith("Bu bir test")
    assert m["html_text"] == "<p>html version</p>"


def test_parse_computes_metrics():
    parsed = parse_document(SAMPLE_DOC, file_path="/x.json")
    m = parsed["meta"]
    assert m["word_count"] > 0
    assert m["sentence_count"] >= 2
    assert m["text_density"] > 0
    assert m["estimated_difficulty"] in ("Kolay", "Orta", "Zor")


def test_parse_kanun_refs():
    parsed = parse_document(SAMPLE_DOC, file_path="/x.json")
    refs = parsed["kanun_refs"]
    assert len(refs) == 2
    assert refs[0]["seq"] == 0
    assert refs[0]["kanun_kodu"] == "193 - GELİR VERGİSİ KANUNU"
    assert refs[0]["kanun_maddesi"] == "37"
    assert refs[0]["kanun_maddesi_turu"] == "ASIL"
    assert refs[1]["seq"] == 1


def test_parse_bkk_refs():
    parsed = parse_document(SAMPLE_DOC, file_path="/x.json")
    refs = parsed["bkk_refs"]
    assert len(refs) == 1
    assert refs[0]["turu"] == "TEBLİĞ"
    assert refs[0]["kanun_kodu"] == "193 - GELİR VERGİSİ KANUNU"
    assert refs[0]["madde_no"] == "325"


def test_parse_missing_evrakoid_raises():
    with pytest.raises(ParseError):
        parse_document({"pdfText": "x"}, file_path="/x.json")


def test_parse_missing_pdftext_raises():
    with pytest.raises(ParseError):
        parse_document({"evrakOid": "abc"}, file_path="/x.json")


def test_parse_optional_fields_missing_become_none():
    minimal = {"evrakOid": "x", "pdfText": "Hello world."}
    parsed = parse_document(minimal, file_path="/x.json")
    m = parsed["meta"]
    assert m["sayi"] is None
    assert m["tarih"] is None
    assert m["konu"] is None
    assert m["mukellefiyet_turu"] is None
    assert m["html_text"] is None
    assert parsed["kanun_refs"] == []
    assert parsed["bkk_refs"] == []


def test_parse_handles_mukellefiyet_turu_when_present():
    doc = {**SAMPLE_DOC, "mukellefiyetTuru": "Tam Mükellef"}
    parsed = parse_document(doc, file_path="/x.json")
    assert parsed["meta"]["mukellefiyet_turu"] == "Tam Mükellef"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_documents_parser.py -v
```

- [ ] **Step 3: Write `backend/documents/parser.py`**

```python
"""JSON → DB row transformation.

Source JSON shape (from external pipeline):
  {
    "evrakOid": str,                # required (= document_id)
    "pdfText": str,                 # required
    "sayi": int|null,
    "tarih": str|null,              # YYYYMMDD
    "basvuruTarihi": str|null,
    "vergiTuru": str|null,
    "vergiDonemi": str|null,
    "konu": str|null,
    "mukellefiyetTuru": str|null,
    "htmlText": str|null,
    "kanunBilgileri": [
      {"kanunMaddesi": str, "kanunKodu": str, "kanunMaddesiTuru": str}, ...
    ],
    "bkkTebligSirkuBilgileri": [
      {"turu": str, "kanunKodu": str, "maddeNo": str}, ...
    ],
  }

Output dict has 3 keys: meta (documents_meta row), kanun_refs (list of rows),
bkk_refs (list of rows). Service layer inserts these.
"""
from typing import Optional
from backend.documents.metrics import (
    word_count, sentence_count, text_density, classify_difficulty
)


class ParseError(ValueError):
    """Raised when the source JSON is missing required fields."""


def _require(doc: dict, key: str, file_path: str) -> object:
    if key not in doc or doc[key] in (None, ""):
        raise ParseError(f"missing required field '{key}' in {file_path}")
    return doc[key]


def parse_document(
    doc: dict,
    *,
    file_path: str,
    kolay_max: int = 500,
    orta_max: int = 2000,
) -> dict:
    document_id = _require(doc, "evrakOid", file_path)
    pdf_text = _require(doc, "pdfText", file_path)

    wc = word_count(pdf_text)
    sc = sentence_count(pdf_text)
    td = text_density(wc, sc)
    diff = classify_difficulty(wc, kolay_max=kolay_max, orta_max=orta_max)

    meta = {
        "document_id": document_id,
        "file_path": file_path,
        "sayi": doc.get("sayi"),
        "tarih": doc.get("tarih"),
        "basvuru_tarihi": doc.get("basvuruTarihi"),
        "vergi_donemi": doc.get("vergiDonemi"),
        "konu": doc.get("konu"),
        "vergi_turu": doc.get("vergiTuru"),
        "mukellefiyet_turu": doc.get("mukellefiyetTuru"),
        "pdf_text": pdf_text,
        "html_text": doc.get("htmlText"),
        "word_count": wc,
        "sentence_count": sc,
        "text_density": td,
        "estimated_difficulty": diff,
        "topic_category": None,  # admin/user later
    }

    kanun_refs = []
    for i, ref in enumerate(doc.get("kanunBilgileri", []) or []):
        kanun_refs.append({
            "seq": i,
            "kanun_kodu": ref.get("kanunKodu", ""),
            "kanun_maddesi": ref.get("kanunMaddesi"),
            "kanun_maddesi_turu": ref.get("kanunMaddesiTuru"),
        })

    bkk_refs = []
    for i, ref in enumerate(doc.get("bkkTebligSirkuBilgileri", []) or []):
        bkk_refs.append({
            "seq": i,
            "turu": ref.get("turu"),
            "kanun_kodu": ref.get("kanunKodu"),
            "madde_no": ref.get("maddeNo"),
        })

    return {"meta": meta, "kanun_refs": kanun_refs, "bkk_refs": bkk_refs}
```

- [ ] **Step 4: Run — expect ALL 9 PASS**

```bash
pytest tests/test_documents_parser.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/documents/parser.py tests/test_documents_parser.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(documents): add JSON parser with metrics computation"
```

---

## Task 3: Service — Ingest + List + Read (TDD)

**Files:**
- Create: `backend/documents/service.py`, `tests/test_documents_service.py`

- [ ] **Step 1: Write `tests/test_documents_service.py`**

```python
import json
import pytest
from pathlib import Path
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.documents import service


SAMPLE = {
    "evrakOid": "doc_abc",
    "sayi": 5,
    "tarih": "20260101",
    "konu": "Test özelge",
    "pdfText": "Bu bir test dokümanıdır. İçinde sorular var. Kanun atıfları da var.",
    "kanunBilgileri": [
        {"kanunMaddesi": "1", "kanunKodu": "193 - GELİR VERGİSİ KANUNU", "kanunMaddesiTuru": "ASIL"},
    ],
    "bkkTebligSirkuBilgileri": [],
}


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def test_ingest_one_document(db, tmp_path):
    f = tmp_path / "a.json"
    f.write_text(json.dumps(SAMPLE))
    count = service.ingest_file(db, f)
    assert count == 1

    row = db.execute("SELECT * FROM documents_meta WHERE document_id=?", ("doc_abc",)).fetchone()
    assert row["sayi"] == 5
    assert row["konu"] == "Test özelge"
    assert row["estimated_difficulty"] in ("Kolay", "Orta", "Zor")
    assert row["word_count"] > 0


def test_ingest_kanun_refs_persisted(db, tmp_path):
    f = tmp_path / "a.json"
    f.write_text(json.dumps(SAMPLE))
    service.ingest_file(db, f)

    refs = db.execute("SELECT * FROM document_kanun_refs WHERE document_id=?", ("doc_abc",)).fetchall()
    assert len(refs) == 1
    assert refs[0]["kanun_kodu"] == "193 - GELİR VERGİSİ KANUNU"


def test_ingest_array_file(db, tmp_path):
    """A JSON file may contain an array of documents."""
    f = tmp_path / "many.json"
    docs = [
        {**SAMPLE, "evrakOid": "doc_1"},
        {**SAMPLE, "evrakOid": "doc_2"},
        {**SAMPLE, "evrakOid": "doc_3"},
    ]
    f.write_text(json.dumps(docs))
    count = service.ingest_file(db, f)
    assert count == 3

    total = db.execute("SELECT COUNT(*) AS c FROM documents_meta").fetchone()["c"]
    assert total == 3


def test_ingest_idempotent_upsert(db, tmp_path):
    """Re-ingesting same evrakOid should upsert (update, not duplicate)."""
    f = tmp_path / "a.json"
    f.write_text(json.dumps(SAMPLE))
    service.ingest_file(db, f)
    service.ingest_file(db, f)

    total = db.execute("SELECT COUNT(*) AS c FROM documents_meta WHERE document_id=?", ("doc_abc",)).fetchone()["c"]
    assert total == 1

    refs_total = db.execute("SELECT COUNT(*) AS c FROM document_kanun_refs WHERE document_id=?", ("doc_abc",)).fetchone()["c"]
    assert refs_total == 1


def test_ingest_directory(db, tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({**SAMPLE, "evrakOid": "doc_1"}))
    (tmp_path / "b.json").write_text(json.dumps({**SAMPLE, "evrakOid": "doc_2"}))
    count = service.ingest_directory(db, tmp_path)
    assert count == 2


def test_list_documents_returns_metadata(db, tmp_path):
    f = tmp_path / "a.json"
    f.write_text(json.dumps(SAMPLE))
    service.ingest_file(db, f)

    docs = service.list_documents(db)
    assert len(docs) == 1
    assert docs[0]["document_id"] == "doc_abc"
    assert "pdf_text" not in docs[0]  # not included in summary view


def test_get_document_full_returns_pdf_text(db, tmp_path):
    f = tmp_path / "a.json"
    f.write_text(json.dumps(SAMPLE))
    service.ingest_file(db, f)

    doc = service.get_document(db, "doc_abc")
    assert doc is not None
    assert doc["pdf_text"].startswith("Bu bir test")


def test_get_document_unknown_returns_none(db):
    assert service.get_document(db, "nonexistent") is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_documents_service.py -v
```

- [ ] **Step 3: Write `backend/documents/service.py`**

```python
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
    """Ingest a JSON file (single doc or array of docs). Returns # docs ingested."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else [raw]
    count = 0
    for item in items:
        parsed = parse_document(item, file_path=str(path))
        meta = parsed["meta"]
        _upsert_meta(db, meta)
        _replace_kanun_refs(db, meta["document_id"], parsed["kanun_refs"])
        _replace_bkk_refs(db, meta["document_id"], parsed["bkk_refs"])
        count += 1
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
```

- [ ] **Step 4: Run — expect ALL 8 PASS**

```bash
pytest tests/test_documents_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/documents/service.py tests/test_documents_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(documents): add ingestion (file + directory), listing, reading services"
```

---

## Task 4: Routes — GET /api/documents, GET /api/documents/{id} (TDD)

**Files:**
- Create: `backend/documents/models.py`, `backend/documents/routes.py`, `tests/test_documents_routes.py`
- Modify: `backend/main.py` (mount router)

- [ ] **Step 1: Write `backend/documents/models.py`**

```python
from typing import Optional
from pydantic import BaseModel


class DocumentSummary(BaseModel):
    document_id: str
    sayi: Optional[int]
    tarih: Optional[str]
    basvuru_tarihi: Optional[str]
    vergi_donemi: Optional[str]
    konu: Optional[str]
    vergi_turu: Optional[str]
    mukellefiyet_turu: Optional[str]
    word_count: int
    sentence_count: int
    text_density: float
    estimated_difficulty: str
    topic_category: Optional[str]
    created_at: str


class DocumentDetail(DocumentSummary):
    pdf_text: str
    html_text: Optional[str]


class DocumentsListResponse(BaseModel):
    documents: list[DocumentSummary]
    total: int
```

- [ ] **Step 2: Write `tests/test_documents_routes.py`**

```python
import json
import pytest
from pathlib import Path


def _seed_invite_and_login(client, username="alice", password="password123"):
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("CODE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": username, "password": password, "invite_code": "CODE",
    })
    client.post("/api/auth/login", json={"username": username, "password": password})


def _ingest_sample_doc(document_id="doc_x"):
    """Ingest a doc directly via the service (test setup, bypassing CLI)."""
    from backend.shared.db import connect
    from backend import config
    from backend.documents import service
    sample = {
        "evrakOid": document_id,
        "sayi": 99,
        "tarih": "20260101",
        "konu": "Test konu",
        "pdfText": "Bu bir test dokümanıdır. İçinde cümleler var. Kanun atfı yapar.",
    }
    # Write to a tmp file and ingest
    tmp = Path("/tmp/_test_doc.json")
    tmp.write_text(json.dumps(sample))
    conn = connect(config.DB_PATH)
    try:
        service.ingest_file(conn, tmp)
    finally:
        conn.close()


def test_list_documents_requires_auth(client):
    r = client.get("/api/documents")
    assert r.status_code == 401


def test_list_documents_empty(client):
    _seed_invite_and_login(client)
    r = client.get("/api/documents")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0


def test_list_documents_after_ingest(client):
    _seed_invite_and_login(client)
    _ingest_sample_doc("doc_a")
    _ingest_sample_doc("doc_b")

    r = client.get("/api/documents")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    ids = [d["document_id"] for d in body["documents"]]
    assert "doc_a" in ids
    assert "doc_b" in ids


def test_list_documents_summary_excludes_pdf_text(client):
    _seed_invite_and_login(client)
    _ingest_sample_doc("doc_a")
    r = client.get("/api/documents")
    body = r.json()
    assert "pdf_text" not in body["documents"][0]


def test_get_document_returns_full_detail(client):
    _seed_invite_and_login(client)
    _ingest_sample_doc("doc_a")
    r = client.get("/api/documents/doc_a")
    assert r.status_code == 200
    body = r.json()
    assert body["document_id"] == "doc_a"
    assert body["pdf_text"].startswith("Bu bir test")


def test_get_document_unknown_returns_404(client):
    _seed_invite_and_login(client)
    r = client.get("/api/documents/nonexistent")
    assert r.status_code == 404


def test_get_document_requires_auth(client):
    r = client.get("/api/documents/doc_a")
    assert r.status_code == 401
```

- [ ] **Step 3: Run — expect FAIL**

```bash
pytest tests/test_documents_routes.py -v
```

- [ ] **Step 4: Write `backend/documents/routes.py`**

```python
"""Document listing and reading endpoints."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.users.deps import get_current_user, get_db
from backend.documents import service
from backend.documents.models import (
    DocumentSummary, DocumentDetail, DocumentsListResponse,
)

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents", response_model=DocumentsListResponse)
def list_docs(
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(get_current_user),
):
    docs = service.list_documents(db)
    return {"documents": docs, "total": len(docs)}


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_doc(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(get_current_user),
):
    doc = service.get_document(db, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    return doc
```

- [ ] **Step 5: Modify `backend/main.py` to mount router**

After `from backend.docs_help.routes import router as help_router`:
```python
from backend.documents.routes import router as documents_router
```

After `app.include_router(help_router)`:
```python
app.include_router(documents_router)
```

- [ ] **Step 6: Run — expect ALL 7 PASS**

```bash
pytest tests/test_documents_routes.py -v
```

- [ ] **Step 7: Verify full suite**

```bash
pytest tests/ -q
```
Expected: 137 tests (101 + 36 new from Paket 4) — actual count may vary slightly based on grouping.

- [ ] **Step 8: Commit**

```bash
git add backend/documents/models.py backend/documents/routes.py backend/main.py tests/test_documents_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(documents): add list and read endpoints with auth"
```

---

## Task 5: CLI — `python -m backend.cli ingest <path>` (TDD)

**Files:**
- Modify: `backend/cli.py`, Create: `tests/test_cli_ingest.py`

- [ ] **Step 1: Write `tests/test_cli_ingest.py`**

```python
import json
import subprocess
import sqlite3
import sys
from pathlib import Path


def _run_cli(tmp_path: Path, *args, extra_env=None) -> subprocess.CompletedProcess:
    env = {
        "DATA_DIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "backend.cli", *args],
        capture_output=True, text=True, env=env,
    )


def test_cli_ingest_single_file(tmp_path):
    _run_cli(tmp_path, "migrate")
    sample = {
        "evrakOid": "cli_test_doc",
        "pdfText": "Bu bir CLI testidir.",
        "sayi": 1,
    }
    f = tmp_path / "doc.json"
    f.write_text(json.dumps(sample))

    result = _run_cli(tmp_path, "ingest", str(f))
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "1" in result.stdout

    db = sqlite3.connect(str(tmp_path / "db" / "annotations.db"))
    row = db.execute("SELECT document_id FROM documents_meta").fetchone()
    db.close()
    assert row[0] == "cli_test_doc"


def test_cli_ingest_directory(tmp_path):
    _run_cli(tmp_path, "migrate")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    for i in range(3):
        (docs_dir / f"doc_{i}.json").write_text(json.dumps({
            "evrakOid": f"d{i}",
            "pdfText": f"Doc {i}",
        }))

    result = _run_cli(tmp_path, "ingest", str(docs_dir))
    assert result.returncode == 0
    assert "3" in result.stdout


def test_cli_ingest_nonexistent_path_fails(tmp_path):
    _run_cli(tmp_path, "migrate")
    result = _run_cli(tmp_path, "ingest", "/does/not/exist")
    assert result.returncode != 0
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_cli_ingest.py -v
```

- [ ] **Step 3: Modify `backend/cli.py`**

Add this command function after `cmd_rotate_invite`:

```python
def cmd_ingest(args) -> int:
    from pathlib import Path
    from backend.documents import service

    config.ensure_dirs()
    target = Path(args.path)
    if not target.exists():
        print(f"ERROR: path does not exist: {target}", file=sys.stderr)
        return 2

    conn = connect(config.DB_PATH)
    try:
        apply_migrations(conn, discover_migrations())
        if target.is_dir():
            count = service.ingest_directory(conn, target)
        else:
            count = service.ingest_file(conn, target)
    finally:
        conn.close()
    print(f"Ingested {count} document(s).")
    return 0
```

Add to `COMMANDS` dict:
```python
COMMANDS = {
    "migrate": cmd_migrate,
    "promote-admin": cmd_promote_admin,
    "demote-admin": cmd_demote_admin,
    "create-invite": cmd_create_invite,
    "rotate-invite": cmd_rotate_invite,
    "ingest": cmd_ingest,
}
```

Add to `main()` parser:
```python
p_ingest = sub.add_parser("ingest", help="Ingest JSON file or directory")
p_ingest.add_argument("path", help="JSON file or directory containing *.json files")
```

- [ ] **Step 4: Run — expect ALL 3 PASS**

```bash
pytest tests/test_cli_ingest.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/cli.py tests/test_cli_ingest.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(cli): add ingest subcommand for JSON files and directories"
```

---

## Task 6: E2E Verification

- [ ] **Step 1: Full suite**

```bash
. .venv/bin/activate
pytest tests/ -q
```
Expected: ~137 tests pass.

- [ ] **Step 2: E2E ingestion flow**

```bash
rm -rf /tmp/p4-e2e && mkdir -p /tmp/p4-e2e/docs
. .venv/bin/activate
DATA_DIR=/tmp/p4-e2e python -m backend.cli migrate
DATA_DIR=/tmp/p4-e2e python -m backend.cli create-invite "BURSIYER-2026"

# Create 3 sample documents
cat > /tmp/p4-e2e/docs/doc_001.json <<'EOF'
{
  "evrakOid": "doc_001",
  "sayi": 24,
  "tarih": "20260123",
  "basvuruTarihi": "20250604",
  "vergiTuru": "0001",
  "vergiDonemi": "01/2025-12/2025",
  "konu": "Kiraya verilen gayrimenkulün vergilendirilmesi",
  "pdfText": "T.C. GELİR İDARESİ. Bu bir test pdfTextidir. Birkaç cümle içerir.",
  "kanunBilgileri": [
    {"kanunMaddesi": "37", "kanunKodu": "193 - GELİR VERGİSİ KANUNU", "kanunMaddesiTuru": "ASIL"},
    {"kanunMaddesi": "70", "kanunKodu": "193 - GELİR VERGİSİ KANUNU", "kanunMaddesiTuru": "ASIL"}
  ],
  "bkkTebligSirkuBilgileri": []
}
EOF

cat > /tmp/p4-e2e/docs/doc_002.json <<'EOF'
{
  "evrakOid": "doc_002",
  "sayi": 23,
  "tarih": "20260119",
  "konu": "Damga Vergisi",
  "pdfText": "488 sayılı Damga Vergisi Kanunu hakkında özelge metni.",
  "kanunBilgileri": [
    {"kanunMaddesi": "1", "kanunKodu": "488 - DAMGA VERGİSİ KANUNU", "kanunMaddesiTuru": "ASIL"}
  ]
}
EOF

DATA_DIR=/tmp/p4-e2e python -m backend.cli ingest /tmp/p4-e2e/docs

# Start server
lsof -ti:8765 | xargs kill -9 2>/dev/null
DATA_DIR=/tmp/p4-e2e uvicorn backend.main:app --port 8765 --log-level error &
until curl -sf http://localhost:8765/api/health >/dev/null 2>&1; do sleep 0.3; done

# Register + login
curl -s -c /tmp/p4-cookies.txt -X POST http://localhost:8765/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"password123","invite_code":"BURSIYER-2026"}' >/dev/null
curl -s -c /tmp/p4-cookies.txt -X POST http://localhost:8765/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"password123"}' >/dev/null

echo "=== List documents ==="
curl -s -b /tmp/p4-cookies.txt http://localhost:8765/api/documents | python3 -m json.tool

echo -e "\n=== Get doc_001 ==="
curl -s -b /tmp/p4-cookies.txt http://localhost:8765/api/documents/doc_001 | python3 -m json.tool | head -20

echo -e "\n=== Direct DB check — kanun_refs as metadata ==="
sqlite3 /tmp/p4-e2e/db/annotations.db "SELECT document_id, kanun_kodu, kanun_maddesi FROM document_kanun_refs ORDER BY document_id, seq"

kill %1 2>/dev/null
```

Expected:
- 2 documents listed
- doc_001 detail includes `pdf_text`
- DB has 3 kanun_refs (2 for doc_001, 1 for doc_002)

- [ ] **Step 3: Tag**

```bash
git tag -a paket-4-documents -m "Paket 4 — Documents Metadata + Ingestion complete"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Implementing task |
|---|---|
| documents_meta JSON-derived fields | T2 parser + T3 service upsert |
| document_kanun_refs (source metadata) | T2 parser + T3 service |
| document_bkk_refs (source metadata) | T2 parser + T3 service |
| word_count, text_density, difficulty | T1 metrics |
| Idempotent upsert | T3 |
| GET /api/documents | T4 |
| GET /api/documents/{id} | T4 |
| Auth required | T4 (uses get_current_user) |
| `has_seen_manual` NOT required | T4 (does not use require_seen_manual) |
| CLI ingest | T5 |

**Placeholder scan:** None. Every step has concrete code.

**Type/method consistency:**
- `parse_document(doc, *, file_path) → dict` returns `{meta, kanun_refs, bkk_refs}` — used in T2 tests + T3 service
- `ingest_file(db, path) → int` — used in T3 tests, T5 CLI
- `ingest_directory(db, dir_path) → int` — used in T3 tests, T5 CLI
- `list_documents(db) → list[dict]` — T3 tests, T4 routes
- `get_document(db, document_id) → Optional[dict]` — T3 tests, T4 routes
- ParseError — T2 module, T3 service catches

**Known compromise:**
- `topic_category` not populated by ingestion (admin/user later via Paket 5+11)
- Difficulty thresholds hard-coded as defaults (500, 2000); admin override via `site_settings` is a Paket 5 enhancement
