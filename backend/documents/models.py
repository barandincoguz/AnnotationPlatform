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


class KanunRef(BaseModel):
    """A single kanun (law) reference attached to a document during
    ingestion. Sourced from `kanunBilgileri[]` in the external JSON."""
    seq: int
    kanun_kodu: str
    kanun_maddesi: Optional[str]
    kanun_maddesi_turu: Optional[str]


class BkkRef(BaseModel):
    """A single BKK / tebliğ / sirküler reference attached to a document
    during ingestion. Sourced from `bkkTebligSirkuBilgileri[]`."""
    seq: int
    turu: Optional[str]
    kanun_kodu: Optional[str]
    madde_no: Optional[str]


class DocumentDetail(DocumentSummary):
    pdf_text: str
    html_text: Optional[str]
    kanun_refs: list[KanunRef]
    bkk_refs: list[BkkRef]


class DocumentsListResponse(BaseModel):
    documents: list[DocumentSummary]
    total: int
