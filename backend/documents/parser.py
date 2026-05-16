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
import html
import re

from backend.documents.metrics import (
    word_count, sentence_count, text_density, classify_difficulty
)


class ParseError(ValueError):
    """Raised when the source JSON is missing required fields."""


def _require(doc: dict, key: str, file_path: str) -> object:
    if key not in doc or doc[key] in (None, ""):
        raise ParseError(f"missing required field '{key}' in {file_path}")
    return doc[key]


_BLOCK_TAG_RE = re.compile(r"</?(p|div|br|li|tr|h[1-6])\b[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RUN_RE = re.compile(r"[ \t]+")
_NL_RUN_RE = re.compile(r"\n\s*\n+")


def html_to_text(s: str) -> str:
    s = _BLOCK_TAG_RE.sub("\n", s)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    s = _WS_RUN_RE.sub(" ", s)
    s = _NL_RUN_RE.sub("\n\n", s)
    return s.strip()


def parse_document(
    doc: dict,
    *,
    file_path: str,
    kolay_max: int = 500,
    orta_max: int = 2000,
) -> dict:
    document_id = _require(doc, "evrakOid", file_path)
    raw_pdf = doc.get("pdfText") or ""
    raw_html = doc.get("htmlText") or ""
    if raw_pdf.strip():
        pdf_text = raw_pdf
    elif raw_html.strip():
        pdf_text = html_to_text(raw_html)
        if not pdf_text:
            raise ParseError(f"empty text after htmlText fallback for evrakOid={document_id} in {file_path}")
    else:
        raise ParseError(f"missing both pdfText and htmlText for evrakOid={document_id} in {file_path}")

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
