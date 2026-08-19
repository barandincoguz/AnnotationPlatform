"""Verified-corpus export: selection rule, deterministic ids, stable manifest."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from export_verified_corpus import export_corpus  # noqa: E402

DOC_TEXT = "Vergi Usul Kanunu'nun 114 uncu maddesi."
REFERENCE = {
    "kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
    "fikra": None, "bent": None, "source_text": "114 uncu maddesi",
}
STAMP = "2026-08-18T00:00:00+00:00"


@pytest.fixture
def db(client, ingest_doc):
    from backend import config
    from backend.shared.db import connect

    for document_id in ("d-beta", "d-alpha", "d-plain", "d-open"):
        ingest_doc(document_id, pdfText=DOC_TEXT)
    conn = connect(config.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def _complete(conn, document_id, *, audited=True, decision="human_override", users=1):
    conn.execute(
        """INSERT INTO annotations(document_id, references_json, is_completed,
             last_editor_user_id, completed_by_user_id, edit_count,
             unique_users_count, created_at, updated_at)
           VALUES (?, ?, 1, NULL, NULL, 1, ?, ?, ?)""",
        (document_id, json.dumps([REFERENCE]), users, STAMP, STAMP),
    )
    if audited:
        conn.execute(
            """INSERT INTO annotation_audit_logs(document_id, user_id, bucket,
                 decision, reasons_json, similarity, model_only_json,
                 human_only_json, prediction_fingerprint, policy_id,
                 model_generation, created_at)
               VALUES (?, NULL, 'RED', ?, '["missing_core_reference"]', 0.5,
                       '[]', '[]', 'fp-1', 'ignore_vuk_213_article_413_v1',
                       'G0', ?)""",
            (document_id, decision, STAMP),
        )


def test_only_completed_and_audited_documents_are_exported(db, tmp_path):
    _complete(db, "d-beta")
    _complete(db, "d-alpha")
    _complete(db, "d-plain", audited=False)          # completed, never audited
    db.execute(
        """INSERT INTO annotations(document_id, references_json, is_completed,
             edit_count, unique_users_count, created_at, updated_at)
           VALUES ('d-open', '[]', 0, 1, 1, ?, ?)""",
        (STAMP, STAMP),
    )

    out = tmp_path / "gt_v4"
    summary = export_corpus(db, out, generated_at=STAMP)

    assert summary["count"] == 2
    assert sorted(p.name for p in (out / "validated").glob("doc_*.json")) == [
        "doc_1.json", "doc_2.json",
    ]
    # Deterministic ids: sorted by document_id, so d-alpha is 1 and d-beta is 2.
    assert json.loads((out / "id_map.json").read_text(encoding="utf-8")) == {
        "d-alpha": 1, "d-beta": 2,
    }


def test_exported_document_carries_text_references_and_provenance(db, tmp_path):
    _complete(db, "d-alpha")
    out = tmp_path / "gt_v4"
    export_corpus(db, out, generated_at=STAMP)
    payload = json.loads((out / "validated" / "doc_1.json").read_text(encoding="utf-8"))
    assert payload["doc_id"] == 1
    assert payload["source_document_id"] == "d-alpha"
    assert payload["text"] == DOC_TEXT
    assert payload["references"] == [REFERENCE]


def test_sidecar_carries_the_latest_audit_row(db, tmp_path):
    _complete(db, "d-alpha", decision="human_override", users=2)
    db.execute(
        """INSERT INTO annotation_audit_logs(document_id, user_id, bucket,
             decision, reasons_json, similarity, model_only_json, human_only_json,
             prediction_fingerprint, policy_id, model_generation, created_at)
           VALUES ('d-alpha', NULL, 'GREEN', 'accepted_model', '[]', 1.0, '[]', '[]',
                   'fp-2', 'ignore_vuk_213_article_413_v1', 'G0', ?)""",
        (STAMP,),
    )
    out = tmp_path / "gt_v4"
    export_corpus(db, out, generated_at=STAMP)
    (line,) = (out / "audit_sidecar.jsonl").read_text(encoding="utf-8").splitlines()
    row = json.loads(line)
    assert row == {
        "doc_id": 1,
        "source_document_id": "d-alpha",
        "bucket": "GREEN",
        "decision": "accepted_model",
        "reasons": [],
        "similarity": 1.0,
        "prediction_fingerprint": "fp-2",
        "policy_id": "ignore_vuk_213_article_413_v1",
        "model_generation": "G0",
        "unique_users_count": 2,
        "audit_at": STAMP,
    }


def test_manifest_fingerprint_is_stable_across_identical_runs(db, tmp_path):
    _complete(db, "d-alpha")
    first = export_corpus(db, tmp_path / "a", generated_at=STAMP)
    second = export_corpus(db, tmp_path / "b", generated_at="2027-01-01T00:00:00+00:00")
    assert first["manifest_fingerprint"] == second["manifest_fingerprint"]


def test_refuses_to_overwrite_a_non_empty_directory_without_force(db, tmp_path):
    _complete(db, "d-alpha")
    out = tmp_path / "gt_v4"
    export_corpus(db, out, generated_at=STAMP)
    with pytest.raises(SystemExit):
        export_corpus(db, out, generated_at=STAMP)
    summary = export_corpus(db, out, generated_at=STAMP, force=True)
    assert summary["count"] == 1
