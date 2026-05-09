"""Tests for backend/exports/routes.py — GET /api/admin/export."""
import csv
import io
import json


def test_export_admin_only(client, passed_user):
    """Non-admin gets 404 (existence-hide). Spec D7."""
    r = client.get("/api/admin/export?format=csv")
    assert r.status_code == 404


def test_export_csv_returns_correct_content_type(client, bootstrap_admin):
    bootstrap_admin()
    r = client.get("/api/admin/export?format=csv")
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers["content-type"]


def test_export_csv_filename_in_disposition(client, bootstrap_admin):
    """Content-Disposition advertises a file download with timestamped name."""
    bootstrap_admin()
    r = client.get("/api/admin/export?format=csv")
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "annotations-export-" in cd
    assert ".csv" in cd


def test_export_jsonl_returns_correct_content_type(client, bootstrap_admin):
    bootstrap_admin()
    r = client.get("/api/admin/export?format=jsonl")
    assert r.status_code == 200, r.text
    assert "application/x-ndjson" in r.headers["content-type"]


def test_export_csv_streams_seeded_data(client, bootstrap_admin, ingest_doc):
    """End-to-end: ingest a doc, write an annotation + 1 reference, then
    GET the export and parse it as CSV. Must contain the seeded document_id."""
    bootstrap_admin()
    doc_id = ingest_doc(document_id="doc_seed_csv")

    # Write an annotation with one reference.
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            """INSERT INTO annotations
               (document_id, references_json, is_completed,
                last_editor_user_id, completed_by_user_id,
                edit_count, unique_users_count, created_at, updated_at)
               VALUES (?, '[]', 1, 1, 1, 1, 1, datetime('now'), datetime('now'))""",
            (doc_id,),
        )
        conn.execute(
            """INSERT INTO annotation_references
               (document_id, seq, kanun_no, kanun_ad, madde, fikra, bent, source_text)
               VALUES (?, 0, '5520', 'Kurumlar Vergisi', '30', '2', 'a', 'madde 30/2-a')""",
            (doc_id,),
        )
        conn.commit()
    finally:
        conn.close()

    r = client.get("/api/admin/export?format=csv")
    assert r.status_code == 200, r.text
    body = r.text
    reader = csv.reader(io.StringIO(body))
    rows = list(reader)
    # Header + at least one data row
    assert len(rows) >= 2
    assert rows[0][0] == "document_id"
    seeded_row = next((row for row in rows[1:] if row[0] == doc_id), None)
    assert seeded_row is not None, f"seeded doc {doc_id} not found in {rows}"


def test_export_jsonl_streams_seeded_data(client, bootstrap_admin, ingest_doc):
    """End-to-end JSONL: same seed, but parse as NDJSON and assert nested
    references shape."""
    bootstrap_admin()
    doc_id = ingest_doc(document_id="doc_seed_jsonl")
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            """INSERT INTO annotations
               (document_id, references_json, is_completed,
                last_editor_user_id, completed_by_user_id,
                edit_count, unique_users_count, created_at, updated_at)
               VALUES (?, '[]', 1, 1, 1, 1, 1, datetime('now'), datetime('now'))""",
            (doc_id,),
        )
        conn.execute(
            """INSERT INTO annotation_references
               (document_id, seq, kanun_no, kanun_ad, madde, fikra, bent, source_text)
               VALUES (?, 0, '5901', 'T.C. Kimlik', '91', NULL, NULL, 'madde 91')""",
            (doc_id,),
        )
        conn.commit()
    finally:
        conn.close()

    r = client.get("/api/admin/export?format=jsonl")
    assert r.status_code == 200, r.text
    lines = [json.loads(line) for line in r.text.strip().split("\n") if line]
    seeded = next((obj for obj in lines if obj["document_id"] == doc_id), None)
    assert seeded is not None
    assert len(seeded["references"]) == 1
    assert seeded["references"][0]["kanun_no"] == "5901"
    assert seeded["references"][0]["fikra"] is None  # NULL preserved


def test_export_filter_status_all_includes_uncompleted(
    client, bootstrap_admin, ingest_doc,
):
    """status=all must include is_completed=0 rows that the default
    status=completed filter would exclude."""
    bootstrap_admin()
    doc_id = ingest_doc(document_id="doc_uncompleted")
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            """INSERT INTO annotations
               (document_id, references_json, is_completed,
                last_editor_user_id,
                edit_count, unique_users_count, created_at, updated_at)
               VALUES (?, '[]', 0, 1, 1, 1, datetime('now'), datetime('now'))""",
            (doc_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # Default filter excludes it.
    r = client.get("/api/admin/export?format=csv")
    assert doc_id not in r.text

    # status=all includes it.
    r = client.get("/api/admin/export?format=csv&status=all")
    assert doc_id in r.text


def test_export_writes_admin_audit_log_after_success(client, bootstrap_admin):
    """admin_audit_log captures the export trigger after the response stream
    completes (BackgroundTasks pattern). On a fresh DB the row count may be
    zero but the audit row still lands."""
    bootstrap_admin()
    r = client.get("/api/admin/export?format=csv")
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        row = conn.execute(
            "SELECT action_type, target_kind, target_id, metadata_json "
            "FROM admin_audit_log "
            "WHERE action_type='export_dataset' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["target_kind"] == "export"
    assert row["target_id"].startswith("annotations-export-")
    assert row["target_id"].endswith(".csv")
    meta = json.loads(row["metadata_json"])
    assert meta["format"] == "csv"
    assert "filters" in meta
    assert "exported_count" in meta


def test_export_empty_result_returns_header_only_csv(client, bootstrap_admin):
    """Filter that matches nothing → still a valid CSV with just the
    header row. Operator's downstream parser should not break on empty
    results."""
    bootstrap_admin()
    r = client.get("/api/admin/export?format=csv&document_id=does_not_exist")
    assert r.status_code == 200
    body = r.text.strip()
    assert body  # not literally empty
    assert "\n" not in body  # exactly one line: the header
    assert body.startswith("document_id,")
