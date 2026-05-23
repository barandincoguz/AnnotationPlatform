"""Pydantic schemas for backup endpoints."""
from typing import Optional

from pydantic import BaseModel


class BackupRunNowResponse(BaseModel):
    ok: bool
    snapshot_path: str
    committed_sha: str | None
    pushed: bool
    rotated_count: int
    trace_id: Optional[str] = None  # set on admin-triggered runs; NULL on loop-origin


class BackupRestoreResponse(BaseModel):
    ok: bool
    tables: dict[str, int]
    total_rows: int
    skipped_tables: list[str]
    trace_id: str
