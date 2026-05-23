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


def test_complete_toggle_idempotent_no_op(db):
    """Calling set_complete with the same target state twice writes only one version."""
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)
    result = ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)
    assert result["is_completed"] is True
    assert result["changed"] is False

    # Only ONE 'complete_mark' version row across the two calls
    versions = db.execute(
        "SELECT * FROM annotation_versions WHERE document_id=? AND action=?",
        ("doc_1", "complete_mark"),
    ).fetchall()
    assert len(versions) == 1


def test_complete_releases_callers_lock(db):
    """Marking a doc complete should release the caller's lock (terminal action)."""
    from datetime import datetime, timezone, timedelta
    ann_service.save_annotation(db, document_id="doc_1", user_id=1, references=[])
    # acquire a lock manually for user 1
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    db.execute(
        "INSERT INTO document_locks(document_id, user_id, acquired_at, last_heartbeat, expires_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("doc_1", 1, now, now, expires),
    )

    ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)

    row = db.execute("SELECT * FROM document_locks WHERE document_id=?", ("doc_1",)).fetchone()
    assert row is None


# === Phase 2: atomic save+complete + skip-draft-cleanup ===
#
# set_complete now accepts an optional `references` list. When supplied
# alongside completed=True, the service runs the full save pipeline
# AND flips the flag inside a single BEGIN IMMEDIATE — collapsing the
# frontend's pre-Phase-2 chain (save → complete → delete_draft) into
# one round-trip. Legacy callers (references=None) keep the prior
# flag-flip-only semantics.
#
# Constraints exercised:
#   - completed=False + references is not None → ValueError
#   - atomic path: refs persist, version row tagged 'complete_mark',
#     flag flips, caller's draft is deleted, version chain coherent
#   - lock conflict rolls back the WHOLE thing (refs and flag stay
#     untouched)
#   - skip_annotation deletes the caller's draft


def _seed_draft(db, *, document_id: str, user_id: int, references: list[dict]) -> None:
    """Insert a draft row directly via SQL — bypasses the drafts service
    so a test can set up "user has unsaved work" without exercising the
    save path under test."""
    now = "2026-01-01T00:00:00+00:00"
    db.execute(
        "INSERT OR REPLACE INTO drafts(document_id, user_id, references_json, updated_at) "
        "VALUES (?, ?, ?, ?)",
        (document_id, user_id, json.dumps(references), now),
    )


def test_complete_with_refs_persists_and_completes_atomically(db):
    """Atomic path: refs supplied alongside completed=True must commit
    BOTH the refs AND the flag flip in a single transaction. The
    annotation row holds the new refs and is_completed=1 after one call."""
    refs = [_ref(kanun_no="193", madde="37", source_text="atif final")]
    result = ann_service.set_complete(
        db, document_id="doc_1", user_id=1,
        completed=True, references=refs,
    )
    # Phase-2-fix: service returns rich dict so the route can emit
    # save + complete side effects. Existing callers that only read
    # `is_completed` keep working.
    assert result["is_completed"] is True
    assert result["did_save"] is True
    assert result["changed"] is True  # first-time complete, state transitioned
    assert result["save_action"] == "create"
    assert result["save_ref_count"] == 1

    row = db.execute(
        "SELECT * FROM annotations WHERE document_id=?", ("doc_1",)
    ).fetchone()
    assert row["is_completed"] == 1
    assert row["completed_by_user_id"] == 1
    parsed = json.loads(row["references_json"])
    assert len(parsed) == 1
    assert parsed[0]["source_text"] == "atif final"


def test_complete_with_refs_after_save_writes_single_complete_mark_version(db):
    """Atomic complete-with-refs on an EXISTING (uncompleted) annotation
    must produce exactly ONE new version row, tagged 'complete_mark',
    carrying the new refs and the real diff vs. prior state. (The
    first-time-create case writes two rows — covered separately below
    to preserve the chain invariant.)"""
    # Prior state: a prior save establishes a baseline so the diff is
    # meaningful (not just "create").
    ann_service.save_annotation(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="initial")],
    )
    initial_count = db.execute(
        "SELECT COUNT(*) AS c FROM annotation_versions WHERE document_id=?",
        ("doc_1",),
    ).fetchone()["c"]

    ann_service.set_complete(
        db, document_id="doc_1", user_id=1,
        completed=True,
        references=[_ref(source_text="final")],
    )

    after_count = db.execute(
        "SELECT COUNT(*) AS c FROM annotation_versions WHERE document_id=?",
        ("doc_1",),
    ).fetchone()["c"]
    # Exactly one new version row on the not-new branch.
    assert after_count - initial_count == 1

    last = db.execute(
        "SELECT * FROM annotation_versions WHERE document_id=? "
        "ORDER BY id DESC LIMIT 1",
        ("doc_1",),
    ).fetchone()
    assert last["action"] == "complete_mark"
    # And the diff captures the ref change (NOT zero).
    assert last["is_diff_zero"] == 0


def test_complete_with_refs_clears_caller_draft(db):
    """Atomic path must remove the caller's draft as part of the same
    transaction — fixes the Phase-1-era bug where a stale draft survived
    completion and shadowed the shared annotation."""
    _seed_draft(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="stale")],
    )
    ann_service.set_complete(
        db, document_id="doc_1", user_id=1,
        completed=True,
        references=[_ref(source_text="final")],
    )
    draft = db.execute(
        "SELECT * FROM drafts WHERE document_id=? AND user_id=?",
        ("doc_1", 1),
    ).fetchone()
    assert draft is None


def test_complete_with_refs_creates_annotation_when_absent(db):
    """First-time atomic complete with refs — no prior annotation row —
    must still succeed: the embedded save creates the row, then the
    flag flips. Verifies the frontend's "skip the save step entirely"
    flow Phase 3 adopts."""
    refs = [_ref(source_text="first commit")]
    result = ann_service.set_complete(
        db, document_id="doc_1", user_id=1,
        completed=True, references=refs,
    )
    assert result["is_completed"] is True
    assert result["did_save"] is True
    assert result["changed"] is True
    assert result["save_action"] == "create"

    row = db.execute(
        "SELECT * FROM annotations WHERE document_id=?", ("doc_1",)
    ).fetchone()
    assert row is not None
    assert row["is_completed"] == 1
    assert row["edit_count"] == 1
    parsed = json.loads(row["references_json"])
    assert parsed[0]["source_text"] == "first commit"


def test_first_time_atomic_complete_writes_both_create_and_complete_mark(db):
    """Chain invariant (Codex review): a completed annotation must have
    at least one 'create' version followed by a 'complete_mark'.
    Without this, audit consumers counting creations would miss
    documents born already-completed via the atomic path."""
    refs = [_ref(source_text="hello")]
    ann_service.set_complete(
        db, document_id="doc_1", user_id=1,
        completed=True, references=refs,
    )

    rows = db.execute(
        "SELECT action FROM annotation_versions WHERE document_id=? ORDER BY id",
        ("doc_1",),
    ).fetchall()
    actions = [r["action"] for r in rows]
    # Exactly two rows in order: create (carries refs), complete_mark (zero-diff marker).
    assert actions == ["create", "complete_mark"]


def test_complete_with_refs_rolls_back_on_lock_conflict(db):
    """Lock held by another user → LockOwnedByOther + NO partial state
    written. Neither refs nor flag must have been committed."""
    from datetime import datetime, timezone, timedelta

    ann_service.save_annotation(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="baseline")],
    )
    # bob holds an active lock; alice tries to atomic-complete.
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    db.execute(
        "INSERT INTO document_locks(document_id, user_id, acquired_at, last_heartbeat, expires_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("doc_1", 2, now, now, expires),
    )

    with pytest.raises(ann_service.LockOwnedByOther):
        ann_service.set_complete(
            db, document_id="doc_1", user_id=1,
            completed=True,
            references=[_ref(source_text="alice's overwrite")],
        )

    # Refs untouched: still bob-less baseline content.
    row = db.execute(
        "SELECT * FROM annotations WHERE document_id=?", ("doc_1",)
    ).fetchone()
    assert row["is_completed"] == 0
    parsed = json.loads(row["references_json"])
    assert parsed[0]["source_text"] == "baseline"


def test_complete_uncomplete_with_refs_raises(db):
    """Defense in depth: the model_validator catches this at the HTTP
    layer, but the service is callable directly. Reject the contradictory
    combination so internal callers can't silently misbehave."""
    ann_service.save_annotation(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="x")],
    )
    ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)
    with pytest.raises(ValueError):
        ann_service.set_complete(
            db, document_id="doc_1", user_id=1,
            completed=False,
            references=[_ref(source_text="y")],
        )


def test_complete_legacy_path_unchanged_when_refs_none(db):
    """references=None must reproduce the pre-Phase-2 behavior exactly:
    flag flip + 'complete_mark' version with is_diff_zero=1 and refs
    copied from the existing annotation row (NOT changed)."""
    ann_service.save_annotation(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="committed")],
    )
    ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)

    last = db.execute(
        "SELECT * FROM annotation_versions WHERE document_id=? "
        "ORDER BY id DESC LIMIT 1",
        ("doc_1",),
    ).fetchone()
    assert last["action"] == "complete_mark"
    assert last["is_diff_zero"] == 1  # legacy contract: no diff
    parsed = json.loads(last["references_json"])
    assert parsed[0]["source_text"] == "committed"


def test_skip_deletes_caller_draft(db):
    """skip_annotation now clears the caller's draft in the same
    transaction as the lock release. Without this, a skipped doc with
    a non-empty draft kept surfacing in the caller's Devam Eden tab
    (any non-empty draft puts the doc there post-Phase 1)."""
    _seed_draft(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="abandoned wip")],
    )
    ann_service.skip_annotation(db, document_id="doc_1", user_id=1)
    draft = db.execute(
        "SELECT * FROM drafts WHERE document_id=? AND user_id=?",
        ("doc_1", 1),
    ).fetchone()
    assert draft is None


def test_skip_does_not_touch_other_users_drafts(db):
    """skip_annotation is per-caller. Bob's draft on the same doc
    survives alice's skip."""
    _seed_draft(
        db, document_id="doc_1", user_id=2,
        references=[_ref(source_text="bob's wip")],
    )
    ann_service.skip_annotation(db, document_id="doc_1", user_id=1)
    bob_draft = db.execute(
        "SELECT * FROM drafts WHERE document_id=? AND user_id=?",
        ("doc_1", 2),
    ).fetchone()
    assert bob_draft is not None


def test_complete_idempotent_with_refs_none_unchanged(db):
    """The idempotent shortcut still applies when references=None:
    same-state toggle is a no-op (no new version row, changed=False).
    Now lives INSIDE BEGIN IMMEDIATE so a concurrent writer cannot
    race between the read and the txn (Codex review fix)."""
    ann_service.save_annotation(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="x")],
    )
    ann_service.set_complete(db, document_id="doc_1", user_id=1, completed=True)

    versions_before = db.execute(
        "SELECT COUNT(*) AS c FROM annotation_versions WHERE document_id=? AND action=?",
        ("doc_1", "complete_mark"),
    ).fetchone()["c"]

    # Same-state poke, refs=None → no-op.
    result = ann_service.set_complete(
        db, document_id="doc_1", user_id=1, completed=True
    )
    assert result["is_completed"] is True
    assert result["changed"] is False  # no transition
    assert result["did_save"] is False

    versions_after = db.execute(
        "SELECT COUNT(*) AS c FROM annotation_versions WHERE document_id=? AND action=?",
        ("doc_1", "complete_mark"),
    ).fetchone()["c"]
    assert versions_before == versions_after


# === Phase 5 B-01: O(1) unique_users_count increment ===
#
# _count_unique_users() ran COUNT(DISTINCT user_id) over annotation_versions
# on every save — O(N) in chain length. Replaced with an EXISTS check on
# (document_id, user_id) + increment-by-1 when the saving user has no prior
# version row. Same external semantics, O(1) instead of O(N).


def test_unique_users_count_incremented_on_first_user_save(db):
    """First save by a new user must increment unique_users_count by exactly 1."""
    result = ann_service.save_annotation(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="first")],
    )
    assert result["is_new"] is True
    row = db.execute(
        "SELECT unique_users_count FROM annotations WHERE document_id=?",
        ("doc_1",),
    ).fetchone()
    assert row["unique_users_count"] == 1


def test_unique_users_count_unchanged_on_repeat_save_same_user(db):
    """Same user saving twice must NOT increment the counter beyond 1."""
    ann_service.save_annotation(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="save-1")],
    )
    ann_service.save_annotation(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="save-2")],
    )
    row = db.execute(
        "SELECT unique_users_count FROM annotations WHERE document_id=?",
        ("doc_1",),
    ).fetchone()
    assert row["unique_users_count"] == 1


def test_unique_users_count_incremented_on_second_distinct_user(db):
    """Different user saving must increment the counter to 2."""
    ann_service.save_annotation(
        db, document_id="doc_1", user_id=1,
        references=[_ref(source_text="alice")],
    )
    ann_service.save_annotation(
        db, document_id="doc_1", user_id=2,
        references=[_ref(source_text="bob")],
    )
    row = db.execute(
        "SELECT unique_users_count FROM annotations WHERE document_id=?",
        ("doc_1",),
    ).fetchone()
    assert row["unique_users_count"] == 2


def test_unique_users_count_no_full_chain_scan_structural(db):
    """Structural: _count_unique_users() must no longer exist on the service
    module. Its presence would mean the O(N) COUNT(DISTINCT user_id) scan
    over annotation_versions is still reachable from the save path (B-01)."""
    assert not hasattr(ann_service, "_count_unique_users"), (
        "_count_unique_users() still exists — B-01 O(N) scan not removed"
    )
