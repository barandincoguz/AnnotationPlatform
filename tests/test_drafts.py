import json
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.annotations import drafts


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) VALUES ('u1','x','user',?,?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, sentence_count, "
        "text_density, estimated_difficulty, created_at) "
        "VALUES ('doc_1','x.json','text',1,1,1.0,'Kolay',?)",
        (now,),
    )
    yield conn
    conn.close()


def _ref(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "x"}
    base.update(kwargs)
    return base


# --- service ---

def test_set_draft_creates_row(db):
    refs = [_ref(kanun_no="193", source_text="wip 1")]
    drafts.set_draft(db, document_id="doc_1", user_id=1, references=refs)
    row = db.execute(
        "SELECT * FROM drafts WHERE document_id='doc_1' AND user_id=1"
    ).fetchone()
    assert row is not None
    assert json.loads(row["references_json"])[0]["source_text"] == "wip 1"


def test_set_draft_upserts(db):
    drafts.set_draft(db, document_id="doc_1", user_id=1, references=[_ref(source_text="v1")])
    drafts.set_draft(db, document_id="doc_1", user_id=1, references=[_ref(source_text="v2")])
    rows = db.execute(
        "SELECT * FROM drafts WHERE document_id='doc_1' AND user_id=1"
    ).fetchall()
    assert len(rows) == 1
    assert json.loads(rows[0]["references_json"])[0]["source_text"] == "v2"


def test_set_draft_allows_invalid_ref_shape(db):
    """Drafts are WIP — source_text=='' is allowed (frontend may persist incomplete rows)."""
    drafts.set_draft(db, document_id="doc_1", user_id=1, references=[
        {"kanun_no": "193", "source_text": ""},  # incomplete, but acceptable as draft
    ])
    out = drafts.get_draft(db, document_id="doc_1", user_id=1)
    assert out is not None
    assert out["references"][0]["source_text"] == ""


def test_get_draft_none_when_absent(db):
    assert drafts.get_draft(db, document_id="doc_1", user_id=1) is None


def test_clear_draft_removes_row(db):
    drafts.set_draft(db, document_id="doc_1", user_id=1, references=[_ref(source_text="x")])
    drafts.clear_draft(db, document_id="doc_1", user_id=1)
    assert drafts.get_draft(db, document_id="doc_1", user_id=1) is None


def test_clear_draft_idempotent(db):
    """No-op if no draft exists."""
    drafts.clear_draft(db, document_id="doc_1", user_id=1)  # does not raise


def test_set_draft_unknown_doc_raises(db):
    with pytest.raises(drafts.DocumentNotFound):
        drafts.set_draft(db, document_id="nonexistent", user_id=1, references=[])


# --- routes ---

def test_put_draft_creates(passed_user, ingest_doc):
    ingest_doc("doc_test")
    c = passed_user["client"]
    r = c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="wip")]})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}


def test_get_draft_after_put(passed_user, ingest_doc):
    ingest_doc("doc_test")
    c = passed_user["client"]
    c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="wip")]})
    r = c.get("/api/drafts/doc_test")
    assert r.status_code == 200
    body = r.json()
    assert len(body["references"]) == 1
    assert body["references"][0]["source_text"] == "wip"


def test_get_draft_404_when_absent(passed_user, ingest_doc):
    ingest_doc("doc_test")
    r = passed_user["client"].get("/api/drafts/doc_test")
    assert r.status_code == 404


def test_delete_draft(passed_user, ingest_doc):
    ingest_doc("doc_test")
    c = passed_user["client"]
    c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="wip")]})
    r = c.delete("/api/drafts/doc_test")
    assert r.status_code == 200

    g = c.get("/api/drafts/doc_test")
    assert g.status_code == 404


def test_put_draft_unknown_doc_404(passed_user):
    r = passed_user["client"].put("/api/drafts/nonexistent", json={"references": []})
    assert r.status_code == 404


def test_drafts_are_per_user(second_passed_user, ingest_doc):
    """Alice's draft should not be visible to Bob."""
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")

    ctx["login"]("alice")
    c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="alice wip")]})

    ctx["login"]("bob")
    r = c.get("/api/drafts/doc_test")
    assert r.status_code == 404


def test_save_clears_callers_draft_only(second_passed_user, ingest_doc):
    """Alice saves → Alice's draft cleared; Bob's draft preserved."""
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")

    ctx["login"]("alice")
    c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="alice wip")]})

    ctx["login"]("bob")
    c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="bob wip")]})

    ctx["login"]("alice")
    c.post("/api/annotations", json={"document_id": "doc_test", "references": [_ref(source_text="final")]})

    ctx["login"]("alice")
    assert c.get("/api/drafts/doc_test").status_code == 404

    ctx["login"]("bob")
    r = c.get("/api/drafts/doc_test")
    assert r.status_code == 200
    assert r.json()["references"][0]["source_text"] == "bob wip"
