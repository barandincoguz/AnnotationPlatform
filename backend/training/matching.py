"""Pure functions: quiz scoring + subset-semantic gold-doc concept matching.

No DB access. No side effects. Used by training.service to compute attempt
scores at submit time.

Subset-semantic concept matching contract:
  Given a concept dict `c` and a user reference dict `r`, `r` matches `c` iff:
    for every key k in c:
      if k == "source_text": skip (source_text is never a constraint)
      if c[k] is empty (None or ""): skip (empty value = wildcard)
      else: r.get(k) must equal c[k] (exact string match)

  A concept "matches" a reference list if AT LEAST ONE reference satisfies
  the above.

  A gold doc's match count = number of distinct concepts that match.
  A gold doc passes if match_count >= min_concept_count.
"""
from typing import Iterable


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


def _concept_constraints(concept: dict) -> dict:
    """Return only the (key, value) pairs in concept that are active match
    constraints — i.e. exclude empty values and the source_text key."""
    return {
        k: v for k, v in concept.items()
        if k not in _IGNORED_FIELDS and v not in (None, "")
    }


def match_concept(concept: dict, references: Iterable[dict]) -> bool:
    """Return True iff at least one reference satisfies all constraints
    in `concept` (subset semantics)."""
    constraints = _concept_constraints(concept)
    if not constraints:
        # A concept with zero constraints is a "match anything" placeholder;
        # treat as matching iff there's at least one reference.
        return any(True for _ in references)
    for r in references:
        if all(r.get(k) == v for k, v in constraints.items()):
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
