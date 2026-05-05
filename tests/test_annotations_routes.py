def _ref_payload(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "default"}
    base.update(kwargs)
    return base


def test_save_requires_auth(client):
    r = client.post("/api/annotations", json={"document_id": "doc_test", "references": []})
    assert r.status_code == 401


def test_save_creates_annotation(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("doc_test")
    r = c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref_payload(kanun_no="193", source_text="atif")],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new"] is True
    assert body["is_diff_zero"] is False
    assert len(body["current_references"]) == 1


def test_save_unknown_document_returns_404(passed_user):
    r = passed_user["client"].post("/api/annotations", json={
        "document_id": "doc_unknown",
        "references": [],
    })
    assert r.status_code == 404


def test_save_rejects_empty_source_text(passed_user, ingest_doc):
    ingest_doc("doc_test")
    r = passed_user["client"].post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref_payload(source_text="")],
    })
    assert r.status_code == 422


def test_save_rejects_duplicate(passed_user, ingest_doc):
    ingest_doc("doc_test")
    r = passed_user["client"].post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [
            _ref_payload(kanun_no="193", source_text="x"),
            _ref_payload(kanun_no="193", source_text="x"),
        ],
    })
    assert r.status_code == 422


def test_skip_returns_ok(passed_user, ingest_doc):
    ingest_doc("doc_test")
    r = passed_user["client"].post("/api/annotations/doc_test/skip")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_skip_unknown_doc_404(passed_user):
    r = passed_user["client"].post("/api/annotations/nonexistent/skip")
    assert r.status_code == 404


def test_complete_toggles(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("doc_test")
    c.post("/api/annotations", json={"document_id": "doc_test", "references": []})
    r = c.post("/api/annotations/doc_test/complete", json={"completed": True})
    assert r.status_code == 200

    g = c.get("/api/documents/doc_test/annotation")
    assert g.json()["annotation"]["is_completed"] is True


def test_complete_without_annotation_404(passed_user, ingest_doc):
    ingest_doc("doc_test")
    r = passed_user["client"].post("/api/annotations/doc_test/complete", json={"completed": True})
    assert r.status_code == 404


def test_get_chain_includes_attribution(second_passed_user, ingest_doc):
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")

    ctx["login"]("alice")
    c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref_payload(kanun_no="193", source_text="v1")],
    })

    ctx["login"]("bob")
    c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref_payload(kanun_no="5520", source_text="v2")],
    })

    r = c.get("/api/documents/doc_test/annotation")
    assert r.status_code == 200
    body = r.json()
    chain = body["chain"]
    assert len(chain) == 2
    usernames = [e["username"] for e in chain]
    assert usernames == ["alice", "bob"]
    assert chain[0]["action"] == "create"
    assert chain[1]["action"] == "edit"


def test_chain_diff_zero_for_identical_resave(second_passed_user, ingest_doc):
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")

    refs = [_ref_payload(kanun_no="193", source_text="x")]
    ctx["login"]("alice")
    c.post("/api/annotations", json={"document_id": "doc_test", "references": refs})
    ctx["login"]("bob")
    r = c.post("/api/annotations", json={"document_id": "doc_test", "references": refs})
    assert r.status_code == 200
    assert r.json()["is_diff_zero"] is True

    chain = c.get("/api/documents/doc_test/annotation").json()["chain"]
    assert chain[1]["is_diff_zero"] is True


def test_get_chain_unknown_doc_404(passed_user):
    r = passed_user["client"].get("/api/documents/nonexistent/annotation")
    assert r.status_code == 404
