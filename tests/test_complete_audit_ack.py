"""/complete recomputes the audit and demands an acknowledgement on mismatch."""
import json

DOC_TEXT = "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir."
VUK_114 = {
    "kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
    "fikra": None, "bent": None, "source_text": "zamanasimi hukmu duzenlenmistir",
}
GVK_94 = {
    "kanun_no": "193", "kanun_ad": "Gelir Vergisi Kanunu", "madde": "94",
    "fikra": None, "bent": None, "source_text": "zamanasimi hukmu duzenlenmistir",
}


def _seed_prediction(references):
    from backend import config
    from backend.quality import service
    from backend.quality.dqcheck_core.fingerprints import sha256_text
    from backend.shared.db import connect

    conn = connect(config.DB_PATH)
    try:
        fingerprint = service.prediction_fingerprint(
            generation="G0", model_fingerprint="mf-1", references=references
        )
        conn.execute(
            """INSERT OR REPLACE INTO model_predictions(
                document_id, generation, status, references_json, truncated,
                model_fingerprint, prediction_fingerprint, text_sha256, source,
                error, operational_json, created_at, updated_at
            ) VALUES ('d1','G0','success',?,0,'mf-1',?,?,'dqcheck_agent',NULL,'{}',
                      datetime('now'), datetime('now'))""",
            (json.dumps(references), fingerprint, sha256_text(DOC_TEXT)),
        )
        return fingerprint
    finally:
        conn.close()


def _audit_rows():
    from backend import config
    from backend.shared.db import connect

    conn = connect(config.DB_PATH)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM annotation_audit_logs ORDER BY id ASC"
        ).fetchall()]
    finally:
        conn.close()


def test_complete_without_prediction_succeeds_and_logs_model_unavailable(
    passed_user, ingest_doc
):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    r = c.post("/api/annotations/d1/complete",
               json={"completed": True, "references": [VUK_114]})
    assert r.status_code == 200, r.text
    (row,) = _audit_rows()
    assert row["decision"] == "model_unavailable"
    assert row["reason"] == "no_prediction"
    assert row["bucket"] is None


def test_green_complete_needs_no_ack_and_logs_no_discrepancy(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction([VUK_114])
    r = c.post("/api/annotations/d1/complete",
               json={"completed": True, "references": [VUK_114]})
    assert r.status_code == 200, r.text
    (row,) = _audit_rows()
    assert (row["bucket"], row["decision"]) == ("GREEN", "accepted_model")


def test_red_complete_without_ack_is_rejected_with_audit_required(
    passed_user, ingest_doc
):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    fingerprint = _seed_prediction([VUK_114, GVK_94])
    r = c.post("/api/annotations/d1/complete",
               json={"completed": True, "references": [VUK_114]})
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "audit_required"
    assert detail["bucket"] == "RED"
    assert detail["prediction_fingerprint"] == fingerprint
    assert _audit_rows() == []
    annotation = c.get("/api/documents/d1/annotation").json()["annotation"]
    assert annotation is None


def test_red_complete_with_ack_commits_and_logs_human_override(
    passed_user, ingest_doc
):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    fingerprint = _seed_prediction([VUK_114, GVK_94])
    r = c.post("/api/annotations/d1/complete", json={
        "completed": True,
        "references": [VUK_114],
        "audit_ack": {"prediction_fingerprint": fingerprint},
    })
    assert r.status_code == 200, r.text
    (row,) = _audit_rows()
    assert (row["bucket"], row["decision"]) == ("RED", "human_override")
    assert json.loads(row["model_only_json"]) == [
        {"kanun_no": "193", "madde": "94", "fikra": "", "bent": ""}
    ]
    annotation = c.get("/api/documents/d1/annotation").json()["annotation"]
    assert annotation["is_completed"] is True


def test_stale_ack_is_rejected_with_audit_stale(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction([VUK_114, GVK_94])
    r = c.post("/api/annotations/d1/complete", json={
        "completed": True,
        "references": [VUK_114],
        "audit_ack": {"prediction_fingerprint": "a-fingerprint-from-before"},
    })
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "audit_stale"
    assert _audit_rows() == []


def test_accepting_the_model_reference_logs_accepted_model(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    fingerprint = _seed_prediction([VUK_114, GVK_94])
    # First commit records the human's own list (RED + override).
    c.post("/api/annotations", json={"document_id": "d1", "references": [VUK_114]})
    r = c.post("/api/annotations/d1/complete", json={
        "completed": True,
        "references": [VUK_114, GVK_94],
        "audit_ack": {"prediction_fingerprint": fingerprint},
    })
    assert r.status_code == 200, r.text
    (row,) = _audit_rows()
    assert (row["bucket"], row["decision"]) == ("GREEN", "accepted_model")


def test_uncomplete_never_audits(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction([VUK_114])
    c.post("/api/annotations/d1/complete",
           json={"completed": True, "references": [VUK_114]})
    before = len(_audit_rows())
    r = c.post("/api/annotations/d1/complete", json={"completed": False})
    assert r.status_code == 200, r.text
    assert len(_audit_rows()) == before


def test_legacy_flag_only_complete_still_audits_stored_references(
    passed_user, ingest_doc
):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction([VUK_114, GVK_94])
    c.post("/api/annotations", json={"document_id": "d1", "references": [VUK_114]})
    r = c.post("/api/annotations/d1/complete", json={"completed": True})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "audit_required"
