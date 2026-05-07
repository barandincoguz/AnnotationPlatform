"""HTTP tests for /api/me/notifications endpoints."""
from backend.shared.db import connect
from backend import config


def test_list_requires_auth(client):
    r = client.get("/api/me/notifications")
    assert r.status_code == 401


def test_list_returns_user_notifications_unread_default(passed_user):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    conn = connect(config.DB_PATH)
    try:
        from backend.notifications import service as notif
        notif.create(conn, user_id=user_id, kind="info", title="N1")
        notif.create(conn, user_id=user_id, kind="info", title="N2")
    finally:
        conn.close()

    r = c.get("/api/me/notifications")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert len(data["items"]) == 2
    titles = sorted(n["title"] for n in data["items"])
    assert titles == ["N1", "N2"]
    assert all(n["is_read"] is False for n in data["items"])


def test_list_unread_only_false_includes_read(passed_user):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    conn = connect(config.DB_PATH)
    try:
        from backend.notifications import service as notif
        n1 = notif.create(conn, user_id=user_id, kind="info", title="N1")
        notif.create(conn, user_id=user_id, kind="info", title="N2")
        notif.mark_read(conn, notification_id=n1, user_id=user_id)
    finally:
        conn.close()

    r = c.get("/api/me/notifications?unread_only=false")
    assert r.status_code == 200
    titles = sorted(n["title"] for n in r.json()["items"])
    assert titles == ["N1", "N2"]


def test_mark_read_persists(passed_user):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    conn = connect(config.DB_PATH)
    try:
        from backend.notifications import service as notif
        nid = notif.create(conn, user_id=user_id, kind="info", title="N")
    finally:
        conn.close()

    r = c.post(f"/api/me/notifications/{nid}/read")
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        row = conn.execute("SELECT is_read FROM notifications WHERE id=?", (nid,)).fetchone()
    finally:
        conn.close()
    assert row["is_read"] == 1


def test_mark_read_other_users_notification_404(second_passed_user):
    ctx = second_passed_user
    c = ctx["client"]
    bob_id = ctx["bob"]["id"]
    conn = connect(config.DB_PATH)
    try:
        from backend.notifications import service as notif
        bobs_id = notif.create(conn, user_id=bob_id, kind="info", title="bob's")
    finally:
        conn.close()

    ctx["login"]("alice")
    r = c.post(f"/api/me/notifications/{bobs_id}/read")
    assert r.status_code == 404


def test_mark_read_unknown_id_404(passed_user):
    r = passed_user["client"].post("/api/me/notifications/99999/read")
    assert r.status_code == 404


def test_list_pre_training_user_can_see_inbox(client):
    """Notification inbox doesn't require training pass — pre-training users
    might receive admin announcements."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("INV-NO-TRAIN",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": "u_pretrain", "password": "password123",
        "invite_code": "INV-NO-TRAIN",
    })
    assert r.status_code == 201
    r = client.post("/api/auth/login", json={
        "username": "u_pretrain", "password": "password123",
    })
    assert r.status_code == 200

    r = client.get("/api/me/notifications")
    assert r.status_code == 200  # NOT 409 (training_not_passed)
    assert r.json()["items"] == []
