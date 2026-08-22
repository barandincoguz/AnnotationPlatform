"""Prediction cache + audit computation for the pre-submit quality audit.

Read path (pre-audit, /complete): one indexed SELECT plus the vendored router —
no inference ever happens inside a request. Write path (internal ingest): a
single BEGIN IMMEDIATE upsert keyed by document_id.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from backend.quality.adapter import (
    AUDIT_POLICY_ID,
    audit_references,
    reference_identities,
)
from backend.quality.dqcheck_core.fingerprints import fingerprint_json, sha256_text
from backend.quality.provenance import (
    ECHO_FIXTURE_MODEL_FINGERPRINT,
    TRUSTED_G0_MODEL_FINGERPRINTS,
)

_GREEN_BUCKET = "GREEN"
_PRODUCTION_PREDICTION_SOURCE = "dqcheck_agent"
_PRODUCTION_BACKEND_ID = "mlx-g0"
_ECHO_FIXTURE_MODEL_FINGERPRINT = ECHO_FIXTURE_MODEL_FINGERPRINT


class QualityServiceError(Exception):
    """Base."""


class DocumentNotFound(QualityServiceError):
    pass


class AuditAckRequired(QualityServiceError):
    """Bucket needs a human acknowledgement the caller did not provide."""

    def __init__(self, *, bucket: str, prediction_fingerprint: Optional[str]) -> None:
        super().__init__(f"audit acknowledgement required for bucket {bucket}")
        self.bucket = bucket
        self.prediction_fingerprint = prediction_fingerprint


class AuditAckStale(QualityServiceError):
    """Caller acknowledged a prediction that has since been superseded."""

    def __init__(self, *, prediction_fingerprint: Optional[str]) -> None:
        super().__init__("acknowledged prediction is no longer current")
        self.prediction_fingerprint = prediction_fingerprint


@dataclass(frozen=True)
class AuditReport:
    audit_status: str
    reason: Optional[str] = None
    bucket: Optional[str] = None
    reasons: tuple[str, ...] = ()
    similarity: Optional[float] = None
    prediction_fingerprint: Optional[str] = None
    model_generation: Optional[str] = None
    discrepancies: tuple[dict[str, Any], ...] = ()
    model_only: tuple[dict[str, str], ...] = ()
    human_only: tuple[dict[str, str], ...] = ()

    def to_response(self) -> dict[str, Any]:
        """Public shape; model_only/human_only stay server-side (audit log)."""
        return {
            "audit_status": self.audit_status,
            "reason": self.reason,
            "bucket": self.bucket,
            "reasons": list(self.reasons),
            "similarity": self.similarity,
            "prediction_fingerprint": self.prediction_fingerprint,
            "model_generation": self.model_generation,
            "discrepancies": [dict(row) for row in self.discrepancies],
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prediction_fingerprint(
    *, generation: str, model_fingerprint: str, references: list[dict[str, Any]]
) -> str:
    """ETag for one prediction; /complete compares the caller's ack against it."""
    return fingerprint_json(
        {
            "generation": generation,
            "model_fingerprint": model_fingerprint,
            "references": references,
        }
    )


def _document_text(db: sqlite3.Connection, document_id: str) -> str:
    row = db.execute(
        "SELECT pdf_text FROM documents_meta WHERE document_id=?", (document_id,)
    ).fetchone()
    if row is None:
        raise DocumentNotFound(document_id)
    return row["pdf_text"]


def load_prediction(db: sqlite3.Connection, document_id: str) -> Optional[sqlite3.Row]:
    return db.execute(
        "SELECT * FROM model_predictions WHERE document_id=?", (document_id,)
    ).fetchone()


def _is_usable_prediction(row: sqlite3.Row, document_text: str) -> bool:
    """Same usability test `_build` applies: successful, not truncated, and
    computed against the document's *current* text. Shared so `model_quotes`
    can never hand out quotes from a prediction `_build` itself would reject
    (model_truncated / prediction_text_stale)."""
    return (
        row["status"] == "success"
        and not row["truncated"]
        and row["text_sha256"] == sha256_text(document_text)
    )


def model_quotes(db: sqlite3.Connection, document_id: str) -> tuple[str, ...]:
    """Source texts the model proposed — behavioral detectors exempt these."""
    row = load_prediction(db, document_id)
    if row is None:
        return ()
    document_text = _document_text(db, document_id)
    if not _is_usable_prediction(row, document_text):
        return ()
    return tuple(
        str(reference.get("source_text") or "")
        for reference in json.loads(row["references_json"])
        if reference.get("source_text")
    )


def _build(
    db: sqlite3.Connection, *, document_id: str, references: list[dict[str, Any]]
) -> tuple[AuditReport, list[dict[str, Any]]]:
    document_text = _document_text(db, document_id)
    row = load_prediction(db, document_id)
    if row is None:
        return AuditReport(audit_status="model_unavailable", reason="no_prediction"), []

    unavailable_reason: Optional[str] = None
    if not _is_usable_prediction(row, document_text):
        if row["truncated"]:
            unavailable_reason = "model_truncated"
        elif row["status"] != "success":
            unavailable_reason = "model_error"
        else:
            unavailable_reason = "prediction_text_stale"
    if unavailable_reason is not None:
        return (
            AuditReport(
                audit_status="model_unavailable",
                reason=unavailable_reason,
                prediction_fingerprint=row["prediction_fingerprint"],
                model_generation=row["generation"],
            ),
            [],
        )

    model_references = json.loads(row["references_json"])
    outcome = audit_references(
        human_references=references,
        model_references=model_references,
        document_text=document_text,
    )
    return (
        AuditReport(
            audit_status="ready",
            bucket=outcome.bucket,
            reasons=outcome.reasons,
            similarity=outcome.similarity,
            prediction_fingerprint=row["prediction_fingerprint"],
            model_generation=row["generation"],
            discrepancies=outcome.discrepancies,
            model_only=outcome.model_only,
            human_only=outcome.human_only,
        ),
        model_references,
    )


def build_report(
    db: sqlite3.Connection, *, document_id: str, references: list[dict[str, Any]]
) -> AuditReport:
    report, _ = _build(db, document_id=document_id, references=references)
    return report


def _requires_ack(bucket: Optional[str]) -> bool:
    """Allowlist, not a denylist: only GREEN needs no acknowledgement.

    Anything else — YELLOW, RED, QUARANTINE, an absent bucket, or a bucket
    value the router gains later — requires one. A denylist of "bad" bucket
    values fails *open* on anything it doesn't recognize (falls through to
    no-ack-required); this fails *closed* instead.
    """
    return bucket != _GREEN_BUCKET


def derive_decision(report: AuditReport, *, accepted_from_model: bool) -> str:
    if report.audit_status != "ready":
        return "model_unavailable"
    if _requires_ack(report.bucket):
        return "human_override"
    return "accepted_model" if accepted_from_model else "no_discrepancy"


def evaluate_for_commit(
    db: sqlite3.Connection,
    *,
    document_id: str,
    references: list[dict[str, Any]],
    previous_references: list[dict[str, Any]],
    ack_fingerprint: Optional[str],
) -> tuple[AuditReport, str]:
    """Recompute the audit for the refs about to be committed.

    Raises AuditAckRequired when the caller must acknowledge a mismatch, and
    AuditAckStale when the prediction changed after the caller's audit. The
    caller is inside a BEGIN IMMEDIATE; both exceptions roll it back.
    """
    report, model_references = _build(
        db, document_id=document_id, references=references
    )
    if report.audit_status != "ready":
        return report, "model_unavailable"
    if _requires_ack(report.bucket) and not ack_fingerprint:
        raise AuditAckRequired(
            bucket=str(report.bucket),
            prediction_fingerprint=report.prediction_fingerprint,
        )
    if ack_fingerprint and ack_fingerprint != report.prediction_fingerprint:
        raise AuditAckStale(prediction_fingerprint=report.prediction_fingerprint)

    # Provable acceptance: an identity that is in the commit AND in the model
    # output but was NOT in the previous version came from the model this turn.
    accepted = bool(
        (reference_identities(references) & reference_identities(model_references))
        - reference_identities(previous_references)
    )
    return report, derive_decision(report, accepted_from_model=accepted)


def log_decision(
    db: sqlite3.Connection,
    *,
    document_id: str,
    user_id: Optional[int],
    report: AuditReport,
    decision: str,
    now: Optional[str] = None,
) -> None:
    db.execute(
        """
        INSERT INTO annotation_audit_logs(
            document_id, user_id, bucket, decision, reason, reasons_json,
            similarity, model_only_json, human_only_json,
            prediction_fingerprint, policy_id, model_generation, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_id,
            user_id,
            report.bucket,
            decision,
            report.reason,
            json.dumps(list(report.reasons), ensure_ascii=False),
            report.similarity,
            json.dumps(list(report.model_only), ensure_ascii=False),
            json.dumps(list(report.human_only), ensure_ascii=False),
            report.prediction_fingerprint,
            AUDIT_POLICY_ID,
            report.model_generation,
            now or _now(),
        ),
    )


def upsert_predictions(
    db: sqlite3.Connection, items: list[dict[str, Any]], *, now: Optional[str] = None
) -> int:
    """Idempotent upsert keyed by document_id. Unknown documents are skipped."""
    stamp = now or _now()
    upserted = 0
    db.execute("BEGIN IMMEDIATE")
    try:
        for item in items:
            document_id = item["document_id"]
            operational = item.get("operational") or {}
            is_trusted_agent_prediction = (
                item.get("generation") == "G0"
                and item.get("source") == _PRODUCTION_PREDICTION_SOURCE
                and isinstance(operational, dict)
                and operational.get("backend") == _PRODUCTION_BACKEND_ID
                and item.get("model_fingerprint") in TRUSTED_G0_MODEL_FINGERPRINTS
            )
            if not is_trusted_agent_prediction:
                continue
            document = db.execute(
                "SELECT pdf_text FROM documents_meta WHERE document_id=?", (document_id,)
            ).fetchone()
            if document is None:
                continue
            if item["text_sha256"] != sha256_text(document["pdf_text"]):
                continue
            references = list(item.get("references") or [])
            db.execute(
                """
                INSERT INTO model_predictions(
                    document_id, generation, status, references_json, truncated,
                    model_fingerprint, prediction_fingerprint, text_sha256,
                    source, error, operational_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    generation=excluded.generation,
                    status=excluded.status,
                    references_json=excluded.references_json,
                    truncated=excluded.truncated,
                    model_fingerprint=excluded.model_fingerprint,
                    prediction_fingerprint=excluded.prediction_fingerprint,
                    text_sha256=excluded.text_sha256,
                    source=excluded.source,
                    error=excluded.error,
                    operational_json=excluded.operational_json,
                    updated_at=excluded.updated_at
                """,
                (
                    document_id,
                    item["generation"],
                    item["status"],
                    json.dumps(references, ensure_ascii=False),
                    1 if item.get("truncated") else 0,
                    item["model_fingerprint"],
                    prediction_fingerprint(
                        generation=item["generation"],
                        model_fingerprint=item["model_fingerprint"],
                        references=references,
                    ),
                    item["text_sha256"],
                    item.get("source") or "dqcheck_agent",
                    item.get("error"),
                    json.dumps(item.get("operational") or {}, ensure_ascii=False),
                    stamp,
                    stamp,
                ),
            )
            upserted += 1
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return upserted


_FIXTURE_PREDICTION_WHERE = """
    source IN ('fixture', 'e2e_seed')
    OR model_fingerprint = ?
    OR operational_json LIKE '%echo-human-fixture-v1%'
"""


def count_fixture_predictions(db: sqlite3.Connection) -> int:
    row = db.execute(
        f"SELECT COUNT(*) AS c FROM model_predictions WHERE {_FIXTURE_PREDICTION_WHERE}",
        (_ECHO_FIXTURE_MODEL_FINGERPRINT,),
    ).fetchone()
    return int(row["c"])


def purge_fixture_predictions(db: sqlite3.Connection) -> int:
    """Delete fixture rows transactionally; outbox DELETE triggers mirror the purge."""
    db.execute("BEGIN IMMEDIATE")
    try:
        cursor = db.execute(
            f"DELETE FROM model_predictions WHERE {_FIXTURE_PREDICTION_WHERE}",
            (_ECHO_FIXTURE_MODEL_FINGERPRINT,),
        )
        deleted = int(cursor.rowcount)
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return deleted


_PENDING_MISSING_SQL = """
    SELECT d.document_id, d.pdf_text
    FROM documents_meta d
    LEFT JOIN model_predictions p ON p.document_id = d.document_id
    WHERE p.document_id IS NULL
    ORDER BY d.document_id DESC
    LIMIT ?
"""


def pending_documents(db: sqlite3.Connection, *, limit: int) -> list[dict[str, Any]]:
    """Documents the agent should predict: those with no `model_predictions` row.

    Staleness (a document whose text changed after its prediction was made)
    is handled at the source instead of by re-scanning here:
    `backend.documents.service._upsert_meta` deletes a document's prediction
    row the moment its `pdf_text` changes, so the document falls back into
    this "no prediction" set naturally. That keeps this a single cheap
    indexed query instead of a bounded scan that re-hashes full document texts
    on every poll. Ordering deliberately matches the production annotation UI's
    canonical `document_id DESC` feed, so a single-threaded predict-agent fills
    the cache in the same order users encounter documents. `_build`'s
    `prediction_text_stale` reason remains as a safety net for any prediction
    that becomes stale by some other path.
    """
    return [
        {
            "document_id": row["document_id"],
            "pdf_text": row["pdf_text"],
            "text_sha256": sha256_text(row["pdf_text"]),
        }
        for row in db.execute(_PENDING_MISSING_SQL, (limit,)).fetchall()
    ]
