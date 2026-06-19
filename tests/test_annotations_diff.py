import pytest
from backend.annotations.diff import (
    normalize_reference,
    normalize_references,
    canonical_key,
    references_diff,
    is_diff_zero,
    InvalidReference,
    DuplicateReference,
)


def _ref(**kwargs):
    base = {
        "kanun_no": None,
        "kanun_ad": None,
        "madde": None,
        "fikra": None,
        "bent": None,
        "source_text": "x",
    }
    base.update(kwargs)
    return base


# --- normalize_reference ---


def test_normalize_strips_whitespace():
    r = normalize_reference({"source_text": "  hello  ", "kanun_no": "  193 "})
    assert r["source_text"] == "hello"
    assert r["kanun_no"] == "193"


def test_normalize_empty_strings_become_none():
    r = normalize_reference({"source_text": "x", "kanun_no": "", "madde": "   "})
    assert r["kanun_no"] is None
    assert r["madde"] is None


def test_normalize_missing_optional_fields_default_to_none():
    r = normalize_reference({"source_text": "x"})
    assert r["kanun_no"] is None
    assert r["kanun_ad"] is None
    assert r["madde"] is None
    assert r["fikra"] is None
    assert r["bent"] is None


def test_normalize_rejects_missing_source_text():
    with pytest.raises(InvalidReference):
        normalize_reference({"kanun_no": "193"})


def test_normalize_rejects_empty_source_text():
    with pytest.raises(InvalidReference):
        normalize_reference({"source_text": "   "})


def test_normalize_preserves_madde_format():
    """Madde is a free string ('Mükerrer 20', 'Geçici 5')."""
    r = normalize_reference({"source_text": "x", "madde": "Mükerrer 20"})
    assert r["madde"] == "Mükerrer 20"


# --- normalize_references (list) ---


def test_normalize_list_empty():
    assert normalize_references([]) == []


def test_normalize_list_rejects_exact_duplicate():
    refs = [
        _ref(kanun_no="193", madde="37", source_text="text A"),
        _ref(kanun_no="193", madde="37", source_text="text A"),
    ]
    with pytest.raises(DuplicateReference):
        normalize_references(refs)


def test_normalize_list_allows_partial_duplicate():
    """Same kanun_no/madde but different source_text → not a duplicate."""
    refs = [
        _ref(kanun_no="193", madde="37", source_text="atif 1"),
        _ref(kanun_no="193", madde="37", source_text="atif 2"),
    ]
    out = normalize_references(refs)
    assert len(out) == 2


def test_normalize_list_normalizes_then_dedupes():
    """Whitespace differences alone don't avoid duplicate detection."""
    refs = [
        _ref(kanun_no="193", source_text="hello"),
        _ref(kanun_no=" 193 ", source_text="hello   "),
    ]
    with pytest.raises(DuplicateReference):
        normalize_references(refs)


# --- canonical_key + diff ---


def test_canonical_key_is_deterministic():
    a = _ref(kanun_no="193", madde="37", source_text="x")
    b = _ref(kanun_no="193", madde="37", source_text="x")
    assert canonical_key(a) == canonical_key(b)


def test_diff_added_only():
    prev = []
    curr = [_ref(kanun_no="193", source_text="atif")]
    diff = references_diff(prev, curr)
    assert len(diff["added"]) == 1
    assert diff["removed"] == []
    assert not is_diff_zero(diff)


def test_diff_removed_only():
    prev = [_ref(kanun_no="193", source_text="atif")]
    curr = []
    diff = references_diff(prev, curr)
    assert diff["added"] == []
    assert len(diff["removed"]) == 1


def test_diff_zero_when_same_content():
    refs = [
        _ref(kanun_no="193", source_text="x"),
        _ref(kanun_no="5520", source_text="y"),
    ]
    assert is_diff_zero(references_diff(refs, refs))


def test_diff_zero_independent_of_order():
    """Set semantics — order doesn't matter."""
    a = _ref(kanun_no="193", source_text="x")
    b = _ref(kanun_no="5520", source_text="y")
    diff = references_diff([a, b], [b, a])
    assert is_diff_zero(diff)


def test_diff_detects_modified_as_remove_plus_add():
    """Set semantics: changed source_text = old removed + new added."""
    prev = [_ref(kanun_no="193", source_text="old text")]
    curr = [_ref(kanun_no="193", source_text="new text")]
    diff = references_diff(prev, curr)
    assert len(diff["added"]) == 1
    assert len(diff["removed"]) == 1
    assert diff["added"][0]["source_text"] == "new text"
    assert diff["removed"][0]["source_text"] == "old text"


def test_normalize_identifier():
    from backend.annotations.diff import normalize_identifier

    assert normalize_identifier("birinci") == "1"
    assert normalize_identifier("ikinci") == "2"
    assert normalize_identifier("üçüncü") == "3"
    assert normalize_identifier("dördüncü") == "4"
    assert normalize_identifier("beşinci") == "5"
    assert normalize_identifier("altıncı") == "6"
    assert normalize_identifier("yedinci") == "7"
    assert normalize_identifier("sekizinci") == "8"
    assert normalize_identifier("dokuzuncu") == "9"
    assert normalize_identifier("onuncu") == "10"
    assert normalize_identifier("(a)") == "a"
    assert normalize_identifier("(A).") == "a"
    assert normalize_identifier('"A"') == "a"
    assert normalize_identifier("'a'") == "a"
    assert normalize_identifier("`A`") == "a"
    assert normalize_identifier("[b]") == "b"
    assert normalize_identifier("{C},") == "c"
    assert normalize_identifier("a.") == "a"
    assert normalize_identifier(None) is None


def test_normalize_kanun_adi():
    from backend.annotations.diff import normalize_kanun_adi

    assert normalize_kanun_adi("KVK") == "Kurumlar Vergisi Kanunu"
    assert normalize_kanun_adi("GVK") == "Gelir Vergisi Kanunu"
    assert normalize_kanun_adi("VUK") == "Vergi Usul Kanunu"
    assert normalize_kanun_adi("VUKKANUNU") == "Vergi Usul Kanunu"
    assert normalize_kanun_adi("GVKKANUNU") == "Gelir Vergisi Kanunu"
    assert normalize_kanun_adi("KVKKANUNU") == "Kurumlar Vergisi Kanunu"
    assert normalize_kanun_adi("DVKKANUNU") == "Damga Vergisi Kanunu"
    
    # Test parenthetical removal
    assert normalize_kanun_adi("Kurumlar Vergisi (KVK) Kanunu") == "Kurumlar Vergisi Kanunu"
    assert normalize_kanun_adi("Kurumlar Vergisi (KVK) Kanununun") == "Kurumlar Vergisi Kanunu"
    
    # Test suffixes on abbreviations
    assert normalize_kanun_adi("KVK'nın") == "Kurumlar Vergisi Kanunu"
    assert normalize_kanun_adi("GVK'ya") == "Gelir Vergisi Kanunu"
    assert normalize_kanun_adi("VUK'un") == "Vergi Usul Kanunu"
    assert normalize_kanun_adi("KDVK'nın") == "Katma Değer Vergisi Kanunu"
    
    # Test suffixes on law name
    assert normalize_kanun_adi("Kurumlar Vergisi Kanunu'na") == "Kurumlar Vergisi Kanunu"
    assert normalize_kanun_adi("Kurumlar Vergisi Kanunundan") == "Kurumlar Vergisi Kanunu"
    
    # Test law base with suffix
    assert normalize_kanun_adi("Kurumlar Vergisi'nde") == "Kurumlar Vergisi Kanunu"
    
    # Test newly added laws/abbreviations
    assert normalize_kanun_adi("TTK") == "Türk Ticaret Kanunu"
    assert normalize_kanun_adi("KVKK'ya") == "Kişisel Verilerin Korunması Kanunu"
    assert normalize_kanun_adi("AATUHK") == "Amme Alacaklarının Tahsil Usulü Hakkında Kanun"

    assert normalize_kanun_adi("Kanun") == "Kanun"
    assert normalize_kanun_adi(None) is None


def test_parse_madde_token():
    from backend.annotations.diff import parse_madde_token

    assert parse_madde_token("16/1-a") == ("16", "1", "a")
    assert parse_madde_token("17/5-a") == ("17", "5", "a")
    assert parse_madde_token("5-a") == ("5", "", "a")
    assert parse_madde_token("17-a") == ("17", "", "a")
    assert parse_madde_token("13/a") == ("13", "", "a")  # No 13/a special exception
    assert parse_madde_token("16/1") == ("16", "1", "")
    assert parse_madde_token("17/5") == ("17", "5", "")
    assert parse_madde_token("5") == ("5", "", "")
    assert parse_madde_token(None) == ("", "", "")


def test_parse_madde_token_rejects_ambiguous_complex_values():
    from backend.annotations.diff import parse_madde_token

    for value in ("17/5/a-b", "17--a", "/5-a", "17/-a", "17/"):
        with pytest.raises(InvalidReference):
            parse_madde_token(value)


def test_normalize_reference_with_complex_madde():
    from backend.annotations.diff import normalize_reference

    ref = {"source_text": "x", "madde": "16/1-a"}
    normalized = normalize_reference(ref)
    assert normalized["madde"] == "16"
    assert normalized["fikra"] == "1"
    assert normalized["bent"] == "a"


def test_normalize_list_dedupes_identifier_case_after_cleaning():
    refs = [
        _ref(kanun_no="193", madde="37", bent="A", source_text="text"),
        _ref(kanun_no="193", madde="37", bent="a", source_text="text"),
    ]
    with pytest.raises(DuplicateReference):
        normalize_references(refs)


def test_generic_reference_suppression():
    from backend.annotations.diff import normalize_references

    refs = [
        {"source_text": "general text", "kanun_no": "5520"},
        {"source_text": "specific text", "kanun_no": "5520", "madde": "5"},
    ]
    normalized = normalize_references(refs)
    # The generic reference should be suppressed, leaving only the specific one
    assert len(normalized) == 1
    assert normalized[0]["madde"] == "5"


def test_generic_reference_suppression_groups_known_law_name_and_number():
    refs = [
        {"source_text": "general text", "kanun_ad": "VUK"},
        {"source_text": "specific text", "kanun_no": "213", "madde": "5"},
        {"source_text": "kvk general", "kanun_ad": "KVK"},
        {"source_text": "kvk specific", "kanun_no": "5520", "madde": "6"},
    ]
    normalized = normalize_references(refs)

    assert len(normalized) == 2
    assert [r["source_text"] for r in normalized] == ["specific text", "kvk specific"]
    assert normalized[0]["kanun_no"] == "213"
    assert normalized[1]["kanun_no"] == "5520"


def test_law_family_key_keeps_kanun_no_authoritative_over_known_name():
    refs = [
        {"source_text": "number wins general", "kanun_no": "999", "kanun_ad": "VUK"},
        {"source_text": "real vuk specific", "kanun_no": "213", "madde": "5"},
    ]
    normalized = normalize_references(refs)

    assert len(normalized) == 2
    assert normalized[0]["kanun_no"] == "999"
    assert normalized[0]["kanun_ad"] == "Vergi Usul Kanunu"
    assert normalized[1]["kanun_no"] == "213"


def test_law_name_family_mapping_does_not_fill_missing_kanun_no():
    normalized = normalize_references([
        {"source_text": "name only", "kanun_ad": "Harçlar Kanunu", "madde": "1"},
    ])

    assert normalized[0]["kanun_ad"] == "Harçlar Kanunu"
    assert normalized[0]["kanun_no"] is None


def test_normalize_madde():
    from backend.annotations.diff import normalize_madde

    assert normalize_madde("15inci") == "15"
    assert normalize_madde("madd 15") == "15"
    assert normalize_madde("15. madde") == "15"
    assert normalize_madde(None) is None
