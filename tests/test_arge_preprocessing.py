"""Regressions for data loss, invented identities, and duplicate SFT targets."""

import json
from pathlib import Path

import pytest

from scripts.preprocess_arge_law_article import Processor, exact_document_groups, load_dq


@pytest.fixture(scope="module")
def processor():
    normalizer, _ = load_dq(Path("/Users/student2/data-quality-checker"))
    root = Path("/Users/student2/ner-project/artifacts")
    names = json.loads((root / "2026-09-16_arge-hizli-veri-temizleme/dataset/review/_canonical_law_names.json").read_text())
    registry = json.loads((root / "2026-09-18_ground-truth-hardening/data/law_provision_registry.json").read_text())
    return Processor(normalizer, names, registry)


def ref(number="193", name="Gelir Vergisi Kanunu", article="94", **extra):
    return {"kanun_no": number, "kanun_ad": name, "madde": article, **extra}


def test_nested_rows_and_different_quotes_become_one_training_target(processor):
    original = [ref(fikra="1", bent="a", source_text="first"),
                ref(fikra="2", bent="b", source_text="second")]
    output, audit, issues = processor.process("d", original, "193 sayılı Gelir Vergisi Kanununun 94 üncü maddesi")
    assert output == [ref()]
    assert [row["action"] for row in audit] == ["kept", "deduplicated"]
    assert not issues and original[0]["fikra"] == "1"


@pytest.mark.parametrize("law,article,expected", [
    ("213", "3/B", "3"), ("213", "mükerrer 298/C", "mükerrer 298"),
    ("5510", "4/B", "4"), ("4962", "17/D", "17"), ("3065", "17/4-a", "17"),
    ("5520", "32/A", "32/A"), ("5520", "32/a", "32/A"), ("213", "325/A", "325/A"),
    ("193", "Geçici 20", "geçici 20"), ("193", "gecici 20", "geçici 20"),
    ("193", "620-645", "620 ila 645"), ("193", "ek 1 ila ek 6", "ek 1 ila 6"),
    ("193", "mülga 64", "64"),
])
def test_article_level_preserves_real_inserted_articles(processor, law, article, expected):
    assert processor.article(law, article) == expected
    assert processor.article(law, expected) == expected


def test_missing_number_stays_missing_and_uses_inflected_name(processor):
    output, _, issues = processor.process("d", [ref(number="")], "Gelir Vergisi Kanununun 94 üncü maddesi")
    assert output == [ref(number="")]
    assert not issues


def test_no_law_is_invented_from_a_bare_year_or_article_number(processor):
    output, _, issues = processor.process("d", [ref(number="193", name="")], "193 lira ve 94 üncü madde")
    assert output == []
    assert issues[0]["reason"] == "law_identity_absent_from_text"


def test_a_wrong_old_number_falls_back_to_the_distinctive_name_in_text(processor):
    original = ref("7491", "Dijital Hizmet Vergisi Kanunu", "1")
    output, _, issues = processor.process("d", [original], "Dijital Hizmet Vergisi Kanununun 1 inci maddesi")
    assert output == [ref("", "Dijital Hizmet Vergisi Kanunu", "1")]
    assert not issues


def test_range_and_short_names_do_not_create_false_quarantine(processor):
    refs = [ref("213", "Vergi Usul Kanunu", str(i)) for i in (215,216,217,218,219)]
    output, _, issues = processor.process("d", refs, "Vergi Usul Kanununun 215-219 uncu ve 221 inci maddeleri")
    assert len(output) == 5 and not issues
    output, _, issues = processor.process("d", [ref("6098", "Türk Borçlar Kanunu", "620")], "Borçlar Kanununun 620 inci maddesi")
    assert len(output) == 1 and not issues


def test_enumerated_law_numbers_and_amendment_notation_are_evidence(processor):
    output, _, issues = processor.process("d", [ref("7153", "", ""), ref("5679", "", "1")],
                                         "7153 ve 7181 sayılı Kanunlar. (Değişik: 1/6/2007-5679/1 md.)")
    assert len(output) == 2 and not issues


def test_empty_old_name_can_be_recovered_without_inventing_a_number(processor):
    old = ref("6245", "", "34", source_text="Harcırah Kanununun 34 üncü maddesinde")
    output, _, issues = processor.process("d", [old], "Harcırah Kanununun 34 üncü maddesinde")
    assert output == [ref("", "Harcırah Kanunu", "34")] and not issues


def test_name_and_number_spelling_of_same_provision_deduplicated(processor):
    output, audit, issues = processor.process("d", [ref(number=""), ref()], "193 sayılı Gelir Vergisi Kanununun 94 üncü maddesi")
    assert output == [ref()] and not issues
    assert sum(row["action"] == "deduplicated" for row in audit) == 1


def test_same_name_does_not_merge_repealed_and_successor_laws(processor):
    output, _, issues = processor.process("d", [ref("5422", "Kurumlar Vergisi Kanunu", "8"),
                                                ref("5520", "Kurumlar Vergisi Kanunu", "8")],
                                         "5422 ve 5520 sayılı Kurumlar Vergisi Kanununun 8 inci maddesi")
    assert {r["kanun_no"] for r in output} == {"5422", "5520"}
    assert not issues


def test_qualifiers_and_laws_never_merge_with_plain_article(processor):
    original = [ref(article="20"), ref(article="Geçici 20"), ref(article="geçici 20"),
                ref(article="mükerrer 20"), ref("213", "Vergi Usul Kanunu", "20")]
    text = "193 sayılı Gelir Vergisi Kanununun 20, geçici 20, mükerrer 20 maddeleri; 213 sayılı Kanunun 20 maddesi"
    output, _, issues = processor.process("d", original, text)
    assert len(output) == 4 and not issues
    assert processor.process("d", output, text)[0] == output


def test_law_only_is_removed_only_if_that_same_law_has_an_article(processor):
    output, audit, issues = processor.process("d", [ref(article=""), ref(), ref("213", "Vergi Usul Kanunu", "")],
                                             "193 sayılı Kanunun 94 üncü maddesi ve Vergi Usul Kanunu")
    assert len(output) == 2 and not issues
    assert sum(row["action"] == "subsumed_law_only" for row in audit) == 1
    assert any(r["kanun_no"] == "213" and not r["madde"] for r in output)


def test_decree_number_and_absent_article_go_to_review(processor):
    output, _, issues = processor.process("d", [ref(number="2007/13033"), ref(article="98765")],
                                         "193 sayılı Gelir Vergisi Kanunu, 2007/13033 sayılı karar")
    assert not output
    assert {r["reason"] for r in issues} == {"invalid_law_number", "article_number_absent_from_text"}


def test_document_duplication_is_separate_from_reference_duplication():
    docs = [{"doc_id":"a", "text":"Vergi KANUNU 94"}, {"doc_id":"b", "text":"vergi kanunu 94"},
            {"doc_id":"c", "text":"vergi kanunu 95"}]
    assert exact_document_groups(docs) == [["a", "b"]]
