"""Pydantic schemas for the pre-submit quality audit and prediction ingest."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.annotations.models import ReferenceItem
from backend.quality.provenance import TRUSTED_G0_MODEL_FINGERPRINTS


class AuditDiscrepancy(BaseModel):
    kind: Literal["model_only", "human_only", "detail_mismatch"]
    kanun_no: str
    kanun_ad: str
    madde: str
    # Normalized reference dicts (all six fields, empty strings never None) as
    # produced by the vendored normalizer — not AP's ReferenceItem.
    model_reference: Optional[dict[str, str]] = None
    human_reference: Optional[dict[str, str]] = None
    field_diffs: list[str] = Field(default_factory=list)
    match_mode: Optional[str] = None


class PreAuditRequest(BaseModel):
    references: list[ReferenceItem] = Field(max_length=200)


class PreAuditResponse(BaseModel):
    audit_status: Literal["ready", "model_unavailable"]
    reason: Optional[str] = None
    bucket: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    similarity: Optional[float] = None
    prediction_fingerprint: Optional[str] = None
    model_generation: Optional[str] = None
    discrepancies: list[AuditDiscrepancy] = Field(default_factory=list)


class ModelReferenceItem(BaseModel):
    """Model output reference.

    Deliberately NOT ReferenceItem: strict annotation validation here would
    reject an otherwise well-formed prediction item when one generated
    reference is malformed. Agent request items are isolated from one another,
    and the raw prediction is retained for diagnosis. The read boundary later
    applies ReferenceItem exactly; invalid output becomes
    ``model_invalid_output`` and is never presented as a real comparison.
    """

    kanun_no: Optional[str] = Field(default=None, max_length=64)
    kanun_ad: Optional[str] = Field(default=None, max_length=512)
    madde: Optional[str] = Field(default=None, max_length=64)
    fikra: Optional[str] = Field(default=None, max_length=64)
    bent: Optional[str] = Field(default=None, max_length=64)
    source_text: str = Field(default="", max_length=4_000)


class PredictionOperational(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    backend: Literal["mlx-g0"]
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    latency_seconds: Optional[float] = Field(default=None, ge=0)
    truncated: Optional[bool] = None
    generation_attempted: Optional[bool] = None
    finish_reason: Optional[str] = Field(default=None, max_length=64)
    ttft_seconds: Optional[float] = Field(default=None, ge=0)
    prompt_tps: Optional[float] = Field(default=None, ge=0)
    generation_tps: Optional[float] = Field(default=None, ge=0)
    peak_memory_bytes: Optional[int] = Field(default=None, ge=0)


class PredictionIngestItem(BaseModel):
    document_id: str = Field(min_length=1, max_length=128)
    generation: Literal["G0"]
    status: Literal["success", "error"]
    references: list[ModelReferenceItem] = Field(default_factory=list, max_length=200)
    truncated: bool = False
    model_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: Literal["dqcheck_agent"]
    error: Optional[str] = Field(default=None, max_length=2_000)
    operational: PredictionOperational

    @field_validator("model_fingerprint")
    @classmethod
    def model_must_be_trusted_g0(cls, value: str) -> str:
        if value not in TRUSTED_G0_MODEL_FINGERPRINTS:
            raise ValueError("model_fingerprint is not an approved G0 seal")
        return value


class PredictionIngestRequest(BaseModel):
    items: list[dict[str, Any]] = Field(min_length=1, max_length=16)


class PredictionIngestResponse(BaseModel):
    upserted: int
    rejected: int


class PendingDocument(BaseModel):
    document_id: str
    pdf_text: str
    text_sha256: str


class PendingResponse(BaseModel):
    documents: list[PendingDocument]
