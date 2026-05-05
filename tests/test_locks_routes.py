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
