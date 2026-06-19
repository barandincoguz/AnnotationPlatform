"""Sanity check on the static quiz question list.

These tests don't pin specific question content (admin will replace later via
Paket 11) — they pin shape invariants so a future edit doesn't accidentally
break the data model the service code depends on.
"""
from backend.training import quiz_data


def test_questions_present():
    assert len(quiz_data.QUIZ_QUESTIONS) >= 8


def test_at_least_5_questions_for_sampling():
    """The training start endpoint samples 5 random questions per attempt;
    we need a minimum stock of 5 to avoid running out."""
    assert len(quiz_data.QUIZ_QUESTIONS) >= 5


def test_question_shape():
    for q in quiz_data.QUIZ_QUESTIONS:
        assert isinstance(q["id"], str) and q["id"].startswith("q")
        assert isinstance(q["text"], str) and len(q["text"]) >= 10
        assert isinstance(q["choices"], list)
        assert len(q["choices"]) == 4
        assert all(isinstance(c, str) and c for c in q["choices"])
        assert isinstance(q["correct_choice_idx"], int)
        assert 0 <= q["correct_choice_idx"] <= 3


def test_question_ids_unique():
    ids = [q["id"] for q in quiz_data.QUIZ_QUESTIONS]
    assert len(ids) == len(set(ids))


def test_questions_in_turkish():
    """Soft heuristic: at least one Turkish-specific character should appear
    across the question text (ç, ğ, ı, ö, ş, ü). Defends against an English
    placeholder leaking in."""
    text_blob = " ".join(q["text"] for q in quiz_data.QUIZ_QUESTIONS)
    tr_chars = set("çğıöşüÇĞİÖŞÜ")
    assert any(c in text_blob for c in tr_chars)


def test_questions_do_not_use_retired_save_button_label():
    content = " ".join(
        text
        for q in quiz_data.QUIZ_QUESTIONS
        for text in [q["text"], *q["choices"]]
    )
    assert "Sakla" not in content


def test_questions_do_not_expose_implementation_jargon():
    content = " ".join(
        text
        for q in quiz_data.QUIZ_QUESTIONS
        for text in [q["text"], *q["choices"]]
    ).lower()
    for term in (
        "is_diff_zero",
        "frontend",
        "primary key",
        "database",
        "veritabanı",
        "backup",
        "tuple",
        "422",
    ):
        assert term not in content
