"""Pure-function reference normalization, deduping, and set-semantic diff.

A reference is a dict with 6 keys:
  {kanun_no, kanun_ad, madde, fikra, bent, source_text}

source_text is REQUIRED (non-empty after strip). The other 5 fields are
optional; empty strings normalize to None. Duplicates are rejected by exact
6-tuple match (after normalization).

Diff is set-based: order doesn't matter. is_diff_zero(diff) means the two
reference lists encode the same set of references.
"""
from typing import Optional

REFERENCE_FIELDS = (
    "kanun_no", "kanun_ad", "madde", "fikra", "bent", "source_text",
)


class InvalidReference(ValueError):
    """source_text missing or empty."""


class DuplicateReference(ValueError):
    """Two refs in the same list have identical canonical keys."""


def _clean(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def normalize_reference(ref: dict) -> dict:
    """Return a 6-key dict with whitespace stripped, empty → None.

    Raises InvalidReference if source_text is missing or empty.
    """
    out = {f: _clean(ref.get(f)) for f in REFERENCE_FIELDS}
    if not out["source_text"]:
        raise InvalidReference("source_text is required")
    return out


def canonical_key(ref: dict) -> tuple:
    """Stable 6-tuple identity for set-based comparison."""
    return tuple(ref.get(f) for f in REFERENCE_FIELDS)


def normalize_references(refs: list[dict]) -> list[dict]:
    """Normalize each ref; reject the list if any two are exact duplicates.

    Order is preserved (used as `seq` for the denormalized index).
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in refs:
        n = normalize_reference(r)
        key = canonical_key(n)
        if key in seen:
            raise DuplicateReference(
                f"duplicate reference: source_text={n['source_text']!r}"
            )
        seen.add(key)
        out.append(n)
    return out


def references_diff(prev: list[dict], curr: list[dict]) -> dict:
    """Set-based symmetric difference. Returns {'added': [...], 'removed': [...]}.

    Inputs should already be normalized.
    """
    prev_map = {canonical_key(r): r for r in prev}
    curr_map = {canonical_key(r): r for r in curr}
    added_keys = curr_map.keys() - prev_map.keys()
    removed_keys = prev_map.keys() - curr_map.keys()
    return {
        "added": [curr_map[k] for k in added_keys],
        "removed": [prev_map[k] for k in removed_keys],
    }


def is_diff_zero(diff: dict) -> bool:
    return not diff["added"] and not diff["removed"]
