"""HTTP tests for GET /api/me/profile."""
from backend.shared.db import connect
from backend import config


def _ref(**overrides):
    base = {
        "kanun_no": "5520", "kanun_ad": "KVK", "madde": "5",
        "fikra": "1", "bent": "a", "source_text": "kısa",
    }
    base.update(overrides)
    return base


def test_profile_requires_auth(client):
    r = client.get("/api/me/profile")
    assert r.status_code == 401


def test_profile_pre_training_user_returns_zero_state(client):
    """Pre-training user can fetch profile — sees zeroed state, no badges."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("INV-PROF",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": "u_prof", "password": "password123", "invite_code": "INV-PROF",
    })
    assert r.status_code == 201
    r = client.post("/api/auth/login", json={
        "username": "u_prof", "password": "password123",
    })
    assert r.status_code == 200

    r = client.get("/api/me/profile")
    assert r.status_code == 200  # NOT 409
    data = r.json()
    assert data["user"]["username"] == "u_prof"
    assert data["xp"]["total"] == 0
    assert data["streak"]["current"] == 0
    assert data["streak"]["last_active_date"] is None
    assert data["today"]["save"] == 0
    assert data["today"]["daily_target"] == 20  # default from settings
    assert data["badges"] == []


def test_profile_after_save_reflects_xp_and_badge(passed_user, ingest_doc):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_prof")

    r = c.post("/api/annotations", json={
        "document_id": "doc_prof", "references": [_ref()],
    })
    assert r.status_code == 200

    r = c.get("/api/me/profile")
    assert r.status_code == 200
    data = r.json()
    assert data["xp"]["total"] == 1
    assert data["streak"]["current"] == 1
    assert data["today"]["save"] == 1
    assert any(b["id"] == "first_annotation" for b in data["badges"])


def test_profile_user_section_has_avatar_color(passed_user):
    r = passed_user["client"].get("/api/me/profile")
    assert r.status_code == 200
    user = r.json()["user"]
    assert "avatar_color" in user
    assert user["avatar_color"].startswith("#")


def test_profile_today_daily_target_reflects_settings(passed_user):
    """Admin-tunable daily target shows up in the response."""
    conn = connect(config.DB_PATH)
    try:
        from backend.shared import settings as S
        S.set_value(conn, "gamification.daily_target_docs", 35, updated_by_user_id=None)
    finally:
        conn.close()
    r = passed_user["client"].get("/api/me/profile")
    assert r.status_code == 200
    assert r.json()["today"]["daily_target"] == 35
