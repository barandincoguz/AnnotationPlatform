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
    assert result == {"is_completed": True}

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
