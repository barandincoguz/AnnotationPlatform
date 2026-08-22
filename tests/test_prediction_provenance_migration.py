import json
import sqlite3

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.quality.provenance import HISTORICAL_G0_MODEL_FINGERPRINT
from backend.shared.db import connect


REAL_FINGERPRINT = HISTORICAL_G0_MODEL_FINGERPRINT
TEXT_HASH = "b" * 64


def _fresh(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    conn.execute(
        """
        INSERT INTO documents_meta(
            document_id, file_path, pdf_text, word_count, sentence_count,
            text_density, estimated_difficulty, created_at
        ) VALUES ('d1', 'd1.json', 'body', 1, 1, 1.0, 'Kolay', 'now')
        """
    )
    return conn


def _insert_prediction(
    conn,
    *,
    generation="G0",
    source="dqcheck_agent",
    backend="mlx-g0",
    model_fingerprint=REAL_FINGERPRINT,
    text_sha256=TEXT_HASH,
):
    conn.execute(
        """
        INSERT INTO model_predictions(
            document_id, generation, status, references_json, truncated,
            model_fingerprint, prediction_fingerprint, text_sha256, source,
            error, operational_json, created_at, updated_at
        ) VALUES ('d1', ?, 'success', '[]', 0, ?, 'prediction-etag', ?, ?,
                  NULL, ?, 'now', 'now')
        """,
        (
            generation,
            model_fingerprint,
            text_sha256,
            source,
            json.dumps({"backend": backend}),
        ),
    )


def test_database_accepts_only_real_agent_provenance(db_path):
    conn = _fresh(db_path)
    try:
        _insert_prediction(conn)
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM model_predictions"
        ).fetchone()["c"] == 1
    finally:
        conn.close()


@pytest.mark.parametrize(
    "overrides",
    [
        {"generation": "fixture"},
        {"source": "fixture"},
        {"backend": "echo-human-fixture-v1"},
        {"backend": ""},
        {"model_fingerprint": "not-a-sha256"},
        {"model_fingerprint": "f" * 64},
        {
            "model_fingerprint": (
                "fed23d7a8dd1a7742bcf0ab83e8ec1f92996febf46ad12fb544f353fd96b96b0"
            )
        },
        {"text_sha256": "not-a-sha256"},
    ],
)
def test_database_rejects_untrusted_prediction_provenance(db_path, overrides):
    conn = _fresh(db_path)
    try:
        with pytest.raises(
            sqlite3.IntegrityError,
            match="untrusted model prediction provenance",
        ):
            _insert_prediction(conn, **overrides)
    finally:
        conn.close()
