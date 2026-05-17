"""Document listing and reading endpoints."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.users.deps import get_current_user, get_db
from backend.documents import service
from backend.documents.models import (
    DocumentDetail, DocumentsListResponse,
)

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents", response_model=DocumentsListResponse)
def list_docs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(get_current_user),
):
    """Paginated. Defaults to 50 rows; max 200. Without these caps the
    endpoint returned every row in `documents_meta` (~17.9k rows in
    production) on every request — a multi-MB JSON response that would
    OOM at larger scale."""
    docs, total = service.list_documents(db, limit=limit, offset=offset)
    return {"documents": docs, "total": total}


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_doc(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(get_current_user),
):
    doc = service.get_document(db, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    return doc
