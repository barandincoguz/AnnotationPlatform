"""POST /api/annotations/{id}/pre-audit contract."""
import json

from backend.quality.dqcheck_core.fingerprints import sha256_text
from backend.quality.provenance import HISTORICAL_G0_MODEL_FINGERPRINT

DOC_TEXT = "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir."
VUK_114 = {
    "kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
    "fikra": None, "bent": None, "source_text": "zamanasimi hukmu duzenlenmistir",
}
GVK_94 = {
    "kanun_no": "193", "kanun_ad": "Gelir Vergisi Kanunu", "madde": "94",
    "fikra": None, "bent": None, "source_text": "zamanasimi hukmu duzenlenmistir",
}


def _seed_prediction(document_id, references):
    from backend import config
    from backend.quality import service
    from backend.shared.db import connect

    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO model_predictions(
                document_id, generation, status, references_json, truncated,
                model_fingerprint, prediction_fingerprint, text_sha256, source,
                error, operational_json, created_at, updated_at
            ) VALUES (?,?,?,?,0,?,?,?,?,NULL,'{"backend":"mlx-g0"}',datetime('now'),datetime('now'))""",
            (document_id, "G0", "success", json.dumps(references),
             HISTORICAL_G0_MODEL_FINGERPRINT,
             service.prediction_fingerprint(
                 generation="G0",
                 model_fingerprint=HISTORICAL_G0_MODEL_FINGERPRINT,
                 references=references,
             ),
             sha256_text(DOC_TEXT), "dqcheck_agent"),
        )
    finally:
        conn.close()


def test_pre_audit_requires_authentication(client, ingest_doc):
    ingest_doc("d1", pdfText=DOC_TEXT)
    r = client.post("/api/annotations/d1/pre-audit", json={"references": []})
    assert r.status_code == 401


def test_pre_audit_reports_model_unavailable_without_prediction(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    r = c.post("/api/annotations/d1/pre-audit", json={"references": [VUK_114]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["audit_status"] == "model_unavailable"
    assert body["reason"] == "no_prediction"
    assert body["bucket"] is None
    assert body["discrepancies"] == []


def test_pre_audit_returns_green_for_matching_sets(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction("d1", [VUK_114])
    r = c.post("/api/annotations/d1/pre-audit", json={"references": [VUK_114]})
    body = r.json()
    assert body["audit_status"] == "ready"
    assert body["bucket"] == "GREEN"
    assert body["prediction_fingerprint"]
    assert body["model_generation"] == "G0"


def test_pre_audit_compound_model_article_matches_api_canonical_form(
    passed_user, ingest_doc
):
    """Regression for the live MLX ``madde=13/b`` canary shape."""
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    model_reference = {
        "kanun_no": "3065",
        "kanun_ad": "Katma Değer Vergisi Kanunu",
        "madde": "13/b",
        "fikra": None,
        "bent": None,
        "source_text": "zamanasimi hukmu duzenlenmistir",
    }
    _seed_prediction("d1", [model_reference])

    # ReferenceItem canonicalizes this request to madde=13 + bent=b before
    # the service compares it with the raw cached model prediction.
    response = c.post(
        "/api/annotations/d1/pre-audit",
        json={"references": [model_reference]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bucket"] == "GREEN"
    assert body["similarity"] == 1.0
    assert body["discrepancies"] == []


def test_pre_audit_returns_actionable_model_only_discrepancy(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction("d1", [VUK_114, GVK_94])
    r = c.post("/api/annotations/d1/pre-audit", json={"references": [VUK_114]})
    body = r.json()
    assert body["bucket"] == "RED"
    assert "extra_or_different_core_reference" in body["reasons"]
    (discrepancy,) = body["discrepancies"]
    assert discrepancy["kind"] == "model_only"
    assert discrepancy["madde"] == "94"
    assert discrepancy["model_reference"]["kanun_ad"] == "Gelir Vergisi Kanunu"
    assert discrepancy["match_mode"] == "normalized_exact"


def test_pre_audit_writes_nothing(passed_user, ingest_doc):
    from backend import config
    from backend.shared.db import connect

    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction("d1", [VUK_114, GVK_94])
    c.post("/api/annotations/d1/pre-audit", json={"references": [VUK_114]})
    conn = connect(config.DB_PATH)
    try:
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM annotation_audit_logs"
        ).fetchone()["c"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM activity_events WHERE event_type='annotation_save'"
        ).fetchone()["c"] == 0
    finally:
        conn.close()


def test_pre_audit_404s_for_unknown_document(passed_user):
    c = passed_user["client"]
    r = c.post("/api/annotations/ghost/pre-audit", json={"references": []})
    assert r.status_code == 404
