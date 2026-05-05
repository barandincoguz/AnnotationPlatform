from backend.documents.parser import parse_document, ParseError
import pytest


SAMPLE_DOC = {
    "evrakOid": "1hmkqodt0v1d55",
    "sayi": 24,
    "tarih": "20260123",
    "basvuruTarihi": "20250604",
    "vergiTuru": "0001",
    "vergiDonemi": "01/2025-12/2025",
    "konu": "Kiraya verilen gayrimenkulün vergilendirilmesi",
    "pdfText": "Bu bir test pdf metnidir. İçinde birkaç cümle var.",
    "htmlText": "<p>html version</p>",
    "kanunBilgileri": [
        {"kanunMaddesi": "37", "kanunKodu": "193 - GELİR VERGİSİ KANUNU", "kanunMaddesiTuru": "ASIL"},
        {"kanunMaddesi": "70", "kanunKodu": "193 - GELİR VERGİSİ KANUNU", "kanunMaddesiTuru": "ASIL"},
    ],
    "bkkTebligSirkuBilgileri": [
        {"turu": "TEBLİĞ", "kanunKodu": "193 - GELİR VERGİSİ KANUNU", "maddeNo": "325"},
    ],
}


def test_parse_extracts_evrakoid_as_document_id():
    parsed = parse_document(SAMPLE_DOC, file_path="/data/sample.json")
    assert parsed["meta"]["document_id"] == "1hmkqodt0v1d55"
    assert parsed["meta"]["file_path"] == "/data/sample.json"


def test_parse_copies_json_fields():
    parsed = parse_document(SAMPLE_DOC, file_path="/x.json")
    m = parsed["meta"]
    assert m["sayi"] == 24
    assert m["tarih"] == "20260123"
    assert m["basvuru_tarihi"] == "20250604"
    assert m["vergi_donemi"] == "01/2025-12/2025"
    assert m["vergi_turu"] == "0001"
    assert m["konu"] == "Kiraya verilen gayrimenkulün vergilendirilmesi"
    assert m["pdf_text"].startswith("Bu bir test")
    assert m["html_text"] == "<p>html version</p>"


def test_parse_computes_metrics():
    parsed = parse_document(SAMPLE_DOC, file_path="/x.json")
    m = parsed["meta"]
    assert m["word_count"] > 0
    assert m["sentence_count"] >= 2
    assert m["text_density"] > 0
    assert m["estimated_difficulty"] in ("Kolay", "Orta", "Zor")


def test_parse_kanun_refs():
    parsed = parse_document(SAMPLE_DOC, file_path="/x.json")
    refs = parsed["kanun_refs"]
    assert len(refs) == 2
    assert refs[0]["seq"] == 0
    assert refs[0]["kanun_kodu"] == "193 - GELİR VERGİSİ KANUNU"
    assert refs[0]["kanun_maddesi"] == "37"
    assert refs[0]["kanun_maddesi_turu"] == "ASIL"
    assert refs[1]["seq"] == 1


def test_parse_bkk_refs():
    parsed = parse_document(SAMPLE_DOC, file_path="/x.json")
    refs = parsed["bkk_refs"]
    assert len(refs) == 1
    assert refs[0]["turu"] == "TEBLİĞ"
    assert refs[0]["kanun_kodu"] == "193 - GELİR VERGİSİ KANUNU"
    assert refs[0]["madde_no"] == "325"


def test_parse_missing_evrakoid_raises():
    with pytest.raises(ParseError):
        parse_document({"pdfText": "x"}, file_path="/x.json")


def test_parse_missing_pdftext_raises():
    with pytest.raises(ParseError):
        parse_document({"evrakOid": "abc"}, file_path="/x.json")


def test_parse_optional_fields_missing_become_none():
    minimal = {"evrakOid": "x", "pdfText": "Hello world."}
    parsed = parse_document(minimal, file_path="/x.json")
    m = parsed["meta"]
    assert m["sayi"] is None
    assert m["tarih"] is None
    assert m["konu"] is None
    assert m["mukellefiyet_turu"] is None
    assert m["html_text"] is None
    assert parsed["kanun_refs"] == []
    assert parsed["bkk_refs"] == []


def test_parse_handles_mukellefiyet_turu_when_present():
    doc = {**SAMPLE_DOC, "mukellefiyetTuru": "Tam Mükellef"}
    parsed = parse_document(doc, file_path="/x.json")
    assert parsed["meta"]["mukellefiyet_turu"] == "Tam Mükellef"
