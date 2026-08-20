import sqlite3
from backend.quality.service import sha256_text
conn = sqlite3.connect("data/db/annotations.db")
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT m.pdf_text, p.text_sha256 FROM documents_meta m JOIN model_predictions p ON m.document_id = p.document_id WHERE m.document_id = '17g6am0v7r1dpj'").fetchone()
doc_hash = sha256_text(row["pdf_text"])
pred_hash = row["text_sha256"]
print(f"Doc hash: {doc_hash}")
print(f"Pred hash: {pred_hash}")
