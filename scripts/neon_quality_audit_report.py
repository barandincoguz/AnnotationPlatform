import os
import json
import psycopg
from psycopg.rows import dict_row

db_url = os.environ.get("NEON_ADMIN_URL") or os.environ.get("NEON_MIRROR_URL")
if not db_url:
    print("NEON_ADMIN_URL not set")
    exit(1)

with psycopg.connect(db_url, row_factory=dict_row) as conn:
    with conn.cursor() as cur:
        print("=== 1. PREDICTIONS METRICS ===")
        cur.execute("SELECT count(*) as total FROM baran_model_predictions")
        total_preds = cur.fetchone()["total"]
        print(f"Total Model Predictions in NeonDB: {total_preds}")

        cur.execute("""
            SELECT status, truncated, count(*) as c 
            FROM baran_model_predictions 
            GROUP BY status, truncated 
            ORDER BY c DESC
        """)
        for r in cur.fetchall():
            print(f"  - status={r['status']}, truncated={r['truncated']}: {r['c']} rows")

        cur.execute("""
            SELECT 
                count(*) as total_success,
                avg(jsonb_array_length(references_json::jsonb)) as avg_refs_per_doc,
                max(jsonb_array_length(references_json::jsonb)) as max_refs_per_doc,
                min(jsonb_array_length(references_json::jsonb)) as min_refs_per_doc
            FROM baran_model_predictions
            WHERE status = 'success'
        """)
        stats = cur.fetchone()
        print(f"Success stats: avg_refs={stats['avg_refs_per_doc']:.2f}, max_refs={stats['max_refs_per_doc']}, min_refs={stats['min_refs_per_doc']}")

        print("\n=== 2. SCHOLAR ANNOTATIONS & SYSTEM STATE ===")
        cur.execute("SELECT count(*) as total, sum(case when is_completed=1 then 1 else 0 end) as completed FROM baran_annotations")
        annot_stats = cur.fetchone()
        print(f"Total Annotations: {annot_stats['total']} (Completed: {annot_stats['completed']})")

        cur.execute("SELECT count(*) as total FROM baran_annotation_references")
        total_refs = cur.fetchone()["total"]
        print(f"Total Human References Persisted: {total_refs}")

        cur.execute("SELECT count(*) as total FROM baran_users")
        total_users = cur.fetchone()["total"]
        print(f"Total Users Registered: {total_users}")

        print("\n=== 3. AUDIT LOGS & HUMAN-MODEL INTERACTIONS ===")
        cur.execute("SELECT count(*) as total FROM baran_annotation_audit_logs")
        total_audits = cur.fetchone()["total"]
        print(f"Total Audit Logs Recorded: {total_audits}")

        if total_audits > 0:
            cur.execute("""
                SELECT decision, count(*) as c
                FROM baran_annotation_audit_logs
                GROUP BY decision
                ORDER BY c DESC
            """)
            print("Decisions breakdown:")
            for r in cur.fetchall():
                print(f"  - {r['decision']}: {r['c']}")

            cur.execute("""
                SELECT bucket, count(*) as c
                FROM baran_annotation_audit_logs
                GROUP BY bucket
                ORDER BY c DESC
            """)
            print("Buckets breakdown:")
            for r in cur.fetchall():
                print(f"  - {r['bucket']}: {r['c']}")

        print("\n=== 4. RECENT ACTIVITY EVENTS ===")
        cur.execute("SELECT count(*) as total FROM baran_activity_events")
        total_events = cur.fetchone()["total"]
        print(f"Total Activity Events: {total_events}")

        cur.execute("""
            SELECT action, count(*) as c 
            FROM baran_activity_events 
            GROUP BY action 
            ORDER BY c DESC 
            LIMIT 10
        """)
        print("Top activity actions:")
        for r in cur.fetchall():
            print(f"  - {r['action']}: {r['c']}")

