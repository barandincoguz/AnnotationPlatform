import sqlite3
from backend.quality.service import _document_text, load_prediction, _is_usable_prediction
conn = sqlite3.connect("data/db/annotations.db")
conn.row_factory = sqlite3.Row
doc_id = '17g6am0v7r1dpj'
doc_text = _document_text(conn, doc_id)
row = load_prediction(conn, doc_id)
is_usable = _is_usable_prediction(row, doc_text)
print(f"Is usable: {is_usable}")
if not is_usable:
    print(f"Status: {row['status']}")
    print(f"Truncated: {row['truncated']}")
    from backend.quality.service import sha256_text
    print(f"Doc hash: {sha256_text(doc_text)}")
    print(f"Pred hash: {row['text_sha256']}")
