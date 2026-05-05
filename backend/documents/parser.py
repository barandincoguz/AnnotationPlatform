"""JSON → DB row transformation.

Source JSON shape (from external pipeline):
  {
    "evrakOid": str,                # required (= document_id)
    "pdfText": str,                 # required
    "sayi": int|null,
    "tarih": str|null,              # YYYYMMDD
    "basvuruTarihi": str|null,
    "vergiTuru": str|null,
    "vergiDonemi": str|null,
    "konu": str|null,
    "mukellefiyetTuru": str|null,
    "htmlText": str|null,
    "kanunBilgileri": [
      {"kanunMaddesi": str, "kanunKodu": str, "kanunMaddesiTuru": str}, ...
    ],
    "bkkTebligSirkuBilgileri": [
      {"turu": str, "kanunKodu": str, "maddeNo": str}, ...
    ],
  }

Output dict has 3 keys: meta (documents_meta row), kanun_refs (list of rows),
bkk_refs (list of rows). Service layer inserts these.
"""
from backend.documents.metrics import (
    word_count, sentence_count, text_density, classify_difficulty
)


class ParseError(ValueError):
    """Raised when the source JSON is missing required fields."""


def _require(doc: dict, key: str, file_path: str) -> object:
    if key not in doc or doc[key] in (None, ""):
        raise ParseError(f"missing required field '{key}' in {file_path}")
    return doc[key]


def parse_document(
    doc: dict,
    *,
    file_path: str,
    kolay_max: int = 500,
    orta_max: int = 2000,
) -> dict:
    document_id = _require(doc, "evrakOid", file_path)
    pdf_text = _require(doc, "pdfText", file_path)

    wc = word_count(pdf_text)
    sc = sentence_count(pdf_text)
    td = text_density(wc, sc)
    diff = classify_difficulty(wc, kolay_max=kolay_max, orta_max=orta_max)

    meta = {
        "document_id": document_id,
        "file_path": file_path,
        "sayi": doc.get("sayi"),
        "tarih": doc.get("tarih"),
        "basvuru_tarihi": doc.get("basvuruTarihi"),
        "vergi_donemi": doc.get("vergiDonemi"),
        "konu": doc.get("konu"),
        "vergi_turu": doc.get("vergiTuru"),
        "mukellefiyet_turu": doc.get("mukellefiyetTuru"),
        "pdf_text": pdf_text,
        "html_text": doc.get("htmlText"),
        "word_count": wc,
        "sentence_count": sc,
        "text_density": td,
        "estimated_difficulty": diff,
        "topic_category": None,  # admin/user later
    }

    kanun_refs = []
    for i, ref in enumerate(doc.get("kanunBilgileri", []) or []):
        kanun_refs.append({
            "seq": i,
            "kanun_kodu": ref.get("kanunKodu", ""),
            "kanun_maddesi": ref.get("kanunMaddesi"),
            "kanun_maddesi_turu": ref.get("kanunMaddesiTuru"),
        })

    bkk_refs = []
    for i, ref in enumerate(doc.get("bkkTebligSirkuBilgileri", []) or []):
        bkk_refs.append({
            "seq": i,
            "turu": ref.get("turu"),
            "kanun_kodu": ref.get("kanunKodu"),
            "madde_no": ref.get("maddeNo"),
        })

    return {"meta": meta, "kanun_refs": kanun_refs, "bkk_refs": bkk_refs}
