import os
import psycopg
from pathlib import Path

url = os.environ.get("NEON_ADMIN_URL")
if not url: raise Exception("Missing NEON_ADMIN_URL")
sql = Path("migrations/postgres/001-baran-init.sql").read_text()
with psycopg.connect(url, autocommit=True) as conn:
    conn.execute(sql)
print("Applied successfully.")
