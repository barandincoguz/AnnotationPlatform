import sqlite3
from backend.quality.service import build_report
conn = sqlite3.connect("data/db/annotations.db")
conn.row_factory = sqlite3.Row
try:
    report = build_report(conn, document_id="4ile76x41d146v", references=[])
    print(report)
except Exception as e:
    print(f"Error: {e}")
