"""Training gate service.

Public API (filled progressively across Paket 10 tasks):
  get_active_gold_docs(db) -> list[dict]                       # Task 4
  start_attempt(db, *, user_id) -> dict                        # Task 5
  submit_quiz(db, *, attempt_id, user_id, answers) -> dict     # Task 5
  submit_annotation(db, *, attempt_id, user_id, gold_id,       # Task 5
                    references) -> dict
  finalize_if_complete(db, *, attempt_id, user_id) -> dict     # Task 5
  is_locked_out(db, *, user_id) -> bool                        # Task 5

The resolver merges the code baseline (`backend.training.gold_docs.GOLD_DOCS`)
with rows in the `training_gold_doc_overrides` table per spec §"Q5 hibrit
modeli" (spec lines 1007-1034).
"""
import json
import logging
import sqlite3

from backend.training import gold_docs as code_gold


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hybrid gold-doc resolver
# ---------------------------------------------------------------------------

def get_active_gold_docs(db: sqlite3.Connection) -> list[dict]:
    """Return the resolved list of gold docs available for the training
    challenge. Code baseline + DB overrides per spec lines 1007-1034.

    Resolution rules:
      - For every code-baseline entry:
          * If override row exists with is_deleted=1 → exclude.
          * If override row exists → merge: override fields win over code
            (NULL/missing in override means fall back to code).
          * Otherwise → use code entry as-is.
      - For every override row with source='custom' AND is_deleted=0 AND
        gold_id NOT in code baseline → append.
    """
    rows = db.execute(
        "SELECT gold_id, is_deleted, content, expected_concepts, "
        "min_concept_count, source FROM training_gold_doc_overrides"
    ).fetchall()
    overrides = {r["gold_id"]: r for r in rows}

    out: list[dict] = []
    seen: set[str] = set()
    for code in code_gold.GOLD_DOCS:
        gid = code["gold_id"]
        ov = overrides.get(gid)
        if ov is not None and ov["is_deleted"]:
            continue
        if ov is not None:
            content = ov["content"] if ov["content"] is not None else code["content"]
            ec_blob = ov["expected_concepts"]
            expected = json.loads(ec_blob) if ec_blob is not None else code["expected_concepts"]
            mcc = ov["min_concept_count"] if ov["min_concept_count"] is not None else code["min_concept_count"]
            out.append({
                "gold_id": gid,
                "content": content,
                "expected_concepts": expected,
                "min_concept_count": mcc,
            })
        else:
            out.append(dict(code))
        seen.add(gid)

    for gid, ov in overrides.items():
        if ov["source"] == "custom" and not ov["is_deleted"] and gid not in seen:
            out.append({
                "gold_id": gid,
                "content": ov["content"],
                "expected_concepts": json.loads(ov["expected_concepts"]) if ov["expected_concepts"] else [],
                "min_concept_count": ov["min_concept_count"] if ov["min_concept_count"] is not None else 1,
            })

    return out
