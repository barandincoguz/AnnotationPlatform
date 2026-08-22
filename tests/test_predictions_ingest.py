"""Internal prediction ingest: token contract + idempotent upsert."""
import pytest

from backend.quality.dqcheck_core.fingerprints import sha256_text
from backend.quality.provenance import HISTORICAL_G0_MODEL_FINGERPRINT
from backend.quality.tokens import parse_bearer_token

DOC_TEXT = "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir."
TOKEN = "t" * 48


@pytest.fixture
def token_client(client, monkeypatch):
    monkeypatch.setattr("backend.config.DQCHECK_INGEST_TOKEN", TOKEN)
    return client


def _item(document_id="d1", **overrides):
    payload = {
        "document_id": document_id,
        "generation": "G0",
        "status": "success",
        "references": [{
            "kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
            "fikra": None, "bent": None,
            "source_text": "zamanasimi hukmu duzenlenmistir",
        }],
        "truncated": False,
        "model_fingerprint": HISTORICAL_G0_MODEL_FINGERPRINT,
        "text_sha256": sha256_text(DOC_TEXT),
        "source": "dqcheck_agent",
        "operational": {"backend": "mlx-g0", "latency_seconds": 12.5},
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("raw,expected", [
    (None, None),
    ("", None),
    ("Bearer", None),
    ("Bearer ", None),
    ("Basic abc", None),
    ("bearer abc", "abc"),
    ("Bearer  abc  ", "abc"),
    ("Bearer abc def", "abc def"),
    (12345, None),
])
def test_bearer_parsing_never_raises(raw, expected):
    assert parse_bearer_token(raw) == expected


def test_endpoints_are_503_when_token_is_unset(client, monkeypatch):
    monkeypatch.setattr("backend.config.DQCHECK_INGEST_TOKEN", "")
    r = client.get("/api/internal/predictions/pending")
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "prediction_ingest_disabled"


def test_missing_or_wrong_token_is_401(token_client):
    assert token_client.get("/api/internal/predictions/pending").status_code == 401
    r = token_client.get(
        "/api/internal/predictions/pending",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "invalid_ingest_token"


def test_pending_lists_documents_without_predictions(token_client, ingest_doc):
    ingest_doc("d1", pdfText=DOC_TEXT)
    r = token_client.get(
        "/api/internal/predictions/pending?limit=4",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 200, r.text
    (row,) = r.json()["documents"]
    assert row["document_id"] == "d1"
    assert row["pdf_text"] == DOC_TEXT
    assert len(row["text_sha256"]) == 64


def test_pending_limit_is_capped_at_16(token_client):
    r = token_client.get(
        "/api/internal/predictions/pending?limit=99",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 422


def test_ingest_upserts_and_is_idempotent(token_client, ingest_doc):
    ingest_doc("d1", pdfText=DOC_TEXT)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    r = token_client.post("/api/internal/predictions",
                          json={"items": [_item()]}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"upserted": 1, "rejected": 0}
    r = token_client.post("/api/internal/predictions",
                          json={"items": [_item()]}, headers=headers)
    assert r.json() == {"upserted": 1, "rejected": 0}

    pending = token_client.get("/api/internal/predictions/pending", headers=headers)
    assert pending.json()["documents"] == []


def test_unknown_document_is_skipped_not_rejected(token_client, ingest_doc):
    ingest_doc("d1", pdfText=DOC_TEXT)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    r = token_client.post(
        "/api/internal/predictions",
        json={"items": [_item(), _item(document_id="ghost")]},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json() == {"upserted": 1, "rejected": 0}


def test_text_hash_mismatch_is_skipped_and_document_stays_pending(
    token_client, ingest_doc
):
    ingest_doc("d1", pdfText=DOC_TEXT)
    headers = {"Authorization": f"Bearer {TOKEN}"}

    r = token_client.post(
        "/api/internal/predictions",
        json={"items": [_item(text_sha256="0" * 64)]},
        headers=headers,
    )

    assert r.status_code == 200, r.text
    assert r.json() == {"upserted": 0, "rejected": 0}
    pending = token_client.get("/api/internal/predictions/pending", headers=headers)
    assert [row["document_id"] for row in pending.json()["documents"]] == ["d1"]


def test_text_hash_requires_lowercase_hex(token_client, ingest_doc):
    ingest_doc("d1", pdfText=DOC_TEXT)
    r = token_client.post(
        "/api/internal/predictions",
        json={"items": [_item(text_sha256="g" * 64)]},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 200
    assert r.json() == {"upserted": 0, "rejected": 1}


def test_malformed_model_reference_does_not_fail_the_batch(token_client, ingest_doc):
    """Compact model notation stays raw at ingest and is canonicalized on read."""
    ingest_doc("d1", pdfText=DOC_TEXT)
    item = _item(references=[{
        "kanun_no": "3065", "kanun_ad": "Katma Değer Vergisi Kanunu",
        "madde": "5/1-a", "fikra": None, "bent": None, "source_text": "x",
    }])
    r = token_client.post("/api/internal/predictions", json={"items": [item]},
                          headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200, r.text
    assert r.json() == {"upserted": 1, "rejected": 0}


def test_invalid_item_is_rejected_without_discarding_valid_sibling(
    token_client, ingest_doc
):
    ingest_doc("d1", pdfText=DOC_TEXT)
    ingest_doc("d2", pdfText=DOC_TEXT)
    invalid = _item(
        document_id="d2",
        references=[{
            "kanun_no": "213",
            "kanun_ad": "Vergi Usul Kanunu",
            "madde": "114",
            "fikra": None,
            "bent": None,
            "source_text": "x" * 4_001,
        }],
    )

    r = token_client.post(
        "/api/internal/predictions",
        json={"items": [_item(), invalid]},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert r.status_code == 200, r.text
    assert r.json() == {"upserted": 1, "rejected": 1}


def test_fixture_predictions_are_blocked_even_if_environment_is_misconfigured(
    token_client, ingest_doc
):
    ingest_doc("d1", pdfText=DOC_TEXT)

    r = token_client.post(
        "/api/internal/predictions",
        json={"items": [_item(source="fixture")]},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert r.status_code == 200
    assert r.json() == {"upserted": 0, "rejected": 1}


def test_known_fixture_backend_is_blocked_even_when_source_claims_agent(
    token_client, ingest_doc
):
    ingest_doc("d1", pdfText=DOC_TEXT)

    r = token_client.post(
        "/api/internal/predictions",
        json={
            "items": [
                _item(
                    source="dqcheck_agent",
                    operational={"backend": "echo-human-fixture-v1"},
                )
            ]
        },
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert r.status_code == 200
    assert r.json() == {"upserted": 0, "rejected": 1}


def test_unknown_model_fingerprint_is_rejected_even_if_sha256_shaped(
    token_client, ingest_doc
):
    ingest_doc("d1", pdfText=DOC_TEXT)

    r = token_client.post(
        "/api/internal/predictions",
        json={"items": [_item(model_fingerprint="f" * 64)]},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert r.status_code == 200
    assert r.json() == {"upserted": 0, "rejected": 1}


def test_batch_size_is_capped_at_16(token_client, ingest_doc):
    ingest_doc("d1", pdfText=DOC_TEXT)
    r = token_client.post(
        "/api/internal/predictions",
        json={"items": [_item() for _ in range(17)]},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 422
