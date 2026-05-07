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


def test_match_concept_source_text_in_concept_ignored():
    """source_text is NEVER a match constraint, even if present in concept."""
    refs = [_ref(kanun_no="5520", madde="5", source_text="totally different wording")]
    concept = {"kanun_no": "5520", "madde": "5", "source_text": "expected wording"}
    assert matching.match_concept(concept, refs) is True


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
