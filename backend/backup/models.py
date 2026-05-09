"""Pydantic schemas for backup endpoints."""
from pydantic import BaseModel


class BackupRunNowResponse(BaseModel):
    ok: bool
    snapshot_path: str
    committed_sha: str | None
    pushed: bool
    rotated_count: int
