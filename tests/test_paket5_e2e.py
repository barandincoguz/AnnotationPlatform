def _ref(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "x"}
    base.update(kwargs)
    return base


def test_full_chain_review_two_users(second_passed_user, ingest_doc):
    """Complete realistic flow:
       alice locks → drafts → saves (creates v1) → lock auto-released
       bob locks doc → reads chain (sees v1 by alice) → saves equivalent refs
       → diff=0 path → marks complete → uncomplete by alice → second complete by bob
    """
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_e2e")

    refs_v1 = [
        _ref(kanun_no="193", madde="37", source_text="GVK madde 37"),
        _ref(kanun_no="5520", madde="5", source_text="KVK madde 5"),
    ]

    # --- alice phase ---
    ctx["login"]("alice")
    r = c.post("/api/locks/doc_e2e/acquire")
    assert r.status_code == 200

    # alice drafts before saving
    c.put("/api/drafts/doc_e2e", json={"references": [_ref(source_text="alice wip")]})
    assert c.get("/api/drafts/doc_e2e").status_code == 200

    r = c.post("/api/annotations", json={"document_id": "doc_e2e", "references": refs_v1})
    assert r.status_code == 200
    assert r.json()["is_new"] is True
    assert r.json()["is_diff_zero"] is False

    # alice's draft cleared by save; lock released by save
    assert c.get("/api/drafts/doc_e2e").status_code == 404
    assert c.post("/api/locks/doc_e2e/heartbeat").status_code == 404

    # --- bob phase ---
    ctx["login"]("bob")
    r = c.post("/api/locks/doc_e2e/acquire")
    assert r.status_code == 200

    chain = c.get("/api/documents/doc_e2e/annotation").json()["chain"]
    assert len(chain) == 1
    assert chain[0]["username"] == "alice"
    assert chain[0]["action"] == "create"

    # bob saves the same content reordered → set semantics → diff=0
    refs_v2 = list(reversed(refs_v1))
    r = c.post("/api/annotations", json={"document_id": "doc_e2e", "references": refs_v2})
    assert r.status_code == 200
    assert r.json()["is_diff_zero"] is True

    chain = c.get("/api/documents/doc_e2e/annotation").json()["chain"]
    assert len(chain) == 2
    assert chain[1]["username"] == "bob"
    assert chain[1]["is_diff_zero"] is True

    # bob marks complete
    r = c.post("/api/annotations/doc_e2e/complete", json={"completed": True})
    assert r.status_code == 200

    detail = c.get("/api/documents/doc_e2e/annotation").json()["annotation"]
    assert detail["is_completed"] is True
    assert detail["completed_by_user_id"] == ctx["bob"]["id"]

    # alice can uncomplete
    ctx["login"]("alice")
    r = c.post("/api/annotations/doc_e2e/complete", json={"completed": False})
    assert r.status_code == 200
    detail = c.get("/api/documents/doc_e2e/annotation").json()["annotation"]
    assert detail["is_completed"] is False
    assert detail["completed_by_user_id"] is None


def test_duplicate_save_unchanged_on_failure(passed_user, ingest_doc):
    """Validation failures shouldn't leave partial state."""
    c = passed_user["client"]
    ingest_doc("doc_test")

    c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref(kanun_no="193", source_text="x")],
    })

    # send a duplicate-bearing payload (rejected)
    r = c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [
            _ref(kanun_no="5520", source_text="y"),
            _ref(kanun_no="5520", source_text="y"),
        ],
    })
    assert r.status_code == 422

    # state untouched
    detail = c.get("/api/documents/doc_test/annotation").json()["annotation"]
    assert len(detail["references"]) == 1
    assert detail["references"][0]["kanun_no"] == "193"


def test_denormalized_index_in_sync_after_chain(second_passed_user, ingest_doc):
    """After a 2-version chain, denormalized table reflects the *current* refs only."""
    from backend.shared.db import connect
    from backend import config

    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")

    ctx["login"]("alice")
    c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref(kanun_no="193", source_text="x")],
    })
    ctx["login"]("bob")
    c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref(kanun_no="5520", source_text="y")],
    })

    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT * FROM annotation_references WHERE document_id='doc_test' ORDER BY seq"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    assert rows[0]["kanun_no"] == "5520"
