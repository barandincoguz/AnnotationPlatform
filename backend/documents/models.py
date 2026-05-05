from typing import Optional
from pydantic import BaseModel


class DocumentSummary(BaseModel):
    document_id: str
    sayi: Optional[int]
    tarih: Optional[str]
    basvuru_tarihi: Optional[str]
    vergi_donemi: Optional[str]
    konu: Optional[str]
    vergi_turu: Optional[str]
    mukellefiyet_turu: Optional[str]
    word_count: int
    sentence_count: int
    text_density: float
    estimated_difficulty: str
    topic_category: Optional[str]
    created_at: str


class DocumentDetail(DocumentSummary):
    pdf_text: str
    html_text: Optional[str]


class DocumentsListResponse(BaseModel):
    documents: list[DocumentSummary]
    total: int
