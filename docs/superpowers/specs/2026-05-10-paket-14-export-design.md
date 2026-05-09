# Paket 14 — Annotation Dataset Export Design

**Status**: LOCKED (brainstormed 2026-05-10, approved by user)
**Depends on**: Paket 5 (annotations chain — produces the data being exported)
**Estimated size**: 5-6 tasks, ~900 LOC, +25 tests (608 → 633)

---

## 1. Scope

Paket 14 adds a single admin HTTP endpoint that streams the platform's annotation dataset out as CSV or JSONL for downstream handoff (ML team, regulatory stakeholders, internal reporting). No new schema, no archive on disk, no scheduled jobs — operator-triggered, immediate-stream-and-go.

### Locked decisions (from brainstorm)

| # | Decision | Reason |
|---|----------|--------|
| D1 | **Use case = ML/stakeholder handoff of annotation dataset.** Not a multi-table admin dump, not a per-user "download my data" feature. | The product of bursiyer team's work is the reference list per document. That is what stakeholders consume. Other use cases (per-user download, full DB dump) are deferred — backups serve the latter. |
| D2 | **Single endpoint** `GET /api/admin/export?format=csv|jsonl&...filters`. | Spec already mandated `format=csv|jsonl` query param. One endpoint keeps surface minimal. |
| D3 | **Streaming response, no disk archive.** Content-Disposition attachment. | At 18K documents × ~5 refs avg = ~90K rows ≈ 10-50 MB, streaming starts < 1s, completes in 5-15s. Operator's `curl > file.csv` or browser download handles archival. `data/exports/` directory exists but is unused for now. |
| D4 | **Both CSV and JSONL formats.** CSV denormalized (one row per reference). JSONL nested (one annotation per line, references in array). | CSV consumed by Excel / SQL import / data analysts. JSONL consumed by ML pipelines / `jq`. Different shapes for different downstream tools. |
| D5 | **Filter parameters**: `status=completed\|all` (default completed), `from_date`, `to_date` (inclusive, on `annotations.updated_at`), `document_id`, `user_id`. All optional, combinable. | Filters cover the primary slicing the operator will need — by completion state, by time window, single-doc test export, per-bursiyer reporting. |
| D6 | **User attribution visible** — both `user_id` (numeric) and `username`. | Internal team reporting (kim ne kadar üretti) requires the username. PII risk is low (no email, no password). Operator's responsibility to sanitize before external sharing. |
| D7 | **Auth = require_admin** (existence-hide 404 for non-admin). | Consistent with other admin endpoints (Paket 11/12/13). Bursiyer'lar kendi annotation'larını zaten aplikasyon içinde görüyor; bulk export operatör için. |
| D8 | **`require_admin` not `require_admin_with_export_capability`** — no fine-grained role split. | YAGNI for our 30-user platform. If needed, role-based scoping is a future paket. |
| D9 | **Audit logged**, but no `system_events` row. Just `admin_audit_log`. | This is an operator action, not an operational event. Same shape as paket-12/13 manual triggers. |

### Non-goals (will NOT be built in Paket 14)

- ❌ Disk archive of generated exports (operator's `curl > file` covers it)
- ❌ Async generation pattern (POST → export_id → poll/download) — overkill at 18K scale
- ❌ Anonymize mode for external sharing (operator sanitizes manually if needed; YAGNI)
- ❌ Additional formats (XLSX, Parquet) — CSV+JSONL covers ML and analyst needs
- ❌ Per-user `/api/me/export` endpoint
- ❌ Version history / annotation_versions in output (current state only)
- ❌ DB schema export (`backup` already does this)
- ❌ Compression at API layer (HTTP `Accept-Encoding` + reverse proxy handles it)
- ❌ Pagination / cursor-based slicing (streaming subsumes this)

---

## 2. Architecture

### Module layout

```
backend/exports/
├── __init__.py        # empty package marker
├── service.py         # build_query, stream_csv_rows, stream_jsonl_objects
├── models.py          # ExportFilters Pydantic (query params validation)
└── routes.py          # GET /api/admin/export

backend/main.py        # +1 import, +1 include_router
```

No migration. No lifespan task. No SSE event.

### Streaming pattern

FastAPI `StreamingResponse` + Python generator. The generator iterates over a SQLite cursor row-by-row (`cursor.fetchmany()` for batched chunks) and yields encoded bytes/strings. Memory footprint is constant (~MB) regardless of row count.

```python
# service.py (sketch)
def stream_csv_rows(cursor) -> Iterator[str]:
    yield CSV_HEADER + "\n"
    buf = io.StringIO()
    writer = csv.writer(buf)
    while True:
        rows = cursor.fetchmany(500)
        if not rows:
            return
        for row in rows:
            writer.writerow(row)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

def stream_jsonl_objects(cursor) -> Iterator[str]:
    """Aggregates references per annotation. Cursor must be ORDERed
    by (document_id, annotation_id, reference_id) so refs of the
    same annotation are contiguous; we just track current_id and
    flush when it changes."""
    current_annotation_id = None
    current_obj = None
    for row in cursor:
        if row.annotation_id != current_annotation_id:
            if current_obj is not None:
                yield json.dumps(current_obj, ensure_ascii=False) + "\n"
            current_annotation_id = row.annotation_id
            current_obj = build_annotation_object(row)
        if row.reference_id is not None:
            current_obj["references"].append(build_reference_object(row))
    if current_obj is not None:
        yield json.dumps(current_obj, ensure_ascii=False) + "\n"
```

### Audit logging

`audit.log_admin_action` is called AFTER the stream completes via FastAPI's `BackgroundTasks` mechanism (so it runs after the response is sent). On stream failure the audit row is NOT written — operator sees a corrupted download and the absence of an audit confirms the export did not succeed.

---

## 3. Endpoint Surface

```
GET /api/admin/export
  ?format=csv|jsonl                          (REQUIRED — Pydantic enum)
  ?status=completed|all                      (default: completed)
  ?from_date=YYYY-MM-DD                      (optional, inclusive lower bound)
  ?to_date=YYYY-MM-DD                        (optional, inclusive upper bound — semantically: < to_date+1day)
  ?document_id=doc_42                        (optional, exact match against documents_meta.id)
  ?user_id=42                                (optional, last_editor OR completed_by)

Auth: require_admin (404 existence-hide on non-admin)

Response 200 (CSV):
  Content-Type: text/csv; charset=utf-8
  Content-Disposition: attachment; filename="annotations-export-YYYYMMDD-HHMM.csv"
  Body: CSV stream (header row first, then data rows)

Response 200 (JSONL):
  Content-Type: application/x-ndjson; charset=utf-8
  Content-Disposition: attachment; filename="annotations-export-YYYYMMDD-HHMM.jsonl"
  Body: NDJSON stream (one annotation per line)

Response 422 (Pydantic validation):
  - format missing or not in {csv, jsonl}
  - from_date or to_date not parseable as YYYY-MM-DD
  - from_date > to_date
  - user_id not positive integer
  - status not in {completed, all}

Response 404:
  - non-admin caller (existence-hide)
  - missing session

Side effects:
  - On stream success: admin_audit_log row
    {action_type='export_dataset', target_kind='export', target_id=<filename>,
     metadata={format, filters: {...applied filters...}, exported_count: <int>}}
  - On stream failure: NO audit row (failure obvious from incomplete download)
```

### Filename convention

`annotations-export-YYYYMMDD-HHMM.{csv|jsonl}` using UTC timestamp. Lexicographic sort = chronological sort, matching backup snapshot naming.

---

## 4. Format Details

### CSV (one row per `annotation × reference`)

Header columns (in this exact order):

```
document_id, doc_sayi, doc_tarih, doc_konu,
annotation_id, last_editor_user_id, last_editor_username, last_edited_at,
completed_by_user_id, completed_by_username, completed_at,
ref_kanun_no, ref_kanun_ad, ref_madde, ref_fikra, ref_bent, ref_source_text
```

Behavior:
- Annotation with 0 references → 1 row, all `ref_*` cells empty
- Annotation with 5 references → 5 rows, doc/annotation columns identical, `ref_*` columns differ
- Header always written first (even if zero data rows)
- Encoding: UTF-8 (no BOM)
- Delimiter: `,`
- Escape: RFC 4180 — fields containing `,`, `"`, `\n`, `\r` quoted with `"`; embedded quotes doubled (`""`)
- Empty cells: empty string (not the literal `null`)

### JSONL (one annotation per line, references nested)

```jsonl
{"document_id":"doc_42","document":{"sayi":1234,"tarih":"20260101","konu":"Test özelge"},"annotation":{"id":12,"last_editor":{"id":42,"username":"ahmet"},"last_edited_at":"2026-04-15T10:30:00+00:00","completed_by":{"id":42,"username":"ahmet"},"completed_at":"2026-04-16T14:00:00+00:00"},"references":[{"kanun_no":"5520","kanun_ad":"Kurumlar Vergisi Kanunu","madde":"30","fikra":"2","bent":"a","source_text":"madde 30/2-a"},{"kanun_no":"5901","kanun_ad":"T.C. Kimlik Kanunu","madde":"91","fikra":null,"bent":null,"source_text":"madde 91"}]}
```

Behavior:
- One JSON object per line (newline-delimited)
- `ensure_ascii=False` — Turkish chars stay readable
- Compact (no indent)
- `references: []` if annotation has no references (always an array, never absent)
- `last_editor: null` if `last_editor_user_id` is NULL (defensive — should never happen per schema, but JSONL must be well-formed regardless)
- `completed_by: null` if `completed_at` is NULL (uncompleted annotation in `status=all` export)
- Encoding: UTF-8

---

## 5. Data Flow

```
HTTP GET /api/admin/export?format=csv&status=completed&from_date=2026-04-01
  ↓
FastAPI dependency injection:
  - require_admin (404 if not admin)
  - get_db (sqlite3.Connection)
  - ExportFilters Pydantic (validates query params; 422 on invalid)
  ↓
service.build_query(filters) → (sql, params)
  ↓
db.execute("BEGIN DEFERRED")    ← read-only consistency for the duration of the stream
db.execute(sql, params)
  ↓
StreamingResponse(
    content=stream_csv_rows(cursor) | stream_jsonl_objects(cursor),
    media_type="text/csv" | "application/x-ndjson",
    headers={"Content-Disposition": f"attachment; filename={filename}"},
    background=BackgroundTasks(log_export, db, admin, filters, count_estimate),
)
  ↓ (response streams; cursor consumed lazily)
on response close:
  background task runs:
    audit.log_admin_action(db, ...,
      action_type='export_dataset',
      target_id=filename,
      metadata={format, filters, exported_count})
```

### SQL template (parameterized; no string interpolation of user input)

```sql
SELECT d.id        AS document_id,
       d.sayi      AS doc_sayi,
       d.tarih     AS doc_tarih,
       d.konu      AS doc_konu,
       a.id        AS annotation_id,
       a.last_editor_user_id,
       ue.username AS last_editor_username,
       a.updated_at AS last_edited_at,
       a.completed_by_user_id,
       uc.username AS completed_by_username,
       a.completed_at,
       ar.id       AS reference_id,
       ar.kanun_no, ar.kanun_ad, ar.madde, ar.fikra, ar.bent, ar.source_text
FROM annotations a
JOIN documents_meta d ON a.document_id = d.id
LEFT JOIN users ue              ON a.last_editor_user_id = ue.id
LEFT JOIN users uc              ON a.completed_by_user_id = uc.id
LEFT JOIN annotation_references ar ON ar.annotation_id = a.id
WHERE 1=1
  -- conditional clauses appended by build_query:
  [AND a.completed_at IS NOT NULL]                       -- if status=completed
  [AND a.updated_at >= ?]                                -- if from_date
  [AND a.updated_at < date(?, '+1 day')]                 -- if to_date (inclusive end)
  [AND a.document_id = ?]                                -- if document_id
  [AND (a.last_editor_user_id = ? OR a.completed_by_user_id = ?)]  -- if user_id
ORDER BY d.id, a.id, ar.id
```

JSONL grouping relies on the `ORDER BY d.id, a.id, ar.id` so references of one annotation are contiguous.

### exported_count tracking

Streaming generator wraps row iteration with a counter. Counter accessible by reference (mutable list `[0]` or counter object) so the BackgroundTask reads the final value after stream completion.

For CSV: counter increments per data row (= reference count + zero-ref annotations).
For JSONL: counter increments per annotation flushed.

Two different counts; `metadata.exported_count` reflects the format.

---

## 6. Error Handling

| Scenario | Behavior |
|----------|----------|
| `format` query param missing or not in {csv, jsonl} | 422 Pydantic validation error |
| `from_date` not YYYY-MM-DD | 422 |
| `to_date` not YYYY-MM-DD | 422 |
| `from_date > to_date` | 422 with detail "from_date must be ≤ to_date" |
| `user_id` not positive int | 422 |
| `document_id` not found in DB | 200 with header-only CSV (or empty JSONL stream). Audit row written with `exported_count=0`. |
| `user_id` not found in DB | Same — empty result, not error |
| Non-admin authenticated user | 404 (require_admin existence-hide) |
| No session | 401 (get_current_user) |
| DB error mid-stream | log.exception, partial response sent to client, audit row NOT written. Client sees malformed/truncated CSV. Operator retries. No transaction to rollback (read-only). |
| Stream interrupted (client disconnect) | FastAPI cancels the generator. No audit row written (BackgroundTasks doesn't fire). |
| Disk full on client (impossible on server side; client-side concern) | Outside scope |

**Per-step fault isolation deliberately NOT implemented**: a streaming response that fails halfway gives the client a malformed download. Acceptable because exports are operator-triggered and easily retriable. Audit row presence/absence is the success signal.

---

## 7. Tests — TDD Coverage Matrix

```
tests/test_exports_service.py
  ├── test_build_query_no_filters
  ├── test_build_query_status_completed_default
  ├── test_build_query_status_all_includes_uncompleted
  ├── test_build_query_from_date_filter
  ├── test_build_query_to_date_inclusive_end_of_day
  ├── test_build_query_document_id_filter
  ├── test_build_query_user_id_matches_editor_or_completer
  ├── test_build_query_combines_multiple_filters
  ├── test_stream_csv_rows_emits_header_first
  ├── test_stream_csv_rows_one_row_per_reference
  ├── test_stream_csv_rows_zero_reference_annotation_emits_one_row_with_nulls
  ├── test_stream_csv_rows_escapes_special_chars        # quote, comma, newline in source_text
  ├── test_stream_jsonl_objects_one_per_annotation
  ├── test_stream_jsonl_objects_groups_references_per_annotation
  ├── test_stream_jsonl_objects_empty_references_array
  └── test_stream_jsonl_handles_turkish_chars            # ensure_ascii=False

tests/test_exports_models.py
  ├── test_filters_format_required
  ├── test_filters_format_rejects_invalid_value
  ├── test_filters_status_default_completed
  ├── test_filters_from_date_after_to_date_rejected
  └── test_filters_user_id_must_be_positive

tests/test_exports_routes.py
  ├── test_export_admin_only                              # 404 for non-admin
  ├── test_export_csv_returns_correct_content_type
  ├── test_export_csv_filename_in_disposition
  ├── test_export_jsonl_returns_correct_content_type
  ├── test_export_csv_streams_seeded_data                 # full-stack: seed + GET + parse
  ├── test_export_jsonl_streams_seeded_data
  ├── test_export_filter_status_all_includes_uncompleted
  ├── test_export_writes_admin_audit_log_after_success
  └── test_export_empty_result_returns_header_only_csv
```

**Total**: ~25 new tests. Suite size **608 → 633** once all tasks implemented.

---

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 18K doc × 5 refs = ~90K rows; generation takes 10+ seconds | High | Low | Streaming starts < 1s; client sees progress. No browser timeout (Content-Disposition triggers download). |
| Operator runs export with all filters wrong → 0 rows | Medium | Low | CSV header always written so empty file is still valid. JSONL empty file is valid (zero objects). Audit `exported_count=0` makes the pattern visible. |
| Concurrent backup/retention loop holds BEGIN IMMEDIATE; export's BEGIN DEFERRED waits | Low | Low | busy_timeout=5000 (Paket 13) handles contention. BEGIN DEFERRED + WAL = readers don't block. |
| Username PII leaks via external sharing of the export file | Medium (operator error) | Medium | Documented in admin UI tooltip + commit message: "outputs include usernames; sanitize before external sharing." Not enforced in code (operator's job). |
| Very long source_text (> 32K chars) breaks Excel CSV parsing | Low | Low | RFC 4180 escape is correct; Excel limit is on its end. Operator using Excel knows the workaround (open in text editor / use LibreOffice). |
| Export running during a write storm causes lock retries | Low | Low | Read-only query + 5s busy_timeout absorbs short writes. If contention is sustained the generator's first chunk delays a few seconds but does not fail. |
| `ORDER BY d.id, a.id, ar.id` requires sort; large result sets use temp space | Medium | Low | annotations and annotation_references both have indexes on relevant FKs. Sort is on already-indexed columns; cost is bounded. |

---

## 9. Open Questions

None. Brainstorming converged on every decision.

---

## 10. Estimated Sub-Tasks (preliminary; finalized in PLAN.md)

1. **T1**: `ExportFilters` Pydantic model + 5 model unit tests
2. **T2**: `service.build_query` + 8 query-construction tests
3. **T3**: `service.stream_csv_rows` + 4 CSV-streaming tests
4. **T4**: `service.stream_jsonl_objects` + 4 JSONL-streaming tests
5. **T5**: `routes.py` HTTP layer + 9 route tests + main.py wire-up + audit + tag

Total: 5 implementation tasks. Smaller than Paket 13 (8) — fewer moving pieces, no migration, no lifespan.
