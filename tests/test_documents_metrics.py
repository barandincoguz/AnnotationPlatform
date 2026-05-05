from backend.documents.metrics import (
    word_count, sentence_count, text_density,
    classify_difficulty,
)


def test_word_count_simple():
    assert word_count("hello world foo") == 3


def test_word_count_empty():
    assert word_count("") == 0


def test_word_count_turkish():
    assert word_count("Ali ve Veli okula gitti.") == 5


def test_sentence_count_periods():
    assert sentence_count("Bu bir cümle. Bu da bir cümle.") == 2


def test_sentence_count_with_question_and_exclamation():
    assert sentence_count("Niye? Çünkü öyle! Ve ayrıca.") == 3


def test_sentence_count_zero_raises_to_one_via_density_helper():
    """text_density(words, 0) should treat sentence_count as 1 to avoid div by zero."""
    assert text_density(50, 0) == 50.0


def test_text_density_normal():
    assert text_density(100, 5) == 20.0


def test_text_density_rounded_one_decimal():
    assert text_density(100, 7) == 14.3


def test_classify_difficulty_kolay():
    assert classify_difficulty(499, kolay_max=500, orta_max=2000) == "Kolay"


def test_classify_difficulty_orta():
    assert classify_difficulty(1500, kolay_max=500, orta_max=2000) == "Orta"


def test_classify_difficulty_zor():
    assert classify_difficulty(3500, kolay_max=500, orta_max=2000) == "Zor"


def test_classify_difficulty_at_boundary_kolay():
    assert classify_difficulty(500, kolay_max=500, orta_max=2000) == "Orta"


def test_classify_difficulty_at_boundary_zor():
    assert classify_difficulty(2000, kolay_max=500, orta_max=2000) == "Zor"
