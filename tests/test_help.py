def test_help_returns_all_9_sections(client):
    # Need to be authenticated for /api/help
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("CODE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "CODE",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    r = client.get("/api/help")
    assert r.status_code == 200
    body = r.json()
    assert "sections" in body
    assert len(body["sections"]) == 9


def test_help_sections_have_id_order_title_body(client):
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("CODE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "CODE",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    r = client.get("/api/help")
    sections = r.json()["sections"]
    for s in sections:
        assert "id" in s
        assert "order" in s
        assert "title" in s
        assert "body" in s
        assert s["body"]  # not empty


def test_help_sections_sorted_by_order(client):
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("CODE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "CODE",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    r = client.get("/api/help")
    sections = r.json()["sections"]
    orders = [s["order"] for s in sections]
    assert orders == sorted(orders)
    assert orders[0] == 1
    assert orders[-1] == 9


def test_help_first_section_is_welcome(client):
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("CODE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "CODE",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    r = client.get("/api/help")
    sections = r.json()["sections"]
    first = sections[0]
    assert first["id"] == "01-welcome"
    assert first["title"].lower().startswith("hoş")


def test_help_unauthenticated_returns_401(client):
    r = client.get("/api/help")
    assert r.status_code == 401


def test_help_works_for_user_without_seen_manual(client):
    """Help endpoint must NOT require has_seen_manual (it IS the manual)."""
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("CODE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "CODE",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    me = client.get("/api/auth/me").json()
    assert me["has_seen_manual"] is False  # never set

    r = client.get("/api/help")
    assert r.status_code == 200


def test_help_content_matches_current_annotation_ui():
    from backend.docs_help.service import list_help_sections

    content = "\n".join(section["body"] for section in list_help_sections())

    assert "Sakla" not in content
    assert "Ctrl+Enter" not in content
    assert "Ctrl+K" not in content
    assert "Doğruladıklarım" not in content
    assert "**Yeni**" in content
    assert "**Devam Eden**" in content
    assert "**Tamamlanan**" in content
    assert "Metinden alıntı (zorunlu)" in content
