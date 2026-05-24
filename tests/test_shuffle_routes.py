import re

import pytest

from backend.shuffle import service as shuffle_service
from backend.shuffle.routes import _SORT_PATTERN


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
    # Total is returned only on page 0 (polish-phase P3 — COUNT(*) is
    # the hottest scan in shuffle/service.py; pages 1+ elide it and
    # the frontend locks onto allPages[0].total).
    assert page1["total"] == 5
    assert page2["total"] is None
    assert page3["total"] is None
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


def test_feed_tabs_mutually_exclusive_via_http(passed_user, ingest_doc):
    """Doc 1 unannotated → new; Doc 2 annotated → review; Doc 3 completed → verified."""
    c = passed_user["client"]
    for i in range(1, 4):
        ingest_doc(f"doc_x{i}")

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


# --- Phase 6: cross-team document_id DESC ordering ---------------------------
# Frontend store v4 sends sort=document_id&order=desc on every feed call.
# Before Wave A, the route regex omitted document_id → every load 422.
# These tests exercise the regex on the HTTP edge (service-layer tests
# bypass FastAPI Query validation and could not have caught the drift).

def test_feed_sort_document_id_desc_new_tab(passed_user, ingest_doc):
    c = passed_user["client"]
    for did in ("doc_a", "doc_b", "doc_c"):
        ingest_doc(did)
    r = c.get("/api/feed?tab=new&sort=document_id&order=desc")
    assert r.status_code == 200, r.text
    ids = [i["document_id"] for i in r.json()["items"]]
    assert ids == ["doc_c", "doc_b", "doc_a"]


def test_feed_sort_document_id_desc_review_tab(passed_user, ingest_doc):
    c = passed_user["client"]
    for did in ("doc_a", "doc_b", "doc_c"):
        ingest_doc(did)
        c.post("/api/annotations", json={"document_id": did, "references": []})
    r = c.get("/api/feed?tab=review&sort=document_id&order=desc")
    assert r.status_code == 200, r.text
    ids = [i["document_id"] for i in r.json()["items"]]
    assert ids == ["doc_c", "doc_b", "doc_a"]


def test_feed_sort_document_id_desc_verified_tab(passed_user, ingest_doc):
    c = passed_user["client"]
    for did in ("doc_a", "doc_b", "doc_c"):
        ingest_doc(did)
        c.post("/api/annotations", json={"document_id": did, "references": []})
        c.post(f"/api/annotations/{did}/complete", json={"completed": True})
    r = c.get("/api/feed?tab=verified&sort=document_id&order=desc")
    assert r.status_code == 200, r.text
    ids = [i["document_id"] for i in r.json()["items"]]
    assert ids == ["doc_c", "doc_b", "doc_a"]


def test_feed_invalid_sort_returns_422(passed_user):
    """Regression guard: unknown sort key still rejected by FastAPI Query."""
    r = passed_user["client"].get("/api/feed?tab=new&sort=zzzzz")
    assert r.status_code == 422


@pytest.mark.parametrize("sort_key", sorted(shuffle_service.SORT_COLUMNS.keys()))
def test_route_regex_contains_every_service_sort_column(sort_key):
    # Invariant: every service.SORT_COLUMNS key must match route _SORT_PATTERN,
    # else legal sort keys 422 in production despite passing service tests.
    assert re.fullmatch(_SORT_PATTERN, sort_key), (
        f"SORT_COLUMNS key {sort_key!r} not matched by _SORT_PATTERN "
        f"{_SORT_PATTERN!r}; contract drift between route and service."
    )
