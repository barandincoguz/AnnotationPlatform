"""AP ↔ DQCheck bridge: policy, routing, and human/model discrepancy alignment.

`dqcheck_core/` is vendored verbatim and must not be edited (see its
UPSTREAM.md). Everything AP-specific lives here.

`ab_diff` is a behavioural reimplementation of
`data_quality_checker.hitl.ab_diff`: that upstream module imports Flask at
module scope and AP must not take a Flask runtime dependency. "a" is always the
human side, "b" the model side.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.quality.dqcheck_core.normalization import (
    core_identity,
    full_identity,
    normalize_reference,
)
from backend.quality.dqcheck_core.reference_policy import (
    DEFAULT_REFERENCE_POLICY_ID,
    apply_reference_policy,
)

# `_evidence_compatible` is underscore-private in the vendored router, but the
# router module is immutable and hash-guarded (see UPSTREAM.md), so its name is
# stable. Importing it — rather than re-deriving the same rule here — is the
# only way `ab_diff`'s "same" decision and the router's bucket can never drift
# apart: the diff must use exactly the compatibility rule the bucket used.
from backend.quality.dqcheck_core.router import _evidence_compatible, route_document
from backend.quality.dqcheck_core.text import evidence_match_mode, normalize_text

AUDIT_POLICY_ID = DEFAULT_REFERENCE_POLICY_ID

# Fields compared when two references share a core identity. Mirrors the
# upstream hitl._DIFF_FIELDS tuple.
_DIFF_FIELDS = ("fikra", "bent", "source_text")


def _field_matches(field: str, a_value: str, b_value: str) -> bool:
    """True when a single field should be treated as agreeing.

    `source_text` uses the router's own `_evidence_compatible` rule (same as
    `status`), so `field_diffs` can never contradict the bucket: a quote pair
    the router treats as compatible evidence must not be reported to the
    annotator as a disagreement. Every other field is plain equality.
    """
    if field == "source_text":
        return _evidence_compatible(a_value, b_value)
    return a_value == b_value


_KIND_BY_STATUS = {
    "only_a": "human_only",
    "only_b": "model_only",
    "differs": "detail_mismatch",
}


@dataclass(frozen=True)
class AuditOutcome:
    bucket: str
    reasons: tuple[str, ...]
    similarity: float
    discrepancies: tuple[dict[str, Any], ...]
    model_only: tuple[dict[str, str], ...]
    human_only: tuple[dict[str, str], ...]


def canonical_tuple(reference: dict[str, str]) -> dict[str, str]:
    """Analysis-friendly identity row (see design spec, rule 5).

    Indexes the four identity keys directly and performs no normalization of
    its own: the caller must pass an already-normalized reference (as
    `route_document` / `ab_diff` produce). Handing this a raw reference (e.g.
    `madde="114."`) writes an un-normalized row straight into the audit table.
    """
    return {
        "kanun_no": reference["kanun_no"],
        "madde": reference["madde"],
        "fikra": reference["fikra"],
        "bent": reference["bent"],
    }


def _canonical_key(reference: dict[str, str]) -> tuple[str, str, str, str]:
    canonical = canonical_tuple(reference)
    return (
        canonical["kanun_no"],
        canonical["madde"],
        canonical["fikra"],
        canonical["bent"],
    )


def _exclusive_canonical_tuples(
    own_references: list[dict[str, str]], other_references: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Canonical tuples of `own_references` absent from `other_references`.

    A true set difference (so a reference both sides cited never lands in
    both `model_only` and `human_only`), but rendered back out in first-
    appearance order of `own_references` rather than set-iteration order, so
    the resulting rows stay deterministic.
    """
    other_keys = {_canonical_key(reference) for reference in other_references}
    seen: set[tuple[str, str, str, str]] = set()
    exclusive: list[dict[str, str]] = []
    for reference in own_references:
        key = _canonical_key(reference)
        if key in other_keys or key in seen:
            continue
        seen.add(key)
        exclusive.append(canonical_tuple(reference))
    return exclusive


def reference_identities(references: list[dict[str, Any]]) -> set[tuple[str, ...]]:
    """Normalized full-identity set; tolerates AP's Optional[str] fields.

    Applies `apply_reference_policy` (with `AUDIT_POLICY_ID`) before
    normalizing, so this stays policy-consistent with `audit_references` by
    construction: a caller comparing raw reference lists never sees an
    identity (e.g. VUK 213/413 boilerplate) that `audit_references` itself
    filters out.
    """
    policy_references, _ = apply_reference_policy(references, policy_id=AUDIT_POLICY_ID)
    return {full_identity(normalize_reference(reference)) for reference in policy_references}


def ab_diff(
    human: list[dict[str, str]], model: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Align human (a) and model (b) references by core law-article identity.

    Deviates from upstream ``hitl.ab_diff`` in one place: "same" additionally
    requires the two sides' ``source_text`` to agree, which upstream's
    ``full_identity``-only comparison does not check. Agreement is decided with
    the router's own ``_evidence_compatible`` (equality after ``folded_text``,
    or loose containment either way) rather than strict string equality, so
    this diff can never contradict the router's bucket: a pair the router
    treats as compatible evidence (contributing to a GREEN/
    ``evidence_format_or_length_only`` outcome) is "same" here too, while a
    pair it rejects (YELLOW/``evidence_mismatch``) still surfaces as a
    ``detail_mismatch`` row.

    Expects normalized **and** compacted input, i.e. exactly what
    ``route_document`` returns (as ``audit_references`` passes it). Raw,
    un-normalized references can throw inside ``core_identity`` on a ``None``
    field, and if one side repeats the same full identity more than once,
    pairing within a group becomes ambiguous.

    Renders only the first reference of a multi-reference core group into the
    row's ``human_reference`` / ``model_reference`` display fields (matching
    upstream). ``human_only`` / ``model_only`` (computed by the caller from
    ``row["a"]`` / ``row["b"]``) stay complete, so this truncation is
    display-only.
    """
    order: list[tuple[str, ...]] = []
    groups: dict[tuple[str, ...], dict[str, list[dict[str, str]]]] = {}
    for label, references in (("a", human), ("b", model)):
        for reference in references:
            key = core_identity(reference)
            if key not in groups:
                groups[key] = {"a": [], "b": []}
                order.append(key)
            groups[key][label].append(reference)

    rows: list[dict[str, Any]] = []
    for key in order:
        a_refs = groups[key]["a"]
        b_refs = groups[key]["b"]
        if a_refs and not b_refs:
            status = "only_a"
        elif b_refs and not a_refs:
            status = "only_b"
        elif sorted(full_identity(r) for r in a_refs) == sorted(
            full_identity(r) for r in b_refs
        ) and all(
            _evidence_compatible(ra["source_text"], rb["source_text"])
            for ra, rb in zip(
                sorted(a_refs, key=full_identity), sorted(b_refs, key=full_identity)
            )
        ):
            status = "same"
        else:
            status = "differs"
        field_diffs: list[str] = []
        if status == "differs" and len(a_refs) == 1 and len(b_refs) == 1:
            field_diffs = [
                field
                for field in _DIFF_FIELDS
                if not _field_matches(
                    field, a_refs[0].get(field, ""), b_refs[0].get(field, "")
                )
            ]
        sample = (a_refs or b_refs)[0]
        rows.append(
            {
                "core": {
                    "kanun_no": sample["kanun_no"],
                    "kanun_ad": sample["kanun_ad"],
                    "madde": sample["madde"],
                },
                "status": status,
                "a": a_refs,
                "b": b_refs,
                "field_diffs": field_diffs,
            }
        )
    return rows


def audit_references(
    *,
    human_references: list[dict[str, Any]],
    model_references: list[dict[str, Any]],
    document_text: str = "",
    model_status: str = "success",
    model_truncated: bool = False,
) -> AuditOutcome:
    """Route the pair, then align the two sides into UI-facing discrepancies.

    `route_document` already applies the reference policy and compaction, and
    returns the normalized views it used — we align those, never the raw input,
    so the UI and the bucket can never disagree about what was compared.
    """
    decision = route_document(
        human_references=human_references,
        model_references=model_references,
        model_status=model_status,
        model_truncated=model_truncated,
        reference_policy_id=AUDIT_POLICY_ID,
    )
    human = list(decision.human_references)
    model = list(decision.model_references)
    normalized_document = normalize_text(document_text)

    discrepancies: list[dict[str, Any]] = []
    model_only: list[dict[str, str]] = []
    human_only: list[dict[str, str]] = []
    for row in ab_diff(human, model):
        if row["status"] == "same":
            continue
        kind = _KIND_BY_STATUS[row["status"]]
        model_reference: Optional[dict[str, str]] = row["b"][0] if row["b"] else None
        human_reference: Optional[dict[str, str]] = row["a"][0] if row["a"] else None
        discrepancies.append(
            {
                "kind": kind,
                "kanun_no": row["core"]["kanun_no"],
                "kanun_ad": row["core"]["kanun_ad"],
                "madde": row["core"]["madde"],
                "model_reference": model_reference,
                "human_reference": human_reference,
                "field_diffs": list(row["field_diffs"]),
                "match_mode": (
                    evidence_match_mode(
                        model_reference["source_text"], normalized_document
                    )
                    if model_reference is not None
                    else None
                ),
            }
        )
        if kind in {"model_only", "detail_mismatch"}:
            model_only.extend(_exclusive_canonical_tuples(row["b"], row["a"]))
        if kind in {"human_only", "detail_mismatch"}:
            human_only.extend(_exclusive_canonical_tuples(row["a"], row["b"]))

    return AuditOutcome(
        bucket=decision.bucket,
        reasons=decision.reasons,
        similarity=decision.similarity,
        discrepancies=tuple(discrepancies),
        model_only=tuple(model_only),
        human_only=tuple(human_only),
    )
