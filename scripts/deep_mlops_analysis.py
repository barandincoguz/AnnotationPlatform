import os
import json
import math
import statistics
import psycopg
from psycopg.rows import dict_row

db_url = os.environ.get("NEON_ADMIN_URL") or os.environ.get("NEON_MIRROR_URL")
if not db_url:
    print("NEON_ADMIN_URL not set")
    exit(1)

with psycopg.connect(db_url, row_factory=dict_row) as conn:
    with conn.cursor() as cur:
        # 1. Total Counts & Population
        cur.execute("SELECT count(*) as total FROM baran_model_predictions")
        total_model_preds = cur.fetchone()["total"]

        cur.execute("SELECT count(*) as total, sum(case when is_completed=1 then 1 else 0 end) as completed FROM baran_annotations")
        annot_stats = cur.fetchone()
        total_human_annotated = annot_stats["total"]
        total_human_completed = annot_stats["completed"]

        # 2. Overlap population
        cur.execute("""
            SELECT 
                a.document_id,
                a.references_json as human_refs_json,
                p.references_json as model_refs_json,
                p.status as model_status,
                p.truncated as model_truncated
            FROM baran_annotations a
            JOIN baran_model_predictions p ON a.document_id = p.document_id
            WHERE a.is_completed = 1
        """)
        overlap_rows = cur.fetchall()

        # 3. Model Reference Count Distribution (All Successful Predictions)
        cur.execute("""
            SELECT jsonb_array_length(references_json::jsonb) as ref_count
            FROM baran_model_predictions
            WHERE status = 'success'
        """)
        model_ref_counts = [r["ref_count"] for r in cur.fetchall()]

        # 4. Human Reference Count Distribution (All Completed Annotations)
        cur.execute("""
            SELECT jsonb_array_length(references_json::jsonb) as ref_count
            FROM baran_annotations
            WHERE is_completed = 1
        """)
        human_ref_counts = [r["ref_count"] for r in cur.fetchall()]

        # Overlap paired metrics
        overlap_human_counts = []
        overlap_model_counts = []
        
        exact_tp, exact_fp, exact_fn = 0, 0, 0
        core_tp, core_fp, core_fn = 0, 0, 0
        jaccard_scores_core = []
        jaccard_scores_exact = []

        law_stats = {}

        def norm(val):
            return str(val or "").strip().lower()

        for row in overlap_rows:
            if row["model_status"] != "success":
                continue
            h_refs = json.loads(row["human_refs_json"]) if isinstance(row["human_refs_json"], str) else row["human_refs_json"]
            m_refs = json.loads(row["model_refs_json"]) if isinstance(row["model_refs_json"], str) else row["model_refs_json"]

            overlap_human_counts.append(len(h_refs))
            overlap_model_counts.append(len(m_refs))

            h_core = set()
            h_exact = set()
            for r in h_refs:
                k = norm(r.get("kanun_no"))
                m = norm(r.get("madde"))
                f = norm(r.get("fikra"))
                b = norm(r.get("bent"))
                if k and m:
                    h_core.add((k, m))
                    h_exact.add((k, m, f, b))

            m_core = set()
            m_exact = set()
            for r in m_refs:
                k = norm(r.get("kanun_no"))
                m = norm(r.get("madde"))
                f = norm(r.get("fikra"))
                b = norm(r.get("bent"))
                if k and m:
                    m_core.add((k, m))
                    m_exact.add((k, m, f, b))

            c_tp_set = h_core & m_core
            c_fp_set = m_core - h_core
            c_fn_set = h_core - m_core
            core_tp += len(c_tp_set)
            core_fp += len(c_fp_set)
            core_fn += len(c_fn_set)
            
            c_union = h_core | m_core
            jaccard_scores_core.append(len(c_tp_set) / len(c_union) if c_union else 1.0)

            e_tp_set = h_exact & m_exact
            e_fp_set = m_exact - h_exact
            e_fn_set = h_exact - m_exact
            exact_tp += len(e_tp_set)
            exact_fp += len(e_fp_set)
            exact_fn += len(e_fn_set)

            e_union = h_exact | m_exact
            jaccard_scores_exact.append(len(e_tp_set) / len(e_union) if e_union else 1.0)

            all_laws = {k for k, _ in h_core} | {k for k, _ in m_core}
            for k in all_laws:
                if k not in law_stats:
                    law_stats[k] = {"tp": 0, "fp": 0, "fn": 0, "human_total": 0, "model_total": 0}
                k_h_maddes = {m for lk, m in h_core if lk == k}
                k_m_maddes = {m for lk, m in m_core if lk == k}
                law_stats[k]["human_total"] += len(k_h_maddes)
                law_stats[k]["model_total"] += len(k_m_maddes)
                law_stats[k]["tp"] += len(k_h_maddes & k_m_maddes)
                law_stats[k]["fp"] += len(k_m_maddes - k_h_maddes)
                law_stats[k]["fn"] += len(k_h_maddes - k_m_maddes)

        def percentile(arr, p):
            if not arr:
                return 0.0
            sorted_arr = sorted(arr)
            k = (len(sorted_arr) - 1) * (p / 100.0)
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return float(sorted_arr[int(k)])
            d0 = sorted_arr[int(f)] * (c - k)
            d1 = sorted_arr[int(c)] * (k - f)
            return float(d0 + d1)

        def dist_summary(arr):
            if not arr:
                return {}
            return {
                "count": len(arr),
                "mean": round(statistics.mean(arr), 3),
                "std": round(statistics.stdev(arr), 3) if len(arr) > 1 else 0.0,
                "median": round(statistics.median(arr), 3),
                "min": min(arr),
                "max": max(arr),
                "p25": round(percentile(arr, 25), 2),
                "p75": round(percentile(arr, 75), 2),
                "p90": round(percentile(arr, 90), 2),
                "p95": round(percentile(arr, 95), 2),
                "p99": round(percentile(arr, 99), 2),
            }

        m_dist = dist_summary(model_ref_counts)
        h_dist = dist_summary(human_ref_counts)

        # Pearson correlation calculation
        def pearson(x, y):
            n = len(x)
            if n < 2:
                return 0.0
            mx, my = statistics.mean(x), statistics.mean(y)
            sx, sy = statistics.stdev(x), statistics.stdev(y)
            if sx == 0 or sy == 0:
                return 0.0
            cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (n - 1)
            return round(cov / (sx * sy), 4)

        corr = pearson(overlap_human_counts, overlap_model_counts)

        core_prec = round(core_tp / (core_tp + core_fp), 4) if (core_tp + core_fp) else 0.0
        core_rec = round(core_tp / (core_tp + core_fn), 4) if (core_tp + core_fn) else 0.0
        core_f1 = round(2 * core_prec * core_rec / (core_prec + core_rec), 4) if (core_prec + core_rec) else 0.0

        exact_prec = round(exact_tp / (exact_tp + exact_fp), 4) if (exact_tp + exact_fp) else 0.0
        exact_rec = round(exact_tp / (exact_tp + exact_fn), 4) if (exact_tp + exact_fn) else 0.0
        exact_f1 = round(2 * exact_prec * exact_rec / (exact_prec + exact_rec), 4) if (exact_prec + exact_rec) else 0.0

        cur.execute("SELECT DISTINCT kanun_no, kanun_ad FROM baran_annotation_references WHERE kanun_ad IS NOT NULL AND kanun_ad != ''")
        law_names = {norm(r["kanun_no"]): r["kanun_ad"] for r in cur.fetchall()}

        report = {
            "dataset_overview": {
                "total_model_predictions": total_model_preds,
                "total_human_annotated": total_human_annotated,
                "total_human_completed": total_human_completed,
                "overlap_evaluated_documents": len(overlap_human_counts),
            },
            "model_reference_distribution": m_dist,
            "human_reference_distribution": h_dist,
            "overlap_correlation_pearson": corr,
            "alignment_metrics": {
                "core_level_law_and_article": {
                    "tp": core_tp,
                    "fp": core_fp,
                    "fn": core_fn,
                    "precision": core_prec,
                    "recall": core_rec,
                    "f1_score": core_f1,
                    "mean_jaccard": round(statistics.mean(jaccard_scores_core), 4),
                    "median_jaccard": round(statistics.median(jaccard_scores_core), 4),
                },
                "exact_level_full_granularity": {
                    "tp": exact_tp,
                    "fp": exact_fp,
                    "fn": exact_fn,
                    "precision": exact_prec,
                    "recall": exact_rec,
                    "f1_score": exact_f1,
                    "mean_jaccard": round(statistics.mean(jaccard_scores_exact), 4),
                    "median_jaccard": round(statistics.median(jaccard_scores_exact), 4),
                }
            },
            "per_law_performance": []
        }

        for k, v in sorted(law_stats.items(), key=lambda x: x[1]["human_total"], reverse=True)[:15]:
            p = round(v["tp"] / (v["tp"] + v["fp"]), 4) if (v["tp"] + v["fp"]) else 0.0
            r = round(v["tp"] / (v["tp"] + v["fn"]), 4) if (v["tp"] + v["fn"]) else 0.0
            f1 = round(2 * p * r / (p + r), 4) if (p + r) else 0.0
            report["per_law_performance"].append({
                "kanun_no": k,
                "kanun_ad": law_names.get(k, "Bilinmiyor"),
                "human_refs_in_overlap": v["human_total"],
                "model_refs_in_overlap": v["model_total"],
                "true_positives": v["tp"],
                "precision": p,
                "recall": r,
                "f1_score": f1,
            })

        print(json.dumps(report, indent=2, ensure_ascii=False))

        with open("scripts/mlops_analysis_results.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
