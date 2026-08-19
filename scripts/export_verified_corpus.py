#!/usr/bin/env python3
"""Export platform-verified annotations as a NEW ground-truth generation.

DQCheck's canonical corpus is sealed: `g0.validate_canonical_sources` demands
exactly 500 doc_*.json files whose directory manifest matches a pinned sha256
(`constants.CANONICAL_GT_MANIFEST_SHA256`), plus a seed-42 394/50/50 split
manifest. Appending platform data to that directory would break the published
reproducibility claim, so this script writes a separate generation directory.
Teaching `train-g0` to consume it is a deliberate, later decision.

Selection rule (design spec, decision 13): every document that is completed AND
has at least one audit row. Human labels are the ground truth — GREEN,
accepted_model and human_override all qualify, because the documents where the
model was wrong are exactly the ones worth learning from. Narrower filters stay
possible afterwards: bucket, decision and unique_users_count all travel in the
sidecar.

Usage:
    /opt/llm-lab/.venv/bin/python scripts/export_verified_corpus.py \
        --out /Users/student2/data-quality-checker/data/ground_truth/gt_v4_platform_2026-08-18
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import config  # noqa: E402
from backend.quality.dqcheck_core.fingerprints import (  # noqa: E402
    directory_manifest,
    manifest_fingerprint,
)
from backend.shared.db import connect  # noqa: E402

SCHEMA_VERSION = 1

_SELECT_DOCUMENTS = """
    SELECT a.document_id, a.references_json, a.unique_users_count, d.pdf_text
    FROM annotations a
    JOIN documents_meta d ON d.document_id = a.document_id
    WHERE a.is_completed = 1
      AND EXISTS (
          SELECT 1 FROM annotation_audit_logs l
          WHERE l.document_id = a.document_id
      )
    ORDER BY a.document_id ASC
"""

_SELECT_LATEST_AUDIT = """
    SELECT bucket, decision, reasons_json, similarity, prediction_fingerprint,
           policy_id, model_generation, created_at
    FROM annotation_audit_logs
    WHERE document_id = ?
    ORDER BY id DESC
    LIMIT 1
"""


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def export_corpus(
    db: sqlite3.Connection,
    out_dir: Path,
    *,
    generated_at: str,
    force: bool = False,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    validated_dir = out_dir / "validated"
    if validated_dir.exists() and any(validated_dir.iterdir()) and not force:
        raise SystemExit(
            f"{validated_dir} already contains an export; pass --force to replace it"
        )
    validated_dir.mkdir(parents=True, exist_ok=True)
    for stale in validated_dir.glob("doc_*.json"):
        stale.unlink()

    rows = db.execute(_SELECT_DOCUMENTS).fetchall()
    id_map: dict[str, int] = {}
    sidecar_lines: list[str] = []
    for doc_id, row in enumerate(rows, start=1):
        document_id = row["document_id"]
        id_map[document_id] = doc_id
        _write_json(
            validated_dir / f"doc_{doc_id}.json",
            {
                "doc_id": doc_id,
                "source_document_id": document_id,
                "text": row["pdf_text"],
                "references": json.loads(row["references_json"]),
            },
        )
        audit = db.execute(_SELECT_LATEST_AUDIT, (document_id,)).fetchone()
        sidecar_lines.append(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "source_document_id": document_id,
                    "bucket": audit["bucket"],
                    "decision": audit["decision"],
                    "reasons": json.loads(audit["reasons_json"]),
                    "similarity": audit["similarity"],
                    "prediction_fingerprint": audit["prediction_fingerprint"],
                    "policy_id": audit["policy_id"],
                    "model_generation": audit["model_generation"],
                    "unique_users_count": row["unique_users_count"],
                    "audit_at": audit["created_at"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    _write_json(out_dir / "id_map.json", id_map)
    (out_dir / "audit_sidecar.jsonl").write_text(
        "".join(f"{line}\n" for line in sidecar_lines), encoding="utf-8"
    )

    manifest_rows = directory_manifest(
        sorted(validated_dir.glob("doc_*.json")), root=out_dir
    )
    # The fingerprint covers file contents only — never `generated_at` — so two
    # exports of the same data are provably identical.
    fingerprint = manifest_fingerprint(manifest_rows)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "count": len(rows),
        "files": manifest_rows,
        "manifest_fingerprint": fingerprint,
    }
    _write_json(out_dir / "manifest.json", summary)
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    db = connect(args.db)
    try:
        summary = export_corpus(
            db,
            args.out,
            generated_at=datetime.now(timezone.utc).isoformat(),
            force=args.force,
        )
    finally:
        db.close()
    print(
        json.dumps(
            {
                "out": str(args.out),
                "count": summary["count"],
                "manifest_fingerprint": summary["manifest_fingerprint"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
