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
from backend.quality.dqcheck_core.reference_policy import DEFAULT_REFERENCE_POLICY_ID
from backend.quality.dqcheck_core.router import route_document
from backend.quality.dqcheck_core.text import evidence_match_mode, normalize_text

AUDIT_POLICY_ID = DEFAULT_REFERENCE_POLICY_ID

# Fields compared when two references share a core identity. Mirrors the
# upstream hitl._DIFF_FIELDS tuple.
_DIFF_FIELDS = ("fikra", "bent", "source_text")

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
    """Analysis-friendly identity row (see design spec, rule 5)."""
    return {
        "kanun_no": reference["kanun_no"],
        "madde": reference["madde"],
        "fikra": reference["fikra"],
        "bent": reference["bent"],
    }


def reference_identities(references: list[dict[str, Any]]) -> set[tuple[str, ...]]:
    """Normalized full-identity set; tolerates AP's Optional[str] fields."""
    return {full_identity(normalize_reference(reference)) for reference in references}


def ab_diff(
    human: list[dict[str, str]], model: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Align human (a) and model (b) references by core law-article identity.

    Deviates from upstream ``hitl.ab_diff`` in one place: "same" is decided on
    ``full_identity(r) + (source_text,)`` rather than ``full_identity(r)``
    alone. Upstream's ``full_identity`` excludes ``source_text``, so a router
    YELLOW/``evidence_mismatch`` bucket (which does compare ``source_text``)
    could pair with a same-status, zero-discrepancy diff — a router/diff
    disagreement that would hide the very mismatch the bucket flags. Including
    ``source_text`` here surfaces it as a ``detail_mismatch`` row instead.
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
        elif sorted(full_identity(r) + (r["source_text"],) for r in a_refs) == sorted(
            full_identity(r) + (r["source_text"],) for r in b_refs
        ):
            status = "same"
        else:
            status = "differs"
        field_diffs: list[str] = []
        if status == "differs" and len(a_refs) == 1 and len(b_refs) == 1:
            field_diffs = [
                field
                for field in _DIFF_FIELDS
                if a_refs[0].get(field, "") != b_refs[0].get(field, "")
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
            model_only.extend(canonical_tuple(reference) for reference in row["b"])
        if kind in {"human_only", "detail_mismatch"}:
            human_only.extend(canonical_tuple(reference) for reference in row["a"])

    return AuditOutcome(
        bucket=decision.bucket,
        reasons=decision.reasons,
        similarity=decision.similarity,
        discrepancies=tuple(discrepancies),
        model_only=tuple(model_only),
        human_only=tuple(human_only),
    )
