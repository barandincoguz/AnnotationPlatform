# Paket 6 — 3-Tab Shuffle Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /api/feed?tab=review|new|verified&limit=N&offset=N` endpoint'i — bursiyere annotation status'üne göre filtrelenmiş, deterministik-shuffled doküman listesi sunar. Backend Paket 5'te tamamlanan annotations + documents tablolarını okur ve sol kolonda (Paket 16'da render edilecek) virtual-scroll için yeterince zengin bir summary döndürür.

**Architecture:** Yeni `backend/shuffle/` modülü — `service.py` üç sekme query'si (new/review/verified) + per-(user, tab, gün) deterministik shuffle, `routes.py` HTTP yüzeyi (`require_passed_training` gating). Document summary, `documents_meta` + `annotations` LEFT JOIN üzerinden tek query'de toplanır. Cross-modül erişim ihlalini önlemek için her tab kendi query helper'ında.

**Tech Stack:** FastAPI, SQLite (LEFT JOIN), Python `random.Random(seed)` ile reproducible shuffle, Pydantic v2.

---

## Mimari Kararlar (Locked)

- **Sekme tanımları (her query'nin SQL kuralı):**
  - `new` → `annotations` row YOK (LEFT JOIN'da NULL)
  - `review` → `annotations` row var VE `is_completed=0`
  - `verified` → `annotations` row var VE `is_completed=1`
- **Shuffle deterministik:** `seed = (user_id, tab, current_date_iso)` — aynı kullanıcı gün boyunca aynı sırayı görür, gün dönünce yeniden karışır. Pagination tutarlılığı bu sayede.
- **Tarih bazı:** UTC takvim günü. `random.Random(f"{user_id}|{tab}|{YYYY-MM-DD}")` deterministic.
- **Pagination:** `limit` default 50 (max 200), `offset` default 0. Total count ayrıca döndürülür (frontend infinite scroll bir sonraki batch'i biliyor mu bilmek için).
- **Item shape (FeedItem):** `document_id, sayi, tarih, konu, vergi_turu, estimated_difficulty, word_count, has_annotation, is_completed, last_editor_user_id, last_editor_username, edit_count, unique_users_count, updated_at` — `pdf_text` ASLA dönmez (UI orta kolonda zaten `GET /api/documents/{id}` ile alır).
- **Auth gating:** `require_passed_training` (Paket 2/5 desenine uyum).
- **Sıralama (shuffle öncesi base order):**
  - new: `documents_meta.created_at DESC, document_id ASC` (en yeni doc'lar önce)
  - review: `annotations.updated_at DESC, document_id ASC` (en son aktivite önce)
  - verified: `annotations.updated_at DESC, document_id ASC`
  - Shuffle bu base order üstüne uygulanır — yani tab içinde shuffle ama tab'ler birbirinden bağımsız.
- **Empty list legitimate:** Her tab boş olabilir (özellikle ilk gün — review/verified 0). Endpoint 200 + `{items: [], total: 0}` döndürür.
- **`unique_users_count` performance**: Annotation tablosunda zaten denormalize, ek query gerek yok.
- **No FK to users**: `last_editor_user_id` NULL olabilir (deleted user — `ON DELETE SET NULL`). `last_editor_username` LEFT JOIN ile bulunur, NULL olabilir.
- **Bu paket SSE event yaymaz:** Paket 7 (annotation_save broadcast) feed'i otomatik refresh ettirecek frontend tarafında. Backend pasif read-only.

## Dosya Yapısı

```
backend/shuffle/
├── __init__.py            # boş
├── service.py             # 3 query helper + deterministic_shuffle + list_feed
├── models.py              # Pydantic FeedItem, FeedResponse
└── routes.py              # GET /api/feed

backend/main.py            # MODIFIED: shuffle_router mount

tests/
├── test_shuffle_service.py    # query correctness + shuffle determinism
├── test_shuffle_routes.py     # HTTP-level tests (auth, pagination, tabs)
└── (no E2E — Paket 5 E2E + route tests cover the integration sufficiently)
```

---

## Task 1: Shuffle Service (TDD)

**Goal:** `list_feed(db, *, user_id, tab, limit, offset) -> dict` — query'ler + deterministic shuffle. Pure DB layer, no HTTP.

**Files:**
- Create: `backend/shuffle/__init__.py`
- Create: `backend/shuffle/service.py`
- Create: `tests/test_shuffle_service.py`

- [ ] **Step 1: Create empty package**

Run:
```bash
mkdir -p /Users/barandincoguz/Desktop/deneme/backend/shuffle
touch /Users/barandincoguz/Desktop/deneme/backend/shuffle/__init__.py
```

- [ ] **Step 2: Write `tests/test_shuffle_service.py`**

```python
import json
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.documents import service as doc_service
from backend.annotations import service as ann_service
from backend.shuffle import service as shuffle_service


@pytest.fixture
def db(db_path, tmp_path):
    """DB with 2 users + 5 ingested documents."""
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) "
        "VALUES ('alice','x','user',?,?), ('bob','x','user',?,?)",
        (now, now, now, now),
    )
    for i in range(1, 6):
        sample = {
            "evrakOid": f"doc_{i}", "sayi": i, "tarih": "20260101",
            "konu": f"Konu {i}", "vergiTuru": "Gelir Vergisi",
            "pdfText": "x" * 100,
            "kanunBilgileri": [], "bkkTebligSirkuBilgileri": [],
        }
        fpath = tmp_path / f"doc_{i}.json"
        fpath.write_text(json.dumps(sample))
        doc_service.ingest_file(conn, fpath)
    yield conn
    conn.close()


def _ref(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "x"}
    base.update(kwargs)
    return base


# === Tab classification ===

def test_new_tab_returns_unannotated_docs(db):
    """All 5 docs unannotated → all in 'new' tab."""
    result = shuffle_service.list_feed(db, user_id=1, tab="new", limit=50, offset=0)
    assert result["total"] == 5
    assert len(result["items"]) == 5
    assert all(item["has_annotation"] is False for item in result["items"])


def test_new_tab_excludes_annotated_docs(db):
    """After alice annotates doc_1, only 4 docs remain in 'new'."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[_ref(source_text="x")])
    result = shuffle_service.list_feed(db, user_id=1, tab="new", limit=50, offset=0)
    assert result["total"] == 4
    doc_ids = {item["document_id"] for item in result["items"]}
    assert "doc_1" not in doc_ids


def test_review_tab_includes_uncompleted_annotations(db):
    """An annotated, not-yet-completed doc shows up in 'review'."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[_ref(source_text="x")])
    result = shuffle_service.list_feed(db, user_id=1, tab="review", limit=50, offset=0)
    assert result["total"] == 1
    item = result["items"][0]
    assert item["document_id"] == "doc_1"
    assert item["has_annotation"] is True
    assert item["is_completed"] is False
    assert item["last_editor_user_id"] == 1
    assert item["last_editor_username"] == "alice"
    assert item["edit_count"] == 1
    assert item["unique_users_count"] == 1


def test_review_tab_excludes_completed_docs(db):
    """A completed doc is NOT in 'review' (it moves to 'verified')."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)
    result = shuffle_service.list_feed(db, user_id=1, tab="review", limit=50, offset=0)
    assert result["total"] == 0


def test_verified_tab_includes_completed_only(db):
    """Only completed docs appear in 'verified' regardless of who completed them."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)
    ann_service.save_annotation(db, document_id="doc_2", user_id=2, references=[])
    # doc_2 not completed
    result = shuffle_service.list_feed(db, user_id=1, tab="verified", limit=50, offset=0)
    assert result["total"] == 1
    assert result["items"][0]["document_id"] == "doc_1"
    assert result["items"][0]["is_completed"] is True


def test_tabs_are_mutually_exclusive(db):
    """Each doc belongs to exactly one tab at any time."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)
    ann_service.save_annotation(db, document_id="doc_2", user_id=2, references=[])

    new = shuffle_service.list_feed(db, user_id=1, tab="new", limit=50, offset=0)
    review = shuffle_service.list_feed(db, user_id=1, tab="review", limit=50, offset=0)
    verified = shuffle_service.list_feed(db, user_id=1, tab="verified", limit=50, offset=0)

    new_ids = {i["document_id"] for i in new["items"]}
    review_ids = {i["document_id"] for i in review["items"]}
    verified_ids = {i["document_id"] for i in verified["items"]}

    assert new_ids.isdisjoint(review_ids)
    assert new_ids.isdisjoint(verified_ids)
    assert review_ids.isdisjoint(verified_ids)
    assert len(new_ids) + len(review_ids) + len(verified_ids) == 5


def test_unknown_tab_raises(db):
    with pytest.raises(shuffle_service.InvalidTab):
        shuffle_service.list_feed(db, user_id=1, tab="bogus", limit=50, offset=0)


# === Determinism ===

def test_shuffle_is_deterministic_per_user_per_day(db):
    """Same user + tab + day → same order across calls."""
    a = shuffle_service.list_feed(db, user_id=1, tab="new", limit=50, offset=0)
    b = shuffle_service.list_feed(db, user_id=1, tab="new", limit=50, offset=0)
    assert [i["document_id"] for i in a["items"]] == [i["document_id"] for i in b["items"]]


def test_shuffle_differs_across_users(db):
    """Different users see different orders (almost always — flaky for tiny lists, but 5 docs ≈ 1/120 collision)."""
    a = shuffle_service.list_feed(db, user_id=1, tab="new", limit=50, offset=0)
    b = shuffle_service.list_feed(db, user_id=2, tab="new", limit=50, offset=0)
    # With 5 items, identical permutation by chance is 1/120; over 100 runs of CI this would flake ~1x.
    # We assert a weaker invariant: the seeds differ, so the shuffle algorithm produces *some* difference for at least one of the orderings.
    # If both happen to be identical, we still want to confirm the seed string itself differs.
    assert shuffle_service._seed_str(user_id=1, tab="new") != shuffle_service._seed_str(user_id=2, tab="new")


def test_shuffle_differs_across_tabs(db):
    """Same user, different tab → different seed (orderings would differ if items overlapped)."""
    assert shuffle_service._seed_str(user_id=1, tab="new") != shuffle_service._seed_str(user_id=1, tab="review")


# === Pagination ===

def test_pagination_limits_results(db):
    """limit caps the items count; total still reflects the full count."""
    result = shuffle_service.list_feed(db, user_id=1, tab="new", limit=2, offset=0)
    assert len(result["items"]) == 2
    assert result["total"] == 5


def test_pagination_offset_skips(db):
    """offset advances the page; total still reflects the full count."""
    page1 = shuffle_service.list_feed(db, user_id=1, tab="new", limit=2, offset=0)
    page2 = shuffle_service.list_feed(db, user_id=1, tab="new", limit=2, offset=2)
    page1_ids = {i["document_id"] for i in page1["items"]}
    page2_ids = {i["document_id"] for i in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert page1["total"] == page2["total"] == 5


def test_pagination_offset_past_end_returns_empty(db):
    result = shuffle_service.list_feed(db, user_id=1, tab="new", limit=10, offset=99)
    assert result["items"] == []
    assert result["total"] == 5


def test_pagination_caps_limit_to_max(db):
    """limit >200 is capped at 200 (defensive — 18K row guard)."""
    result = shuffle_service.list_feed(db, user_id=1, tab="new", limit=10000, offset=0)
    # we only have 5 docs in this test, but the call must not raise
    assert len(result["items"]) == 5


def test_negative_limit_or_offset_raises(db):
    with pytest.raises(ValueError):
        shuffle_service.list_feed(db, user_id=1, tab="new", limit=-1, offset=0)
    with pytest.raises(ValueError):
        shuffle_service.list_feed(db, user_id=1, tab="new", limit=10, offset=-1)


# === Item shape ===

def test_item_does_not_include_pdf_text(db):
    """pdf_text never leaks via feed — frontend uses GET /api/documents/{id}."""
    items = shuffle_service.list_feed(db, user_id=1, tab="new", limit=50, offset=0)["items"]
    for item in items:
        assert "pdf_text" not in item


def test_item_shape_for_new_tab(db):
    """New-tab items expose document metadata only — no chain fields populated."""
    items = shuffle_service.list_feed(db, user_id=1, tab="new", limit=50, offset=0)["items"]
    item = items[0]
    expected_keys = {
        "document_id", "sayi", "tarih", "konu", "vergi_turu",
        "estimated_difficulty", "word_count", "has_annotation",
        "is_completed", "last_editor_user_id", "last_editor_username",
        "edit_count", "unique_users_count", "updated_at",
    }
    assert set(item.keys()) == expected_keys
    assert item["has_annotation"] is False
    assert item["is_completed"] is False
    assert item["last_editor_user_id"] is None
    assert item["last_editor_username"] is None
    assert item["edit_count"] == 0
    assert item["unique_users_count"] == 0
    assert item["updated_at"] is None
```

- [ ] **Step 3: Run failing tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_shuffle_service.py -q
```
Expected: ImportError — module not yet defined.

- [ ] **Step 4: Implement `backend/shuffle/service.py`**

```python
"""3-tab shuffle feed service.

Public API:
  list_feed(db, *, user_id, tab, limit, offset) -> dict

Returns:
  {"items": list[FeedItem], "total": int}

Tab semantics:
  new      → no annotation row exists for the document
  review   → annotation row exists AND is_completed=0
  verified → annotation row exists AND is_completed=1

Shuffle is deterministic per-(user_id, tab, UTC date) so:
  - The same user gets the same order all day → pagination is stable.
  - The order rotates daily.
  - Different users see different orders.

The feed item is a flat denormalized record optimized for the left-column
list. pdf_text is intentionally excluded — frontend reads full doc content
via GET /api/documents/{id}.
"""
import random
import sqlite3
from datetime import datetime, timezone
from typing import Iterable


VALID_TABS = ("new", "review", "verified")
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class ShuffleServiceError(Exception):
    pass


class InvalidTab(ShuffleServiceError):
    pass


def _seed_str(*, user_id: int, tab: str) -> str:
    """Public helper (also used by tests) — UTC date-based per-day rotation."""
    today = datetime.now(timezone.utc).date().isoformat()
    return f"{user_id}|{tab}|{today}"


def _shuffle(items: list[dict], *, user_id: int, tab: str) -> list[dict]:
    """Deterministic shuffle in place; returns the same list."""
    rng = random.Random(_seed_str(user_id=user_id, tab=tab))
    rng.shuffle(items)
    return items


_NEW_QUERY = """
SELECT
    d.document_id, d.sayi, d.tarih, d.konu, d.vergi_turu,
    d.estimated_difficulty, d.word_count
FROM documents_meta d
LEFT JOIN annotations a ON a.document_id = d.document_id
WHERE a.document_id IS NULL
ORDER BY d.created_at DESC, d.document_id ASC
"""

_REVIEW_QUERY = """
SELECT
    d.document_id, d.sayi, d.tarih, d.konu, d.vergi_turu,
    d.estimated_difficulty, d.word_count,
    a.is_completed, a.last_editor_user_id, u.username AS last_editor_username,
    a.edit_count, a.unique_users_count, a.updated_at
FROM documents_meta d
INNER JOIN annotations a ON a.document_id = d.document_id
LEFT JOIN users u ON u.id = a.last_editor_user_id
WHERE a.is_completed = 0
ORDER BY a.updated_at DESC, d.document_id ASC
"""

_VERIFIED_QUERY = """
SELECT
    d.document_id, d.sayi, d.tarih, d.konu, d.vergi_turu,
    d.estimated_difficulty, d.word_count,
    a.is_completed, a.last_editor_user_id, u.username AS last_editor_username,
    a.edit_count, a.unique_users_count, a.updated_at
FROM documents_meta d
INNER JOIN annotations a ON a.document_id = d.document_id
LEFT JOIN users u ON u.id = a.last_editor_user_id
WHERE a.is_completed = 1
ORDER BY a.updated_at DESC, d.document_id ASC
"""


def _empty_chain_fields() -> dict:
    return {
        "has_annotation": False,
        "is_completed": False,
        "last_editor_user_id": None,
        "last_editor_username": None,
        "edit_count": 0,
        "unique_users_count": 0,
        "updated_at": None,
    }


def _row_to_item_new(row: sqlite3.Row) -> dict:
    return {
        "document_id": row["document_id"],
        "sayi": row["sayi"],
        "tarih": row["tarih"],
        "konu": row["konu"],
        "vergi_turu": row["vergi_turu"],
        "estimated_difficulty": row["estimated_difficulty"],
        "word_count": row["word_count"],
        **_empty_chain_fields(),
    }


def _row_to_item_chain(row: sqlite3.Row) -> dict:
    return {
        "document_id": row["document_id"],
        "sayi": row["sayi"],
        "tarih": row["tarih"],
        "konu": row["konu"],
        "vergi_turu": row["vergi_turu"],
        "estimated_difficulty": row["estimated_difficulty"],
        "word_count": row["word_count"],
        "has_annotation": True,
        "is_completed": bool(row["is_completed"]),
        "last_editor_user_id": row["last_editor_user_id"],
        "last_editor_username": row["last_editor_username"],
        "edit_count": row["edit_count"],
        "unique_users_count": row["unique_users_count"],
        "updated_at": row["updated_at"],
    }


def list_feed(
    db: sqlite3.Connection,
    *,
    user_id: int,
    tab: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    """Return paginated, deterministically-shuffled feed items for a tab.

    Raises InvalidTab on unknown tab; ValueError on negative limit/offset.
    """
    if tab not in VALID_TABS:
        raise InvalidTab(f"unknown tab: {tab!r} (valid: {VALID_TABS})")
    if limit < 0:
        raise ValueError("limit must be >= 0")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    limit = min(limit, MAX_LIMIT)

    if tab == "new":
        rows = db.execute(_NEW_QUERY).fetchall()
        items = [_row_to_item_new(r) for r in rows]
    elif tab == "review":
        rows = db.execute(_REVIEW_QUERY).fetchall()
        items = [_row_to_item_chain(r) for r in rows]
    else:  # verified
        rows = db.execute(_VERIFIED_QUERY).fetchall()
        items = [_row_to_item_chain(r) for r in rows]

    total = len(items)
    items = _shuffle(items, user_id=user_id, tab=tab)
    page = items[offset : offset + limit]
    return {"items": page, "total": total}
```

- [ ] **Step 5: Run tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_shuffle_service.py -q
```
Expected: all pass.

- [ ] **Step 6: Run full suite**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest -q
```
Expected: 0 failed (current count is 229 from end of Paket 5; expect ~245 after).

- [ ] **Step 7: Commit**

```bash
cd /Users/barandincoguz/Desktop/deneme && git -c user.email=maarkval@icloud.com -c user.name=baran add backend/shuffle tests/test_shuffle_service.py && git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(shuffle): add 3-tab feed service (new/review/verified)

Pure DB layer that classifies documents into three mutually-exclusive
tabs:
  new      → no annotation row
  review   → annotation exists, is_completed=0
  verified → annotation exists, is_completed=1

Per-(user_id, tab, UTC date) deterministic shuffle keeps pagination
stable for the day, rotates daily, differs across users. Single LEFT/
INNER JOIN per query; pdf_text never returned. Pagination clamps limit
to MAX_LIMIT=200.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Models + HTTP Routes

**Goal:** `GET /api/feed?tab=...&limit=N&offset=N` endpoint exposing the service. Pydantic v2 models for OpenAPI completeness.

**Files:**
- Create: `backend/shuffle/models.py`
- Create: `backend/shuffle/routes.py`
- Modify: `backend/main.py` (mount router)
- Create: `tests/test_shuffle_routes.py`

- [ ] **Step 1: Write `backend/shuffle/models.py`**

```python
"""Pydantic response models for the shuffle feed."""
from typing import Optional
from pydantic import BaseModel


class FeedItem(BaseModel):
    document_id: str
    sayi: Optional[int]
    tarih: Optional[str]
    konu: Optional[str]
    vergi_turu: Optional[str]
    estimated_difficulty: str
    word_count: int

    has_annotation: bool
    is_completed: bool
    last_editor_user_id: Optional[int]
    last_editor_username: Optional[str]
    edit_count: int
    unique_users_count: int
    updated_at: Optional[str]


class FeedResponse(BaseModel):
    items: list[FeedItem]
    total: int
```

- [ ] **Step 2: Write `backend/shuffle/routes.py`**

```python
"""3-tab shuffle feed HTTP endpoint. Auth: require_passed_training."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.shuffle import service
from backend.shuffle.models import FeedResponse
from backend.users.deps import get_db, require_passed_training


router = APIRouter(prefix="/api", tags=["shuffle"])


@router.get("/feed", response_model=FeedResponse)
def get_feed(
    tab: str = Query(..., pattern="^(new|review|verified)$"),
    limit: int = Query(service.DEFAULT_LIMIT, ge=0, le=service.MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        return service.list_feed(
            db, user_id=user["id"], tab=tab, limit=limit, offset=offset,
        )
    except service.InvalidTab as e:
        # FastAPI's pattern Query already rejects unknown tab → 422 before this runs.
        # Defensive — we surface 400 if the validation is bypassed somehow.
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 3: Mount router in `backend/main.py`**

After the existing `from backend.locks.routes import router as locks_router` line, add:

```python
from backend.shuffle.routes import router as shuffle_router
```

After the existing `app.include_router(locks_router)` line, add:

```python
app.include_router(shuffle_router)
```

- [ ] **Step 4: Write `tests/test_shuffle_routes.py`**

```python
import json


def test_feed_requires_auth(client):
    r = client.get("/api/feed?tab=new")
    assert r.status_code == 401


def test_feed_new_tab_returns_unannotated(passed_user, ingest_doc):
    ingest_doc("doc_a")
    ingest_doc("doc_b")
    r = passed_user["client"].get("/api/feed?tab=new")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    doc_ids = {i["document_id"] for i in body["items"]}
    assert doc_ids == {"doc_a", "doc_b"}
    assert all(i["has_annotation"] is False for i in body["items"])


def test_feed_review_tab_includes_uncompleted(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("doc_test")
    c.post("/api/annotations", json={"document_id": "doc_test", "references": []})

    r = c.get("/api/feed?tab=review")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["document_id"] == "doc_test"
    assert item["has_annotation"] is True
    assert item["is_completed"] is False
    assert item["last_editor_username"] == "alice"


def test_feed_verified_tab_includes_completed(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("doc_test")
    c.post("/api/annotations", json={"document_id": "doc_test", "references": []})
    c.post("/api/annotations/doc_test/complete", json={"completed": True})

    r = c.get("/api/feed?tab=verified")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["is_completed"] is True


def test_feed_invalid_tab_returns_422(passed_user):
    r = passed_user["client"].get("/api/feed?tab=bogus")
    assert r.status_code == 422  # FastAPI Query pattern rejects


def test_feed_pagination(passed_user, ingest_doc):
    """Page through 5 unannotated docs in 2-item batches."""
    for i in range(1, 6):
        ingest_doc(f"doc_p{i}")

    page1 = passed_user["client"].get("/api/feed?tab=new&limit=2&offset=0").json()
    page2 = passed_user["client"].get("/api/feed?tab=new&limit=2&offset=2").json()
    page3 = passed_user["client"].get("/api/feed?tab=new&limit=2&offset=4").json()

    all_ids = {i["document_id"] for page in (page1, page2, page3) for i in page["items"]}
    assert all_ids == {f"doc_p{i}" for i in range(1, 6)}
    assert page1["total"] == page2["total"] == page3["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert len(page3["items"]) == 1


def test_feed_pagination_stable_within_session(passed_user, ingest_doc):
    """Same user, same tab, same day → identical ordering across calls."""
    for i in range(1, 11):
        ingest_doc(f"doc_s{i}")

    a = passed_user["client"].get("/api/feed?tab=new&limit=10&offset=0").json()
    b = passed_user["client"].get("/api/feed?tab=new&limit=10&offset=0").json()
    assert [i["document_id"] for i in a["items"]] == [i["document_id"] for i in b["items"]]


def test_feed_default_limit_is_50(passed_user, ingest_doc):
    """No limit param → uses DEFAULT_LIMIT=50; 5 docs all returned."""
    for i in range(1, 6):
        ingest_doc(f"doc_d{i}")
    r = passed_user["client"].get("/api/feed?tab=new").json()
    assert len(r["items"]) == 5
    assert r["total"] == 5


def test_feed_limit_negative_returns_422(passed_user):
    r = passed_user["client"].get("/api/feed?tab=new&limit=-1")
    assert r.status_code == 422


def test_feed_limit_too_large_returns_422(passed_user):
    """limit > MAX_LIMIT (200) → 422 (FastAPI Query enforces le=200)."""
    r = passed_user["client"].get("/api/feed?tab=new&limit=10000")
    assert r.status_code == 422


def test_feed_empty_when_no_docs(passed_user):
    """No documents ingested → all tabs return empty list, total 0."""
    for tab in ("new", "review", "verified"):
        r = passed_user["client"].get(f"/api/feed?tab={tab}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["items"] == []
        assert body["total"] == 0


def test_feed_tabs_mutually_exclusive_via_http(second_passed_user, ingest_doc):
    """Doc 1 unannotated → new; Doc 2 annotated → review; Doc 3 completed → verified."""
    ctx = second_passed_user
    c = ctx["client"]
    for i in range(1, 4):
        ingest_doc(f"doc_x{i}")

    ctx["login"]("alice")
    c.post("/api/annotations", json={"document_id": "doc_x2", "references": []})
    c.post("/api/annotations", json={"document_id": "doc_x3", "references": []})
    c.post("/api/annotations/doc_x3/complete", json={"completed": True})

    new_ids = {i["document_id"] for i in c.get("/api/feed?tab=new").json()["items"]}
    review_ids = {i["document_id"] for i in c.get("/api/feed?tab=review").json()["items"]}
    verified_ids = {i["document_id"] for i in c.get("/api/feed?tab=verified").json()["items"]}

    assert new_ids == {"doc_x1"}
    assert review_ids == {"doc_x2"}
    assert verified_ids == {"doc_x3"}


def test_feed_pdf_text_never_in_response(passed_user, ingest_doc):
    ingest_doc("doc_test")
    body = passed_user["client"].get("/api/feed?tab=new").json()
    for item in body["items"]:
        assert "pdf_text" not in item
```

- [ ] **Step 5: Run failing tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_shuffle_routes.py -q
```
Expected: errors due to router not yet mounted (depending on order of test creation, may pass after main.py edit). The truthful failure mode is that the routes module doesn't exist yet.

- [ ] **Step 6: Run tests after wiring**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_shuffle_routes.py -q
```
Expected: all 13 tests pass.

- [ ] **Step 7: Run full suite**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest -q
```
Expected: 0 failed.

- [ ] **Step 8: Commit**

```bash
cd /Users/barandincoguz/Desktop/deneme && git -c user.email=maarkval@icloud.com -c user.name=baran add backend/shuffle/models.py backend/shuffle/routes.py backend/main.py tests/test_shuffle_routes.py && git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(shuffle): add GET /api/feed HTTP endpoint

Query params: tab=new|review|verified (required, FastAPI pattern-validated),
limit=0..200 (default 50), offset>=0 (default 0). Returns
{items: list[FeedItem], total: int}. Gated by require_passed_training.
pdf_text never serialized. Empty tabs return 200 with empty list.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Smoke Test + Tag

**Goal:** Verify the route is mounted, the OpenAPI schema includes it, and tag the package release.

**Files:**
- (no new code; verification + tag only)

- [ ] **Step 1: Smoke test the route registration**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -c "from backend.main import app; paths = sorted([r.path for r in app.routes if hasattr(r,'path')]); print('\\n'.join(p for p in paths if 'feed' in p))"
```
Expected output: `/api/feed`

- [ ] **Step 2: Smoke test the OpenAPI schema**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -c "
from backend.main import app
import json
schema = app.openapi()
feed_op = schema['paths']['/api/feed']['get']
params = {p['name']: p for p in feed_op['parameters']}
print('tab values:', params['tab']['schema'].get('pattern'))
print('limit max:', params['limit']['schema'].get('maximum'))
print('limit min:', params['limit']['schema'].get('minimum'))
print('offset min:', params['offset']['schema'].get('minimum'))
print('response model:', feed_op['responses']['200']['content']['application/json']['schema']['\$ref'])
"
```
Expected:
```
tab values: ^(new|review|verified)$
limit max: 200
limit min: 0
offset min: 0
response model: #/components/schemas/FeedResponse
```

- [ ] **Step 3: Run full suite one final time**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest -q
```
Expected: all green.

- [ ] **Step 4: Tag the release**

```bash
cd /Users/barandincoguz/Desktop/deneme && git tag paket-6-shuffle-feed && git tag --list "paket-*"
```
Expected: list shows paket-1 through paket-6.

---

## Verification

After Task 3:

- All Paket 6 files exist with the layout in §"Dosya Yapısı"
- `python -m pytest -q` reports 0 failures
- `paket-6-shuffle-feed` tag points at the most recent commit
- `git log --oneline ef074cb..HEAD` shows the new commits ordered correctly
- OpenAPI schema includes `/api/feed` with the right pattern/min/max constraints

## Open Items For Later Packages (NOT this paket)

- **Paket 7 (SSE):** When `annotation_save` event fires, frontend should invalidate the appropriate tab caches (TanStack Query). Backend already gives all the inputs needed.
- **Paket 8 (Behavioral Detectors):** May want to log `feed_load` activity events to track tab usage patterns. Not in scope here.
- **Paket 9 (Gamification):** Daily target progress is computed from `today_save_count` (already in `gamification_state`); feed module doesn't touch it.
- **Paket 11 (Admin):** Admin filter (`tab=all` or `?as_admin=1`) — not in v1 scope.
- **Paket 16 (Frontend):** Will consume `/api/feed` via `useFeed(tab)` hook + virtual-scroll list.
- **Per-user filter ("ben doğruladığım")**: spec is ambiguous about whether "Doğruladıklarım" means *I* completed vs. completed-globally. This plan implements the global interpretation. If the user later wants the per-user interpretation, add `?as_user=me` filter.

## Self-Review Notes

- **Spec coverage:** `GET /api/feed?tab=...` from spec line 673 ✓; 3 tab semantics from line 85, 753 ✓; chain attribution surface (last_editor_username) from line 763 ✓; difficulty/word_count fields from documents_meta schema; per-user shuffle from line 85 ("Bursiyere kontrol") ✓; `require_passed_training` gating (Paket 5 pattern) ✓.
- **Type consistency:** `FeedItem` field names match the dict keys returned by `service.list_feed`. `MAX_LIMIT` and `DEFAULT_LIMIT` are referenced consistently in routes.py and tests.
- **No placeholders:** Every step contains the actual file content / command / expected output. Validation errors mapped to status codes consistently (422 for query-param violations via FastAPI, 401 for unauth).
- **Performance sanity:** Each tab is one query against the existing indexes (`idx_ann_completed`, `idx_docs_*`). Shuffle is O(N) in Python on the in-memory list — fine up to ~50K items; will become a problem only beyond that scale (post-MVP concern).

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-06-package-6-shuffle-feed.md`.**
