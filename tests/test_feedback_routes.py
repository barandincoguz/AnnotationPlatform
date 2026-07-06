"""Tests for feedback submission and admin listing endpoints."""
from __future__ import annotations


def _seed_feedback(db_conn, user_id: int, *, type_: str, message: str) -> int:
    cur = db_conn.execute(
        """
        INSERT INTO user_feedback(user_id, type, message, created_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (user_id, type_, message),
    )
    return int(cur.lastrowid)


def test_submit_feedback_success(passed_user):
    r = passed_user["client"].post(
        "/api/feedback",
        json={"type": "suggestion", "message": "  Add bulk export  "},
    )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] > 0
    assert body["user_id"] == passed_user["user"]["id"]
    assert body["username"] == passed_user["user"]["username"]
    assert body["type"] == "suggestion"
    assert body["message"] == "Add bulk export"
    assert isinstance(body["created_at"], str)


def test_submit_feedback_empty_message_returns_422(passed_user):
    r = passed_user["client"].post(
        "/api/feedback",
        json={"type": "complaint", "message": "   "},
    )

    assert r.status_code == 422


def test_submit_feedback_requires_auth(client):
    r = client.post(
        "/api/feedback",
        json={"type": "complaint", "message": "Cannot reach the form"},
    )

    assert r.status_code == 401


def test_admin_lists_feedback(client, bootstrap_admin, seed_extra_user, db_conn):
    user_id = seed_extra_user(username="feedback-owner")
    _seed_feedback(db_conn, user_id, type_="complaint", message="A")
    _seed_feedback(db_conn, user_id, type_="suggestion", message="B")
    bootstrap_admin()

    r = client.get("/api/admin/feedback")

    assert r.status_code == 200, r.text
    rows = r.json()
    assert [row["message"] for row in rows] == ["B", "A"]
    assert {row["type"] for row in rows} == {"complaint", "suggestion"}
    assert all(row["username"] == "feedback-owner" for row in rows)


def test_admin_filters_feedback_by_type(client, bootstrap_admin, seed_extra_user, db_conn):
    user_id = seed_extra_user(username="feedback-filter-owner")
    _seed_feedback(db_conn, user_id, type_="complaint", message="Complaint A")
    _seed_feedback(db_conn, user_id, type_="complaint", message="Complaint B")
    _seed_feedback(db_conn, user_id, type_="suggestion", message="Suggestion C")
    bootstrap_admin()

    r = client.get("/api/admin/feedback?type_filter=complaint")

    assert r.status_code == 200, r.text
    rows = r.json()
    assert [row["type"] for row in rows] == ["complaint", "complaint"]
    assert [row["message"] for row in rows] == ["Complaint B", "Complaint A"]


def test_admin_feedback_non_admin_returns_404(passed_user):
    r = passed_user["client"].get("/api/admin/feedback")

    assert r.status_code == 404


def test_admin_feedback_invalid_type_filter_returns_422(client, bootstrap_admin):
    bootstrap_admin()

    r = client.get("/api/admin/feedback?type_filter=all")

    assert r.status_code == 422
