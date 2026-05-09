"""Pydantic schemas for /api/admin/retention/{run-now,preview}."""
from typing import Optional

from pydantic import BaseModel, Field


class RetentionRunNowResponse(BaseModel):
    ok: bool = Field(..., description="True if cycle committed successfully")
    purged: dict[str, int] = Field(
        ...,
        description="Per-table row counts deleted in this cycle. "
                    "Kill-switched tables show 0.",
    )
    total: int = Field(..., description="Sum of purged values")
    trace_id: Optional[str] = Field(
        None,
        description="16-char hex correlation token. Set on admin-triggered "
                    "runs; None on loop-origin runs.",
    )


class RetentionPolicyEntry(BaseModel):
    table: str
    days: int = Field(
        ..., description="Effective retention window. 0 = kill switch."
    )
    cutoff_iso: Optional[str] = Field(
        None,
        description="ISO-8601 timestamp; rows older than this would be "
                    "purged. Null for kill-switched tables.",
    )


class RetentionPreviewResponse(BaseModel):
    rows_to_purge: dict[str, int] = Field(
        ...,
        description="Per-table row counts a run_purge would delete now. "
                    "Excludes kill-switched tables.",
    )
    total: int
    policy: list[RetentionPolicyEntry]
