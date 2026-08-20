import sqlite3
from backend.quality.service import pending_documents
conn = sqlite3.connect("data/db/annotations.db")
conn.row_factory = sqlite3.Row
docs = pending_documents(conn, limit=4)
print(len(docs))
