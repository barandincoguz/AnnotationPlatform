"""v0017 schema, outbox trigger scope, and backup/mirror wiring."""
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


def _fresh(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    return conn


def test_both_tables_exist_with_expected_columns(db_path):
    conn = _fresh(db_path)
    try:
        pred = {r["name"] for r in conn.execute("PRAGMA table_info('model_predictions')")}
        assert pred == {
            "document_id", "generation", "status", "references_json", "truncated",
            "model_fingerprint", "prediction_fingerprint", "text_sha256", "source",
            "error", "operational_json", "created_at", "updated_at",
        }
        audit = {r["name"] for r in conn.execute("PRAGMA table_info('annotation_audit_logs')")}
        assert audit == {
            "id", "document_id", "user_id", "bucket", "decision", "reason",
            "reasons_json", "similarity", "model_only_json", "human_only_json",
            "prediction_fingerprint", "policy_id", "model_generation", "created_at",
        }
    finally:
        conn.close()


def test_audit_logs_and_predictions_are_mirrored(db_path):
    conn = _fresh(db_path)
    try:
        triggers = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        assert {
            "_outbox_annotation_audit_logs_ins",
            "_outbox_annotation_audit_logs_upd",
            "_outbox_annotation_audit_logs_del",
            "_outbox_model_predictions_ins",
            "_outbox_model_predictions_upd",
            "_outbox_model_predictions_del",
        } <= triggers
    finally:
        conn.close()


def test_predictions_survive_backup_dump_and_audit_logs_are_restorable():
    from backend.backup.service import EXCLUDED_TABLES
    from backend.main import MIRROR_RESTORE_TABLES

    assert "model_predictions" not in EXCLUDED_TABLES
    assert "annotation_audit_logs" not in EXCLUDED_TABLES
    assert "annotation_audit_logs" in MIRROR_RESTORE_TABLES
    assert "model_predictions" not in MIRROR_RESTORE_TABLES


def test_decision_check_constraint_rejects_unknown_values(db_path):
    import sqlite3

    import pytest

    conn = _fresh(db_path)
    try:
        conn.execute(
            "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count,"
            " sentence_count, text_density, estimated_difficulty, created_at)"
            " VALUES ('d1','/tmp/d1.json','metin',1,1,1.0,'Kolay',datetime('now'))"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO annotation_audit_logs(document_id, decision, policy_id, created_at)"
                " VALUES ('d1','made_up_decision','p',datetime('now'))"
            )
    finally:
        conn.close()


def test_prediction_row_is_deleted_with_its_document(db_path):
    conn = _fresh(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count,"
            " sentence_count, text_density, estimated_difficulty, created_at)"
            " VALUES ('d1','/tmp/d1.json','metin',1,1,1.0,'Kolay',datetime('now'))"
        )
        conn.execute(
            "INSERT INTO model_predictions(document_id, generation, status,"
            " references_json, truncated, model_fingerprint, prediction_fingerprint,"
            " text_sha256, source, operational_json, created_at, updated_at)"
            " VALUES ('d1','G0','success','[]',0,'mf','pf','ts','dqcheck_agent','{}',"
            " datetime('now'), datetime('now'))"
        )
        conn.execute("DELETE FROM documents_meta WHERE document_id='d1'")
        assert conn.execute("SELECT COUNT(*) AS c FROM model_predictions").fetchone()["c"] == 0
    finally:
        conn.close()
