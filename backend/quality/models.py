"""Pydantic schemas for the pre-submit quality audit and prediction ingest."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from backend.annotations.models import ReferenceItem


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

    Deliberately NOT ReferenceItem: that model runs AP's `pre_normalize`
    validator and rejects e.g. madde="5/1-a", which would fail a whole 16-item
    agent batch because of one malformed model row. Model references are
    normalized at audit time by the vendored `validate_reference_list`.
    """

    kanun_no: Optional[str] = Field(default=None, max_length=64)
    kanun_ad: Optional[str] = Field(default=None, max_length=512)
    madde: Optional[str] = Field(default=None, max_length=64)
    fikra: Optional[str] = Field(default=None, max_length=64)
    bent: Optional[str] = Field(default=None, max_length=64)
    source_text: str = Field(default="", max_length=4_000)


class PredictionIngestItem(BaseModel):
    document_id: str = Field(min_length=1, max_length=128)
    generation: str = Field(min_length=1, max_length=32)
    status: Literal["success", "error"]
    references: list[ModelReferenceItem] = Field(default_factory=list, max_length=200)
    truncated: bool = False
    model_fingerprint: str = Field(min_length=1, max_length=128)
    text_sha256: str = Field(min_length=64, max_length=64)
    error: Optional[str] = Field(default=None, max_length=2_000)
    operational: dict[str, Any] = Field(default_factory=dict)


class PredictionIngestRequest(BaseModel):
    items: list[PredictionIngestItem] = Field(min_length=1, max_length=16)


class PredictionIngestResponse(BaseModel):
    upserted: int


class PendingDocument(BaseModel):
    document_id: str
    pdf_text: str
    text_sha256: str


class PendingResponse(BaseModel):
    documents: list[PendingDocument]
