"""Prediction ingest endpoints for the Mac-side `dqcheck predict-agent`.

Not part of the annotator API surface: guarded by a service token, never
mounted under the SPA, and intentionally free of user-session semantics.
"""
import sqlite3

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError

from backend.quality import service
from backend.quality.models import (
    PendingResponse,
    PredictionIngestItem,
    PredictionIngestRequest,
    PredictionIngestResponse,
)
from backend.quality.tokens import require_ingest_token
from backend.users.deps import get_db

router = APIRouter(
    prefix="/api/internal",
    tags=["internal"],
    dependencies=[Depends(require_ingest_token)],
)


@router.get("/predictions/pending", response_model=PendingResponse)
def pending_predictions(
    limit: int = Query(default=8, ge=1, le=16),
    db: sqlite3.Connection = Depends(get_db),
):
    """Documents needing a prediction: none stored, or stored against older text."""
    return {"documents": service.pending_documents(db, limit=limit)}


@router.post("/predictions", response_model=PredictionIngestResponse)
def ingest_predictions(
    payload: PredictionIngestRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    """Idempotent upsert. Items for unknown documents are skipped, not rejected."""
    accepted = []
    rejected = 0
    for raw_item in payload.items:
        try:
            accepted.append(PredictionIngestItem.model_validate(raw_item).model_dump())
        except ValidationError:
            rejected += 1
    upserted = service.upsert_predictions(db, accepted) if accepted else 0
    return {"upserted": upserted, "rejected": rejected}
