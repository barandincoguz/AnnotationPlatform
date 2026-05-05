import json
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
