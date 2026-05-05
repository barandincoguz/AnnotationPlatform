"""Pydantic request/response models for annotation routes."""
from typing import Optional
from pydantic import BaseModel, Field


class ReferenceItem(BaseModel):
    kanun_no: Optional[str] = None
    kanun_ad: Optional[str] = None
    madde: Optional[str] = None
    fikra: Optional[str] = None
    bent: Optional[str] = None
    source_text: str = Field(min_length=1)


class SaveAnnotationRequest(BaseModel):
    document_id: str
    references: list[ReferenceItem]


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
