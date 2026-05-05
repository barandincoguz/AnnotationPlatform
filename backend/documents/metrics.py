"""Text metrics + difficulty classification.

All metrics are computed from `pdf_text` only. They run on document ingest
and are stored in `documents_meta`. Used by the UI to show difficulty badge,
by training to pick balanced gold docs, and by analytics.
"""
from typing import Literal


def word_count(text: str) -> int:
    """Whitespace-split word count."""
    return len(text.split())


def sentence_count(text: str) -> int:
    """Count sentence-terminating punctuation. Min 1 if any text exists."""
    if not text:
        return 0
    count = text.count(".") + text.count("?") + text.count("!")
    return max(count, 1) if text.strip() else 0


def text_density(words: int, sentences: int) -> float:
    """Average words per sentence. Returns 0 for empty input."""
    if words == 0:
        return 0.0
    safe_sentences = sentences if sentences > 0 else 1
    return round(words / safe_sentences, 1)


def classify_difficulty(
    words: int,
    *,
    kolay_max: int = 500,
    orta_max: int = 2000,
) -> Literal["Kolay", "Orta", "Zor"]:
    """Classify by word count. Thresholds are admin-configurable via site_settings."""
    if words < kolay_max:
        return "Kolay"
    if words < orta_max:
        return "Orta"
    return "Zor"
