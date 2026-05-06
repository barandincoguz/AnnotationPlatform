"""High-risk invariant audit across Paket 1-6.

Each test pins down a behavior that, if it silently regressed, would either
(a) leak a security/auth gate, (b) corrupt data atomicity, or (c) drift from
the spec's documented semantics. These are red-team tests, not happy-path.
"""
import pytest

from backend.shared.db import connect
from backend import config
from backend.annotations.diff import (
    normalize_references, references_diff, is_diff_zero,
)


def _ref(**kwargs):
    base = {"kanun_no": None, "kanun_ad": None, "madde": None,
            "fikra": None, "bent": None, "source_text": "x"}
    base.update(kwargs)
    return base


# === RISK 1: Auth gate enforcement (require_passed_training) ===

def test_user_without_training_blocked_from_paket5_endpoints(client):
    """Untrained user gets 409 from every Paket 5/6 endpoint.

    Hypothesis: require_passed_training raises 409 with detail.error=
    'training_not_passed' when has_passed_training=0. No bypass.
    """
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("INVITE-AUDIT",),
        )
    finally:
        conn.close()

    r = client.post("/api/auth/register", json={
        "username": "untrained", "password": "password123",
        "invite_code": "INVITE-AUDIT", "email": "u@example.com",
    })
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]

    # Mark manual seen but NOT training passed — simulate a user mid-onboarding
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE users SET has_seen_manual=1 WHERE id=?", (user_id,))
    finally:
        conn.close()

    client.post("/api/auth/login", json={
        "username": "untrained", "password": "password123",
    })

    # Every Paket 5/6 endpoint must be gated
    blocked_endpoints = [
        ("POST", "/api/annotations", {"document_id": "x", "references": []}),
        ("POST", "/api/annotations/x/skip", None),
        ("POST", "/api/annotations/x/complete", {"completed": True}),
        ("GET", "/api/documents/x/annotation", None),
        ("PUT", "/api/drafts/x", {"references": []}),
        ("GET", "/api/drafts/x", None),
        ("DELETE", "/api/drafts/x", None),
        ("POST", "/api/locks/x/acquire", None),
        ("POST", "/api/locks/x/heartbeat", None),
        ("POST", "/api/locks/x/release", None),
        ("GET", "/api/feed?tab=new", None),
    ]
    for method, path, body in blocked_endpoints:
        if method == "GET":
            r = client.get(path)
        elif method == "POST":
            r = client.post(path, json=body) if body else client.post(path)
        elif method == "PUT":
            r = client.put(path, json=body)
        else:
            r = client.delete(path)
        assert r.status_code == 409, f"{method} {path}: expected 409, got {r.status_code} (body={r.text})"
        detail = r.json().get("detail", {})
        assert detail.get("error") == "training_not_passed", f"{method} {path}: wrong error key in {detail}"


def test_user_without_seen_manual_blocked_too(client):
    """Pre-manual user gets 409 with manual_not_seen on training-gated routes.

    require_passed_training delegates to require_seen_manual; if has_seen_manual=0,
    the manual_not_seen 409 must surface (not training_not_passed).
    """
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("INVITE-AUDIT2",),
        )
    finally:
        conn.close()

    r = client.post("/api/auth/register", json={
        "username": "fresh", "password": "password123",
        "invite_code": "INVITE-AUDIT2",
    })
    assert r.status_code == 201
    client.post("/api/auth/login", json={"username": "fresh", "password": "password123"})

    r = client.get("/api/feed?tab=new")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "manual_not_seen"


# === RISK 2: Atomic rollback under partial failure ===

def test_save_annotation_rollback_when_audit_fails(passed_user, ingest_doc, monkeypatch):
    """If audit.log_activity raises mid-transaction, NO mutation persists.

    Hypothesis: BEGIN/COMMIT/ROLLBACK wraps version + current + denorm + draft +
    lock_release + audit. If audit raises (e.g. broken serialization), all five
    earlier writes roll back.
    """
    ingest_doc("doc_audit")

    # Pre-condition: doc has no annotation
    db = connect(config.DB_PATH)
    try:
        assert db.execute("SELECT * FROM annotations WHERE document_id='doc_audit'").fetchone() is None
        assert db.execute("SELECT COUNT(*) AS c FROM annotation_versions WHERE document_id='doc_audit'").fetchone()["c"] == 0
    finally:
        db.close()

    # Inject a failure in audit.log_activity
    from backend.shared import audit as audit_module
    real_log_activity = audit_module.log_activity

    def boom(*args, **kwargs):
        raise RuntimeError("simulated audit failure")
    monkeypatch.setattr(audit_module, "log_activity", boom)

    # Save should raise — caller sees the error
    with pytest.raises(Exception):
        passed_user["client"].post("/api/annotations", json={
            "document_id": "doc_audit",
            "references": [_ref(source_text="should_not_persist")],
        })

    # Restore for cleanup integrity
    monkeypatch.setattr(audit_module, "log_activity", real_log_activity)

    # Post-condition: NOTHING persisted
    db = connect(config.DB_PATH)
    try:
        ann = db.execute("SELECT * FROM annotations WHERE document_id='doc_audit'").fetchone()
        assert ann is None, "annotation row should NOT exist after rollback"

        ver_count = db.execute(
            "SELECT COUNT(*) AS c FROM annotation_versions WHERE document_id='doc_audit'"
        ).fetchone()["c"]
        assert ver_count == 0, "version row should NOT exist after rollback"

        denorm_count = db.execute(
            "SELECT COUNT(*) AS c FROM annotation_references WHERE document_id='doc_audit'"
        ).fetchone()["c"]
        assert denorm_count == 0, "denormalized refs should NOT exist after rollback"
    finally:
        db.close()


# === RISK 3: FK SET NULL on user delete preserves chain attribution ===

def test_chain_survives_user_deletion_via_set_null(passed_user, ingest_doc):
    """Deleting a user should cascade NULL into annotations.last_editor_user_id,
    not break the chain or wipe versions.

    annotation_versions.user_id is also ON DELETE SET NULL — so versions remain
    readable but with user_id=NULL.
    """
    c = passed_user["client"]
    ingest_doc("doc_fk")
    user_id = passed_user["user"]["id"]

    c.post("/api/annotations", json={
        "document_id": "doc_fk",
        "references": [_ref(source_text="alice's ref")],
    })

    # Delete the user — FKs should SET NULL where configured
    db = connect(config.DB_PATH)
    try:
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
    finally:
        db.close()

    # Chain still queryable
    db = connect(config.DB_PATH)
    try:
        ann = db.execute("SELECT * FROM annotations WHERE document_id='doc_fk'").fetchone()
        assert ann is not None, "annotation row should survive user delete"
        assert ann["last_editor_user_id"] is None, \
            f"last_editor_user_id should be NULL after user delete, got {ann['last_editor_user_id']}"

        ver = db.execute(
            "SELECT * FROM annotation_versions WHERE document_id='doc_fk'"
        ).fetchone()
        assert ver is not None
        assert ver["user_id"] is None, "version user_id should be NULL after user delete"

        # References (denormalized) survive — they don't reference users
        ref_count = db.execute(
            "SELECT COUNT(*) AS c FROM annotation_references WHERE document_id='doc_fk'"
        ).fetchone()["c"]
        assert ref_count == 1
    finally:
        db.close()


# === RISK 4: Set-semantic equality with whitespace + Turkish characters ===

def test_diff_zero_with_turkish_chars_and_whitespace():
    """Same Turkish reference text with leading/trailing whitespace → diff=0.

    Hypothesis: normalize_reference strips whitespace before canonical_key,
    so '  Türkçe metin  ' and 'Türkçe metin' are the same canonical key.
    """
    refs_a = [
        _ref(kanun_no="193", kanun_ad="Gelir Vergisi Kanunu",
             madde="Mükerrer 20", source_text="  Türkçe atıf metni  "),
    ]
    refs_b = [
        _ref(kanun_no=" 193 ", kanun_ad="Gelir Vergisi Kanunu",
             madde="Mükerrer 20", source_text="Türkçe atıf metni"),
    ]
    a_norm = normalize_references(refs_a)
    b_norm = normalize_references(refs_b)
    diff = references_diff(a_norm, b_norm)
    assert is_diff_zero(diff), \
        f"whitespace+Turkish should normalize to same canonical key, got diff={diff}"


def test_diff_distinguishes_unicode_NFC_vs_NFD():
    """Unicode normalization is NOT applied — ü (ü) and u+̈ (combining diaeresis)
    are distinct canonical keys. This is intentional (no surprise normalization).

    If a future commit added unicodedata.normalize() into _clean(), this test
    would fail and we'd know to update the spec.
    """
    nfc = "ü"  # ü as single codepoint (NFC)
    nfd = "ü"  # u + combining diaeresis (NFD)
    refs_a = [_ref(source_text=nfc)]
    refs_b = [_ref(source_text=nfd)]
    a_norm = normalize_references(refs_a)
    b_norm = normalize_references(refs_b)
    diff = references_diff(a_norm, b_norm)
    assert not is_diff_zero(diff), \
        "byte-different Unicode forms should be different keys (no implicit normalization)"


# === RISK 5: Idempotent re-ingest preserves annotations ===

def test_reingest_does_not_wipe_existing_annotations(passed_user, ingest_doc):
    """Re-ingesting the same doc must NOT delete its annotations.

    Hypothesis: documents.service.ingest_file does ON CONFLICT UPDATE on
    documents_meta and replaces document_kanun_refs/document_bkk_refs, but
    leaves annotations/annotation_versions/annotation_references untouched.
    """
    c = passed_user["client"]
    ingest_doc("doc_reingest", konu="First version")
    c.post("/api/annotations", json={
        "document_id": "doc_reingest",
        "references": [_ref(source_text="alice's ref")],
    })

    # Sanity: annotation persisted
    db = connect(config.DB_PATH)
    try:
        ann_before = db.execute("SELECT * FROM annotations WHERE document_id='doc_reingest'").fetchone()
        assert ann_before is not None
        ver_count_before = db.execute(
            "SELECT COUNT(*) AS c FROM annotation_versions WHERE document_id='doc_reingest'"
        ).fetchone()["c"]
        assert ver_count_before == 1
    finally:
        db.close()

    # Re-ingest with updated metadata
    ingest_doc("doc_reingest", konu="Second version (updated)")

    # Annotation must survive; documents_meta.konu must update
    db = connect(config.DB_PATH)
    try:
        meta = db.execute("SELECT konu FROM documents_meta WHERE document_id='doc_reingest'").fetchone()
        assert meta["konu"] == "Second version (updated)", "metadata must upsert"

        ann = db.execute("SELECT * FROM annotations WHERE document_id='doc_reingest'").fetchone()
        assert ann is not None, "annotation must survive re-ingest"

        ver_count = db.execute(
            "SELECT COUNT(*) AS c FROM annotation_versions WHERE document_id='doc_reingest'"
        ).fetchone()["c"]
        assert ver_count == ver_count_before, "version count must be unchanged"

        ref_count = db.execute(
            "SELECT COUNT(*) AS c FROM annotation_references WHERE document_id='doc_reingest'"
        ).fetchone()["c"]
        assert ref_count == 1, "denormalized refs must survive"
    finally:
        db.close()


# === RISK 6: Cross-tab consistency under save ===

def test_save_moves_doc_from_new_to_review(passed_user, ingest_doc):
    """A doc starts in 'new'; after save it disappears from 'new' and shows up in 'review'.

    Hypothesis: Each save updates the annotations table, which the feed queries
    join on. There is no caching layer, so the change is immediate.
    """
    c = passed_user["client"]
    ingest_doc("doc_move")

    # Pre: in 'new'
    new_ids = {i["document_id"] for i in c.get("/api/feed?tab=new").json()["items"]}
    assert "doc_move" in new_ids

    review_ids = {i["document_id"] for i in c.get("/api/feed?tab=review").json()["items"]}
    assert "doc_move" not in review_ids

    # Save
    c.post("/api/annotations", json={
        "document_id": "doc_move",
        "references": [_ref(source_text="x")],
    })

    # Post: NOT in 'new', IS in 'review'
    new_ids = {i["document_id"] for i in c.get("/api/feed?tab=new").json()["items"]}
    assert "doc_move" not in new_ids, "doc must leave 'new' after save"

    review_ids = {i["document_id"] for i in c.get("/api/feed?tab=review").json()["items"]}
    assert "doc_move" in review_ids, "doc must appear in 'review' after save"


# === RISK 7: Sweep + heartbeat race ===

def test_heartbeat_after_force_release_returns_404(passed_user, ingest_doc):
    """If a sweep / force_release has cleared the lock, the original holder's
    heartbeat must 404 (not silently succeed). Frontend then re-acquires.

    Simulates the race where sweep runs between heartbeats.
    """
    c = passed_user["client"]
    ingest_doc("doc_race")

    r = c.post("/api/locks/doc_race/acquire")
    assert r.status_code == 200

    # Simulate sweep dropping the lock
    db = connect(config.DB_PATH)
    try:
        db.execute("DELETE FROM document_locks WHERE document_id='doc_race'")
    finally:
        db.close()

    # Original holder's heartbeat now finds nothing
    r = c.post("/api/locks/doc_race/heartbeat")
    assert r.status_code == 404, f"heartbeat after lock drop must 404, got {r.status_code}"


# === RISK 8: Lock 409 conflict response shape (frontend contract) ===

def test_lock_409_conflict_carries_full_metadata(second_passed_user, ingest_doc):
    """409 detail dict must include error/by_user_id/by_username/acquired_at/expires_at.
    Frontend Paket 16 LockConflictModal will parse this exact shape.
    """
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_409")

    ctx["login"]("alice")
    c.post("/api/locks/doc_409/acquire")

    ctx["login"]("bob")
    r = c.post("/api/locks/doc_409/acquire")
    assert r.status_code == 409
    detail = r.json()["detail"]
    required_keys = {"error", "by_user_id", "by_username", "acquired_at", "expires_at"}
    assert required_keys.issubset(detail.keys()), \
        f"missing keys {required_keys - detail.keys()} in 409 detail: {detail}"
    assert detail["error"] == "lock_held_by_other"
    assert detail["by_username"] == "alice"
    assert isinstance(detail["by_user_id"], int)
    assert isinstance(detail["expires_at"], str) and detail["expires_at"]


# === RISK 9: Same user re-acquiring own lock is a refresh (no 409 on self) ===

def test_user_can_reacquire_own_lock(passed_user, ingest_doc):
    """Acquiring an already-owned lock must succeed (treat as refresh).
    Otherwise, a tab refresh in the UI would wedge the user.
    """
    c = passed_user["client"]
    ingest_doc("doc_self_reacquire")

    r1 = c.post("/api/locks/doc_self_reacquire/acquire")
    assert r1.status_code == 200

    r2 = c.post("/api/locks/doc_self_reacquire/acquire")
    assert r2.status_code == 200, f"self-reacquire must succeed, got {r2.status_code}"

    # Both responses have the same document_id and user
    assert r1.json()["document_id"] == r2.json()["document_id"]
    assert r1.json()["by_username"] == r2.json()["by_username"]
