"""Unit tests for training.matching pure functions."""
from backend.training import matching


# ---- score_quiz ----

def test_score_quiz_all_correct():
    questions = [
        {"id": "q01", "correct_choice_idx": 1, "text": "?", "choices": ["a", "b", "c", "d"]},
        {"id": "q02", "correct_choice_idx": 0, "text": "?", "choices": ["a", "b", "c", "d"]},
    ]
    answers = {"q01": 1, "q02": 0}
    assert matching.score_quiz(questions, answers) == 2


def test_score_quiz_partial():
    questions = [
        {"id": "q01", "correct_choice_idx": 1, "text": "?", "choices": ["a", "b", "c", "d"]},
        {"id": "q02", "correct_choice_idx": 0, "text": "?", "choices": ["a", "b", "c", "d"]},
        {"id": "q03", "correct_choice_idx": 2, "text": "?", "choices": ["a", "b", "c", "d"]},
    ]
    answers = {"q01": 1, "q02": 3, "q03": 2}  # 2 right, 1 wrong
    assert matching.score_quiz(questions, answers) == 2


def test_score_quiz_missing_answer_counts_as_wrong():
    questions = [
        {"id": "q01", "correct_choice_idx": 1, "text": "?", "choices": ["a", "b", "c", "d"]},
        {"id": "q02", "correct_choice_idx": 0, "text": "?", "choices": ["a", "b", "c", "d"]},
    ]
    answers = {"q01": 1}  # q02 unanswered
    assert matching.score_quiz(questions, answers) == 1


def test_score_quiz_extra_answers_ignored():
    """Defensive: if frontend sends an answer for a question that isn't
    in this attempt's selection, ignore it gracefully."""
    questions = [
        {"id": "q01", "correct_choice_idx": 1, "text": "?", "choices": ["a", "b", "c", "d"]},
    ]
    answers = {"q01": 1, "q99": 0}
    assert matching.score_quiz(questions, answers) == 1


def test_score_quiz_zero_questions():
    assert matching.score_quiz([], {}) == 0


# ---- match_gold_doc + is_doc_pass ----

def _ref(**kw):
    base = {"kanun_no": "", "kanun_ad": "", "madde": "", "fikra": "", "bent": "", "source_text": ""}
    base.update(kw)
    return base


def test_match_concept_full_field_match():
    refs = [_ref(kanun_no="5520", madde="5", source_text="any text")]
    concept = {"kanun_no": "5520", "madde": "5"}
    assert matching.match_concept(concept, refs) is True


def test_match_concept_partial_field_in_concept_uses_subset_semantics():
    """concept has only kanun_no+madde. Ref has more fields filled — still matches."""
    refs = [_ref(kanun_no="5520", madde="5", fikra="1", bent="a", source_text="x")]
    concept = {"kanun_no": "5520", "madde": "5"}
    assert matching.match_concept(concept, refs) is True


def test_match_concept_extra_field_in_concept_must_match():
    """If concept demands fikra=1, ref's fikra must be 1 (or match wildcard rules)."""
    refs = [_ref(kanun_no="5520", madde="5", fikra="2")]
    concept = {"kanun_no": "5520", "madde": "5", "fikra": "1"}
    assert matching.match_concept(concept, refs) is False


def test_match_concept_empty_string_fields_in_concept_are_wildcard():
    """Empty values in concept ARE NOT match constraints."""
    refs = [_ref(kanun_no="5520", madde="5", fikra="2")]
    concept = {"kanun_no": "5520", "madde": "5", "fikra": ""}
    assert matching.match_concept(concept, refs) is True


def test_match_concept_source_text_fuzzy_matched():
    """source_text is matched fuzzily if present in concept."""
    concept = {"kanun_no": "5520", "madde": "5", "source_text": "KDV iadesi talep edilmektedir"}
    
    # 1. Close match / Substring -> passes
    refs_close = [_ref(kanun_no="5520", madde="5", source_text="kdv iadesi talep ediliyor")]
    assert matching.match_concept(concept, refs_close) is True

    # 2. Exact match -> passes
    refs_exact = [_ref(kanun_no="5520", madde="5", source_text="KDV iadesi talep edilmektedir")]
    assert matching.match_concept(concept, refs_exact) is True

    # 3. Completely different wording -> fails
    refs_diff = [_ref(kanun_no="5520", madde="5", source_text="bambaska bir alinti metni")]
    assert matching.match_concept(concept, refs_diff) is False


def test_match_concept_no_refs():
    assert matching.match_concept({"kanun_no": "5520", "madde": "5"}, []) is False


def test_match_gold_doc_counts_distinct_concepts():
    refs = [
        _ref(kanun_no="5520", madde="5", fikra="1", bent="a"),
        _ref(kanun_no="3065", madde="29"),
    ]
    expected = [
        {"kanun_no": "5520", "madde": "5"},
        {"kanun_no": "5520", "madde": "5", "fikra": "1", "bent": "a"},
        {"kanun_no": "3065", "madde": "29"},
    ]
    summary = matching.match_gold_doc(expected, refs)
    assert summary["matched_count"] == 3
    assert summary["expected_count"] == 3


def test_match_gold_doc_missed_concept():
    refs = [_ref(kanun_no="5520", madde="5")]
    expected = [
        {"kanun_no": "5520", "madde": "5"},
        {"kanun_no": "3065", "madde": "29"},  # not in refs
    ]
    summary = matching.match_gold_doc(expected, refs)
    assert summary["matched_count"] == 1
    assert summary["expected_count"] == 2


def test_is_doc_pass_threshold():
    summary = {"matched_count": 1, "expected_count": 2}
    assert matching.is_doc_pass(summary, min_concept_count=1) is True
    assert matching.is_doc_pass(summary, min_concept_count=2) is False
    assert matching.is_doc_pass({"matched_count": 0, "expected_count": 1}, min_concept_count=1) is False


# ------------------------------------------------------------------
# 16c.1 normalization tests
# ------------------------------------------------------------------

from backend.training.matching import _normalize_value, match_concept


class TestNormalizeValue:
    def test_none_passes_through(self):
        assert _normalize_value(None) is None

    def test_empty_string_passes_through_as_empty(self):
        assert _normalize_value("") == ""

    def test_trim_and_lowercase_ascii(self):
        assert _normalize_value(" Hello ") == "hello"

    def test_collapse_internal_whitespace(self):
        assert _normalize_value("Geçici  67") == "geçici 67"
        assert _normalize_value("Mükerrer\t\t80") == "mükerrer 80"

    def test_turkish_capital_i_loses_combining_dot(self):
        # "İ".lower() → "i" + combining dot above (U+0307).
        # _normalize_value must strip the combining mark.
        assert _normalize_value("İstanbul") == "istanbul"

    def test_leading_zero_strip_on_pure_numeric_token(self):
        assert _normalize_value("05520") == "5520"
        assert _normalize_value("0") == "0"  # never empty
        assert _normalize_value("Geçici 067") == "geçici 67"

    def test_non_numeric_token_keeps_leading_zero(self):
        # "0a" is not a pure digit token
        assert _normalize_value("0a") == "0a"

    def test_nfc_composition(self):
        # "ü" can be expressed as U+00FC or "u" + U+0308 combining diaeresis.
        decomposed = "ü"
        composed = "ü"
        assert _normalize_value(decomposed) == _normalize_value(composed)


class TestMatchConceptNormalization:
    def test_trailing_space_matches(self):
        concept = {"madde": "5"}
        refs = [{"madde": "5 ", "source_text": "x"}]
        assert match_concept(concept, refs) is True

    def test_case_insensitive_match(self):
        concept = {"bent": "a"}
        refs = [{"bent": "A", "source_text": "x"}]
        assert match_concept(concept, refs) is True

    def test_internal_whitespace_collapse_match(self):
        concept = {"madde": "Geçici 67"}
        refs = [{"madde": "geçici  67", "source_text": "x"}]
        assert match_concept(concept, refs) is True

    def test_leading_zero_match(self):
        concept = {"kanun_no": "5520"}
        refs = [{"kanun_no": "05520", "source_text": "x"}]
        assert match_concept(concept, refs) is True

    def test_different_values_still_reject(self):
        concept = {"madde": "5"}
        refs = [{"madde": "6", "source_text": "x"}]
        assert match_concept(concept, refs) is False

    def test_close_but_distinct_numeric_still_reject(self):
        concept = {"kanun_no": "193"}
        refs = [{"kanun_no": "194", "source_text": "x"}]
        assert match_concept(concept, refs) is False

    def test_law_name_and_number_symmetrical_match(self):
        # 1. Concept specifies number, ref specifies name/abbreviation
        concept_no = {"kanun_no": "5520", "madde": "5"}
        refs_name = [{"kanun_ad": "KVK", "madde": "5", "source_text": "x"}]
        assert match_concept(concept_no, refs_name) is True

        # 2. Concept specifies name, ref specifies number
        concept_name = {"kanun_ad": "Kurumlar Vergisi Kanunu", "madde": "5"}
        refs_no = [{"kanun_no": "5520", "madde": "5", "source_text": "x"}]
        assert match_concept(concept_name, refs_no) is True

