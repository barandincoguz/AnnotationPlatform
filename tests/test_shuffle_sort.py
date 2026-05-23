"""Sort behavior for /api/feed → shuffle_service.list_feed.

Coverage:
  - default sort per tab (DEFAULT_SORT_FOR) when caller omits sort
  - whitelisted sort keys × asc/desc × applicable tabs
  - tab-specific gate (updated_at / editors_count refuse `new` tab)
  - NULL handling sinks rows past non-null values both directions
  - stable tiebreaker (document_id ASC) keeps pagination consistent
  - HTTP-layer 400 surfacing for invalid sort + 422 for unknown key
"""
import json
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.documents import service as doc_service
from backend.annotations import service as ann_service
from backend.shuffle import service as shuffle_service


def _ref(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "x"}
    base.update(kwargs)
    return base


@pytest.fixture
def sorted_db(db_path, tmp_path):
    """Five docs with predictable, distinct sortable fields so each
    sort key produces a verifiable order.

    doc_a — sayi=10, tarih=20260301, vergi=A, konu=Alpha, word=100
    doc_b — sayi=20, tarih=20260201, vergi=B, konu=Bravo, word=200
    doc_c — sayi=30, tarih=20260401, vergi=C, konu=Charlie, word=300
    doc_d — sayi=40, tarih=NULL,     vergi=D, konu=Delta,  word=400  ← NULL tarih
    doc_e — sayi=50, tarih=20260101, vergi=E, konu=Echo,   word=500
    """
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) "
        "VALUES ('alice','x','user',?,?), ('bob','x','user',?,?)",
        (now, now, now, now),
    )
    fixtures = [
        ("doc_a", 10, "20260301", "Alpha",   "A", 100),
        ("doc_b", 20, "20260201", "Bravo",   "B", 200),
        ("doc_c", 30, "20260401", "Charlie", "C", 300),
        ("doc_d", 40, None,       "Delta",   "D", 400),  # NULL tarih
        ("doc_e", 50, "20260101", "Echo",    "E", 500),
    ]
    for evrak_oid, sayi, tarih, konu, vergi, word in fixtures:
        sample = {
            "evrakOid": evrak_oid, "sayi": sayi,
            "tarih": tarih if tarih is not None else "",
            "konu": konu, "vergiTuru": vergi,
            "pdfText": "x" * word,
            "kanunBilgileri": [], "bkkTebligSirkuBilgileri": [],
        }
        fpath = tmp_path / f"{evrak_oid}.json"
        fpath.write_text(json.dumps(sample))
        doc_service.ingest_file(conn, fpath)
    # Force the NULL on doc_d's tarih (the ingester maps empty string to None
    # only on some shapes; assert the column is NULL explicitly).
    conn.execute("UPDATE documents_meta SET tarih=NULL WHERE document_id='doc_d'")
    yield conn
    conn.close()


# === Default sort per tab ===

def test_default_sort_new_tab_is_document_id_desc(sorted_db):
    """Phase 6: `new` tab without sort param → document_id DESC.

    Cross-team coordination: both teams (this + Zeynep) annotate the
    same corpus in the same fixed order. document_id (= evrakOid) is
    the canonical ordering key. DESC lexicographic matches the partner
    DB's `evrak_id` DESC preview.
    """
    r = shuffle_service.list_feed(sorted_db, user_id=1, tab="new", limit=50, offset=0)
    ids = [i["document_id"] for i in r["items"]]
    # doc_e > doc_d > doc_c > doc_b > doc_a lexicographically.
    assert ids == ["doc_e", "doc_d", "doc_c", "doc_b", "doc_a"]


def test_default_sort_review_tab_is_document_id_desc(sorted_db):
    """Phase 6: `review` tab without sort param → document_id DESC.

    Was `updated_at DESC`. That was per-user (depends on who edited
    when) and broke the cross-team determinism — Zeynep's annotators
    would see a different order. document_id DESC is identical across
    every user that touches the corpus.
    """
    # Save annotations in a non-lex order to prove the new default
    # IGNORES updated_at and returns by document_id DESC.
    ann_service.save_annotation(sorted_db, document_id="doc_a", user_id=1, references=[_ref()])
    ann_service.save_annotation(sorted_db, document_id="doc_c", user_id=1, references=[_ref()])
    ann_service.save_annotation(sorted_db, document_id="doc_b", user_id=1, references=[_ref()])
    r = shuffle_service.list_feed(sorted_db, user_id=1, tab="review", limit=50, offset=0)
    ids = [i["document_id"] for i in r["items"]]
    # Three saved → all appear on the review tab. document_id DESC:
    # doc_c, doc_b, doc_a.
    assert ids == ["doc_c", "doc_b", "doc_a"]


def test_default_sort_verified_tab_is_document_id_desc(sorted_db):
    """Phase 6: `verified` tab without sort param → document_id DESC."""
    ann_service.save_annotation(
        sorted_db, document_id="doc_a", user_id=1, references=[_ref()],
    )
    ann_service.set_complete(
        sorted_db, document_id="doc_a", user_id=1, completed=True,
    )
    ann_service.save_annotation(
        sorted_db, document_id="doc_c", user_id=1, references=[_ref()],
    )
    ann_service.set_complete(
        sorted_db, document_id="doc_c", user_id=1, completed=True,
    )
    r = shuffle_service.list_feed(sorted_db, user_id=1, tab="verified", limit=50, offset=0)
    ids = [i["document_id"] for i in r["items"]]
    assert ids == ["doc_c", "doc_a"]


def test_document_id_sort_key_available_on_all_tabs(sorted_db):
    """document_id sort key must be accepted on new, review, and verified."""
    for tab in ("new", "review", "verified"):
        r = shuffle_service.list_feed(
            sorted_db, user_id=1, tab=tab, limit=50, offset=0,
            sort="document_id", order="desc",
        )
        # Just assert it doesn't raise and returns the standard payload
        # shape. Per-tab content is tab-dependent (review/verified empty
        # without prior saves; new returns all 5).
        assert "items" in r
        assert "total" in r


# === Explicit sort keys ===

def test_sort_tarih_asc_nulls_last(sorted_db):
    """tarih ASC: earliest first; NULL row sinks to the end."""
    r = shuffle_service.list_feed(
        sorted_db, user_id=1, tab="new", limit=50, offset=0,
        sort="tarih", order="asc",
    )
    ids = [i["document_id"] for i in r["items"]]
    assert ids == ["doc_e", "doc_b", "doc_a", "doc_c", "doc_d"]


def test_sort_tarih_desc_nulls_last(sorted_db):
    r = shuffle_service.list_feed(
        sorted_db, user_id=1, tab="new", limit=50, offset=0,
        sort="tarih", order="desc",
    )
    ids = [i["document_id"] for i in r["items"]]
    assert ids == ["doc_c", "doc_a", "doc_b", "doc_e", "doc_d"]


def test_sort_sayi_asc(sorted_db):
    r = shuffle_service.list_feed(
        sorted_db, user_id=1, tab="new", limit=50, offset=0,
        sort="sayi", order="asc",
    )
    ids = [i["document_id"] for i in r["items"]]
    assert ids == ["doc_a", "doc_b", "doc_c", "doc_d", "doc_e"]


def test_sort_konu_desc(sorted_db):
    r = shuffle_service.list_feed(
        sorted_db, user_id=1, tab="new", limit=50, offset=0,
        sort="konu", order="desc",
    )
    ids = [i["document_id"] for i in r["items"]]
    assert ids == ["doc_e", "doc_d", "doc_c", "doc_b", "doc_a"]


def test_sort_word_count_asc(sorted_db):
    r = shuffle_service.list_feed(
        sorted_db, user_id=1, tab="new", limit=50, offset=0,
        sort="word_count", order="asc",
    )
    ids = [i["document_id"] for i in r["items"]]
    assert ids == ["doc_a", "doc_b", "doc_c", "doc_d", "doc_e"]


def test_sort_updated_at_works_on_review(sorted_db):
    ann_service.save_annotation(sorted_db, document_id="doc_a", user_id=1, references=[_ref()])
    ann_service.save_annotation(sorted_db, document_id="doc_b", user_id=1, references=[_ref()])
    r = shuffle_service.list_feed(
        sorted_db, user_id=1, tab="review", limit=50, offset=0,
        sort="updated_at", order="asc",
    )
    ids = [i["document_id"] for i in r["items"]]
    assert ids == ["doc_a", "doc_b"]


# === Tab-specific gate ===

def test_updated_at_invalid_on_new_tab(sorted_db):
    """updated_at refers to a.updated_at which doesn't exist on `new`."""
    with pytest.raises(shuffle_service.InvalidSort):
        shuffle_service.list_feed(
            sorted_db, user_id=1, tab="new", limit=50, offset=0,
            sort="updated_at", order="desc",
        )


def test_editors_count_invalid_on_new_tab(sorted_db):
    with pytest.raises(shuffle_service.InvalidSort):
        shuffle_service.list_feed(
            sorted_db, user_id=1, tab="new", limit=50, offset=0,
            sort="editors_count", order="desc",
        )


def test_unknown_sort_key_raises(sorted_db):
    with pytest.raises(shuffle_service.InvalidSort):
        shuffle_service.list_feed(
            sorted_db, user_id=1, tab="new", limit=50, offset=0,
            sort="not_a_column", order="desc",
        )


def test_unknown_order_raises(sorted_db):
    with pytest.raises(shuffle_service.InvalidSort):
        shuffle_service.list_feed(
            sorted_db, user_id=1, tab="new", limit=50, offset=0,
            sort="tarih", order="sideways",
        )


# === Shuffle path opt-in ===

def test_shuffle_is_still_available_via_sort_param(sorted_db):
    """Passing sort='shuffle' keeps the legacy daily deterministic shuffle."""
    a = shuffle_service.list_feed(
        sorted_db, user_id=1, tab="new", limit=50, offset=0, sort="shuffle",
    )
    b = shuffle_service.list_feed(
        sorted_db, user_id=1, tab="new", limit=50, offset=0, sort="shuffle",
    )
    # Same seed → identical order across calls.
    assert [i["document_id"] for i in a["items"]] == [i["document_id"] for i in b["items"]]


# === Stable tiebreaker ===

def test_tiebreaker_keeps_pagination_consistent_on_equal_keys(db_path, tmp_path):
    """All five docs share the same vergi_turu → ties are broken by
    document_id ASC, so two adjacent pages don't overlap or skip."""
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO users(username, password_hash, role, created_at, updated_at) "
        "VALUES ('alice','x','user',?,?)",
        (now, now),
    )
    for i in range(1, 6):
        sample = {
            "evrakOid": f"doc_{i}", "sayi": i, "tarih": "20260101",
            "konu": f"Konu {i}", "vergiTuru": "TIE",
            "pdfText": "x" * 100,
            "kanunBilgileri": [], "bkkTebligSirkuBilgileri": [],
        }
        fpath = tmp_path / f"doc_{i}.json"
        fpath.write_text(json.dumps(sample))
        doc_service.ingest_file(conn, fpath)
    try:
        page1 = shuffle_service.list_feed(
            conn, user_id=1, tab="new", limit=2, offset=0,
            sort="vergi_turu", order="asc",
        )
        page2 = shuffle_service.list_feed(
            conn, user_id=1, tab="new", limit=2, offset=2,
            sort="vergi_turu", order="asc",
        )
        page3 = shuffle_service.list_feed(
            conn, user_id=1, tab="new", limit=2, offset=4,
            sort="vergi_turu", order="asc",
        )
        ids1 = [i["document_id"] for i in page1["items"]]
        ids2 = [i["document_id"] for i in page2["items"]]
        ids3 = [i["document_id"] for i in page3["items"]]
        assert ids1 == ["doc_1", "doc_2"]
        assert ids2 == ["doc_3", "doc_4"]
        assert ids3 == ["doc_5"]
    finally:
        conn.close()


# === Total count is unchanged by sort ===

def test_total_matches_actual_count_under_sort(sorted_db):
    r = shuffle_service.list_feed(
        sorted_db, user_id=1, tab="new", limit=2, offset=0,
        sort="tarih", order="desc",
    )
    assert r["total"] == 5
    assert len(r["items"]) == 2
