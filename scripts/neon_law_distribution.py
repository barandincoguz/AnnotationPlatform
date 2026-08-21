import os
import psycopg
from psycopg.rows import dict_row

db_url = os.environ.get("NEON_ADMIN_URL") or os.environ.get("NEON_MIRROR_URL")
with psycopg.connect(db_url, row_factory=dict_row) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                elem->>'kanun_no' as kanun_no,
                elem->>'kanun_ad' as kanun_ad,
                count(*) as citation_count
            FROM baran_model_predictions,
                 jsonb_array_elements(references_json::jsonb) as elem
            WHERE status = 'success'
            GROUP BY kanun_no, kanun_ad
            ORDER BY citation_count DESC
            LIMIT 10
        """)
        print("Top 10 Laws Cited in Model Predictions:")
        for r in cur.fetchall():
            print(f"  - Kanun No: {r['kanun_no']} | {r['kanun_ad']}: {r['citation_count']} citations")

        cur.execute("""
            SELECT 
                kanun_no,
                kanun_ad,
                count(*) as citation_count
            FROM baran_annotation_references
            GROUP BY kanun_no, kanun_ad
            ORDER BY citation_count DESC
            LIMIT 10
        """)
        print("\nTop 10 Laws Cited in Scholar Annotations:")
        for r in cur.fetchall():
            print(f"  - Kanun No: {r['kanun_no']} | {r['kanun_ad']}: {r['citation_count']} citations")
