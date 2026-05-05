import json
import pytest
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
