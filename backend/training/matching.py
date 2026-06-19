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
import re
from typing import Iterable
import unicodedata


_IGNORED_FIELDS = ("source_text",)


def _clean_for_fuzzy_match(text: str) -> str:
    if not text:
        return ""
    t = (
        str(text).lower()
        .replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    s = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", s)


def _fuzzy_match_source_text(user_text: str, concept_text: str) -> bool:
    if not user_text or not concept_text:
        return True
    
    clean_user = _clean_for_fuzzy_match(user_text)
    clean_concept = _clean_for_fuzzy_match(concept_text)
    
    if not clean_user or not clean_concept:
        return True
        
    # Substring match (either user excerpt is within concept excerpt or vice-versa)
    if clean_user in clean_concept or clean_concept in clean_user:
        return True
        
    # Word-level fallback (at least 70% of user words appear in concept excerpt)
    user_words = [w for w in (_clean_for_fuzzy_match(w) for w in str(user_text).split()) if len(w) >= 3]
    if not user_words:
        return True
        
    matched = sum(1 for w in user_words if w in clean_concept)
    if matched / len(user_words) >= 0.7:
        return True
        
    # Concept word-level fallback (at least 70% of concept words appear in user excerpt)
    concept_words = [w for w in (_clean_for_fuzzy_match(w) for w in str(concept_text).split()) if len(w) >= 3]
    if not concept_words:
        return True
        
    matched_concept = sum(1 for w in concept_words if w in clean_user)
    if matched_concept / len(concept_words) >= 0.7:
        return True
        
    return False


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


def _enrich_law_fields(d: dict) -> dict:
    res = dict(d)
    k_no = res.get("kanun_no")
    k_ad = res.get("kanun_ad")
    
    if k_no:
        k_no = str(k_no).strip()
    if k_ad:
        from backend.annotations.diff import normalize_kanun_adi
        k_ad = normalize_kanun_adi(str(k_ad))
        
    if not k_no and k_ad:
        from backend.annotations.diff import LAW_NUMBER_BY_NAME
        k_no = LAW_NUMBER_BY_NAME.get(k_ad)
        
    if k_no and not k_ad:
        from backend.annotations.diff import LAW_NUMBER_BY_NAME
        rev = {v: k for k, v in LAW_NUMBER_BY_NAME.items()}
        k_no_clean = k_no.lstrip("0") or "0"
        k_ad = rev.get(k_no_clean)
        
    res["kanun_no"] = k_no
    res["kanun_ad"] = k_ad
    return res


def match_concept(concept: dict, references: Iterable[dict]) -> bool:
    """Return True iff at least one reference satisfies all constraints
    in `concept` (subset semantics) after string normalization.

    Normalization is applied symmetrically to concept values AND
    reference values before equality comparison; see _normalize_value
    for the pipeline. source_text is checked via fuzzy matching if present.
    """
    enriched_concept = _enrich_law_fields(concept)
    constraints_raw = _concept_constraints(enriched_concept)
    constraints = {k: _normalize_value(v) for k, v in constraints_raw.items()}
    concept_source_text = enriched_concept.get("source_text")

    if not constraints:
        if concept_source_text:
            return any(_fuzzy_match_source_text(r.get("source_text"), concept_source_text) for r in references)
        return any(True for _ in references)

    for r in references:
        enriched_r = _enrich_law_fields(r)
        normed = {k: _normalize_value(enriched_r.get(k)) for k in constraints}
        if all(normed.get(k) == v for k, v in constraints.items()):
            if concept_source_text:
                if _fuzzy_match_source_text(enriched_r.get("source_text"), concept_source_text):
                    return True
            else:
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
