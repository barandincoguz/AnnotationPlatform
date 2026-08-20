import sqlite3
import dataclasses
from backend.quality.service import build_report
conn = sqlite3.connect("data/db/annotations.db")
conn.row_factory = sqlite3.Row
doc_id = '17g6am0v7r1dpj'
report = build_report(conn, document_id=doc_id, references=[])
print(dataclasses.asdict(report))
