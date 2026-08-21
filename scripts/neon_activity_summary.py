import os
import psycopg
from psycopg.rows import dict_row

db_url = os.environ.get("NEON_ADMIN_URL") or os.environ.get("NEON_MIRROR_URL")
with psycopg.connect(db_url, row_factory=dict_row) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                count(DISTINCT document_id) as distinct_docs_annotated,
                count(DISTINCT completed_by_user_id) as active_annotators
            FROM baran_annotations
        """)
        r = cur.fetchone()
        print(f"Distinct Documents Annotated: {r['distinct_docs_annotated']}")
        print(f"Active Annotator Scholars: {r['active_annotators']}")
