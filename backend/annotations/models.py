"""Pydantic request/response models for annotation routes."""
from typing import Optional
from pydantic import BaseModel, Field


class ReferenceItem(BaseModel):
    # Per-field caps prevent multi-MB payloads from ballooning the
    # annotations + version-history rows. Lengths are generous (Turkish
    # law identifiers + free-text source quotes typical of özelge work).
    kanun_no: Optional[str] = Field(default=None, max_length=64)
    kanun_ad: Optional[str] = Field(default=None, max_length=512)
    madde: Optional[str] = Field(default=None, max_length=64)
    fikra: Optional[str] = Field(default=None, max_length=64)
    bent: Optional[str] = Field(default=None, max_length=64)
    source_text: str = Field(min_length=1, max_length=4_000)


class SaveAnnotationRequest(BaseModel):
    # Document IDs are 14-char base36 in production; cap is loose to
    # accommodate seed-e2e fixtures while still rejecting unbounded blobs.
    document_id: str = Field(min_length=1, max_length=128)
    # Caps total reference count; combined with ReferenceItem caps this
    # bounds the worst-case payload to ~800 KB.
    references: list[ReferenceItem] = Field(max_length=200)


class SaveAnnotationResponse(BaseModel):
    is_new: bool
    is_diff_zero: bool
    current_references: list[ReferenceItem]


class AnnotationDetail(BaseModel):
    document_id: str
    references: list[ReferenceItem]
    is_completed: bool
    last_editor_user_id: Optional[int]
    completed_by_user_id: Optional[int]
    edit_count: int
    unique_users_count: int
    created_at: str
    updated_at: str


class ChainEntry(BaseModel):
    version_id: int
    user_id: Optional[int]
    username: Optional[str]
    action: str
    is_diff_zero: bool
    ref_count: int
    diff_summary: dict
    created_at: str


class AnnotationWithChain(BaseModel):
    annotation: Optional[AnnotationDetail]
    chain: list[ChainEntry]


class CompleteRequest(BaseModel):
    completed: bool


class OkResponse(BaseModel):
    ok: bool = True
