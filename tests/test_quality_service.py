"""Prediction cache, audit report, ack contract, and decision derivation."""
import json

import pytest

from backend.quality import service

DOC_TEXT = (
    "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir. "
    "Gelir Vergisi Kanunu'nun 94 uncu maddesi tevkifat esaslarini belirler."
)
VUK_114 = {
    "kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
    "fikra": "", "bent": "", "source_text": "zamanasimi hukmu duzenlenmistir",
}
GVK_94 = {
    "kanun_no": "193", "kanun_ad": "Gelir Vergisi Kanunu", "madde": "94",
    "fikra": "", "bent": "", "source_text": "tevkifat esaslarini belirler",
}


@pytest.fixture
def db(client, ingest_doc):
    from backend import config
    from backend.shared.db import connect

    ingest_doc("d1", pdfText=DOC_TEXT)
    conn = connect(config.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def seed_prediction(conn, *, document_id="d1", references=(VUK_114,), status="success",
                    truncated=0, text=DOC_TEXT, generation="G0"):
    from backend.quality.dqcheck_core.fingerprints import sha256_text

    refs = list(references)
    fingerprint = service.prediction_fingerprint(
        generation=generation, model_fingerprint="mf-1", references=refs
    )
    conn.execute(
        """INSERT OR REPLACE INTO model_predictions(
            document_id, generation, status, references_json, truncated,
            model_fingerprint, prediction_fingerprint, text_sha256, source,
            error, operational_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,NULL,'{}',datetime('now'),datetime('now'))""",
        (document_id, generation, status, json.dumps(refs), truncated,
         "mf-1", fingerprint, sha256_text(text), "dqcheck_agent"),
    )
    return fingerprint


def test_missing_prediction_reports_model_unavailable(db):
    report = service.build_report(db, document_id="d1", references=[VUK_114])
    assert report.audit_status == "model_unavailable"
    assert report.reason == "no_prediction"
    assert report.bucket is None
    assert report.discrepancies == ()


def test_unknown_document_raises(db):
    with pytest.raises(service.DocumentNotFound):
        service.build_report(db, document_id="nope", references=[])


def test_model_error_status_reports_model_error(db):
    seed_prediction(db, status="error", references=[])
    report = service.build_report(db, document_id="d1", references=[VUK_114])
    assert (report.audit_status, report.reason) == ("model_unavailable", "model_error")


def test_truncated_prediction_reports_model_truncated(db):
    seed_prediction(db, truncated=1)
    report = service.build_report(db, document_id="d1", references=[VUK_114])
    assert (report.audit_status, report.reason) == ("model_unavailable", "model_truncated")


def test_prediction_against_older_text_is_stale(db):
    seed_prediction(db, text="tamamen baska bir metin")
    report = service.build_report(db, document_id="d1", references=[VUK_114])
    assert (report.audit_status, report.reason) == (
        "model_unavailable", "prediction_text_stale",
    )


def test_matching_sets_are_green_and_need_no_ack(db):
    fingerprint = seed_prediction(db)
    report, decision = service.evaluate_for_commit(
        db, document_id="d1", references=[VUK_114],
        previous_references=[VUK_114], ack_fingerprint=None,
    )
    assert (report.audit_status, report.bucket) == ("ready", "GREEN")
    assert decision == "no_discrepancy"
    assert report.prediction_fingerprint == fingerprint


def test_red_bucket_without_ack_raises_ack_required(db):
    fingerprint = seed_prediction(db, references=[VUK_114, GVK_94])
    with pytest.raises(service.AuditAckRequired) as excinfo:
        service.evaluate_for_commit(
            db, document_id="d1", references=[VUK_114],
            previous_references=[VUK_114], ack_fingerprint=None,
        )
    assert excinfo.value.bucket == "RED"
    assert excinfo.value.prediction_fingerprint == fingerprint


def test_red_bucket_with_ack_records_human_override(db):
    fingerprint = seed_prediction(db, references=[VUK_114, GVK_94])
    report, decision = service.evaluate_for_commit(
        db, document_id="d1", references=[VUK_114],
        previous_references=[VUK_114], ack_fingerprint=fingerprint,
    )
    assert (report.bucket, decision) == ("RED", "human_override")


def test_ack_for_superseded_prediction_raises_stale(db):
    seed_prediction(db, references=[VUK_114, GVK_94])
    with pytest.raises(service.AuditAckStale):
        service.evaluate_for_commit(
            db, document_id="d1", references=[VUK_114],
            previous_references=[VUK_114], ack_fingerprint="stale-fingerprint",
        )


def test_accepting_a_model_reference_records_accepted_model(db):
    fingerprint = seed_prediction(db, references=[VUK_114, GVK_94])
    report, decision = service.evaluate_for_commit(
        db, document_id="d1", references=[VUK_114, GVK_94],
        previous_references=[VUK_114], ack_fingerprint=fingerprint,
    )
    assert (report.bucket, decision) == ("GREEN", "accepted_model")


def test_decision_log_row_is_queryable_with_json_each(db):
    seed_prediction(db, references=[VUK_114, GVK_94])
    report, decision = service.evaluate_for_commit(
        db, document_id="d1", references=[VUK_114],
        previous_references=[VUK_114],
        ack_fingerprint=service.load_prediction(db, "d1")["prediction_fingerprint"],
    )
    service.log_decision(db, document_id="d1", user_id=None, report=report, decision=decision)
    rows = db.execute(
        """SELECT json_extract(m.value, '$.kanun_no') AS kanun_no,
                  json_extract(m.value, '$.madde')    AS madde
           FROM annotation_audit_logs a, json_each(a.model_only_json) m
           WHERE a.decision='human_override'"""
    ).fetchall()
    assert [(r["kanun_no"], r["madde"]) for r in rows] == [("193", "94")]
    stored = db.execute("SELECT * FROM annotation_audit_logs").fetchone()
    assert stored["policy_id"] == "ignore_vuk_213_article_413_v1"
    assert stored["bucket"] == "RED"


def test_upsert_is_idempotent_and_skips_unknown_documents(db):
    item = {
        "document_id": "d1", "generation": "G0", "status": "success",
        "references": [VUK_114], "truncated": False, "model_fingerprint": "mf-1",
        "text_sha256": "abc", "error": None, "operational": {"latency_seconds": 1.5},
    }
    unknown = {**item, "document_id": "ghost"}
    assert service.upsert_predictions(db, [item, unknown]) == 1
    assert service.upsert_predictions(db, [item]) == 1
    assert db.execute("SELECT COUNT(*) AS c FROM model_predictions").fetchone()["c"] == 1


def test_pending_returns_missing_then_stale(db, ingest_doc):
    ingest_doc("d2", pdfText="ikinci dokuman metni")
    seed_prediction(db, document_id="d1", text="eski metin")  # stale
    pending = service.pending_documents(db, limit=8)
    ids = [row["document_id"] for row in pending]
    assert ids == ["d2", "d1"]
    assert pending[0]["text_sha256"] and pending[1]["text_sha256"]


def test_model_quotes_returns_prediction_source_texts(db):
    seed_prediction(db, references=[VUK_114, GVK_94])
    assert service.model_quotes(db, "d1") == (
        "zamanasimi hukmu duzenlenmistir", "tevkifat esaslarini belirler",
    )
