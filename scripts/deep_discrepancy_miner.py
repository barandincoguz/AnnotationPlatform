import os
import json
import psycopg
from psycopg.rows import dict_row
from collections import defaultdict, Counter

db_url = os.environ.get("NEON_ADMIN_URL") or os.environ.get("NEON_MIRROR_URL")
if not db_url:
    print("NEON_ADMIN_URL not set")
    exit(1)

def norm(val):
    return str(val or "").strip().lower()

with psycopg.connect(db_url, row_factory=dict_row) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                a.document_id,
                d.pdf_text,
                d.word_count,
                d.estimated_difficulty,
                a.references_json as human_refs_json,
                p.references_json as model_refs_json,
                p.status as model_status
            FROM baran_annotations a
            JOIN baran_model_predictions p ON a.document_id = p.document_id
            JOIN baran_documents_meta d ON a.document_id = d.document_id
            WHERE a.is_completed = 1 AND p.status = 'success'
        """)
        rows = cur.fetchall()

print(f"Total Completed & Predicted Documents Analyzed: {len(rows)}")

discrepancy_types = Counter()
human_omissions_by_law = Counter()
model_excess_by_law = Counter()
detail_mismatches_by_law = Counter()
document_level_cases = []

perfect_match_docs = []
high_discrepancy_docs = []
human_omission_heavy_docs = []
model_excess_heavy_docs = []

for r in rows:
    doc_id = r["document_id"]
    pdf_text = r["pdf_text"] or ""
    h_refs = json.loads(r["human_refs_json"]) if isinstance(r["human_refs_json"], str) else r["human_refs_json"]
    m_refs = json.loads(r["model_refs_json"]) if isinstance(r["model_refs_json"], str) else r["model_refs_json"]

    h_core_map = defaultdict(list)
    for ref in h_refs:
        k = norm(ref.get("kanun_no"))
        m = norm(ref.get("madde"))
        if k and m:
            h_core_map[(k, m)].append(ref)

    m_core_map = defaultdict(list)
    for ref in m_refs:
        k = norm(ref.get("kanun_no"))
        m = norm(ref.get("madde"))
        if k and m:
            m_core_map[(k, m)].append(ref)

    h_core_keys = set(h_core_map.keys())
    m_core_keys = set(m_core_map.keys())

    matched_cores = h_core_keys & m_core_keys
    model_only_cores = m_core_keys - h_core_keys
    human_only_cores = h_core_keys - m_core_keys

    detail_diffs = []
    for k, m in matched_cores:
        h_tuples = {(norm(x.get("fikra")), norm(x.get("bent"))) for x in h_core_map[(k, m)]}
        m_tuples = {(norm(x.get("fikra")), norm(x.get("bent"))) for x in m_core_map[(k, m)]}
        if h_tuples != m_tuples:
            detail_diffs.append({
                "kanun_no": k,
                "madde": m,
                "human_details": list(h_tuples),
                "model_details": list(m_tuples),
            })
            detail_mismatches_by_law[k] += 1
            discrepancy_types["detail_mismatch"] += 1

    for k, m in model_only_cores:
        model_excess_by_law[k] += 1
        discrepancy_types["model_only_reference"] += 1

    for k, m in human_only_cores:
        human_omissions_by_law[k] += 1
        discrepancy_types["human_only_reference"] += 1

    total_diff_count = len(model_only_cores) + len(human_only_cores) + len(detail_diffs)
    
    doc_summary = {
        "document_id": doc_id,
        "word_count": r["word_count"],
        "difficulty": r["estimated_difficulty"],
        "human_ref_count": len(h_refs),
        "model_ref_count": len(m_refs),
        "matched_core_count": len(matched_cores),
        "model_only_cores": [{"kanun_no": k, "madde": m, "sample": m_core_map[(k, m)][0]} for k, m in model_only_cores],
        "human_only_cores": [{"kanun_no": k, "madde": m, "sample": h_core_map[(k, m)][0]} for k, m in human_only_cores],
        "detail_mismatches": detail_diffs,
        "total_discrepancies": total_diff_count,
        "text_preview": pdf_text[:400] + ("..." if len(pdf_text) > 400 else "")
    }

    if total_diff_count == 0:
        perfect_match_docs.append(doc_summary)
    else:
        if len(model_only_cores) >= 2 and len(human_only_cores) == 0:
            human_omission_heavy_docs.append(doc_summary)
        elif len(human_only_cores) >= 2 and len(model_only_cores) == 0:
            model_excess_heavy_docs.append(doc_summary)
        if total_diff_count >= 3:
            high_discrepancy_docs.append(doc_summary)

print("\n=== DISCREPANCY SUMMARY ===")
for dtype, count in discrepancy_types.items():
    print(f"  - {dtype}: {count}")

print(f"\nPerfect Match Documents (100% Agreement): {len(perfect_match_docs)} ({len(perfect_match_docs)/len(rows)*100:.2f}%)")
print(f"Documents with Human Omission Candidates: {len(human_omission_heavy_docs)}")
print(f"Documents with Model Omission / Excess Candidates: {len(model_excess_heavy_docs)}")
print(f"High Discrepancy Multi-Tax Documents: {len(high_discrepancy_docs)}")

print("\nTop 5 Laws where Model found reference but Human omitted (Potential Human Misses):")
for k, c in model_excess_by_law.most_common(5):
    print(f"  - Kanun {k}: {c} times")

print("\nTop 5 Laws where Human found reference but Model missed (Model Recall Gaps):")
for k, c in human_omissions_by_law.most_common(5):
    print(f"  - Kanun {k}: {c} times")

output_payload = {
    "summary": {
        "total_documents": len(rows),
        "perfect_matches": len(perfect_match_docs),
        "perfect_match_ratio": round(len(perfect_match_docs)/len(rows), 4),
        "discrepancies": dict(discrepancy_types),
        "top_model_excess_laws": dict(model_excess_by_law.most_common(10)),
        "top_human_omission_laws": dict(human_omissions_by_law.most_common(10)),
        "top_detail_mismatch_laws": dict(detail_mismatches_by_law.most_common(10)),
    },
    "case_study_candidates": {
        "perfect_matches_sample": perfect_match_docs[:10],
        "human_omissions_sample": human_omission_heavy_docs[:15],
        "model_omissions_sample": model_excess_heavy_docs[:15],
        "high_discrepancy_sample": high_discrepancy_docs[:15]
    }
}

with open("scripts/discrepancy_analysis_full.json", "w", encoding="utf-8") as f:
    json.dump(output_payload, f, indent=2, ensure_ascii=False)

print("\nFull discrepancy mining results written to scripts/discrepancy_analysis_full.json")
