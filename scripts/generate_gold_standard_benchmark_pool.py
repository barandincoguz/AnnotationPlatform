import os
import json
import psycopg
from psycopg.rows import dict_row

db_url = os.environ.get("NEON_ADMIN_URL") or os.environ.get("NEON_MIRROR_URL")
if not db_url:
    print("NEON_ADMIN_URL not set")
    exit(1)

os.makedirs("data", exist_ok=True)

with psycopg.connect(db_url, row_factory=dict_row) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                a.document_id,
                d.file_path,
                d.pdf_text,
                d.word_count,
                d.sentence_count,
                d.text_density,
                d.estimated_difficulty,
                a.references_json as human_references,
                p.references_json as model_references,
                p.generation as model_generation,
                p.model_fingerprint,
                p.prediction_fingerprint,
                a.created_at,
                a.updated_at
            FROM baran_annotations a
            JOIN baran_model_predictions p ON a.document_id = p.document_id
            JOIN baran_documents_meta d ON a.document_id = d.document_id
            WHERE a.is_completed = 1 AND p.status = 'success'
            ORDER BY d.word_count DESC
        """)
        rows = cur.fetchall()

def norm(val):
    return str(val or "").strip().lower()

curated_pool = []
for r in rows:
    h_refs = json.loads(r["human_references"]) if isinstance(r["human_references"], str) else r["human_references"]
    m_refs = json.loads(r["model_references"]) if isinstance(r["model_references"], str) else r["model_references"]

    h_core = {(norm(x.get("kanun_no")), norm(x.get("madde"))) for x in h_refs if x.get("kanun_no") and x.get("madde")}
    m_core = {(norm(x.get("kanun_no")), norm(x.get("madde"))) for x in m_refs if x.get("kanun_no") and x.get("madde")}

    tp = len(h_core & m_core)
    union = len(h_core | m_core)
    jaccard = round(tp / union, 4) if union > 0 else 1.0

    curated_pool.append({
        "document_id": r["document_id"],
        "metadata": {
            "word_count": r["word_count"],
            "sentence_count": r["sentence_count"],
            "text_density": r["text_density"],
            "estimated_difficulty": r["estimated_difficulty"],
            "file_path": r["file_path"],
            "updated_at": str(r["updated_at"]),
        },
        "evaluation_metrics": {
            "human_ref_count": len(h_refs),
            "model_ref_count": len(m_refs),
            "core_tp": tp,
            "core_jaccard_similarity": jaccard,
            "agreement_bucket": "GREEN" if jaccard >= 0.85 else ("YELLOW" if jaccard >= 0.5 else "RED")
        },
        "human_ground_truth": h_refs,
        "model_prediction": {
            "generation": r["model_generation"],
            "model_fingerprint": r["model_fingerprint"],
            "prediction_fingerprint": r["prediction_fingerprint"],
            "references": m_refs
        },
        "pdf_text": r["pdf_text"]
    })

output_path = "data/gold_standard_benchmark_pool.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump({
        "schema_version": "1.0",
        "description": "Curated benchmark dataset pool for Turkish tax statutory reference extraction.",
        "total_documents": len(curated_pool),
        "documents": curated_pool
    }, f, indent=2, ensure_ascii=False)

print(f"Successfully generated gold standard benchmark pool with {len(curated_pool)} documents at {output_path}")
