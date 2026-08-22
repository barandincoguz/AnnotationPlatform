"""Prediction cache, audit report, ack contract, and decision derivation."""
import json

import pytest

from backend.quality import service
from backend.quality.provenance import (
    CURRENT_G0_MODEL_FINGERPRINT,
    HISTORICAL_G0_MODEL_FINGERPRINT,
)

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
        generation=generation,
        model_fingerprint=HISTORICAL_G0_MODEL_FINGERPRINT,
        references=refs,
    )
    conn.execute(
        """INSERT OR REPLACE INTO model_predictions(
            document_id, generation, status, references_json, truncated,
            model_fingerprint, prediction_fingerprint, text_sha256, source,
            error, operational_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,NULL,'{"backend":"mlx-g0"}',datetime('now'),datetime('now'))""",
        (document_id, generation, status, json.dumps(refs), truncated,
         HISTORICAL_G0_MODEL_FINGERPRINT, fingerprint, sha256_text(text), "dqcheck_agent"),
    )
    return fingerprint


def mark_as_historical_fixture(conn, *, document_id="d1"):
    from backend.migrations.v0020_prediction_provenance_guard import (
        TRIGGER_NAMES,
        install_prediction_provenance_guards,
    )

    for name in TRIGGER_NAMES:
        conn.execute(f"DROP TRIGGER {name}")
    try:
        conn.execute(
            """
            UPDATE model_predictions
            SET operational_json='{"backend":"echo-human-fixture-v1"}'
            WHERE document_id=?
            """,
            (document_id,),
        )
    finally:
        install_prediction_provenance_guards(conn)


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
        "references": [VUK_114], "truncated": False,
        "model_fingerprint": HISTORICAL_G0_MODEL_FINGERPRINT,
        "text_sha256": service.sha256_text(DOC_TEXT), "error": None,
        "source": "dqcheck_agent",
        "operational": {"backend": "mlx-g0", "latency_seconds": 1.5},
    }
    unknown = {**item, "document_id": "ghost"}
    assert service.upsert_predictions(db, [item, unknown]) == 1
    assert service.upsert_predictions(db, [item]) == 1
    assert db.execute("SELECT COUNT(*) AS c FROM model_predictions").fetchone()["c"] == 1


def test_purge_fixture_predictions_matches_legacy_and_new_provenance(db):
    seed_prediction(db, references=[])
    mark_as_historical_fixture(db)
    assert service.count_fixture_predictions(db) == 1
    assert service.purge_fixture_predictions(db) == 1
    assert service.load_prediction(db, "d1") is None


def test_direct_service_call_rejects_non_agent_prediction_provenance(db):
    valid_hash = service.sha256_text(DOC_TEXT)
    item = {
        "document_id": "d1",
        "generation": "G0",
        "status": "success",
        "references": [],
        "truncated": False,
        "model_fingerprint": HISTORICAL_G0_MODEL_FINGERPRINT,
        "text_sha256": valid_hash,
        "source": "manual_backfill",
        "error": None,
        "operational": {"backend": "mlx-g0"},
    }

    assert service.upsert_predictions(db, [item]) == 0
    assert service.load_prediction(db, "d1") is None


def test_direct_service_call_rejects_unknown_sha256_shaped_model(db):
    item = {
        "document_id": "d1",
        "generation": "G0",
        "status": "success",
        "references": [],
        "truncated": False,
        "model_fingerprint": "f" * 64,
        "text_sha256": service.sha256_text(DOC_TEXT),
        "source": "dqcheck_agent",
        "error": None,
        "operational": {"backend": "mlx-g0"},
    }

    assert service.upsert_predictions(db, [item]) == 0
    assert service.load_prediction(db, "d1") is None


def test_production_boot_purges_fixture_before_serving_and_queues_neon_delete(
    db, monkeypatch
):
    from backend import config
    from backend.main import _purge_fixture_predictions_before_serve

    trusted_item = {
        "document_id": "d1",
        "generation": "G0",
        "status": "success",
        "references": [],
        "truncated": False,
        "model_fingerprint": HISTORICAL_G0_MODEL_FINGERPRINT,
        "text_sha256": service.sha256_text(DOC_TEXT),
        "source": "dqcheck_agent",
        "error": None,
        "operational": {"backend": "mlx-g0"},
    }
    assert service.upsert_predictions(db, [trusted_item]) == 1
    mark_as_historical_fixture(db)
    monkeypatch.setattr(config, "is_production", lambda: True)

    assert _purge_fixture_predictions_before_serve(db) == 1
    assert service.load_prediction(db, "d1") is None
    delete_event = db.execute(
        """
        SELECT op
        FROM _outbox
        WHERE table_name='model_predictions' AND pk_value='d1'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    assert delete_event["op"] == "DELETE"


def test_pending_documents_returns_documents_without_predictions(db, ingest_doc):
    ingest_doc("d2", pdfText="ikinci dokuman metni")
    pending = service.pending_documents(db, limit=8)
    ids = [row["document_id"] for row in pending]
    # The prediction queue must match the production UI's canonical
    # annotation order (backend.shuffle.service.DEFAULT_SORT_FOR):
    # document_id DESC across every tab.
    assert ids == ["d2", "d1"]
    assert pending[0]["text_sha256"] and pending[1]["text_sha256"]


def test_pending_documents_excludes_documents_with_any_prediction(db, ingest_doc):
    """Staleness is no longer rescanned here: it is handled at ingest time
    (backend.documents.service._upsert_meta deletes the prediction row when
    text changes), so pending_documents excludes a document the moment it
    has *any* prediction row, fresh or not."""
    ingest_doc("d2", pdfText="ikinci dokuman metni")
    seed_prediction(db, document_id="d1", text="eski metin")  # a "stale" row
    pending = service.pending_documents(db, limit=8)
    assert [row["document_id"] for row in pending] == ["d2"]


def test_pending_documents_respects_limit(db, ingest_doc):
    ingest_doc("d2", pdfText="ikinci dokuman metni")
    pending = service.pending_documents(db, limit=1)
    assert len(pending) == 1


def test_pending_documents_does_not_starve_rows_outside_legacy_3000_window(db):
    rows = [
        (
            f"z{i:04d}",
            f"z{i:04d}.json",
            "body",
            1,
            1,
            1.0,
            "Kolay",
            f"{i:04d}",
        )
        for i in range(3001)
    ]
    db.executemany(
        """
        INSERT INTO documents_meta(
            document_id, file_path, pdf_text, word_count, sentence_count,
            text_density, estimated_difficulty, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    pending = service.pending_documents(db, limit=1)

    assert pending[0]["document_id"] == "z3000"


def test_model_quotes_returns_prediction_source_texts(db):
    seed_prediction(db, references=[VUK_114, GVK_94])
    assert service.model_quotes(db, "d1") == (
        "zamanasimi hukmu duzenlenmistir", "tevkifat esaslarini belirler",
    )


def test_model_quotes_empty_when_no_prediction(db):
    assert service.model_quotes(db, "d1") == ()


def test_model_quotes_empty_when_prediction_truncated(db):
    seed_prediction(db, references=[VUK_114, GVK_94], truncated=1)
    assert service.model_quotes(db, "d1") == ()


def test_model_quotes_empty_when_prediction_text_stale(db):
    seed_prediction(db, references=[VUK_114, GVK_94], text="baska bir metin")
    assert service.model_quotes(db, "d1") == ()


def test_evaluate_for_commit_returns_model_unavailable_decision_without_raising(db):
    """A prediction that isn't usable must let the commit proceed with no
    audit at all -- evaluate_for_commit must not raise here."""
    seed_prediction(db, status="error", references=[])
    report, decision = service.evaluate_for_commit(
        db, document_id="d1", references=[VUK_114],
        previous_references=[VUK_114], ack_fingerprint=None,
    )
    assert decision == "model_unavailable"
    assert report.audit_status == "model_unavailable"
    assert report.reason == "model_error"


def test_derive_decision_fails_closed_on_unrecognized_or_missing_bucket():
    """derive_decision must be an allowlist (only GREEN needs no ack), not a
    denylist of known "bad" buckets -- a bucket the router hasn't produced
    yet (or a missing one) must still require acknowledgement."""
    for bucket in (None, "SOME_FUTURE_BUCKET"):
        report = service.AuditReport(audit_status="ready", bucket=bucket)
        assert service.derive_decision(report, accepted_from_model=False) == "human_override"
        assert service.derive_decision(report, accepted_from_model=True) == "human_override"


@pytest.mark.parametrize(
    "bucket, decision_when_not_accepted, decision_when_accepted",
    [
        ("GREEN", "no_discrepancy", "accepted_model"),
        ("YELLOW", "human_override", "human_override"),
        ("RED", "human_override", "human_override"),
        ("QUARANTINE", "human_override", "human_override"),
    ],
)
def test_derive_decision_pins_full_bucket_vocabulary(
    bucket, decision_when_not_accepted, decision_when_accepted
):
    """Pure-function pin over the router's full bucket vocabulary. Only
    GREEN tolerates accepted_from_model=False without an override; every
    other bucket always yields human_override regardless -- i.e. every
    non-GREEN bucket requires an acknowledgement."""
    report = service.AuditReport(audit_status="ready", bucket=bucket)
    assert (
        service.derive_decision(report, accepted_from_model=False)
        == decision_when_not_accepted
    )
    assert (
        service.derive_decision(report, accepted_from_model=True)
        == decision_when_accepted
    )


def test_upsert_updates_every_conflict_column_and_preserves_created_at(db):
    first_item = {
        "document_id": "d1", "generation": "G0", "status": "success",
        "references": [VUK_114], "truncated": False,
        "model_fingerprint": HISTORICAL_G0_MODEL_FINGERPRINT,
        "text_sha256": service.sha256_text(DOC_TEXT),
        "source": "dqcheck_agent", "error": None,
        "operational": {"backend": "mlx-g0", "latency_seconds": 1.5},
    }
    service.upsert_predictions(db, [first_item], now="2026-01-01T00:00:00+00:00")
    created_at = service.load_prediction(db, "d1")["created_at"]

    second_item = {
        "document_id": "d1", "generation": "G0", "status": "error",
        "references": [GVK_94], "truncated": True,
        "model_fingerprint": CURRENT_G0_MODEL_FINGERPRINT,
        "text_sha256": service.sha256_text(DOC_TEXT),
        "source": "dqcheck_agent", "error": "boom",
        "operational": {"backend": "mlx-g0", "latency_seconds": 9.0},
    }
    assert service.upsert_predictions(
        db, [second_item], now="2026-01-02T00:00:00+00:00"
    ) == 1
    assert db.execute(
        "SELECT COUNT(*) AS c FROM model_predictions"
    ).fetchone()["c"] == 1

    row = service.load_prediction(db, "d1")
    assert row["created_at"] == created_at
    assert row["updated_at"] == "2026-01-02T00:00:00+00:00"
    assert row["generation"] == "G0"
    assert row["status"] == "error"
    assert json.loads(row["references_json"]) == [GVK_94]
    assert row["truncated"] == 1
    assert row["model_fingerprint"] == CURRENT_G0_MODEL_FINGERPRINT
    assert row["text_sha256"] == service.sha256_text(DOC_TEXT)
    assert row["source"] == "dqcheck_agent"
    assert row["error"] == "boom"
    assert json.loads(row["operational_json"]) == {
        "backend": "mlx-g0",
        "latency_seconds": 9.0,
    }
    assert row["prediction_fingerprint"] == service.prediction_fingerprint(
        generation="G0",
        model_fingerprint=CURRENT_G0_MODEL_FINGERPRINT,
        references=[GVK_94],
    )


def test_ack_stale_carries_new_fingerprint_when_references_change(db):
    """Pinned against the real fingerprint, not a literal string: if
    prediction_fingerprint ignored `references`, re-seeding with different
    references would not change the fingerprint and this would fail to
    raise."""
    old_fingerprint = seed_prediction(db, references=[VUK_114, GVK_94])
    new_fingerprint = seed_prediction(db, references=[VUK_114])
    assert new_fingerprint != old_fingerprint
    with pytest.raises(service.AuditAckStale) as excinfo:
        service.evaluate_for_commit(
            db, document_id="d1", references=[VUK_114],
            previous_references=[VUK_114], ack_fingerprint=old_fingerprint,
        )
    assert excinfo.value.prediction_fingerprint == new_fingerprint


def test_to_response_key_set_is_pinned(db):
    seed_prediction(db, references=[VUK_114, GVK_94])
    report = service.build_report(db, document_id="d1", references=[VUK_114])
    assert set(report.to_response().keys()) == {
        "audit_status", "reason", "bucket", "reasons", "similarity",
        "prediction_fingerprint", "model_generation", "discrepancies",
    }


def test_log_decision_persists_human_only_json(db):
    fingerprint = seed_prediction(db, references=[VUK_114])
    report, decision = service.evaluate_for_commit(
        db, document_id="d1", references=[VUK_114, GVK_94],
        previous_references=[VUK_114], ack_fingerprint=fingerprint,
    )
    assert report.human_only == ({"kanun_no": "193", "madde": "94", "fikra": "", "bent": ""},)
    service.log_decision(db, document_id="d1", user_id=None, report=report, decision=decision)
    stored = db.execute("SELECT human_only_json FROM annotation_audit_logs").fetchone()
    assert json.loads(stored["human_only_json"]) == [
        {"kanun_no": "193", "madde": "94", "fikra": "", "bent": ""}
    ]
