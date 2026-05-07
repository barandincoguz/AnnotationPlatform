"""Unit tests for notifications.service CRUD."""
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.notifications import service as notif


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (2, 'bob', 'x', 'user', ?, ?)",
        (now, now),
    )
    yield conn
    conn.close()


def test_create_returns_id_and_persists(db):
    nid = notif.create(
        db, user_id=1, kind="badge_unlocked",
        title="Yeni rozet!", body="İlk Annotation rozetini kazandın.",
        data={"badge_id": "first_annotation"},
    )
    assert isinstance(nid, int) and nid > 0

    rows = db.execute("SELECT user_id, kind, title, is_read FROM notifications").fetchall()
    assert len(rows) == 1
    assert rows[0]["user_id"] == 1
    assert rows[0]["kind"] == "badge_unlocked"
    assert rows[0]["title"] == "Yeni rozet!"
    assert rows[0]["is_read"] == 0


def test_list_for_user_unread_only(db):
    notif.create(db, user_id=1, kind="badge_unlocked", title="N1")
    nid_read = notif.create(db, user_id=1, kind="info", title="N2")
    notif.mark_read(db, notification_id=nid_read, user_id=1)
    notif.create(db, user_id=2, kind="info", title="N-bob")

    out = notif.list_for_user(db, user_id=1, unread_only=True)
    assert len(out) == 1
    assert out[0]["title"] == "N1"


def test_list_for_user_all_returns_read_too(db):
    n1 = notif.create(db, user_id=1, kind="a", title="N1")
    n2 = notif.create(db, user_id=1, kind="b", title="N2")
    notif.mark_read(db, notification_id=n1, user_id=1)

    out = notif.list_for_user(db, user_id=1, unread_only=False)
    titles = sorted(o["title"] for o in out)
    assert titles == ["N1", "N2"]


def test_list_for_user_other_users_excluded(db):
    notif.create(db, user_id=1, kind="x", title="alice")
    notif.create(db, user_id=2, kind="x", title="bob")

    alice = notif.list_for_user(db, user_id=1)
    bob = notif.list_for_user(db, user_id=2)
    assert [n["title"] for n in alice] == ["alice"]
    assert [n["title"] for n in bob] == ["bob"]


def test_list_orders_newest_first(db):
    n1 = notif.create(db, user_id=1, kind="a", title="first")
    n2 = notif.create(db, user_id=1, kind="b", title="second")
    out = notif.list_for_user(db, user_id=1)
    assert [o["id"] for o in out] == [n2, n1]


def test_list_respects_limit(db):
    for i in range(15):
        notif.create(db, user_id=1, kind="x", title=f"N{i}")
    out = notif.list_for_user(db, user_id=1, limit=5)
    assert len(out) == 5


def test_mark_read_idempotent(db):
    nid = notif.create(db, user_id=1, kind="x", title="N")
    notif.mark_read(db, notification_id=nid, user_id=1)
    notif.mark_read(db, notification_id=nid, user_id=1)  # second time: no error
    row = db.execute("SELECT is_read FROM notifications WHERE id=?", (nid,)).fetchone()
    assert row["is_read"] == 1


def test_mark_read_wrong_user_raises_not_found(db):
    nid = notif.create(db, user_id=1, kind="x", title="N")
    with pytest.raises(notif.NotificationNotFound):
        notif.mark_read(db, notification_id=nid, user_id=2)


def test_mark_read_unknown_id_raises_not_found(db):
    with pytest.raises(notif.NotificationNotFound):
        notif.mark_read(db, notification_id=99999, user_id=1)


def test_data_json_roundtrips(db):
    nid = notif.create(
        db, user_id=1, kind="x", title="N",
        data={"badge_id": "annotations_10", "earned_at": "2026-05-07T10:00:00+00:00"},
    )
    out = notif.list_for_user(db, user_id=1)
    assert out[0]["data"] == {"badge_id": "annotations_10", "earned_at": "2026-05-07T10:00:00+00:00"}


def test_create_with_no_data_returns_none_data_in_list(db):
    nid = notif.create(db, user_id=1, kind="x", title="N")
    out = notif.list_for_user(db, user_id=1)
    assert out[0]["data"] is None
