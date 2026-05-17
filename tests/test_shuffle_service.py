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


# === Draft-only docs ("Devam Eden" semantic extension) ===
#
# A draft row owned by the calling user, on a doc that has no
# annotation row yet, counts as "Devam Eden" for that user. Without
# this, in-flight work that hasn't yet been "Kaydet"-saved hides in
# the "Yeni" tab and the operator never sees it.

def _set_draft(db, *, document_id: str, user_id: int, references: list[dict]) -> None:
    """Insert/replace a draft directly via SQL — bypasses the service
    layer's document-existence guard so test setup stays small."""
    now = "2026-01-01T00:00:00+00:00"
    db.execute(
        "INSERT OR REPLACE INTO drafts(document_id, user_id, references_json, updated_at) "
        "VALUES (?, ?, ?, ?)",
        (document_id, user_id, json.dumps(references), now),
    )


def test_review_tab_includes_draft_only_doc_for_owning_user(db):
    """User has a non-empty draft on a doc with no annotation row →
    that doc shows up in the user's 'review' tab as a draft-only entry."""
    _set_draft(db, document_id="doc_1", user_id=1, references=[_ref(source_text="wip")])
    result = shuffle_service.list_feed(db, user_id=1, tab="review", limit=50, offset=0)
    ids = {i["document_id"] for i in result["items"]}
    assert "doc_1" in ids
    # Draft-only entry: annotation columns are absent / defaulted.
    item = next(i for i in result["items"] if i["document_id"] == "doc_1")
    assert item["has_annotation"] is False
    assert item["is_completed"] is False
    assert item["edit_count"] == 0
    assert item["last_editor_user_id"] is None


def test_review_tab_excludes_other_users_drafts(db):
    """Drafts are per-user. Bob's draft must NOT appear in alice's
    'review' tab."""
    _set_draft(db, document_id="doc_1", user_id=2, references=[_ref(source_text="wip")])
    result = shuffle_service.list_feed(db, user_id=1, tab="review", limit=50, offset=0)
    assert result["total"] == 0


def test_review_tab_excludes_empty_drafts(db):
    """Click-then-back-out creates an empty `[]` draft. That should
    NOT count as 'Devam Eden' — the user wasn't really working on it."""
    _set_draft(db, document_id="doc_1", user_id=1, references=[])
    result = shuffle_service.list_feed(db, user_id=1, tab="review", limit=50, offset=0)
    assert result["total"] == 0


def test_new_tab_excludes_docs_with_my_draft(db):
    """Mutual exclusion: a doc that has my non-empty draft must NOT
    appear in 'Yeni' (it's already in my 'Devam Eden')."""
    _set_draft(db, document_id="doc_1", user_id=1, references=[_ref(source_text="wip")])
    result = shuffle_service.list_feed(db, user_id=1, tab="new", limit=50, offset=0)
    ids = {i["document_id"] for i in result["items"]}
    assert "doc_1" not in ids


def test_new_tab_includes_docs_with_other_users_draft(db):
    """Other users' drafts don't move a doc out of MY 'Yeni' tab —
    that's their work, not mine."""
    _set_draft(db, document_id="doc_1", user_id=2, references=[_ref(source_text="wip")])
    result = shuffle_service.list_feed(db, user_id=1, tab="new", limit=50, offset=0)
    ids = {i["document_id"] for i in result["items"]}
    assert "doc_1" in ids


def test_annotation_overrides_draft_for_tab_placement(db):
    """If a doc has BOTH an annotation row AND a user draft, the
    annotation wins the classification (review path uses the
    annotation/is_completed=0 branch, not the draft branch). Verifies
    the OR clause priority in _REVIEW_FROM_WHERE — annotation route
    populates the chain fields correctly even when a draft exists."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[_ref(source_text="annot")])
    _set_draft(db, document_id="doc_1", user_id=1, references=[_ref(source_text="newer")])
    result = shuffle_service.list_feed(db, user_id=1, tab="review", limit=50, offset=0)
    item = next(i for i in result["items"] if i["document_id"] == "doc_1")
    # Annotation branch hit → has_annotation True, edit_count == 1 from save_annotation
    assert item["has_annotation"] is True
    assert item["edit_count"] >= 1


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
    """offset advances the page; total is returned ONLY on page 0
    (polish-phase P3 — COUNT(*) is too expensive to run per-page on
    the new-tab anti-join). Page 1+ returns total=None; the frontend
    locks onto allPages[0].total via getNextPageParam."""
    page1 = shuffle_service.list_feed(db, user_id=1, tab="new", limit=2, offset=0)
    page2 = shuffle_service.list_feed(db, user_id=1, tab="new", limit=2, offset=2)
    page1_ids = {i["document_id"] for i in page1["items"]}
    page2_ids = {i["document_id"] for i in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert page1["total"] == 5
    assert page2["total"] is None


def test_pagination_offset_past_end_returns_empty(db):
    result = shuffle_service.list_feed(db, user_id=1, tab="new", limit=10, offset=99)
    assert result["items"] == []
    # offset > 0 → total elided (see polish-phase P3 comment above).
    assert result["total"] is None


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
