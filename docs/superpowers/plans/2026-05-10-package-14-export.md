# Paket 14 — Annotation Dataset Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single admin-only HTTP endpoint that streams the annotation dataset out as CSV (one row per reference, denormalized) or JSONL (one annotation per line, references nested), with filterable scope (status / from_date / to_date / document_id / user_id).

**Architecture:** New `backend/exports/` package with three small modules: `service.py` (pure-function `build_query` + two streaming generators), `models.py` (Pydantic `ExportFilters` for query-param validation), `routes.py` (single `GET /api/admin/export` admin endpoint). FastAPI `StreamingResponse` consumes generators that iterate a SQLite cursor row-by-row, so memory is constant. Audit row is written via `BackgroundTasks` after the stream completes successfully.

**Tech Stack:** Existing FastAPI + SQLite + Pydantic + Python `csv` + `json` standard libs. No new third-party dependencies. Reuses `backend.shared.audit.log_admin_action`, `backend.users.deps.{get_db, require_admin}`.

---

## Mimari Kararlar (Locked from spec 2026-05-10-paket-14-export-design.md, commit `a8c4880`)

- **Module layout:**
  - `backend/exports/__init__.py` — empty package marker
  - `backend/exports/service.py` — `build_query`, `stream_csv_rows`, `stream_jsonl_objects`, plus the canonical column ordering constants
  - `backend/exports/models.py` — `ExportFilters` Pydantic schema (validates query params)
  - `backend/exports/routes.py` — `GET /api/admin/export`
  - `backend/main.py` — +1 import, +1 `include_router` call (no lifespan touch)
- **Auth:** `Depends(require_admin)` → 404 existence-hide for non-admin.
- **Filter semantics:**
  - `format` ∈ {csv, jsonl} REQUIRED
  - `status` ∈ {completed, all}, default `completed`
  - `from_date`, `to_date` ISO date strings, both inclusive (to_date implemented as `< date(?, '+1 day')`)
  - `document_id` exact match against `annotations.document_id`
  - `user_id` matches `last_editor_user_id` OR `completed_by_user_id`
  - All filters optional, combinable
- **Response shape:**
  - `Content-Type: text/csv; charset=utf-8` or `application/x-ndjson; charset=utf-8`
  - `Content-Disposition: attachment; filename="annotations-export-YYYYMMDD-HHMM.<ext>"`
  - Streaming body via `StreamingResponse(generator, media_type=…, background=BackgroundTasks(…))`
- **CSV semantics:** RFC 4180 (delimiter `,`, quote `"`, embedded quote doubled), UTF-8 no-BOM. Header always written. Annotation with 0 references → 1 row with empty `ref_*` cells. Annotation with N references → N rows, doc/annotation cells repeated.
- **JSONL semantics:** one compact JSON object per line, `ensure_ascii=False`, `references: []` when none, `last_editor`/`completed_by` are `null` when the FK is NULL.
- **Schema reality (verified via PRAGMA):**
  - `annotations` is PK'd on `document_id` (one annotation row per document)
  - `annotations.is_completed` is the boolean (NO `completed_at` column exists)
  - `annotation_references` joins via `document_id`, ordered by `seq`
- **Audit:** `admin_audit_log` row only on stream success (via FastAPI `BackgroundTasks`). No `system_events` row (this is operator action, not operational event).
- **No new schema, no migration, no lifespan task, no SSE.**

---

## Files Created/Modified

| File | Action | Purpose |
|------|--------|---------|
| `backend/exports/__init__.py` | Create | Empty package marker |
| `backend/exports/service.py` | Create | CSV_COLUMNS constant, `build_query`, `stream_csv_rows`, `stream_jsonl_objects` |
| `backend/exports/models.py` | Create | `ExportFilters` Pydantic schema |
| `backend/exports/routes.py` | Create | `GET /api/admin/export` |
| `backend/main.py` | Modify (2 small edits) | Import + `include_router` |
| `tests/test_exports_models.py` | Create | 5 tests |
| `tests/test_exports_service.py` | Create | 16 tests (8 build_query + 4 CSV stream + 4 JSONL stream) |
| `tests/test_exports_routes.py` | Create | 9 tests (auth, content-type, filename, end-to-end, audit) |

**Test budget:** 30 new tests. Suite size **608 → 638**.

(Note: spec section 7 estimated ~25 tests; the plan breaks them down more granularly so the actual count is 30. Same coverage scope.)

---

## Task 1: ExportFilters Pydantic schema

**Files:**
- Create: `backend/exports/__init__.py`
- Create: `backend/exports/models.py`
- Test: `tests/test_exports_models.py`

Validates query parameters before the route ever touches the DB. Pydantic's enum + date parsing does most of the work; we only add the cross-field check `from_date <= to_date`.

- [ ] **Step 1: Create the empty package marker**

Create `backend/exports/__init__.py` as an empty file:

```python
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_exports_models.py`:

```python
"""Tests for backend/exports/models.py — ExportFilters query-param validation."""
import pytest
from datetime import date

from pydantic import ValidationError


def test_filters_format_required():
    """`format` is the only mandatory query param. Without it Pydantic
    rejects the request before any DB work happens."""
    from backend.exports.models import ExportFilters
    with pytest.raises(ValidationError) as exc:
        ExportFilters()
    assert "format" in str(exc.value)


def test_filters_format_rejects_invalid_value():
    """Only csv and jsonl are valid. xml/txt/null all 422."""
    from backend.exports.models import ExportFilters
    with pytest.raises(ValidationError):
        ExportFilters(format="xml")


def test_filters_status_default_completed():
    """When status is omitted, default to completed (the more selective
    filter — operator who wants 'everything' must opt in via status=all)."""
    from backend.exports.models import ExportFilters
    f = ExportFilters(format="csv")
    assert f.status == "completed"


def test_filters_from_date_after_to_date_rejected():
    """Cross-field validation: from_date must not be after to_date."""
    from backend.exports.models import ExportFilters
    with pytest.raises(ValidationError) as exc:
        ExportFilters(
            format="csv",
            from_date=date(2026, 5, 10),
            to_date=date(2026, 4, 1),
        )
    assert "from_date" in str(exc.value)


def test_filters_user_id_must_be_positive():
    """user_id is a primary key; zero/negative values can never match
    any real user. Reject at validation rather than do a wasted query."""
    from backend.exports.models import ExportFilters
    with pytest.raises(ValidationError):
        ExportFilters(format="csv", user_id=0)
    with pytest.raises(ValidationError):
        ExportFilters(format="csv", user_id=-1)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_exports_models.py -v`
Expected: 5 FAILS with `ImportError: cannot import name 'ExportFilters' from 'backend.exports.models'`.

- [ ] **Step 4: Write minimal implementation**

Create `backend/exports/models.py`:

```python
"""Pydantic schemas for /api/admin/export."""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ExportFilters(BaseModel):
    """Query-param validation for the export endpoint. All fields except
    `format` are optional; the route applies them as conditional WHERE
    clauses in build_query."""

    format: Literal["csv", "jsonl"] = Field(
        ..., description="Output format. csv = denormalized one-row-per-reference; "
                         "jsonl = one annotation per line with references nested."
    )
    status: Literal["completed", "all"] = Field(
        default="completed",
        description="completed → only is_completed=1 rows; all → every annotation row.",
    )
    from_date: Optional[date] = Field(
        default=None,
        description="Inclusive lower bound on annotations.updated_at. ISO YYYY-MM-DD.",
    )
    to_date: Optional[date] = Field(
        default=None,
        description="Inclusive upper bound on annotations.updated_at. End of day.",
    )
    document_id: Optional[str] = Field(
        default=None,
        description="Exact match against annotations.document_id.",
    )
    user_id: Optional[int] = Field(
        default=None, gt=0,
        description="Matches last_editor_user_id OR completed_by_user_id.",
    )

    @model_validator(mode="after")
    def _check_date_order(self):
        if (
            self.from_date is not None
            and self.to_date is not None
            and self.from_date > self.to_date
        ):
            raise ValueError(
                f"from_date ({self.from_date}) must be ≤ to_date ({self.to_date})"
            )
        return self
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_exports_models.py -v`
Expected: 5 passed.

Full suite check: `.venv/bin/python -m pytest -x`
Expected: 613 passed (608 baseline + 5 new).

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/exports/__init__.py \
  backend/exports/models.py \
  tests/test_exports_models.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket14-T1): ExportFilters Pydantic schema

Validates the 6 query params (format/status/from_date/to_date/
document_id/user_id) before the route reaches the DB. Cross-field
validator rejects from_date > to_date. user_id constrained to
positive integers (gt=0) so zero/negative values 422 instead of
silently producing empty results.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: build_query SQL construction

**Files:**
- Modify: `backend/exports/service.py` (create with `CSV_COLUMNS` constant + `build_query`)
- Test: `tests/test_exports_service.py` (8 tests)

`build_query(filters)` returns `(sql_string, params_tuple)` for parameterized execution. No DB access in this function — it's pure construction. The SQL skeleton is fixed; only the `WHERE` clauses and bound params vary by filter.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_exports_service.py`:

```python
"""Tests for backend/exports/service.py — build_query (Task 2),
stream_csv_rows (Task 3), stream_jsonl_objects (Task 4)."""
from datetime import date


# ---------------- build_query ----------------


def test_build_query_no_filters():
    """With format-only filters, no conditional WHERE clauses are added.
    The SQL still has a `WHERE 1=1` skeleton so future appends are uniform."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(ExportFilters(format="csv", status="all"))
    assert "WHERE 1=1" in sql
    assert "is_completed" not in sql       # status=all → no completion clause
    assert "updated_at >=" not in sql
    assert "updated_at < date" not in sql
    assert params == ()


def test_build_query_status_completed_default():
    """Default status=completed appends `AND a.is_completed = 1`."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(ExportFilters(format="csv"))
    assert "AND a.is_completed = 1" in sql
    assert params == ()


def test_build_query_status_all_omits_completion_clause():
    """Explicit status=all suppresses the is_completed clause so the
    export includes uncompleted (saved-but-not-finalized) annotations."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(ExportFilters(format="csv", status="all"))
    assert "is_completed" not in sql


def test_build_query_from_date_filter():
    """from_date appends `AND a.updated_at >= ?` and binds the ISO string."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(
        ExportFilters(format="csv", status="all", from_date=date(2026, 4, 1))
    )
    assert "AND a.updated_at >= ?" in sql
    assert "2026-04-01" in params


def test_build_query_to_date_inclusive_end_of_day():
    """to_date uses `< date(?, '+1 day')` so '2026-04-30' includes all rows
    up to and including 2026-04-30T23:59:59."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(
        ExportFilters(format="csv", status="all", to_date=date(2026, 4, 30))
    )
    assert "AND a.updated_at < date(?, '+1 day')" in sql
    assert "2026-04-30" in params


def test_build_query_document_id_filter():
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(
        ExportFilters(format="csv", status="all", document_id="doc_42")
    )
    assert "AND a.document_id = ?" in sql
    assert "doc_42" in params


def test_build_query_user_id_matches_editor_or_completer():
    """user_id binds to BOTH last_editor_user_id AND completed_by_user_id
    in a single OR clause (so a user is included if they touched the
    annotation in any role)."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    sql, params = build_query(
        ExportFilters(format="csv", status="all", user_id=42)
    )
    assert "(a.last_editor_user_id = ? OR a.completed_by_user_id = ?)" in sql
    # Same user_id bound twice
    assert params.count(42) == 2


def test_build_query_combines_multiple_filters():
    """All five conditional clauses can stack. Order matters less than
    determinism — same input → same SQL string + param tuple."""
    from backend.exports.models import ExportFilters
    from backend.exports.service import build_query

    filters = ExportFilters(
        format="csv",
        status="completed",
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 30),
        document_id="doc_42",
        user_id=42,
    )
    sql, params = build_query(filters)
    assert "is_completed = 1" in sql
    assert "updated_at >=" in sql
    assert "updated_at < date" in sql
    assert "a.document_id = ?" in sql
    assert "last_editor_user_id = ? OR a.completed_by_user_id = ?" in sql
    assert "ORDER BY a.document_id, ar.seq" in sql
    # 2 dates + 1 doc_id + 2 user_ids = 5 params
    assert len(params) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_exports_service.py -v`
Expected: 8 FAILS with `ImportError: cannot import name 'build_query' from 'backend.exports.service'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/exports/service.py`:

```python
"""Annotation dataset export — pure-function service layer.

Three things here:
  1. build_query(filters) → (sql, params) for parameterized cursor execute
  2. stream_csv_rows(cursor) → Iterator[str] of CSV-encoded lines
  3. stream_jsonl_objects(cursor) → Iterator[str] of NDJSON-encoded lines

No async, no DB session state, no caller-side mutation — generators
consume a cursor passed in and yield bytes for FastAPI's
StreamingResponse to chunk to the client.
"""
from typing import Iterator

from backend.exports.models import ExportFilters


# Canonical CSV column order. The header row, the data rows, and the
# downstream consumers all rely on this exact tuple. Stays in sync
# with the SELECT in build_query — adding a column means editing both.
CSV_COLUMNS: tuple[str, ...] = (
    "document_id",
    "doc_sayi",
    "doc_tarih",
    "doc_konu",
    "last_editor_user_id",
    "last_editor_username",
    "last_edited_at",
    "is_completed",
    "completed_by_user_id",
    "completed_by_username",
    "edit_count",
    "unique_users_count",
    "ref_seq",
    "ref_kanun_no",
    "ref_kanun_ad",
    "ref_madde",
    "ref_fikra",
    "ref_bent",
    "ref_source_text",
)


_BASE_SELECT = """
SELECT d.document_id  AS document_id,
       d.sayi         AS doc_sayi,
       d.tarih        AS doc_tarih,
       d.konu         AS doc_konu,
       a.last_editor_user_id,
       ue.username    AS last_editor_username,
       a.updated_at   AS last_edited_at,
       a.is_completed,
       a.completed_by_user_id,
       uc.username    AS completed_by_username,
       a.edit_count,
       a.unique_users_count,
       ar.seq         AS ref_seq,
       ar.kanun_no, ar.kanun_ad, ar.madde, ar.fikra, ar.bent, ar.source_text
FROM annotations a
JOIN documents_meta d           ON a.document_id = d.document_id
LEFT JOIN users ue              ON a.last_editor_user_id = ue.id
LEFT JOIN users uc              ON a.completed_by_user_id = uc.id
LEFT JOIN annotation_references ar ON ar.document_id = a.document_id
WHERE 1=1
""".strip()


def build_query(filters: ExportFilters) -> tuple[str, tuple]:
    """Build the parameterized SQL for the requested filter slice.

    Returns (sql_string, params_tuple). The cursor's caller is responsible
    for `db.execute(sql, params)` and iteration. SQL is constructed from a
    fixed _BASE_SELECT plus zero or more conditional `AND ...` clauses
    appended in deterministic order; all bound values flow through `?`
    placeholders so user input never enters the SQL string itself.
    """
    sql_parts = [_BASE_SELECT]
    params: list = []

    if filters.status == "completed":
        sql_parts.append("  AND a.is_completed = 1")

    if filters.from_date is not None:
        sql_parts.append("  AND a.updated_at >= ?")
        params.append(filters.from_date.isoformat())

    if filters.to_date is not None:
        sql_parts.append("  AND a.updated_at < date(?, '+1 day')")
        params.append(filters.to_date.isoformat())

    if filters.document_id is not None:
        sql_parts.append("  AND a.document_id = ?")
        params.append(filters.document_id)

    if filters.user_id is not None:
        sql_parts.append(
            "  AND (a.last_editor_user_id = ? OR a.completed_by_user_id = ?)"
        )
        params.append(filters.user_id)
        params.append(filters.user_id)

    sql_parts.append("ORDER BY a.document_id, ar.seq")

    return "\n".join(sql_parts), tuple(params)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_exports_service.py -v`
Expected: 8 passed.

Full suite: `.venv/bin/python -m pytest -x`
Expected: 621 passed (613 + 8 new).

- [ ] **Step 5: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/exports/service.py \
  tests/test_exports_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket14-T2): build_query SQL construction

Pure function: takes ExportFilters, returns (sql, params) for
parameterized cursor execute. Fixed _BASE_SELECT (annotations JOIN
documents_meta + LEFT JOIN annotation_references + LEFT JOIN users
twice for editor/completer attribution) followed by deterministic
conditional WHERE clauses. ORDER BY a.document_id, ar.seq makes JSONL
grouping a single-pass aggregate.

All user-supplied values flow through ? placeholders; the SQL string
contains no interpolated input.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: stream_csv_rows generator

**Files:**
- Modify: `backend/exports/service.py` (add `stream_csv_rows`)
- Modify: `tests/test_exports_service.py` (add 4 tests + a helper that builds an in-memory cursor over fake rows)

Generator that takes a SQLite cursor (or any iterable yielding row tuples in CSV_COLUMNS order minus the leading SELECT-aliased fields) and yields CSV-encoded strings: header first, then one line per row.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_exports_service.py`:

```python
# ---------------- stream_csv_rows ----------------


def _fake_row(**kwargs):
    """Helper: produces a tuple matching the SELECT column order in
    build_query. Defaults are non-empty for required fields, NULL for
    nullable ones. Override only what the test cares about."""
    defaults = {
        "document_id": "doc_42",
        "doc_sayi": 1234,
        "doc_tarih": "20260101",
        "doc_konu": "Test özelge",
        "last_editor_user_id": 42,
        "last_editor_username": "ahmet",
        "last_edited_at": "2026-04-15T10:30:00+00:00",
        "is_completed": 1,
        "completed_by_user_id": 42,
        "completed_by_username": "ahmet",
        "edit_count": 3,
        "unique_users_count": 2,
        "ref_seq": 0,
        "ref_kanun_no": "5520",
        "ref_kanun_ad": "Kurumlar Vergisi Kanunu",
        "ref_madde": "30",
        "ref_fikra": "2",
        "ref_bent": "a",
        "ref_source_text": "madde 30/2-a",
    }
    defaults.update(kwargs)
    # Match the SELECT order from _BASE_SELECT
    return (
        defaults["document_id"], defaults["doc_sayi"], defaults["doc_tarih"],
        defaults["doc_konu"], defaults["last_editor_user_id"],
        defaults["last_editor_username"], defaults["last_edited_at"],
        defaults["is_completed"], defaults["completed_by_user_id"],
        defaults["completed_by_username"], defaults["edit_count"],
        defaults["unique_users_count"], defaults["ref_seq"],
        defaults["ref_kanun_no"], defaults["ref_kanun_ad"],
        defaults["ref_madde"], defaults["ref_fikra"], defaults["ref_bent"],
        defaults["ref_source_text"],
    )


def test_stream_csv_rows_emits_header_first():
    """Header row is the FIRST yielded chunk, regardless of data presence."""
    from backend.exports.service import stream_csv_rows, CSV_COLUMNS
    chunks = list(stream_csv_rows(iter([])))  # zero data rows
    assert chunks[0].startswith(",".join(CSV_COLUMNS))
    assert chunks[0].endswith("\r\n") or chunks[0].endswith("\n")
    assert len(chunks) == 1  # only header


def test_stream_csv_rows_one_row_per_reference():
    """Two reference rows for the same document → 2 CSV data lines, all
    fields except ref_* repeated exactly."""
    from backend.exports.service import stream_csv_rows
    rows = [
        _fake_row(ref_seq=0, ref_kanun_no="5520", ref_madde="30"),
        _fake_row(ref_seq=1, ref_kanun_no="5901", ref_madde="91"),
    ]
    out = "".join(stream_csv_rows(iter(rows)))
    lines = out.strip().split("\n")
    assert len(lines) == 3  # header + 2 data
    assert "5520" in lines[1]
    assert "5901" in lines[2]
    # Same document_id + last_editor on both data rows
    assert "doc_42" in lines[1] and "doc_42" in lines[2]
    assert "ahmet" in lines[1] and "ahmet" in lines[2]


def test_stream_csv_rows_zero_reference_annotation_emits_one_row_with_nulls():
    """An annotation with no references comes back as a single row with
    LEFT JOIN producing NULL for ar.* — verify those land as empty cells,
    not the literal 'None' or 'null'."""
    from backend.exports.service import stream_csv_rows
    row = _fake_row(
        ref_seq=None, ref_kanun_no=None, ref_kanun_ad=None,
        ref_madde=None, ref_fikra=None, ref_bent=None, ref_source_text=None,
    )
    out = "".join(stream_csv_rows(iter([row])))
    lines = out.strip().split("\n")
    assert len(lines) == 2  # header + 1 row
    # Trailing fields should be empty (the row ends in a string of commas)
    assert lines[1].rstrip().endswith(",,,,,,,") or lines[1].rstrip().endswith(",,,,,,")
    assert "None" not in lines[1]
    assert "null" not in lines[1]


def test_stream_csv_rows_escapes_special_chars():
    """Source text containing quotes, commas, and newlines must be
    RFC 4180-escaped: wrapped in double quotes, embedded quotes doubled.
    Otherwise downstream Excel/pandas parsers misalign columns."""
    from backend.exports.service import stream_csv_rows
    tricky = 'has "quotes", commas, and\nnewlines'
    row = _fake_row(ref_source_text=tricky)
    out = "".join(stream_csv_rows(iter([row])))
    # The dangerous cell must be quoted with internal quotes doubled.
    assert '"has ""quotes"", commas, and\nnewlines"' in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_exports_service.py -v -k "stream_csv_rows"`
Expected: 4 FAILS with `ImportError: cannot import name 'stream_csv_rows'`.

- [ ] **Step 3: Append minimal implementation to `backend/exports/service.py`**

Add at the bottom of the file:

```python
import csv
import io


def stream_csv_rows(cursor) -> Iterator[str]:
    """Yield CSV-encoded chunks from a SQLite cursor (or any iterable of
    tuples in _BASE_SELECT column order). Header is the first chunk,
    even if cursor is empty.

    Uses a per-row io.StringIO buffer + seek/truncate so memory stays
    bounded regardless of result size.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header
    writer.writerow(CSV_COLUMNS)
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate()

    for row in cursor:
        # NULL → empty string (csv writer renders None as 'None' otherwise)
        clean = tuple("" if v is None else v for v in row)
        writer.writerow(clean)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_exports_service.py -v`
Expected: 12 passed (8 build_query + 4 csv).

Full suite: `.venv/bin/python -m pytest -x`
Expected: 625 passed.

- [ ] **Step 5: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/exports/service.py \
  tests/test_exports_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket14-T3): stream_csv_rows generator

Header always emitted as the first chunk; per-row StringIO + truncate
keeps memory constant regardless of result size. NULLs from LEFT JOINs
render as empty cells (Python csv would default to literal 'None').
RFC 4180 escaping is the stdlib csv.writer's default — quotes get
doubled, fields with embedded delimiters/newlines/quotes get wrapped.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: stream_jsonl_objects generator

**Files:**
- Modify: `backend/exports/service.py` (add `stream_jsonl_objects`)
- Modify: `tests/test_exports_service.py` (add 4 tests)

JSONL groups references by `document_id`. Because the cursor is `ORDER BY a.document_id, ar.seq`, references of the same annotation are guaranteed contiguous — single-pass grouping with no peek-ahead.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_exports_service.py`:

```python
# ---------------- stream_jsonl_objects ----------------


def test_stream_jsonl_objects_one_per_annotation():
    """Each contiguous group of cursor rows with the same document_id
    yields exactly one JSON line."""
    from backend.exports.service import stream_jsonl_objects
    import json
    rows = [
        _fake_row(document_id="doc_a", ref_seq=0, ref_kanun_no="A"),
        _fake_row(document_id="doc_a", ref_seq=1, ref_kanun_no="B"),
        _fake_row(document_id="doc_b", ref_seq=0, ref_kanun_no="C"),
    ]
    lines = list(stream_jsonl_objects(iter(rows)))
    assert len(lines) == 2
    obj_a = json.loads(lines[0])
    obj_b = json.loads(lines[1])
    assert obj_a["document_id"] == "doc_a"
    assert obj_b["document_id"] == "doc_b"


def test_stream_jsonl_objects_groups_references_per_annotation():
    """One JSON line for doc_a contains BOTH its references in order.
    The references list must be sorted by ref_seq."""
    from backend.exports.service import stream_jsonl_objects
    import json
    rows = [
        _fake_row(document_id="doc_a", ref_seq=0, ref_kanun_no="5520"),
        _fake_row(document_id="doc_a", ref_seq=1, ref_kanun_no="5901"),
    ]
    lines = list(stream_jsonl_objects(iter(rows)))
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert len(obj["references"]) == 2
    assert obj["references"][0]["kanun_no"] == "5520"
    assert obj["references"][1]["kanun_no"] == "5901"


def test_stream_jsonl_objects_empty_references_array():
    """An annotation with zero references produces a row where ref_seq
    and ref_kanun_no are NULL (LEFT JOIN miss). The JSONL must emit
    `references: []`, not omit the field and not put a single null
    entry."""
    from backend.exports.service import stream_jsonl_objects
    import json
    row = _fake_row(
        document_id="doc_a",
        ref_seq=None, ref_kanun_no=None, ref_kanun_ad=None,
        ref_madde=None, ref_fikra=None, ref_bent=None, ref_source_text=None,
    )
    lines = list(stream_jsonl_objects(iter([row])))
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["references"] == []


def test_stream_jsonl_handles_turkish_chars():
    """ensure_ascii=False so 'özelge' stays readable as 'özelge', not
    escaped to '\\u00f6zelge'. Critical for downstream readability and
    common-sense file size."""
    from backend.exports.service import stream_jsonl_objects
    row = _fake_row(doc_konu="Türkçe özelge başlık")
    lines = list(stream_jsonl_objects(iter([row])))
    assert "ö" in lines[0] and "ü" in lines[0]
    assert "\\u00" not in lines[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_exports_service.py -v -k "stream_jsonl"`
Expected: 4 FAILS with `ImportError: cannot import name 'stream_jsonl_objects'`.

- [ ] **Step 3: Append minimal implementation to `backend/exports/service.py`**

Add at the bottom of the file (after `stream_csv_rows`):

```python
import json


def stream_jsonl_objects(cursor) -> Iterator[str]:
    """Yield NDJSON-encoded annotation objects, one per line, with
    references nested as an array. Cursor MUST be ordered by
    (document_id, ref_seq) so all references of one annotation are
    contiguous; we accumulate and flush whenever document_id changes.

    Tuple field positions follow the SELECT order in _BASE_SELECT.
    """
    current_doc_id: str | None = None
    current_obj: dict | None = None

    def _flush():
        if current_obj is not None:
            return json.dumps(current_obj, ensure_ascii=False) + "\n"
        return None

    for row in cursor:
        (document_id, doc_sayi, doc_tarih, doc_konu,
         last_editor_user_id, last_editor_username, last_edited_at,
         is_completed, completed_by_user_id, completed_by_username,
         edit_count, unique_users_count,
         ref_seq, ref_kanun_no, ref_kanun_ad,
         ref_madde, ref_fikra, ref_bent, ref_source_text) = row

        if document_id != current_doc_id:
            chunk = _flush()
            if chunk is not None:
                yield chunk
            current_doc_id = document_id
            current_obj = {
                "document_id": document_id,
                "document": {
                    "sayi": doc_sayi,
                    "tarih": doc_tarih,
                    "konu": doc_konu,
                },
                "annotation": {
                    "last_editor": (
                        {"id": last_editor_user_id, "username": last_editor_username}
                        if last_editor_user_id is not None else None
                    ),
                    "last_edited_at": last_edited_at,
                    "is_completed": bool(is_completed),
                    "completed_by": (
                        {"id": completed_by_user_id, "username": completed_by_username}
                        if completed_by_user_id is not None else None
                    ),
                    "edit_count": edit_count,
                    "unique_users_count": unique_users_count,
                },
                "references": [],
            }

        # Reference is present iff the LEFT JOIN found a row.
        if ref_seq is not None:
            current_obj["references"].append({
                "seq": ref_seq,
                "kanun_no": ref_kanun_no,
                "kanun_ad": ref_kanun_ad,
                "madde": ref_madde,
                "fikra": ref_fikra,
                "bent": ref_bent,
                "source_text": ref_source_text,
            })

    chunk = _flush()
    if chunk is not None:
        yield chunk
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_exports_service.py -v`
Expected: 16 passed (8 + 4 + 4).

Full suite: `.venv/bin/python -m pytest -x`
Expected: 629 passed.

- [ ] **Step 5: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/exports/service.py \
  tests/test_exports_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket14-T4): stream_jsonl_objects generator

Single-pass grouping by document_id. Cursor must come pre-sorted by
(document_id, ref_seq) per build_query's ORDER BY; we accumulate
references into the current object and flush when document_id
changes. Zero-reference annotations correctly emit an empty
references array via the LEFT JOIN ref_seq IS NULL branch.

ensure_ascii=False keeps Turkish chars readable in the output —
'özelge' stays as 'özelge', not '\\u00f6zelge'. is_completed is
coerced to a Python bool so the JSON renders as true/false rather
than 1/0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: routes + main.py wire-up + audit + smoke + tag

**Files:**
- Create: `backend/exports/routes.py`
- Modify: `backend/main.py` (2 small edits)
- Test: `tests/test_exports_routes.py` (9 tests)

The HTTP layer is thin: validate filters via Pydantic, open a connection, execute the query, hand the cursor to the appropriate generator, return a `StreamingResponse` with `BackgroundTasks` for the audit row.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_exports_routes.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_exports_routes.py -v`
Expected: 9 FAILS — endpoint not registered (404 across the board) and import errors.

- [ ] **Step 3: Create the route module**

Create `backend/exports/routes.py`:

```python
"""Admin HTTP endpoint for streaming the annotation dataset export."""
import logging
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse

from backend.exports.models import ExportFilters
from backend.exports.service import (
    build_query, stream_csv_rows, stream_jsonl_objects,
)
from backend.shared import audit
from backend.users.deps import get_db, require_admin


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/export", tags=["admin-export"])


def _utc_filename_stamp() -> str:
    """YYYYMMDD-HHMM in UTC; matches backup snapshot naming convention."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")


def _filters_for_audit(filters: ExportFilters) -> dict:
    """Render filters as a JSON-serializable dict for admin_audit_log."""
    return {
        "format": filters.format,
        "status": filters.status,
        "from_date": filters.from_date.isoformat() if filters.from_date else None,
        "to_date": filters.to_date.isoformat() if filters.to_date else None,
        "document_id": filters.document_id,
        "user_id": filters.user_id,
    }


@router.get("")
def admin_export_dataset(
    background: BackgroundTasks,
    filters: ExportFilters = Depends(),
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Stream the annotation dataset matching `filters` as CSV or JSONL.

    The cursor is consumed lazily by the generator passed to
    StreamingResponse; memory stays constant at ~MB regardless of result
    size. The audit row is written by a background task that fires after
    the response stream closes — operator-visible failures (incomplete
    download) correspond to absent audit rows.
    """
    sql, params = build_query(filters)
    cursor = db.execute(sql, params)

    # Counter is mutable so the background task can read the post-stream value.
    counter = [0]

    if filters.format == "csv":
        def _counted_csv():
            for chunk in stream_csv_rows(_count_rows(cursor, counter)):
                yield chunk
        media_type = "text/csv; charset=utf-8"
        ext = "csv"
        body_iter = _counted_csv()
    else:  # jsonl
        def _counted_jsonl():
            for chunk in stream_jsonl_objects(_count_rows(cursor, counter)):
                counter[0] += 1  # one annotation flushed per chunk
                yield chunk
        media_type = "application/x-ndjson; charset=utf-8"
        ext = "jsonl"
        body_iter = _counted_jsonl()

    filename = f"annotations-export-{_utc_filename_stamp()}.{ext}"

    def _record_audit():
        try:
            audit.log_admin_action(
                db, admin_user_id=admin["id"], action_type="export_dataset",
                target_kind="export", target_id=filename,
                metadata={
                    "format": filters.format,
                    "filters": _filters_for_audit(filters),
                    "exported_count": counter[0],
                },
            )
        except Exception:
            log.exception("audit export_dataset failed")

    background.add_task(_record_audit)

    return StreamingResponse(
        body_iter,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        background=background,
    )


def _count_rows(cursor, counter: list[int]):
    """Wrap a cursor so iteration increments `counter[0]`. The CSV path
    counts every cursor row (each = one CSV data line). The JSONL path
    counts annotation flushes separately because cursor rows are
    references, multiple per annotation."""
    for row in cursor:
        counter[0] += 1
        yield row
```

Note: the JSONL path's `counter[0] += 1` after each chunk replaces the row-level count from `_count_rows`. We accept slight bookkeeping duplication to keep both formats counting the right thing — for CSV the unit is row, for JSONL it's annotation. The tests only assert "exported_count" key exists, not the exact value, so the counter definition is internal to this paket.

Actually that double-counting is wrong — the wrapper `_count_rows` is INCREMENTING for every cursor row even in JSONL, which would over-count. Fix: in the JSONL branch, do NOT use `_count_rows`; iterate the cursor directly inside the generator and bump the counter on flush:

```python
    if filters.format == "csv":
        def _counted_csv():
            for chunk in stream_csv_rows(_count_rows(cursor, counter)):
                yield chunk
        media_type = "text/csv; charset=utf-8"
        ext = "csv"
        body_iter = _counted_csv()
    else:  # jsonl
        # JSONL counts annotations (= unique document_ids), not cursor rows.
        # We track previous document_id ourselves inside the wrapper.
        def _count_annotations(cursor_inner):
            seen = None
            for row in cursor_inner:
                doc_id = row[0]
                if doc_id != seen:
                    counter[0] += 1
                    seen = doc_id
                yield row
        body_iter = stream_jsonl_objects(_count_annotations(cursor))
        media_type = "application/x-ndjson; charset=utf-8"
        ext = "jsonl"
```

Use this corrected version when implementing — the comment in the docstring above explains the contract.

- [ ] **Step 4: Wire the router into the app**

Modify `backend/main.py`. Find the existing import block at the top:

```python
from backend.locks import sweep as locks_sweep
from backend.backup import loop as backup_loop
from backend.retention import loop as retention_loop
```

These imports already exist after Paket 13. NO new top-level import needed for the router right now — we'll mount it inline next to the other `app.include_router(...)` calls.

Find the `app.include_router(...)` block (search for `include_router` in `backend/main.py`). After the existing retention router include, add:

```python
from backend.exports.routes import router as exports_router
app.include_router(exports_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_exports_routes.py -v`
Expected: 9 passed.

Full suite: `.venv/bin/python -m pytest -x`
Expected: 638 passed (629 + 9 new).

- [ ] **Step 6: End-to-end smoke test against live server (encouraged)**

Stop any running server first:
```bash
lsof -ti:8000 | xargs -r kill 2>/dev/null
sleep 1
```

Start the dev server:
```bash
DATA_DIR=$(pwd)/deneme-dev/data .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
sleep 2
```

Login as admin:
```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"adminpass123"}' \
  -c /tmp/deneme-cookies.txt -b /tmp/deneme-cookies.txt
```

CSV export:
```bash
curl -s -b /tmp/deneme-cookies.txt 'http://127.0.0.1:8000/api/admin/export?format=csv&status=all' | head -5
```
Expected: header line + 0 or more data rows. Header column 1 = `document_id`.

JSONL export:
```bash
curl -s -b /tmp/deneme-cookies.txt 'http://127.0.0.1:8000/api/admin/export?format=jsonl&status=all' | head -3
```
Expected: 0 or more JSON objects, one per line. (Empty if dev DB has no annotations.)

Audit verification:
```bash
.venv/bin/python -c "
import sqlite3
db = sqlite3.connect('deneme-dev/data/db/annotations.db')
db.row_factory = sqlite3.Row
for r in db.execute(
    \"SELECT id, action_type, target_id, metadata_json, created_at \"
    \"FROM admin_audit_log WHERE action_type='export_dataset' \"
    \"ORDER BY id DESC LIMIT 3\"
):
    print(dict(r))
"
```
Expected: 1-2 audit rows from the smoke calls above.

Tear down:
```bash
lsof -ti:8000 | xargs -r kill 2>/dev/null
```

If the smoke reveals a real issue, surface it via DONE_WITH_CONCERNS.

- [ ] **Step 7: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/exports/routes.py \
  backend/main.py \
  tests/test_exports_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket14-T5): admin export endpoint with streaming + audit

GET /api/admin/export?format=csv|jsonl&... uses Pydantic ExportFilters
for query-param validation, build_query for parameterized SQL, the
appropriate generator for body streaming, and FastAPI's
BackgroundTasks for the post-stream admin_audit_log row.

CSV path counts cursor rows (= reference rows); JSONL path counts
unique document_ids (= annotation flushes). exported_count in audit
metadata reflects the format-appropriate count.

Filename annotations-export-<UTC YYYYMMDD-HHMM>.<ext> matches backup
snapshot naming convention.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 8: Tag the paket**

```bash
git tag paket-14-export HEAD
git tag -l "paket-14-*" --format="%(refname:short)  %(objectname:short)  %(subject)"
```

Expected:
```
paket-14-export  <new sha>  feat(paket14-T5): admin export endpoint with streaming + audit
```

---

## Self-Review Checklist (run after writing the plan, fix inline)

✅ **Spec coverage:**
- D1 (ML/stakeholder handoff scope) — single endpoint, dataset-only. No multi-table dump, no per-user variant. ✓
- D2 (single endpoint `GET /api/admin/export?format=...`) — Task 5. ✓
- D3 (streaming, no disk archive) — `StreamingResponse` in T5, no writes to `EXPORTS_DIR`. ✓
- D4 (CSV + JSONL formats) — T3 + T4 generators. ✓
- D5 (filter params: status/from_date/to_date/document_id/user_id) — T1 Pydantic, T2 build_query. ✓
- D6 (username + user_id visible) — included in CSV_COLUMNS and JSONL annotation block. ✓
- D7 (require_admin, 404 existence-hide) — T5 routes, asserted in `test_export_admin_only`. ✓
- D8 (no fine-grained role split) — single require_admin. ✓
- D9 (admin_audit_log only, no system_events) — T5 BackgroundTasks. ✓
- Schema reality (annotations PK'd on document_id, is_completed boolean, refs joined via document_id) — T2 SQL template, all generators use the corrected layout. ✓

✅ **Placeholder scan:**
- No "TBD", "TODO", "fill in" in any task.
- The `_count_rows` / JSONL counter discussion in T5 explicitly shows the corrected version.

✅ **Type consistency:**
- `CSV_COLUMNS` defined in T2, used by T3 generator + T5 routes — same constant.
- `ExportFilters` field names match across T1 (definition), T2 (`filters.from_date.isoformat()` etc.), T5 (`filters.format`). ✓
- `build_query` signature `(filters) -> (sql, params)` consistent across T2, T5. ✓
- Generator signature `Iterator[str]` consistent T3, T4, T5. ✓
- `audit.log_admin_action` kwargs match the call site in `backend/backup/routes.py` and `backend/retention/routes.py` (action_type, target_kind, target_id, metadata). ✓

✅ **Test counts:**
- T1: 5 tests (models)
- T2: 8 tests (build_query)
- T3: 4 tests (CSV generator)
- T4: 4 tests (JSONL generator)
- T5: 9 tests (routes)
- **Total: 30 new tests.** Suite size 608 → 638.

✅ **No backward-compatibility shims, no feature flags, no scope creep.** No migration. No new third-party deps.

✅ **Frequent commits:** 5 commits (one per task), atomic, paket-tagged messages. Plus the final tag.
