"""Pydantic schemas for /api/admin/export."""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ExportFilters(BaseModel):
    """Query-param validation for the export endpoint. All fields except
    `format` are optional; the route applies them as conditional WHERE
    clauses in build_query."""

    format: Literal["csv", "jsonl"] = Field(
        ..., description="Output format. csv = denormalized one-row-per-reference; "
                         "jsonl = one annotation per line with references nested."
    )
    status: Literal["completed", "all"] = Field(
        default="completed",
        description="completed → only is_completed=1 rows; all → every annotation row.",
    )
    from_date: Optional[date] = Field(
        default=None,
        description="Inclusive lower bound on annotations.updated_at. ISO YYYY-MM-DD.",
    )
    to_date: Optional[date] = Field(
        default=None,
        description="Inclusive upper bound on annotations.updated_at. End of day.",
    )
    document_id: Optional[str] = Field(
        default=None,
        description="Exact match against annotations.document_id.",
    )
    user_id: Optional[int] = Field(
        default=None, gt=0,
        description="Matches last_editor_user_id OR completed_by_user_id.",
    )

    @model_validator(mode="after")
    def _check_date_order(self):
        if (
            self.from_date is not None
            and self.to_date is not None
            and self.from_date > self.to_date
        ):
            raise ValueError(
                f"from_date ({self.from_date}) must be ≤ to_date ({self.to_date})"
            )
        return self
