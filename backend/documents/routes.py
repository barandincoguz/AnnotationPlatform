"""Document listing and reading endpoints."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.users.deps import get_current_user, get_db
from backend.documents import service
from backend.documents.models import (
    DocumentSummary, DocumentDetail, DocumentsListResponse,
)

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents", response_model=DocumentsListResponse)
def list_docs(
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(get_current_user),
):
    docs = service.list_documents(db)
    return {"documents": docs, "total": len(docs)}


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
