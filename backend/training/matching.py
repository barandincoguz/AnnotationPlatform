"""Pure functions: quiz scoring + subset-semantic gold-doc concept matching.

No DB access. No side effects. Used by training.service to compute attempt
scores at submit time.

Subset-semantic concept matching contract:
  Given a concept dict `c` and a user reference dict `r`, `r` matches `c` iff:
    for every key k in c:
      if k == "source_text": skip (source_text is never a constraint)
      if c[k] is empty (None or ""): skip (empty value = wildcard)
      else: r.get(k) must equal c[k] (after string normalization)

  A concept "matches" a reference list if AT LEAST ONE reference satisfies
  the above.

  A gold doc's match count = number of distinct concepts that match.
  A gold doc passes if match_count >= min_concept_count.
"""
from typing import Iterable
import unicodedata


_IGNORED_FIELDS = ("source_text",)


def score_quiz(
    questions: Iterable[dict],
    answers: dict[str, int],
) -> int:
    """Return the count of correct answers across the given questions.

    `questions`: iterable of {"id", "correct_choice_idx", ...}.
    `answers`:   {question_id: chosen_choice_idx}.

    Missing answers count as wrong. Extra answers (for question_ids not in
    `questions`) are ignored.
    """
    score = 0
    for q in questions:
        chosen = answers.get(q["id"])
        if chosen is not None and chosen == q["correct_choice_idx"]:
            score += 1
    return score


def score_quiz_detailed(
    questions: Iterable[dict],
    answers: dict[str, int],
) -> tuple[int, list[dict]]:
    """Like score_quiz but returns per-question results alongside the score.

    Returns (score, results) where each result dict has:
      question_id, user_choice (int|None), correct_choice (int), is_correct (bool).
    """
    score = 0
    results: list[dict] = []
    for q in questions:
        chosen = answers.get(q["id"])
        correct = q["correct_choice_idx"]
        is_correct = chosen is not None and chosen == correct
        if is_correct:
            score += 1
        results.append({
            "question_id": q["id"],
            "user_choice": chosen,
            "correct_choice": correct,
            "is_correct": is_correct,
        })
    return score, results


def _concept_constraints(concept: dict) -> dict:
    """Return only the (key, value) pairs in concept that are active match
    constraints — i.e. exclude empty values and the source_text key."""
    return {
        k: v for k, v in concept.items()
        if k not in _IGNORED_FIELDS and v not in (None, "")
    }


def _normalize_value(v):
    """Normalize a concept/reference field value for tolerant comparison.

    Pipeline:
      1. None → return None (preserves wildcard semantics in
         _concept_constraints).
      2. unicodedata.normalize('NFC', str(v)) — combine code points
         so 'ü' and 'ü' compare equal.
      3. .strip().lower() — Turkish-safe; Python's str.lower() handles
         most cases, including İ → i + combining dot.
      4. Strip U+0307 (combining dot above) that lower() introduced on İ.
      5. ' '.join(s.split()) — collapse runs of whitespace.
      6. For each space-separated token that is pure digits, strip
         leading zeros (preserving '0' as '0' so it never becomes empty).

    Returns '' for inputs that became empty after strip, so that
    _concept_constraints' empty-value filter still excludes them as
    'wildcard' values.
    """
    if v is None:
        return None
    s = unicodedata.normalize("NFC", str(v))
    if not s.strip():
        return ""
    s = s.strip().lower().replace("̇", "")
    s = " ".join(s.split())
    parts = s.split(" ")
    out_parts: list[str] = []
    for p in parts:
        if p.isdigit():
            out_parts.append(p.lstrip("0") or "0")
        else:
            out_parts.append(p)
    return " ".join(out_parts)


def match_concept(concept: dict, references: Iterable[dict]) -> bool:
    """Return True iff at least one reference satisfies all constraints
    in `concept` (subset semantics) after string normalization.

    Normalization is applied symmetrically to concept values AND
    reference values before equality comparison; see _normalize_value
    for the pipeline. source_text is still excluded from constraints.
    """
    constraints_raw = _concept_constraints(concept)
    constraints = {k: _normalize_value(v) for k, v in constraints_raw.items()}
    if not constraints:
        return any(True for _ in references)
    for r in references:
        normed = {k: _normalize_value(r.get(k)) for k in constraints}
        if all(normed.get(k) == v for k, v in constraints.items()):
            return True
    return False


def match_gold_doc(
    expected_concepts: list[dict],
    references: list[dict],
) -> dict:
    """Return a summary: {matched_count, expected_count, matched_concepts}.

    `matched_concepts` is the list of concept dicts (in the order given) for
    which at least one reference matched."""
    matched: list[dict] = []
    for c in expected_concepts:
        if match_concept(c, references):
            matched.append(c)
    return {
        "matched_count": len(matched),
        "expected_count": len(expected_concepts),
        "matched_concepts": matched,
    }


def is_doc_pass(summary: dict, *, min_concept_count: int) -> bool:
    """Return True iff the user's annotation passes the gold doc's threshold."""
    return summary["matched_count"] >= min_concept_count
