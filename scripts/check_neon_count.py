import os
import psycopg
url = os.environ.get("NEON_ADMIN_URL")
with psycopg.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM baran_model_predictions;")
        print(cur.fetchone()[0])
