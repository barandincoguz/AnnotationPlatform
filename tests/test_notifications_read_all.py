"""Tests for POST /api/me/notifications/read-all."""
from backend.notifications import service as notif_service


def test_read_all_requires_auth(client):
    res = client.post("/api/me/notifications/read-all")
    assert res.status_code == 401


def test_read_all_marks_only_current_user_unread(
    passed_user, db_conn, seed_extra_user,
):
    """The endpoint marks ONLY the caller's unread rows. Returns marked_count."""
    me_id = passed_user["user"]["id"]
    stranger_id = seed_extra_user(username="stranger_t4")
    notif_service.create(db_conn, user_id=me_id, kind="admin_announcement",
                         title="A1", body=None)
    notif_service.create(db_conn, user_id=me_id, kind="admin_announcement",
                         title="A2", body=None)
    notif_service.create(db_conn, user_id=stranger_id, kind="admin_announcement",
                         title="B1", body=None)
    db_conn.commit()

    res = passed_user["client"].post("/api/me/notifications/read-all")
    assert res.status_code == 200
    assert res.json() == {"marked_count": 2}

    rows = db_conn.execute(
        "SELECT is_read FROM notifications WHERE user_id=? ORDER BY id",
        (me_id,),
    ).fetchall()
    assert all(r["is_read"] == 1 for r in rows)
    stranger_rows = db_conn.execute(
        "SELECT is_read FROM notifications WHERE user_id=?", (stranger_id,),
    ).fetchall()
    assert stranger_rows[0]["is_read"] == 0


def test_read_all_is_idempotent(passed_user, db_conn):
    """Re-calling read-all on an already-clean inbox returns 0."""
    me_id = passed_user["user"]["id"]
    notif_service.create(db_conn, user_id=me_id, kind="admin_announcement",
                         title="X", body=None)
    db_conn.commit()

    res1 = passed_user["client"].post("/api/me/notifications/read-all")
    assert res1.json() == {"marked_count": 1}
    res2 = passed_user["client"].post("/api/me/notifications/read-all")
    assert res2.json() == {"marked_count": 0}


def test_read_all_with_empty_inbox(passed_user):
    """Empty inbox returns 0."""
    res = passed_user["client"].post("/api/me/notifications/read-all")
    assert res.status_code == 200
    assert res.json() == {"marked_count": 0}
