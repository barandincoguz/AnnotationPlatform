# Paket 5 — Annotations Chain (versions, diff, drafts) + Locks (heartbeat) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multi-user chain review için anotasyon kaydetme, sürümleme, set-semantic diff hesabı, per-user draft autosave, ve heartbeat-based document locks. Paket 5 sonunda iki kullanıcı birbiri ardına aynı doküman üstünde çalışıp tutarlı bir version chain üretebiliyor olacak.

**Architecture:** Hibrit storage — `annotations.references_json` (JSON blob, current state) + `annotation_references` (denormalized index, cross-doc query için). Her save sonrası: yeni `annotation_versions` snapshot satırı yazılır, set-semantic diff hesaplanır, `annotation_references` denorm tablosu yeniden yazılır, draft silinir, lock release edilir. Locks `document_locks` (active-only) tablosu üzerinden — heartbeat refresh + background sweep. Bu pakette **SSE event yayını YOK** (Paket 7 ekler); pure DB + HTTP layer.

**Tech Stack:** Python stdlib (`json`, `sqlite3`, `asyncio`), FastAPI, Pydantic, pytest. Paket 2 auth deps (`get_current_user`, `require_passed_training`) ve Paket 4 documents tabloları kullanılır.

---

## Mimari Kararlar (Spec'ten Kilitlenmiş)

- **Reference shape:** `{kanun_no, kanun_ad, madde, fikra, bent, source_text}` — `source_text` REQUIRED, diğerleri opsiyonel (None veya boş string → None).
- **Madde format:** Tek string field; "1", "Mükerrer 20", "Geçici 5" gibi serbest formatta.
- **0 referans OK:** Yasal atfı olmayan bir doküman için boş liste `[]` legitimate state — save edilebilir, complete işaretlenebilir.
- **Duplicate detection:** Tam 6-tuple eşleşmesi (her field birebir aynı) → reddedilir (`DuplicateReference`).
- **Diff:** Set semantics — canonical 6-tuple key set'i çıkarılır, simetrik fark alınır. Sıra önemsiz; aynı içerik farklı sırada save edilirse diff=0.
- **Storage:** Hibrit — `annotations.references_json` JSON blob (canonical source) + `annotation_references` denormalized index (her save'de DELETE+INSERT ile yeniden yazılır).
- **Auto-suggest YOK:** `document_kanun_refs`/`document_bkk_refs` tabloları sadece source metadata; bu pakette UI'a sızdırılmaz.
- **Completion:** Hibrit — manuel toggle her zaman mümkün; `is_diff_zero=1` olduğunda frontend prominent gösterir (UI Paket 16). Backend sadece toggle endpoint sunar.
- **Lock:** Heartbeat 30sn, expires 5dk (`site_settings`'den okunur), idle release sweep her 60sn. Queue yok — 409 + "başka doc seç".
- **Lock holder check:** heartbeat/release endpoint'leri çağrıyı yapan user lock'un sahibi değilse 404 (varlığı saklı tut). force_release sadece admin (Paket 11; bu paket admin route'unu yazmaz).
- **Auth gating:** Tüm Paket 5 route'ları `require_passed_training` kullanır (manual + training gate'i geçmiş olmak şart).
- **Atomic save:** annotation save tek transaction'da yapılır — version + current update + denorm rebuild + draft delete + lock release. Hepsi başarılı yoksa rollback.
- **Draft semantics:** Per-user (`PRIMARY KEY (document_id, user_id)`). Save'den sonra **yalnızca o user'ın** draft'ı silinir; diğer kullanıcıların aynı doc üzerindeki draft'ları kalır (chain review öncesi WIP korunur).
- **Skip:** annotation tablosuna dokunmaz; sadece activity_event yazar ve lock release eder. (Spec: "skip" yeni version yaratmaz.)
- **Version action types:** `'create'` (ilk versionda), `'edit'` (mevcut annotation üstüne yazıldı), `'complete_mark'`, `'uncomplete'`. Skip version yazmaz.
- **SSE:** Bu pakette yok — Paket 7'de eklenir. Service layer pure DB; route'lar HTTP yanıtı dönmekle yetinir.

## Dosya Yapısı

```
backend/annotations/
├── __init__.py            # boş
├── diff.py                # pure: normalize_reference, normalize_references, references_diff, is_diff_zero
├── service.py             # save, get_annotation, get_chain, skip, set_complete + custom exceptions
├── drafts.py              # service: get_draft, set_draft, clear_draft
├── routes.py              # POST /api/annotations, GET /api/documents/{id}/annotation, /skip, /complete, drafts
└── models.py              # Pydantic: ReferenceItem, SaveAnnotationRequest, AnnotationDetail, ChainEntry, DraftPayload

backend/locks/
├── __init__.py            # boş
├── service.py             # acquire, heartbeat, release, force_release, get_lock, sweep_expired + exceptions
├── routes.py              # POST /api/locks/{id}/acquire|heartbeat|release
├── models.py              # Pydantic: LockInfo, LockConflict
└── sweep.py               # async background sweep loop helper

backend/main.py            # MODIFIED: mount annotations_router, locks_router, schedule lock sweep on startup

tests/
├── test_annotations_diff.py        # pure-function tests (normalize, diff, dup detection)
├── test_annotations_service.py     # save, versioning, denorm rebuild, completion
├── test_annotations_routes.py      # POST /api/annotations, GET chain, skip, complete
├── test_drafts.py                  # service + PUT/GET/DELETE /api/drafts/{id}
├── test_locks_service.py           # acquire/heartbeat/release/sweep
├── test_locks_routes.py            # 200/409/404 cases
└── test_paket5_e2e.py              # full multi-user chain review flow
```

## Yeni Test Fixture'ları

`tests/conftest.py`'a Paket 5 testleri için yardımcı fixture'lar eklenecek (Task 1'in ilk adımında). Hatırlatma: gating'i geçmiş user'a ihtiyaç var çünkü route'lar `require_passed_training` istiyor.

---

## Task 1: Conftest Helpers + Diff Module (TDD)

**Goal:** Paket 5 testleri için ortak fixture'lar (gating geçmiş user, ingest helper) + saf normalize/diff fonksiyonları.

**Files:**
- Modify: `tests/conftest.py`
- Create: `backend/annotations/__init__.py`
- Create: `backend/annotations/diff.py`
- Create: `tests/test_annotations_diff.py`

- [ ] **Step 1: Create empty annotations package**

Run:
```bash
mkdir -p /Users/barandincoguz/Desktop/deneme/backend/annotations
touch /Users/barandincoguz/Desktop/deneme/backend/annotations/__init__.py
```

- [ ] **Step 2: Add shared fixtures to `tests/conftest.py`**

Replace the existing `tests/conftest.py` (which currently has `db_path` and `client`) with the version below — the originals are preserved verbatim, the new fixtures are appended:

```python
import json
from pathlib import Path
import pytest


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """FastAPI TestClient with isolated DATA_DIR / DB."""
    from fastapi.testclient import TestClient
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("backend.config.DB_DIR", tmp_path / "db")
    monkeypatch.setattr("backend.config.DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr("backend.config.DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr("backend.config.BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr("backend.config.EXPORTS_DIR", tmp_path / "exports")
    from backend.main import app
    with TestClient(app) as c:
        yield c


# === Paket 5 helpers ===

_SAMPLE_DOC = {
    "evrakOid": "doc_test",
    "sayi": 1,
    "tarih": "20260101",
    "konu": "Test özelge",
    "pdfText": "Bu bir test dokümanıdır. Kanun atıfları içerir.",
    "kanunBilgileri": [],
    "bkkTebligSirkuBilgileri": [],
}


@pytest.fixture
def ingest_doc(client):
    """Ingest a single document into the test DB. Returns document_id."""
    from backend.shared.db import connect
    from backend.documents import service as doc_service
    from backend import config

    def _ingest(document_id: str = "doc_test", **overrides) -> str:
        payload = {**_SAMPLE_DOC, "evrakOid": document_id, **overrides}
        path = config.DOCUMENTS_DIR / f"{document_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        conn = connect(config.DB_PATH)
        try:
            doc_service.ingest_file(conn, path)
        finally:
            conn.close()
        return document_id
    return _ingest


@pytest.fixture
def passed_user(client):
    """Register a user, mark gating flags True, return logged-in client + user dict.

    Returns dict: {"client": TestClient, "user": {...}}.
    The client carries the session cookie.
    """
    from backend.shared.db import connect
    from backend import config

    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("BURSIYER-2026",),
        )
    finally:
        conn.close()

    r = client.post("/api/auth/register", json={
        "username": "alice", "password": "password123",
        "invite_code": "BURSIYER-2026", "email": "alice@example.com",
    })
    assert r.status_code == 201, r.text
    user = r.json()

    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET has_seen_manual=1, has_passed_training=1 WHERE id=?",
            (user["id"],),
        )
    finally:
        conn.close()

    r = client.post("/api/auth/login", json={
        "username": "alice", "password": "password123",
    })
    assert r.status_code == 200, r.text
    return {"client": client, "user": user}


@pytest.fixture
def second_passed_user(client, passed_user):
    """Adds a second user (bob) sharing the same client/cookie jar via logout/login.

    Returns helper dict with login(name) function so tests can switch users:
      ctx = second_passed_user
      ctx["login"]("alice")  # switches cookie to alice
      ctx["login"]("bob")    # switches to bob
    """
    from backend.shared.db import connect
    from backend import config

    r = client.post("/api/auth/register", json={
        "username": "bob", "password": "password123",
        "invite_code": "BURSIYER-2026", "email": "bob@example.com",
    })
    assert r.status_code == 201, r.text
    bob = r.json()

    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET has_seen_manual=1, has_passed_training=1 WHERE id=?",
            (bob["id"],),
        )
    finally:
        conn.close()

    def login(username: str) -> None:
        client.cookies.clear()
        r = client.post("/api/auth/login", json={
            "username": username, "password": "password123",
        })
        assert r.status_code == 200, r.text

    return {"alice": passed_user["user"], "bob": bob, "login": login, "client": client}
```

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_auth_routes.py -q
```
Expected: existing tests still PASS (we only appended fixtures, didn't change existing ones).

- [ ] **Step 3: Write `tests/test_annotations_diff.py`**

```python
import pytest
from backend.annotations.diff import (
    normalize_reference, normalize_references, canonical_key,
    references_diff, is_diff_zero,
    InvalidReference, DuplicateReference,
)


def _ref(**kwargs):
    base = {
        "kanun_no": None, "kanun_ad": None, "madde": None,
        "fikra": None, "bent": None, "source_text": "x",
    }
    base.update(kwargs)
    return base


# --- normalize_reference ---

def test_normalize_strips_whitespace():
    r = normalize_reference({"source_text": "  hello  ", "kanun_no": "  193 "})
    assert r["source_text"] == "hello"
    assert r["kanun_no"] == "193"


def test_normalize_empty_strings_become_none():
    r = normalize_reference({"source_text": "x", "kanun_no": "", "madde": "   "})
    assert r["kanun_no"] is None
    assert r["madde"] is None


def test_normalize_missing_optional_fields_default_to_none():
    r = normalize_reference({"source_text": "x"})
    assert r["kanun_no"] is None
    assert r["kanun_ad"] is None
    assert r["madde"] is None
    assert r["fikra"] is None
    assert r["bent"] is None


def test_normalize_rejects_missing_source_text():
    with pytest.raises(InvalidReference):
        normalize_reference({"kanun_no": "193"})


def test_normalize_rejects_empty_source_text():
    with pytest.raises(InvalidReference):
        normalize_reference({"source_text": "   "})


def test_normalize_preserves_madde_format():
    """Madde is a free string ('Mükerrer 20', 'Geçici 5')."""
    r = normalize_reference({"source_text": "x", "madde": "Mükerrer 20"})
    assert r["madde"] == "Mükerrer 20"


# --- normalize_references (list) ---

def test_normalize_list_empty():
    assert normalize_references([]) == []


def test_normalize_list_rejects_exact_duplicate():
    refs = [
        _ref(kanun_no="193", madde="37", source_text="text A"),
        _ref(kanun_no="193", madde="37", source_text="text A"),
    ]
    with pytest.raises(DuplicateReference):
        normalize_references(refs)


def test_normalize_list_allows_partial_duplicate():
    """Same kanun_no/madde but different source_text → not a duplicate."""
    refs = [
        _ref(kanun_no="193", madde="37", source_text="atif 1"),
        _ref(kanun_no="193", madde="37", source_text="atif 2"),
    ]
    out = normalize_references(refs)
    assert len(out) == 2


def test_normalize_list_normalizes_then_dedupes():
    """Whitespace differences alone don't avoid duplicate detection."""
    refs = [
        _ref(kanun_no="193", source_text="hello"),
        _ref(kanun_no=" 193 ", source_text="hello   "),
    ]
    with pytest.raises(DuplicateReference):
        normalize_references(refs)


# --- canonical_key + diff ---

def test_canonical_key_is_deterministic():
    a = _ref(kanun_no="193", madde="37", source_text="x")
    b = _ref(kanun_no="193", madde="37", source_text="x")
    assert canonical_key(a) == canonical_key(b)


def test_diff_added_only():
    prev = []
    curr = [_ref(kanun_no="193", source_text="atif")]
    diff = references_diff(prev, curr)
    assert len(diff["added"]) == 1
    assert diff["removed"] == []
    assert not is_diff_zero(diff)


def test_diff_removed_only():
    prev = [_ref(kanun_no="193", source_text="atif")]
    curr = []
    diff = references_diff(prev, curr)
    assert diff["added"] == []
    assert len(diff["removed"]) == 1


def test_diff_zero_when_same_content():
    refs = [_ref(kanun_no="193", source_text="x"), _ref(kanun_no="5520", source_text="y")]
    assert is_diff_zero(references_diff(refs, refs))


def test_diff_zero_independent_of_order():
    """Set semantics — order doesn't matter."""
    a = _ref(kanun_no="193", source_text="x")
    b = _ref(kanun_no="5520", source_text="y")
    diff = references_diff([a, b], [b, a])
    assert is_diff_zero(diff)


def test_diff_detects_modified_as_remove_plus_add():
    """Set semantics: changed source_text = old removed + new added."""
    prev = [_ref(kanun_no="193", source_text="old text")]
    curr = [_ref(kanun_no="193", source_text="new text")]
    diff = references_diff(prev, curr)
    assert len(diff["added"]) == 1
    assert len(diff["removed"]) == 1
    assert diff["added"][0]["source_text"] == "new text"
    assert diff["removed"][0]["source_text"] == "old text"
```

- [ ] **Step 4: Run failing tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_annotations_diff.py -q
```
Expected: ImportError / module not found.

- [ ] **Step 5: Implement `backend/annotations/diff.py`**

```python
"""Pure-function reference normalization, deduping, and set-semantic diff.

A reference is a dict with 6 keys:
  {kanun_no, kanun_ad, madde, fikra, bent, source_text}

source_text is REQUIRED (non-empty after strip). The other 5 fields are
optional; empty strings normalize to None. Duplicates are rejected by exact
6-tuple match (after normalization).

Diff is set-based: order doesn't matter. is_diff_zero(diff) means the two
reference lists encode the same set of references.
"""
from typing import Optional

REFERENCE_FIELDS = (
    "kanun_no", "kanun_ad", "madde", "fikra", "bent", "source_text",
)


class InvalidReference(ValueError):
    """source_text missing or empty."""


class DuplicateReference(ValueError):
    """Two refs in the same list have identical canonical keys."""


def _clean(value: Optional[object]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def normalize_reference(ref: dict) -> dict:
    """Return a 6-key dict with whitespace stripped, empty → None.

    Raises InvalidReference if source_text is missing or empty.
    """
    out = {f: _clean(ref.get(f)) for f in REFERENCE_FIELDS}
    if not out["source_text"]:
        raise InvalidReference("source_text is required")
    return out


def canonical_key(ref: dict) -> tuple:
    """Stable 6-tuple identity for set-based comparison."""
    return tuple(ref.get(f) for f in REFERENCE_FIELDS)


def normalize_references(refs: list[dict]) -> list[dict]:
    """Normalize each ref; reject the list if any two are exact duplicates.

    Order is preserved (used as `seq` for the denormalized index).
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in refs:
        n = normalize_reference(r)
        key = canonical_key(n)
        if key in seen:
            raise DuplicateReference(
                f"duplicate reference: source_text={n['source_text']!r}"
            )
        seen.add(key)
        out.append(n)
    return out


def references_diff(prev: list[dict], curr: list[dict]) -> dict:
    """Set-based symmetric difference. Returns {'added': [...], 'removed': [...]}.

    Inputs should already be normalized.
    """
    prev_map = {canonical_key(r): r for r in prev}
    curr_map = {canonical_key(r): r for r in curr}
    added_keys = curr_map.keys() - prev_map.keys()
    removed_keys = prev_map.keys() - curr_map.keys()
    return {
        "added": [curr_map[k] for k in added_keys],
        "removed": [prev_map[k] for k in removed_keys],
    }


def is_diff_zero(diff: dict) -> bool:
    return not diff["added"] and not diff["removed"]
```

- [ ] **Step 6: Run tests to verify pass**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_annotations_diff.py -q
```
Expected: 13 passed.

- [ ] **Step 7: Run full suite to check nothing regressed**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest -q
```
Expected: previous 141 + 13 new = 154 passed. (Number may differ slightly if test count changed; the key signal is "0 failed".)

- [ ] **Step 8: Commit**

```bash
cd /Users/barandincoguz/Desktop/deneme && git -c user.email=maarkval@icloud.com -c user.name=baran add backend/annotations tests/conftest.py tests/test_annotations_diff.py && git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(annotations): add reference normalization + set-semantic diff

Pure functions: normalize_reference, normalize_references (rejects exact-duplicate
6-tuples), references_diff (set semantics — order independent), is_diff_zero.

Adds shared test fixtures (passed_user, second_passed_user, ingest_doc) for
upcoming Paket 5 service/route tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Annotation Service (versioning + denorm rebuild)

**Goal:** `save_annotation`, `get_annotation`, `get_chain`, `skip_annotation`, `set_complete` — all transactional, all write to `annotation_versions` (history) + `annotations` (current) + `annotation_references` (denorm) atomically.

**Files:**
- Create: `backend/annotations/service.py`
- Create: `tests/test_annotations_service.py`

- [ ] **Step 1: Write `tests/test_annotations_service.py`**

```python
import json
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.documents import service as doc_service
from backend.annotations import service as ann_service


@pytest.fixture
def db(db_path, tmp_path):
    """DB with schema applied + 2 users + 1 ingested document."""
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) "
        "VALUES ('alice','x','user',?,?), ('bob','x','user',?,?)",
        (now, now, now, now),
    )
    sample = {
        "evrakOid": "doc_1", "sayi": 1, "tarih": "20260101",
        "konu": "Test", "pdfText": "x" * 50,
        "kanunBilgileri": [], "bkkTebligSirkuBilgileri": [],
    }
    fpath = tmp_path / "doc_1.json"
    fpath.write_text(json.dumps(sample))
    doc_service.ingest_file(conn, fpath)
    yield conn
    conn.close()


def _ref(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "x"}
    base.update(kwargs)
    return base


# --- save_annotation ---

def test_save_creates_annotation_row(db):
    refs = [_ref(kanun_no="193", madde="37", source_text="atif 1")]
    result = ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=refs)
    assert result["is_new"] is True
    assert result["is_diff_zero"] is False  # first save creates content

    row = db.execute("SELECT * FROM annotations WHERE document_id=?", ("doc_1",)).fetchone()
    assert row is not None
    parsed = json.loads(row["references_json"])
    assert len(parsed) == 1
    assert parsed[0]["source_text"] == "atif 1"
    assert row["edit_count"] == 1
    assert row["unique_users_count"] == 1
    assert row["last_editor_user_id"] == 1


def test_save_creates_version_snapshot(db):
    refs = [_ref(kanun_no="193", source_text="atif 1")]
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=refs)
    versions = db.execute(
        "SELECT * FROM annotation_versions WHERE document_id=? ORDER BY id", ("doc_1",)
    ).fetchall()
    assert len(versions) == 1
    assert versions[0]["action"] == "create"
    assert versions[0]["user_id"] == 1
    assert versions[0]["is_diff_zero"] == 0


def test_save_rebuilds_denormalized_index(db):
    refs = [
        _ref(kanun_no="193", madde="37", source_text="atif 1"),
        _ref(kanun_no="5520", madde="5", source_text="atif 2"),
    ]
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=refs)

    rows = db.execute(
        "SELECT * FROM annotation_references WHERE document_id=? ORDER BY seq", ("doc_1",)
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["kanun_no"] == "193"
    assert rows[0]["seq"] == 0
    assert rows[1]["kanun_no"] == "5520"


def test_second_save_rebuilds_denorm_no_duplicates(db):
    refs1 = [_ref(kanun_no="193", source_text="atif 1")]
    refs2 = [_ref(kanun_no="5520", source_text="atif 2")]
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=refs1)
    ann_service.save_annotation(db, document_id="doc_1", user_id=2, references=refs2)

    rows = db.execute(
        "SELECT * FROM annotation_references WHERE document_id=?", ("doc_1",)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["kanun_no"] == "5520"


def test_save_with_same_content_sets_diff_zero(db):
    refs = [_ref(kanun_no="193", source_text="atif 1")]
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=refs)
    result = ann_service.save_annotation(db, document_id="doc_1", user_id=2, references=refs)
    assert result["is_diff_zero"] is True

    last_version = db.execute(
        "SELECT * FROM annotation_versions WHERE document_id=? ORDER BY id DESC LIMIT 1",
        ("doc_1",),
    ).fetchone()
    assert last_version["is_diff_zero"] == 1
    assert last_version["action"] == "edit"


def test_save_diff_zero_independent_of_order(db):
    refs_a = [
        _ref(kanun_no="193", source_text="x"),
        _ref(kanun_no="5520", source_text="y"),
    ]
    refs_b = list(reversed(refs_a))
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=refs_a)
    result = ann_service.save_annotation(db, document_id="doc_1", user_id=2, references=refs_b)
    assert result["is_diff_zero"] is True


def test_save_increments_edit_count_and_unique_users(db):
    refs1 = [_ref(kanun_no="193", source_text="a")]
    refs2 = [_ref(kanun_no="193", source_text="b")]
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=refs1)
    ann_service.save_annotation(db, document_id="doc_1", user_id=2, references=refs2)
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=refs1)

    row = db.execute("SELECT * FROM annotations WHERE document_id=?", ("doc_1",)).fetchone()
    assert row["edit_count"] == 3
    assert row["unique_users_count"] == 2  # alice + bob


def test_save_empty_list_is_legitimate(db):
    """0 references is a valid annotation state."""
    result = ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    assert result["is_new"] is True
    row = db.execute("SELECT * FROM annotations WHERE document_id=?", ("doc_1",)).fetchone()
    assert json.loads(row["references_json"]) == []


def test_save_rejects_duplicate_refs(db):
    from backend.annotations.diff import DuplicateReference
    refs = [
        _ref(kanun_no="193", source_text="x"),
        _ref(kanun_no="193", source_text="x"),
    ]
    with pytest.raises(DuplicateReference):
        ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=refs)


def test_save_rejects_unknown_document(db):
    with pytest.raises(ann_service.DocumentNotFound):
        ann_service.save_annotation(db, document_id="nonexistent", user_id=1, references=[])


def test_save_logs_activity_event(db):
    refs = [_ref(kanun_no="193", source_text="x")]
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=refs)
    rows = db.execute(
        "SELECT * FROM activity_events WHERE user_id=? AND event_type=?", (1, "annotation_save")
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["document_id"] == "doc_1"


def test_save_clears_only_callers_draft(db):
    """save() deletes the saving user's draft but leaves other users' drafts intact."""
    db.execute(
        "INSERT INTO drafts(document_id, user_id, references_json, updated_at) "
        "VALUES ('doc_1', 1, '[]', datetime('now')), ('doc_1', 2, '[]', datetime('now'))"
    )
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    rows = db.execute("SELECT user_id FROM drafts WHERE document_id='doc_1'").fetchall()
    assert [r["user_id"] for r in rows] == [2]


# --- get_annotation ---

def test_get_annotation_none_when_never_saved(db):
    assert ann_service.get_annotation(db, "doc_1") is None


def test_get_annotation_returns_current_state(db):
    refs = [_ref(kanun_no="193", source_text="x")]
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=refs)
    out = ann_service.get_annotation(db, "doc_1")
    assert out is not None
    assert len(out["references"]) == 1
    assert out["is_completed"] is False
    assert out["last_editor_user_id"] == 1


# --- get_chain ---

def test_get_chain_returns_versions_oldest_first_with_attribution(db):
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[_ref(source_text="v1")])
    ann_service.save_annotation(db, document_id="doc_1", user_id=2, references=[_ref(source_text="v2")])
    chain = ann_service.get_chain(db, "doc_1")
    assert len(chain) == 2
    assert chain[0]["username"] == "alice"
    assert chain[0]["action"] == "create"
    assert chain[1]["username"] == "bob"
    assert chain[1]["action"] == "edit"
    assert "diff_summary" in chain[1]
    assert chain[1]["diff_summary"]["added_count"] >= 1


def test_get_chain_empty_when_no_annotation(db):
    assert ann_service.get_chain(db, "doc_1") == []


# --- skip ---

def test_skip_logs_activity_no_version(db):
    ann_service.skip_annotation(db, document_id="doc_1", user_id=1)
    versions = db.execute(
        "SELECT * FROM annotation_versions WHERE document_id=?", ("doc_1",)
    ).fetchall()
    assert versions == []
    activity = db.execute(
        "SELECT * FROM activity_events WHERE event_type=?", ("annotation_skip",)
    ).fetchall()
    assert len(activity) == 1


# --- complete toggle ---

def test_complete_toggle_marks_completed(db):
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    result = ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)
    assert result["is_completed"] is True

    row = db.execute("SELECT * FROM annotations WHERE document_id=?", ("doc_1",)).fetchone()
    assert row["is_completed"] == 1
    assert row["completed_by_user_id"] == 1

    versions = db.execute(
        "SELECT action FROM annotation_versions WHERE document_id=? ORDER BY id DESC LIMIT 1",
        ("doc_1",),
    ).fetchone()
    assert versions["action"] == "complete_mark"


def test_complete_toggle_uncomplete(db):
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)
    ann_service.set_complete(db, document_id="doc_1", user_id=2, completed=False)
    row = db.execute("SELECT * FROM annotations WHERE document_id=?", ("doc_1",)).fetchone()
    assert row["is_completed"] == 0
    assert row["completed_by_user_id"] is None


def test_complete_requires_existing_annotation(db):
    with pytest.raises(ann_service.AnnotationNotFound):
        ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)
```

- [ ] **Step 2: Run failing tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_annotations_service.py -q
```
Expected: ImportError — module not yet defined.

- [ ] **Step 3: Implement `backend/annotations/service.py`**

```python
"""Annotation chain service.

Public API:
  save_annotation(db, document_id, user_id, references) -> dict
  get_annotation(db, document_id) -> Optional[dict]
  get_chain(db, document_id) -> list[dict]
  skip_annotation(db, document_id, user_id) -> None
  set_complete(db, document_id, user_id, completed) -> dict

Each save is atomic:
  1. Validate references (normalize + dedupe)
  2. Compute set-semantic diff vs. previous current state
  3. Append annotation_versions snapshot (with diff_from_previous, is_diff_zero, action)
  4. Upsert annotations CURRENT row (last_editor, edit_count++, unique_users)
  5. Rebuild annotation_references denorm table
  6. Delete the caller's draft
  7. Release the caller's lock if any (no-op if not held)
  8. Log activity_event 'annotation_save'

skip writes only an activity_event + lock release. complete toggle creates a
'complete_mark'/'uncomplete' version and updates the CURRENT row.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from backend.annotations.diff import (
    normalize_references, references_diff, is_diff_zero,
)
from backend.shared import audit


class AnnotationServiceError(Exception):
    """Base."""


class DocumentNotFound(AnnotationServiceError):
    pass


class AnnotationNotFound(AnnotationServiceError):
    """set_complete called on a document with no annotation row yet."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _document_exists(db: sqlite3.Connection, document_id: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM documents_meta WHERE document_id=?", (document_id,)
    ).fetchone()
    return row is not None


def _release_caller_lock(db: sqlite3.Connection, document_id: str, user_id: int) -> None:
    db.execute(
        "DELETE FROM document_locks WHERE document_id=? AND user_id=?",
        (document_id, user_id),
    )


def _delete_caller_draft(db: sqlite3.Connection, document_id: str, user_id: int) -> None:
    db.execute(
        "DELETE FROM drafts WHERE document_id=? AND user_id=?",
        (document_id, user_id),
    )


def _rebuild_denormalized(
    db: sqlite3.Connection, document_id: str, refs: list[dict]
) -> None:
    db.execute(
        "DELETE FROM annotation_references WHERE document_id=?", (document_id,)
    )
    for seq, r in enumerate(refs):
        db.execute(
            """
            INSERT INTO annotation_references(
                document_id, seq, kanun_no, kanun_ad, madde, fikra, bent, source_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id, seq,
                r["kanun_no"], r["kanun_ad"], r["madde"],
                r["fikra"], r["bent"], r["source_text"],
            ),
        )


def _count_unique_users(db: sqlite3.Connection, document_id: str) -> int:
    row = db.execute(
        "SELECT COUNT(DISTINCT user_id) AS c FROM annotation_versions WHERE document_id=?",
        (document_id,),
    ).fetchone()
    return row["c"]


def save_annotation(
    db: sqlite3.Connection,
    *,
    document_id: str,
    user_id: int,
    references: list[dict],
) -> dict:
    """Save reference list, snapshot version, rebuild denorm. Atomic.

    Returns: {is_new, is_diff_zero, current_references}.
    Raises: DocumentNotFound, DuplicateReference, InvalidReference.
    """
    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)

    cleaned = normalize_references(references)

    cur_row = db.execute(
        "SELECT references_json FROM annotations WHERE document_id=?", (document_id,)
    ).fetchone()
    is_new = cur_row is None
    prev = [] if is_new else json.loads(cur_row["references_json"])

    diff = references_diff(prev, cleaned)
    diff_zero = is_diff_zero(diff)
    action = "create" if is_new else "edit"
    now = _now()

    db.execute("BEGIN")
    try:
        db.execute(
            """
            INSERT INTO annotation_versions(
                document_id, user_id, references_json, diff_from_previous,
                is_diff_zero, action, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id, user_id, json.dumps(cleaned),
                json.dumps(diff), 1 if diff_zero else 0, action, now,
            ),
        )

        unique_users = _count_unique_users(db, document_id)
        if is_new:
            db.execute(
                """
                INSERT INTO annotations(
                    document_id, references_json, is_completed,
                    last_editor_user_id, edit_count, unique_users_count,
                    created_at, updated_at
                ) VALUES (?, ?, 0, ?, 1, ?, ?, ?)
                """,
                (document_id, json.dumps(cleaned), user_id, unique_users, now, now),
            )
        else:
            db.execute(
                """
                UPDATE annotations SET
                    references_json=?,
                    last_editor_user_id=?,
                    edit_count=edit_count+1,
                    unique_users_count=?,
                    updated_at=?
                WHERE document_id=?
                """,
                (json.dumps(cleaned), user_id, unique_users, now, document_id),
            )

        _rebuild_denormalized(db, document_id, cleaned)
        _delete_caller_draft(db, document_id, user_id)
        _release_caller_lock(db, document_id, user_id)

        audit.log_activity(
            db, user_id, "annotation_save",
            document_id=document_id,
            extra={
                "action": action,
                "is_diff_zero": diff_zero,
                "ref_count": len(cleaned),
                "added_count": len(diff["added"]),
                "removed_count": len(diff["removed"]),
            },
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    return {
        "is_new": is_new,
        "is_diff_zero": diff_zero,
        "current_references": cleaned,
    }


def get_annotation(db: sqlite3.Connection, document_id: str) -> Optional[dict]:
    row = db.execute(
        "SELECT * FROM annotations WHERE document_id=?", (document_id,)
    ).fetchone()
    if row is None:
        return None
    return {
        "document_id": row["document_id"],
        "references": json.loads(row["references_json"]),
        "is_completed": bool(row["is_completed"]),
        "last_editor_user_id": row["last_editor_user_id"],
        "completed_by_user_id": row["completed_by_user_id"],
        "edit_count": row["edit_count"],
        "unique_users_count": row["unique_users_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_chain(db: sqlite3.Connection, document_id: str) -> list[dict]:
    """Return all versions oldest-first with attribution + diff summary."""
    rows = db.execute(
        """
        SELECT v.id, v.user_id, u.username, v.action, v.diff_from_previous,
               v.is_diff_zero, v.created_at,
               v.references_json
        FROM annotation_versions v
        LEFT JOIN users u ON u.id=v.user_id
        WHERE v.document_id=?
        ORDER BY v.id ASC
        """,
        (document_id,),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        diff_blob = json.loads(r["diff_from_previous"]) if r["diff_from_previous"] else {"added": [], "removed": []}
        refs = json.loads(r["references_json"])
        out.append({
            "version_id": r["id"],
            "user_id": r["user_id"],
            "username": r["username"],
            "action": r["action"],
            "is_diff_zero": bool(r["is_diff_zero"]),
            "ref_count": len(refs),
            "diff_summary": {
                "added_count": len(diff_blob["added"]),
                "removed_count": len(diff_blob["removed"]),
            },
            "created_at": r["created_at"],
        })
    return out


def skip_annotation(
    db: sqlite3.Connection, *, document_id: str, user_id: int
) -> None:
    """Skip = no DB row in annotations; log activity + release lock."""
    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)
    db.execute("BEGIN")
    try:
        _release_caller_lock(db, document_id, user_id)
        audit.log_activity(
            db, user_id, "annotation_skip", document_id=document_id,
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def set_complete(
    db: sqlite3.Connection, *, document_id: str, user_id: int, completed: bool
) -> dict:
    """Toggle is_completed. Writes a 'complete_mark'/'uncomplete' version.

    Raises AnnotationNotFound if no annotation row exists for the document.
    """
    cur = db.execute(
        "SELECT references_json, is_completed FROM annotations WHERE document_id=?",
        (document_id,),
    ).fetchone()
    if cur is None:
        raise AnnotationNotFound(document_id)
    if bool(cur["is_completed"]) == completed:
        # no-op (idempotent toggle)
        return {"is_completed": completed}

    now = _now()
    action = "complete_mark" if completed else "uncomplete"
    db.execute("BEGIN")
    try:
        db.execute(
            """
            INSERT INTO annotation_versions(
                document_id, user_id, references_json, diff_from_previous,
                is_diff_zero, action, created_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                document_id, user_id, cur["references_json"],
                json.dumps({"added": [], "removed": []}),
                action, now,
            ),
        )
        if completed:
            db.execute(
                "UPDATE annotations SET is_completed=1, completed_by_user_id=?, updated_at=? WHERE document_id=?",
                (user_id, now, document_id),
            )
        else:
            db.execute(
                "UPDATE annotations SET is_completed=0, completed_by_user_id=NULL, updated_at=? WHERE document_id=?",
                (now, document_id),
            )
        audit.log_activity(
            db, user_id, action, document_id=document_id,
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return {"is_completed": completed}
```

- [ ] **Step 4: Run tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_annotations_service.py -q
```
Expected: 18 passed (or however many we added — all green).

- [ ] **Step 5: Run full suite**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest -q
```
Expected: 0 failed.

- [ ] **Step 6: Commit**

```bash
cd /Users/barandincoguz/Desktop/deneme && git -c user.email=maarkval@icloud.com -c user.name=baran add backend/annotations/service.py tests/test_annotations_service.py && git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(annotations): add chain service (save, versions, denorm rebuild, complete)

save_annotation is atomic: snapshots a version, upserts the current row,
rebuilds the denormalized index, deletes the caller's draft, releases the
caller's lock, and logs an activity event. Set-semantic diff drives
is_diff_zero. skip writes activity only; complete toggle writes a
'complete_mark'/'uncomplete' version with diff_zero=1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Annotation Routes (HTTP layer)

**Goal:** REST endpoints — POST /api/annotations, POST /api/annotations/{id}/skip, POST /api/annotations/{id}/complete, GET /api/documents/{id}/annotation. All require `require_passed_training`.

**Files:**
- Create: `backend/annotations/models.py`
- Create: `backend/annotations/routes.py`
- Modify: `backend/main.py` (mount router)
- Create: `tests/test_annotations_routes.py`

- [ ] **Step 1: Write `backend/annotations/models.py`**

```python
"""Pydantic request/response models for annotation routes."""
from typing import Optional
from pydantic import BaseModel, Field


class ReferenceItem(BaseModel):
    kanun_no: Optional[str] = None
    kanun_ad: Optional[str] = None
    madde: Optional[str] = None
    fikra: Optional[str] = None
    bent: Optional[str] = None
    source_text: str = Field(min_length=1)


class SaveAnnotationRequest(BaseModel):
    document_id: str
    references: list[ReferenceItem]


class SaveAnnotationResponse(BaseModel):
    is_new: bool
    is_diff_zero: bool
    current_references: list[ReferenceItem]


class AnnotationDetail(BaseModel):
    document_id: str
    references: list[ReferenceItem]
    is_completed: bool
    last_editor_user_id: Optional[int]
    completed_by_user_id: Optional[int]
    edit_count: int
    unique_users_count: int
    created_at: str
    updated_at: str


class ChainEntry(BaseModel):
    version_id: int
    user_id: Optional[int]
    username: Optional[str]
    action: str
    is_diff_zero: bool
    ref_count: int
    diff_summary: dict
    created_at: str


class AnnotationWithChain(BaseModel):
    annotation: Optional[AnnotationDetail]
    chain: list[ChainEntry]


class CompleteRequest(BaseModel):
    completed: bool


class OkResponse(BaseModel):
    ok: bool = True
```

- [ ] **Step 2: Write `backend/annotations/routes.py`**

```python
"""Annotation HTTP endpoints. Auth: require_passed_training on all."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.annotations import service
from backend.annotations.diff import (
    DuplicateReference, InvalidReference,
)
from backend.annotations.models import (
    SaveAnnotationRequest, SaveAnnotationResponse,
    AnnotationDetail, ChainEntry, AnnotationWithChain,
    CompleteRequest, OkResponse,
)
from backend.users.deps import get_db, get_current_user, require_passed_training


router = APIRouter(prefix="/api", tags=["annotations"])


@router.post(
    "/annotations",
    response_model=SaveAnnotationResponse,
)
def save(
    payload: SaveAnnotationRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    refs = [r.model_dump() for r in payload.references]
    try:
        result = service.save_annotation(
            db,
            document_id=payload.document_id,
            user_id=user["id"],
            references=refs,
        )
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {payload.document_id} not found")
    except DuplicateReference as e:
        raise HTTPException(status_code=422, detail=str(e))
    except InvalidReference as e:
        raise HTTPException(status_code=422, detail=str(e))
    return result


@router.post(
    "/annotations/{document_id}/skip",
    response_model=OkResponse,
)
def skip(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        service.skip_annotation(db, document_id=document_id, user_id=user["id"])
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    return {"ok": True}


@router.post(
    "/annotations/{document_id}/complete",
    response_model=OkResponse,
)
def complete(
    document_id: str,
    payload: CompleteRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        service.set_complete(
            db, document_id=document_id, user_id=user["id"],
            completed=payload.completed,
        )
    except service.AnnotationNotFound:
        raise HTTPException(status_code=404, detail=f"no annotation for {document_id}")
    return {"ok": True}


@router.get(
    "/documents/{document_id}/annotation",
    response_model=AnnotationWithChain,
)
def get_annotation_with_chain(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(require_passed_training),
):
    """Returns current annotation + version chain. Caller uses this for chain review."""
    ann = service.get_annotation(db, document_id)
    chain = service.get_chain(db, document_id)
    if ann is None and not chain:
        # confirm doc exists, otherwise 404 (not all-empty for a missing doc)
        row = db.execute(
            "SELECT 1 FROM documents_meta WHERE document_id=?", (document_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    return {"annotation": ann, "chain": chain}
```

- [ ] **Step 3: Mount router in `backend/main.py`**

Edit `backend/main.py` line 20 area — after `from backend.documents.routes import router as documents_router`, add:

```python
from backend.annotations.routes import router as annotations_router
```

And after `app.include_router(documents_router)` (line 50), add:

```python
app.include_router(annotations_router)
```

- [ ] **Step 4: Write `tests/test_annotations_routes.py`**

```python
def _ref_payload(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "default"}
    base.update(kwargs)
    return base


def test_save_requires_auth(client):
    r = client.post("/api/annotations", json={"document_id": "doc_test", "references": []})
    assert r.status_code == 401


def test_save_creates_annotation(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("doc_test")
    r = c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref_payload(kanun_no="193", source_text="atif")],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new"] is True
    assert body["is_diff_zero"] is False
    assert len(body["current_references"]) == 1


def test_save_unknown_document_returns_404(passed_user):
    r = passed_user["client"].post("/api/annotations", json={
        "document_id": "doc_unknown",
        "references": [],
    })
    assert r.status_code == 404


def test_save_rejects_empty_source_text(passed_user, ingest_doc):
    ingest_doc("doc_test")
    r = passed_user["client"].post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref_payload(source_text="")],
    })
    assert r.status_code == 422


def test_save_rejects_duplicate(passed_user, ingest_doc):
    ingest_doc("doc_test")
    r = passed_user["client"].post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [
            _ref_payload(kanun_no="193", source_text="x"),
            _ref_payload(kanun_no="193", source_text="x"),
        ],
    })
    assert r.status_code == 422


def test_skip_returns_ok(passed_user, ingest_doc):
    ingest_doc("doc_test")
    r = passed_user["client"].post("/api/annotations/doc_test/skip")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_skip_unknown_doc_404(passed_user):
    r = passed_user["client"].post("/api/annotations/nonexistent/skip")
    assert r.status_code == 404


def test_complete_toggles(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("doc_test")
    c.post("/api/annotations", json={"document_id": "doc_test", "references": []})
    r = c.post("/api/annotations/doc_test/complete", json={"completed": True})
    assert r.status_code == 200

    g = c.get("/api/documents/doc_test/annotation")
    assert g.json()["annotation"]["is_completed"] is True


def test_complete_without_annotation_404(passed_user, ingest_doc):
    ingest_doc("doc_test")
    r = passed_user["client"].post("/api/annotations/doc_test/complete", json={"completed": True})
    assert r.status_code == 404


def test_get_chain_includes_attribution(second_passed_user, ingest_doc):
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")

    ctx["login"]("alice")
    c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref_payload(kanun_no="193", source_text="v1")],
    })

    ctx["login"]("bob")
    c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref_payload(kanun_no="5520", source_text="v2")],
    })

    r = c.get("/api/documents/doc_test/annotation")
    assert r.status_code == 200
    body = r.json()
    chain = body["chain"]
    assert len(chain) == 2
    usernames = [e["username"] for e in chain]
    assert usernames == ["alice", "bob"]
    assert chain[0]["action"] == "create"
    assert chain[1]["action"] == "edit"


def test_chain_diff_zero_for_identical_resave(second_passed_user, ingest_doc):
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")

    refs = [_ref_payload(kanun_no="193", source_text="x")]
    ctx["login"]("alice")
    c.post("/api/annotations", json={"document_id": "doc_test", "references": refs})
    ctx["login"]("bob")
    r = c.post("/api/annotations", json={"document_id": "doc_test", "references": refs})
    assert r.status_code == 200
    assert r.json()["is_diff_zero"] is True

    chain = c.get("/api/documents/doc_test/annotation").json()["chain"]
    assert chain[1]["is_diff_zero"] is True


def test_get_chain_unknown_doc_404(passed_user):
    r = passed_user["client"].get("/api/documents/nonexistent/annotation")
    assert r.status_code == 404
```

- [ ] **Step 5: Run tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_annotations_routes.py -q
```
Expected: all pass.

- [ ] **Step 6: Run full suite**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest -q
```
Expected: 0 failed.

- [ ] **Step 7: Commit**

```bash
cd /Users/barandincoguz/Desktop/deneme && git -c user.email=maarkval@icloud.com -c user.name=baran add backend/annotations/models.py backend/annotations/routes.py backend/main.py tests/test_annotations_routes.py && git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(annotations): add HTTP routes for save / skip / complete / chain read

POST /api/annotations, POST /api/annotations/{id}/skip,
POST /api/annotations/{id}/complete, GET /api/documents/{id}/annotation.
All gated by require_passed_training. 422 for duplicate or empty source_text;
404 for unknown document or unknown annotation on complete.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Drafts (Service + Routes)

**Goal:** Per-user autosave for WIP reference list. PUT /api/drafts/{id}, GET /api/drafts/{id}, DELETE /api/drafts/{id}.

**Files:**
- Create: `backend/annotations/drafts.py`
- Modify: `backend/annotations/models.py` (add DraftPayload)
- Modify: `backend/annotations/routes.py` (add 3 draft endpoints)
- Create: `tests/test_drafts.py`

- [ ] **Step 1: Write `tests/test_drafts.py`**

```python
import json
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.annotations import drafts


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) VALUES ('u1','x','user',?,?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, sentence_count, "
        "text_density, estimated_difficulty, created_at) "
        "VALUES ('doc_1','x.json','text',1,1,1.0,'Kolay',?)",
        (now,),
    )
    yield conn
    conn.close()


def _ref(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "x"}
    base.update(kwargs)
    return base


# --- service ---

def test_set_draft_creates_row(db):
    refs = [_ref(kanun_no="193", source_text="wip 1")]
    drafts.set_draft(db, document_id="doc_1", user_id=1, references=refs)
    row = db.execute(
        "SELECT * FROM drafts WHERE document_id='doc_1' AND user_id=1"
    ).fetchone()
    assert row is not None
    assert json.loads(row["references_json"])[0]["source_text"] == "wip 1"


def test_set_draft_upserts(db):
    drafts.set_draft(db, document_id="doc_1", user_id=1, references=[_ref(source_text="v1")])
    drafts.set_draft(db, document_id="doc_1", user_id=1, references=[_ref(source_text="v2")])
    rows = db.execute(
        "SELECT * FROM drafts WHERE document_id='doc_1' AND user_id=1"
    ).fetchall()
    assert len(rows) == 1
    assert json.loads(rows[0]["references_json"])[0]["source_text"] == "v2"


def test_set_draft_allows_invalid_ref_shape(db):
    """Drafts are WIP — source_text=='' is allowed (frontend may persist incomplete rows)."""
    drafts.set_draft(db, document_id="doc_1", user_id=1, references=[
        {"kanun_no": "193", "source_text": ""},  # incomplete, but acceptable as draft
    ])
    out = drafts.get_draft(db, document_id="doc_1", user_id=1)
    assert out is not None
    assert out["references"][0]["source_text"] == ""


def test_get_draft_none_when_absent(db):
    assert drafts.get_draft(db, document_id="doc_1", user_id=1) is None


def test_clear_draft_removes_row(db):
    drafts.set_draft(db, document_id="doc_1", user_id=1, references=[_ref(source_text="x")])
    drafts.clear_draft(db, document_id="doc_1", user_id=1)
    assert drafts.get_draft(db, document_id="doc_1", user_id=1) is None


def test_clear_draft_idempotent(db):
    """No-op if no draft exists."""
    drafts.clear_draft(db, document_id="doc_1", user_id=1)  # does not raise


def test_set_draft_unknown_doc_raises(db):
    with pytest.raises(drafts.DocumentNotFound):
        drafts.set_draft(db, document_id="nonexistent", user_id=1, references=[])


# --- routes ---

def test_put_draft_creates(passed_user, ingest_doc):
    ingest_doc("doc_test")
    c = passed_user["client"]
    r = c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="wip")]})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}


def test_get_draft_after_put(passed_user, ingest_doc):
    ingest_doc("doc_test")
    c = passed_user["client"]
    c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="wip")]})
    r = c.get("/api/drafts/doc_test")
    assert r.status_code == 200
    body = r.json()
    assert len(body["references"]) == 1
    assert body["references"][0]["source_text"] == "wip"


def test_get_draft_404_when_absent(passed_user, ingest_doc):
    ingest_doc("doc_test")
    r = passed_user["client"].get("/api/drafts/doc_test")
    assert r.status_code == 404


def test_delete_draft(passed_user, ingest_doc):
    ingest_doc("doc_test")
    c = passed_user["client"]
    c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="wip")]})
    r = c.delete("/api/drafts/doc_test")
    assert r.status_code == 200

    g = c.get("/api/drafts/doc_test")
    assert g.status_code == 404


def test_put_draft_unknown_doc_404(passed_user):
    r = passed_user["client"].put("/api/drafts/nonexistent", json={"references": []})
    assert r.status_code == 404


def test_drafts_are_per_user(second_passed_user, ingest_doc):
    """Alice's draft should not be visible to Bob."""
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")

    ctx["login"]("alice")
    c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="alice wip")]})

    ctx["login"]("bob")
    r = c.get("/api/drafts/doc_test")
    assert r.status_code == 404


def test_save_clears_callers_draft_only(second_passed_user, ingest_doc):
    """Alice saves → Alice's draft cleared; Bob's draft preserved."""
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")

    ctx["login"]("alice")
    c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="alice wip")]})

    ctx["login"]("bob")
    c.put("/api/drafts/doc_test", json={"references": [_ref(source_text="bob wip")]})

    ctx["login"]("alice")
    c.post("/api/annotations", json={"document_id": "doc_test", "references": [_ref(source_text="final")]})

    ctx["login"]("alice")
    assert c.get("/api/drafts/doc_test").status_code == 404

    ctx["login"]("bob")
    r = c.get("/api/drafts/doc_test")
    assert r.status_code == 200
    assert r.json()["references"][0]["source_text"] == "bob wip"
```

- [ ] **Step 2: Run failing tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_drafts.py -q
```
Expected: ImportError.

- [ ] **Step 3: Implement `backend/annotations/drafts.py`**

```python
"""Per-user draft (WIP) reference list service.

Drafts are write-through: PUT replaces the row. They store raw payload (no
strict validation) — frontend may save incomplete rows during typing. The
moment the user hits Save, the matching annotation service.save_annotation()
call deletes the draft as part of its atomic transaction.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional


class DraftServiceError(Exception):
    pass


class DocumentNotFound(DraftServiceError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _document_exists(db: sqlite3.Connection, document_id: str) -> bool:
    return db.execute(
        "SELECT 1 FROM documents_meta WHERE document_id=?", (document_id,)
    ).fetchone() is not None


def set_draft(
    db: sqlite3.Connection,
    *,
    document_id: str,
    user_id: int,
    references: list[dict],
) -> None:
    """Upsert draft. Stores raw references payload (no validation)."""
    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)
    db.execute(
        """
        INSERT INTO drafts(document_id, user_id, references_json, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(document_id, user_id) DO UPDATE SET
            references_json=excluded.references_json,
            updated_at=excluded.updated_at
        """,
        (document_id, user_id, json.dumps(references), _now()),
    )


def get_draft(
    db: sqlite3.Connection, *, document_id: str, user_id: int
) -> Optional[dict]:
    row = db.execute(
        "SELECT * FROM drafts WHERE document_id=? AND user_id=?",
        (document_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return {
        "document_id": row["document_id"],
        "references": json.loads(row["references_json"]),
        "updated_at": row["updated_at"],
    }


def clear_draft(
    db: sqlite3.Connection, *, document_id: str, user_id: int
) -> None:
    """Idempotent — no error if draft absent."""
    db.execute(
        "DELETE FROM drafts WHERE document_id=? AND user_id=?",
        (document_id, user_id),
    )
```

- [ ] **Step 4: Append draft endpoints to `backend/annotations/routes.py`**

Append at the bottom of the existing file:

```python


from backend.annotations import drafts as drafts_service


class _DraftPutRequest(__import__('pydantic').BaseModel):
    references: list[dict]  # raw — frontend may send incomplete rows


@router.put("/drafts/{document_id}", response_model=OkResponse)
def put_draft(
    document_id: str,
    payload: _DraftPutRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        drafts_service.set_draft(
            db, document_id=document_id, user_id=user["id"],
            references=payload.references,
        )
    except drafts_service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    return {"ok": True}


@router.get("/drafts/{document_id}")
def get_draft(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    out = drafts_service.get_draft(db, document_id=document_id, user_id=user["id"])
    if out is None:
        raise HTTPException(status_code=404, detail="no draft")
    return out


@router.delete("/drafts/{document_id}", response_model=OkResponse)
def delete_draft(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    drafts_service.clear_draft(db, document_id=document_id, user_id=user["id"])
    return {"ok": True}
```

(The dynamic `__import__('pydantic').BaseModel` keeps the new model local to the routes module without disturbing the cleaner imports already at the top. If a top-level import is preferred, add `from pydantic import BaseModel` at the head and use `BaseModel` directly — both work.)

- [ ] **Step 5: Run tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_drafts.py -q
```
Expected: all pass.

- [ ] **Step 6: Run full suite**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest -q
```
Expected: 0 failed.

- [ ] **Step 7: Commit**

```bash
cd /Users/barandincoguz/Desktop/deneme && git -c user.email=maarkval@icloud.com -c user.name=baran add backend/annotations/drafts.py backend/annotations/routes.py tests/test_drafts.py && git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(annotations): add per-user draft autosave (PUT/GET/DELETE)

Drafts are per-(document, user) WIP storage — written on every keystroke
debounce by the frontend. Stores raw references with no validation (allows
incomplete rows while typing). Save endpoint deletes the caller's draft
atomically as part of save_annotation; other users' drafts on the same doc
are preserved.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Locks (Service + Routes + Background Sweep)

**Goal:** Heartbeat-based document locks. Single-row-per-doc, expires_at-based timeout, async sweep job clears expired rows.

**Files:**
- Create: `backend/locks/__init__.py`
- Create: `backend/locks/service.py`
- Create: `backend/locks/models.py`
- Create: `backend/locks/routes.py`
- Create: `backend/locks/sweep.py`
- Modify: `backend/main.py` (mount router + start sweep loop in lifespan)
- Create: `tests/test_locks_service.py`
- Create: `tests/test_locks_routes.py`

- [ ] **Step 1: Create locks package**

Run:
```bash
mkdir -p /Users/barandincoguz/Desktop/deneme/backend/locks
touch /Users/barandincoguz/Desktop/deneme/backend/locks/__init__.py
```

- [ ] **Step 2: Write `tests/test_locks_service.py`**

```python
import time
import pytest
from datetime import datetime, timezone, timedelta
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.locks import service as locks


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) "
        "VALUES ('alice','x','user',?,?), ('bob','x','user',?,?)",
        (now, now, now, now),
    )
    conn.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
        "sentence_count, text_density, estimated_difficulty, created_at) "
        "VALUES ('doc_1','x.json','text',1,1,1.0,'Kolay',?)",
        (now,),
    )
    yield conn
    conn.close()


def test_acquire_creates_lock(db):
    info = locks.acquire(db, document_id="doc_1", user_id=1)
    assert info["document_id"] == "doc_1"
    assert info["user_id"] == 1
    assert "expires_at" in info


def test_acquire_unknown_document_raises(db):
    with pytest.raises(locks.DocumentNotFound):
        locks.acquire(db, document_id="nonexistent", user_id=1)


def test_acquire_held_by_other_raises_conflict(db):
    locks.acquire(db, document_id="doc_1", user_id=1)
    with pytest.raises(locks.LockHeldByOther) as exc:
        locks.acquire(db, document_id="doc_1", user_id=2)
    info = exc.value.info
    assert info["by_user_id"] == 1
    assert info["by_username"] == "alice"
    assert "expires_at" in info


def test_acquire_same_user_refreshes(db):
    """Acquiring an already-owned lock just refreshes the heartbeat."""
    first = locks.acquire(db, document_id="doc_1", user_id=1)
    time.sleep(0.01)  # ensure timestamp tick
    second = locks.acquire(db, document_id="doc_1", user_id=1)
    assert second["expires_at"] >= first["expires_at"]


def test_heartbeat_extends_expiry(db):
    info1 = locks.acquire(db, document_id="doc_1", user_id=1)
    time.sleep(0.01)
    info2 = locks.heartbeat(db, document_id="doc_1", user_id=1)
    assert info2["expires_at"] >= info1["expires_at"]


def test_heartbeat_by_non_holder_raises(db):
    locks.acquire(db, document_id="doc_1", user_id=1)
    with pytest.raises(locks.NotLockHolder):
        locks.heartbeat(db, document_id="doc_1", user_id=2)


def test_heartbeat_when_no_lock_raises(db):
    with pytest.raises(locks.NotLockHolder):
        locks.heartbeat(db, document_id="doc_1", user_id=1)


def test_release_by_holder(db):
    locks.acquire(db, document_id="doc_1", user_id=1)
    locks.release(db, document_id="doc_1", user_id=1)
    assert locks.get_lock(db, "doc_1") is None


def test_release_by_non_holder_raises(db):
    locks.acquire(db, document_id="doc_1", user_id=1)
    with pytest.raises(locks.NotLockHolder):
        locks.release(db, document_id="doc_1", user_id=2)


def test_release_when_absent_no_op(db):
    """Releasing a lock that was already cleared (e.g. by sweep) is silent."""
    locks.release(db, document_id="doc_1", user_id=1)  # does not raise


def test_force_release_drops_lock(db):
    locks.acquire(db, document_id="doc_1", user_id=1)
    locks.force_release(db, document_id="doc_1")
    assert locks.get_lock(db, "doc_1") is None


def test_sweep_removes_expired_only(db):
    """Insert a lock with past expires_at; sweep deletes it. Active lock survives."""
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    db.execute(
        "INSERT INTO document_locks(document_id, user_id, acquired_at, last_heartbeat, expires_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("doc_1", 1, past, past, past),
    )
    # also insert a fresh active lock for a fake doc
    db.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
        "sentence_count, text_density, estimated_difficulty, created_at) "
        "VALUES ('doc_2','y.json','text',1,1,1.0,'Kolay',datetime('now'))"
    )
    locks.acquire(db, document_id="doc_2", user_id=2)

    released = locks.sweep_expired(db)
    assert "doc_1" in released
    assert "doc_2" not in released

    assert locks.get_lock(db, "doc_1") is None
    assert locks.get_lock(db, "doc_2") is not None
```

- [ ] **Step 3: Implement `backend/locks/service.py`**

```python
"""Document lock service — heartbeat-based exclusive editing.

Lifecycle:
  acquire    → creates a row (or refreshes if same user holds it)
  heartbeat  → bumps expires_at by lock.expires_seconds
  release    → deletes the row (idempotent; raises if held by another user)
  sweep_expired → background job: deletes rows where expires_at < now

Settings (admin-tunable via site_settings):
  lock.expires_seconds        default 300 (5 minutes)
  lock.heartbeat_interval_seconds default 30 (frontend uses this)
"""
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

from backend.shared import settings


DEFAULT_LOCK_EXPIRES_SECONDS = 300


class LockServiceError(Exception):
    pass


class DocumentNotFound(LockServiceError):
    pass


class NotLockHolder(LockServiceError):
    """Caller does not currently hold the lock (or no lock exists)."""


class LockHeldByOther(LockServiceError):
    """Lock exists and is held by another user."""

    def __init__(self, info: dict):
        super().__init__(f"locked by {info.get('by_username')!r}")
        self.info = info


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _document_exists(db: sqlite3.Connection, document_id: str) -> bool:
    return db.execute(
        "SELECT 1 FROM documents_meta WHERE document_id=?", (document_id,)
    ).fetchone() is not None


def _expires_seconds(db: sqlite3.Connection) -> int:
    return settings.get_int(db, "lock.expires_seconds", DEFAULT_LOCK_EXPIRES_SECONDS)


def _row_to_info(row: sqlite3.Row, db: sqlite3.Connection) -> dict:
    user = db.execute(
        "SELECT username FROM users WHERE id=?", (row["user_id"],)
    ).fetchone()
    return {
        "document_id": row["document_id"],
        "user_id": row["user_id"],
        "by_user_id": row["user_id"],
        "by_username": user["username"] if user else None,
        "acquired_at": row["acquired_at"],
        "last_heartbeat": row["last_heartbeat"],
        "expires_at": row["expires_at"],
    }


def get_lock(db: sqlite3.Connection, document_id: str) -> Optional[dict]:
    """Read current lock state for a document. Sweeps if expired."""
    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    if row is None:
        return None
    if row["expires_at"] < _now().isoformat():
        db.execute("DELETE FROM document_locks WHERE document_id=?", (document_id,))
        return None
    return _row_to_info(row, db)


def acquire(db: sqlite3.Connection, *, document_id: str, user_id: int) -> dict:
    """Create or refresh a lock. Raises LockHeldByOther if another user holds it."""
    if not _document_exists(db, document_id):
        raise DocumentNotFound(document_id)

    existing = get_lock(db, document_id)
    if existing is not None and existing["user_id"] != user_id:
        raise LockHeldByOther(existing)

    now = _now()
    expires = now + timedelta(seconds=_expires_seconds(db))
    db.execute(
        """
        INSERT INTO document_locks(document_id, user_id, acquired_at, last_heartbeat, expires_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(document_id) DO UPDATE SET
            user_id=excluded.user_id,
            last_heartbeat=excluded.last_heartbeat,
            expires_at=excluded.expires_at
        """,
        (document_id, user_id, now.isoformat(), now.isoformat(), expires.isoformat()),
    )
    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    return _row_to_info(row, db)


def heartbeat(db: sqlite3.Connection, *, document_id: str, user_id: int) -> dict:
    """Bump expires_at. Raises NotLockHolder if user doesn't hold the lock."""
    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        raise NotLockHolder(document_id)

    now = _now()
    expires = now + timedelta(seconds=_expires_seconds(db))
    db.execute(
        "UPDATE document_locks SET last_heartbeat=?, expires_at=? WHERE document_id=?",
        (now.isoformat(), expires.isoformat(), document_id),
    )
    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    return _row_to_info(row, db)


def release(db: sqlite3.Connection, *, document_id: str, user_id: int) -> None:
    """Drop lock. No-op if no lock; raises NotLockHolder if held by another user."""
    row = db.execute(
        "SELECT * FROM document_locks WHERE document_id=?", (document_id,)
    ).fetchone()
    if row is None:
        return  # already released — silent
    if row["user_id"] != user_id:
        raise NotLockHolder(document_id)
    db.execute("DELETE FROM document_locks WHERE document_id=?", (document_id,))


def force_release(db: sqlite3.Connection, *, document_id: str) -> None:
    """Admin override; unconditional delete."""
    db.execute("DELETE FROM document_locks WHERE document_id=?", (document_id,))


def sweep_expired(db: sqlite3.Connection) -> list[str]:
    """Delete expired locks; return released document_ids."""
    now_iso = _now().isoformat()
    rows = db.execute(
        "SELECT document_id FROM document_locks WHERE expires_at < ?", (now_iso,),
    ).fetchall()
    released = [r["document_id"] for r in rows]
    if released:
        db.execute("DELETE FROM document_locks WHERE expires_at < ?", (now_iso,))
    return released
```

- [ ] **Step 4: Run service tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_locks_service.py -q
```
Expected: all pass.

- [ ] **Step 5: Write `backend/locks/models.py`**

```python
"""Pydantic response models for lock endpoints."""
from typing import Optional
from pydantic import BaseModel


class LockInfo(BaseModel):
    document_id: str
    user_id: int
    by_username: Optional[str]
    acquired_at: str
    last_heartbeat: str
    expires_at: str


class LockConflict(BaseModel):
    error: str = "lock_held_by_other"
    by_user_id: int
    by_username: Optional[str]
    acquired_at: str
    expires_at: str


class OkResponse(BaseModel):
    ok: bool = True
```

- [ ] **Step 6: Write `backend/locks/routes.py`**

```python
"""Lock HTTP endpoints. Auth: require_passed_training on all."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.locks import service
from backend.locks.models import LockInfo, OkResponse
from backend.users.deps import get_db, require_passed_training


router = APIRouter(prefix="/api/locks", tags=["locks"])


def _strip_dup_keys(info: dict) -> dict:
    """Service returns both user_id and by_user_id (same value); keep the response shape clean."""
    return {k: v for k, v in info.items() if k != "by_user_id"}


@router.post("/{document_id}/acquire", response_model=LockInfo)
def acquire(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        info = service.acquire(db, document_id=document_id, user_id=user["id"])
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    except service.LockHeldByOther as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "lock_held_by_other",
                "by_user_id": e.info["by_user_id"],
                "by_username": e.info["by_username"],
                "acquired_at": e.info["acquired_at"],
                "expires_at": e.info["expires_at"],
            },
        )
    return _strip_dup_keys(info)


@router.post("/{document_id}/heartbeat", response_model=LockInfo)
def heartbeat(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        info = service.heartbeat(db, document_id=document_id, user_id=user["id"])
    except service.NotLockHolder:
        raise HTTPException(status_code=404, detail="lock not found or not held by you")
    return _strip_dup_keys(info)


@router.post("/{document_id}/release", response_model=OkResponse)
def release(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    try:
        service.release(db, document_id=document_id, user_id=user["id"])
    except service.NotLockHolder:
        raise HTTPException(status_code=404, detail="lock held by another user")
    return {"ok": True}
```

- [ ] **Step 7: Write `backend/locks/sweep.py`**

```python
"""Background sweep — periodically clears expired locks.

Runs every `interval_seconds` (default 60). Started from main.py lifespan,
cancelled on shutdown. Single-process; safe with WAL mode.

SSE event emission ('lock_released' broadcast) is added in Paket 7.
"""
import asyncio
import logging
from typing import Optional

from backend import config
from backend.shared.db import connect
from backend.locks import service

log = logging.getLogger(__name__)


async def sweep_loop(interval_seconds: int = 60) -> None:
    """Async loop. Cancel via task.cancel()."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            conn = connect(config.DB_PATH)
            try:
                released = service.sweep_expired(conn)
                if released:
                    log.info("Lock sweep released %d locks: %s", len(released), released)
            finally:
                conn.close()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("Lock sweep iteration failed")


_task: Optional[asyncio.Task] = None


def start(interval_seconds: int = 60) -> asyncio.Task:
    """Start the sweep task; returns the task handle for shutdown cancellation."""
    global _task
    _task = asyncio.create_task(sweep_loop(interval_seconds))
    return _task


def stop() -> None:
    """Cancel the running sweep task (no-op if not started)."""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
    _task = None
```

- [ ] **Step 8: Wire router + sweep into `backend/main.py`**

Modify `backend/main.py`. Add to imports (after `from backend.documents.routes import router as documents_router`):

```python
from backend.locks.routes import router as locks_router
from backend.locks import sweep as locks_sweep
```

In the `lifespan` function, after the startup audit log block (and before `yield`), add:

```python
    sweep_task = locks_sweep.start(interval_seconds=60)
```

After `yield`, before the shutdown audit log block, add:

```python
    locks_sweep.stop()
    try:
        await sweep_task
    except Exception:
        pass
```

After existing `app.include_router(annotations_router)` (added in Task 3), add:

```python
app.include_router(locks_router)
```

The full updated `lifespan` block should look like:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        applied = apply_migrations(conn, discover_migrations())
        audit.log_system_event(
            conn, "startup", "info",
            message=f"app v{VERSION} started; migrations applied: {applied}",
            extra={"version": VERSION, "migrations_applied": applied},
        )
    finally:
        conn.close()

    sweep_task = locks_sweep.start(interval_seconds=60)
    yield

    locks_sweep.stop()
    try:
        await sweep_task
    except Exception:
        pass

    conn = connect(config.DB_PATH)
    try:
        audit.log_system_event(conn, "shutdown", "info", message=f"app v{VERSION} shutting down")
    finally:
        conn.close()
```

- [ ] **Step 9: Write `tests/test_locks_routes.py`**

```python
def test_acquire_returns_lock_info(passed_user, ingest_doc):
    ingest_doc("doc_test")
    r = passed_user["client"].post("/api/locks/doc_test/acquire")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document_id"] == "doc_test"
    assert body["by_username"] == "alice"
    assert "expires_at" in body


def test_acquire_unknown_document_404(passed_user):
    r = passed_user["client"].post("/api/locks/nonexistent/acquire")
    assert r.status_code == 404


def test_acquire_held_by_other_409(second_passed_user, ingest_doc):
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")

    ctx["login"]("alice")
    c.post("/api/locks/doc_test/acquire")

    ctx["login"]("bob")
    r = c.post("/api/locks/doc_test/acquire")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "lock_held_by_other"
    assert detail["by_username"] == "alice"


def test_heartbeat_extends_expiry(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("doc_test")
    first = c.post("/api/locks/doc_test/acquire").json()
    second = c.post("/api/locks/doc_test/heartbeat").json()
    assert second["expires_at"] >= first["expires_at"]


def test_heartbeat_by_non_holder_404(second_passed_user, ingest_doc):
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")
    ctx["login"]("alice")
    c.post("/api/locks/doc_test/acquire")
    ctx["login"]("bob")
    r = c.post("/api/locks/doc_test/heartbeat")
    assert r.status_code == 404


def test_release_by_holder(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("doc_test")
    c.post("/api/locks/doc_test/acquire")
    r = c.post("/api/locks/doc_test/release")
    assert r.status_code == 200


def test_release_when_no_lock_is_ok(passed_user, ingest_doc):
    """Idempotent: releasing a non-held lock is a 200 (because release() is silent on absent)."""
    ingest_doc("doc_test")
    r = passed_user["client"].post("/api/locks/doc_test/release")
    assert r.status_code == 200


def test_release_when_held_by_other_404(second_passed_user, ingest_doc):
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")
    ctx["login"]("alice")
    c.post("/api/locks/doc_test/acquire")
    ctx["login"]("bob")
    r = c.post("/api/locks/doc_test/release")
    assert r.status_code == 404


def test_save_releases_callers_lock(passed_user, ingest_doc):
    """Saving an annotation while holding the lock automatically releases it."""
    c = passed_user["client"]
    ingest_doc("doc_test")
    c.post("/api/locks/doc_test/acquire")
    c.post("/api/annotations", json={"document_id": "doc_test", "references": []})
    # Heartbeat should now 404 because lock was released
    r = c.post("/api/locks/doc_test/heartbeat")
    assert r.status_code == 404
```

- [ ] **Step 10: Run tests**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_locks_routes.py tests/test_locks_service.py -q
```
Expected: all pass.

- [ ] **Step 11: Run full suite**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest -q
```
Expected: 0 failed.

- [ ] **Step 12: Commit**

```bash
cd /Users/barandincoguz/Desktop/deneme && git -c user.email=maarkval@icloud.com -c user.name=baran add backend/locks backend/main.py tests/test_locks_service.py tests/test_locks_routes.py && git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(locks): add heartbeat-based document locks + async sweep

document_locks single-row-per-doc with expires_at-based timeout (default
5 min, admin-tunable). acquire/heartbeat/release endpoints; 409 on conflict
returns by_username + expires_at. Background async sweep clears expired
rows every 60s (started from app lifespan). Saving an annotation
automatically releases the caller's lock.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: End-to-End Multi-User Flow + Tag

**Goal:** Single test that exercises the realistic two-user chain review path: lock → save → second user locks → reads chain → saves → diff=0 path → completion → drafts cleared correctly. Confirms all subsystems compose. Then tag `paket-5-annotations-chain`.

**Files:**
- Create: `tests/test_paket5_e2e.py`

- [ ] **Step 1: Write `tests/test_paket5_e2e.py`**

```python
def _ref(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "x"}
    base.update(kwargs)
    return base


def test_full_chain_review_two_users(second_passed_user, ingest_doc):
    """Complete realistic flow:
       alice locks → drafts → saves (creates v1) → lock auto-released
       bob locks doc → reads chain (sees v1 by alice) → saves equivalent refs
       → diff=0 path → marks complete → uncomplete by alice → second complete by bob
    """
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_e2e")

    refs_v1 = [
        _ref(kanun_no="193", madde="37", source_text="GVK madde 37"),
        _ref(kanun_no="5520", madde="5", source_text="KVK madde 5"),
    ]

    # --- alice phase ---
    ctx["login"]("alice")
    r = c.post("/api/locks/doc_e2e/acquire")
    assert r.status_code == 200

    # alice drafts before saving
    c.put("/api/drafts/doc_e2e", json={"references": [_ref(source_text="alice wip")]})
    assert c.get("/api/drafts/doc_e2e").status_code == 200

    r = c.post("/api/annotations", json={"document_id": "doc_e2e", "references": refs_v1})
    assert r.status_code == 200
    assert r.json()["is_new"] is True
    assert r.json()["is_diff_zero"] is False

    # alice's draft cleared by save; lock released by save
    assert c.get("/api/drafts/doc_e2e").status_code == 404
    assert c.post("/api/locks/doc_e2e/heartbeat").status_code == 404

    # --- bob phase ---
    ctx["login"]("bob")
    r = c.post("/api/locks/doc_e2e/acquire")
    assert r.status_code == 200

    chain = c.get("/api/documents/doc_e2e/annotation").json()["chain"]
    assert len(chain) == 1
    assert chain[0]["username"] == "alice"
    assert chain[0]["action"] == "create"

    # bob saves the same content reordered → set semantics → diff=0
    refs_v2 = list(reversed(refs_v1))
    r = c.post("/api/annotations", json={"document_id": "doc_e2e", "references": refs_v2})
    assert r.status_code == 200
    assert r.json()["is_diff_zero"] is True

    chain = c.get("/api/documents/doc_e2e/annotation").json()["chain"]
    assert len(chain) == 2
    assert chain[1]["username"] == "bob"
    assert chain[1]["is_diff_zero"] is True

    # bob marks complete
    r = c.post("/api/annotations/doc_e2e/complete", json={"completed": True})
    assert r.status_code == 200

    detail = c.get("/api/documents/doc_e2e/annotation").json()["annotation"]
    assert detail["is_completed"] is True
    assert detail["completed_by_user_id"] == ctx["bob"]["id"]

    # alice can uncomplete
    ctx["login"]("alice")
    r = c.post("/api/annotations/doc_e2e/complete", json={"completed": False})
    assert r.status_code == 200
    detail = c.get("/api/documents/doc_e2e/annotation").json()["annotation"]
    assert detail["is_completed"] is False
    assert detail["completed_by_user_id"] is None


def test_duplicate_save_unchanged_on_failure(passed_user, ingest_doc):
    """Validation failures shouldn't leave partial state."""
    c = passed_user["client"]
    ingest_doc("doc_test")

    c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref(kanun_no="193", source_text="x")],
    })

    # send a duplicate-bearing payload (rejected)
    r = c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [
            _ref(kanun_no="5520", source_text="y"),
            _ref(kanun_no="5520", source_text="y"),
        ],
    })
    assert r.status_code == 422

    # state untouched
    detail = c.get("/api/documents/doc_test/annotation").json()["annotation"]
    assert len(detail["references"]) == 1
    assert detail["references"][0]["kanun_no"] == "193"


def test_denormalized_index_in_sync_after_chain(second_passed_user, ingest_doc):
    """After a 2-version chain, denormalized table reflects the *current* refs only."""
    from backend.shared.db import connect
    from backend import config

    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_test")

    ctx["login"]("alice")
    c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref(kanun_no="193", source_text="x")],
    })
    ctx["login"]("bob")
    c.post("/api/annotations", json={
        "document_id": "doc_test",
        "references": [_ref(kanun_no="5520", source_text="y")],
    })

    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT * FROM annotation_references WHERE document_id='doc_test' ORDER BY seq"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    assert rows[0]["kanun_no"] == "5520"
```

- [ ] **Step 2: Run E2E test**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest tests/test_paket5_e2e.py -q
```
Expected: 3 passed.

- [ ] **Step 3: Run full suite (final regression check)**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m pytest -q
```
Expected: all green. Print the final test count for the commit message.

- [ ] **Step 4: Manual smoke test (optional but recommended)**

Run:
```bash
cd /Users/barandincoguz/Desktop/deneme && python -m backend.cli migrate
```
Expected: "No pending migrations." (since dev DB exists; or applies v0001 on a fresh DB).

```bash
cd /Users/barandincoguz/Desktop/deneme && python -c "from backend.main import app; print(sorted([r.path for r in app.routes if hasattr(r,'path')]))"
```
Expected: list includes `/api/annotations`, `/api/annotations/{document_id}/skip`, `/api/annotations/{document_id}/complete`, `/api/documents/{document_id}/annotation`, `/api/drafts/{document_id}`, `/api/locks/{document_id}/acquire`, `/api/locks/{document_id}/heartbeat`, `/api/locks/{document_id}/release`.

- [ ] **Step 5: Commit + tag**

```bash
cd /Users/barandincoguz/Desktop/deneme && git -c user.email=maarkval@icloud.com -c user.name=baran add tests/test_paket5_e2e.py && git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
test(paket5): add multi-user chain review E2E

Covers: alice locks → drafts → saves (v1) → auto-release; bob locks → reads
chain → saves reordered same content → diff=0 verified; complete toggle by
either user; denormalized index always reflects current refs only;
validation errors leave previous state intact.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)" && git tag paket-5-annotations-chain
```

---

## Verification

After Task 6 completes, the following should be true:

- All Paket 5 packages exist with the file layout in §"Dosya Yapısı"
- `python -m pytest -q` reports 0 failures
- `paket-5-annotations-chain` tag created on the final commit
- `git log --oneline -10` shows 6 atomic commits (one per task)
- `python -c "from backend.main import app"` boots cleanly (sweep loop starts on app startup, cancelled on shutdown)

## Open Items For Later Packages (NOT this paket)

These are surfaced to the next planner — do not implement here:

- **Paket 6 (3-Tab Shuffle Feed):** New (no annotation), Review (annotation exists, not completed), Verified (completed) — uses the data this paket persists
- **Paket 7 (SSE):** Add `lock_acquired`, `lock_released`, `annotation_saved`, `complete_marked` event broadcasts inside the routes/services we just wrote. The hooks are clean — service functions return enough context to broadcast
- **Paket 8 (Behavioral Detectors):** Hooks into `audit.log_activity` calls we already write (`annotation_save`, `annotation_skip`, `complete_mark`)
- **Paket 9 (Gamification):** Hooks into the same activity events for XP delta + streak tracking
- **Paket 11 (Admin Panel):** Adds `POST /api/admin/locks/{id}/force-release` route over the already-existing `service.force_release()`

## Self-Review Notes

- **Spec coverage:** `references_json`/`annotation_versions`/`drafts`/`document_locks`/`annotation_references` tables — all written and read; set-semantic diff implemented; hybrid completion (manual toggle + diff=0 surfaced via `is_diff_zero` flag) covered; per-user draft semantics verified by `test_save_clears_callers_draft_only` and `test_drafts_are_per_user`; lock heartbeat + 409-no-queue covered; SSE explicitly deferred to Paket 7.
- **Type consistency:** `save_annotation` returns `{is_new, is_diff_zero, current_references}` — matches `SaveAnnotationResponse` model and route consumers. `acquire/heartbeat` returns same `LockInfo` shape (sans `by_user_id` duplicate stripped at the route boundary). `references` field name uniform across draft and annotation routes.
- **No placeholders:** every step contains the actual file content / command / expected output. Validation errors mapped to status codes consistently (404 for unknown doc/lock/annotation, 422 for bad references, 409 for lock conflict).
- **Atomicity:** save_annotation, skip_annotation, set_complete each wrap in BEGIN/COMMIT/ROLLBACK. Test `test_duplicate_save_unchanged_on_failure` verifies rollback semantics (the validator runs before BEGIN, but the test still proves no partial state).

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-05-package-5-annotations-chain.md`.**
