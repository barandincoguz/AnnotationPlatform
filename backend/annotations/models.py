"""Pydantic request/response models for annotation routes."""

from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator


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

    @model_validator(mode="before")
    @classmethod
    def pre_normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            from backend.annotations.diff import (
                parse_madde_token,
                normalize_kanun_no,
                normalize_kanun_adi,
                normalize_identifier,
                normalize_madde,
            )

            src = data.get("source_text")
            if src is not None:
                data["source_text"] = str(src).strip()

            madde = data.get("madde")
            if madde is not None:
                madde_str = str(madde).strip()
                if madde_str:
                    m, f, b = parse_madde_token(madde_str)
                    if m and not any(x and ("/" in x or "-" in x) for x in (m, f, b)):
                        data["madde"] = m
                        if f:
                            data["fikra"] = f
                        if b:
                            data["bent"] = b
                    else:
                        data["madde"] = normalize_madde(madde_str)

            for f in ("kanun_no", "kanun_ad", "fikra", "bent"):
                if f in data and data[f] is not None:
                    s = str(data[f]).strip()
                    data[f] = s if s else None

            if data.get("kanun_no"):
                data["kanun_no"] = normalize_kanun_no(data["kanun_no"])
            if data.get("kanun_ad"):
                data["kanun_ad"] = normalize_kanun_adi(
                    data["kanun_ad"], kanun_no=data.get("kanun_no") or ""
                )
            if data.get("fikra"):
                data["fikra"] = normalize_identifier(data["fikra"])
            if data.get("bent"):
                data["bent"] = normalize_identifier(data["bent"])

        return data

    @model_validator(mode="after")
    def validate_madde_format(self) -> "ReferenceItem":
        if self.madde and ("/" in self.madde or "-" in self.madde):
            raise ValueError(
                "madde format is invalid. Complex formats like 5/1-a must be split."
            )
        return self


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
    # Optional atomic save: when `completed=True` and `references` is
    # provided, the service persists the refs AND flips the flag inside
    # a single BEGIN IMMEDIATE. Phase 3 frontend will populate this so
    # `handleComplete` collapses from a 3-call chain (save → complete →
    # delete_draft) into one round-trip. Omitting it preserves the
    # legacy flag-flip-only behavior. Cap matches SaveAnnotationRequest
    # so payload bounds stay consistent (~800 KB worst-case).
    references: Optional[list[ReferenceItem]] = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _refs_only_when_completing(self) -> "CompleteRequest":
        # `completed=False` + refs is meaningless: uncomplete reverses a
        # prior commit, it does not freeze a new ref set. Reject at the
        # contract boundary so the service never has to reason about
        # this combination. The service layer still re-checks for direct
        # callers (tests, internal code paths).
        if self.completed is False and self.references is not None:
            raise ValueError("references only allowed when completed=true")
        return self


class OkResponse(BaseModel):
    ok: bool = True
