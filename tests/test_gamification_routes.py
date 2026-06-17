"""Tests for GET /api/badges/catalog."""


def test_badges_catalog_requires_auth(client):
    """Anonymous request returns 401."""
    res = client.get("/api/badges/catalog")
    assert res.status_code == 401


def test_badges_catalog_returns_all_seven(passed_user):
    """The catalog returns one entry per BADGE_DEFS key with criterion
    surfaced. Order is stable across calls (insertion order of BADGE_DEFS)."""
    c = passed_user["client"]
    res = c.get("/api/badges/catalog")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) == 7

    ids = [b["id"] for b in body]
    assert ids == [
        "first_annotation", "annotations_10", "annotations_100",
        "annotations_1000", "first_completion", "marathoner", "good_reviewer",
    ]

    first = body[0]
    assert first["id"] == "first_annotation"
    assert first["name"] == "İlk Anotasyon"
    assert first["description"] == "İlk kayıt başarıyla yapıldı."
    assert first["criterion"] == "İlk anotasyon kaydını yap."


def test_badges_catalog_shape_is_stable(passed_user):
    """Every entry has exactly id/name/description/criterion keys."""
    c = passed_user["client"]
    res = c.get("/api/badges/catalog")
    body = res.json()
    for entry in body:
        assert set(entry.keys()) == {"id", "name", "description", "criterion"}
        assert isinstance(entry["id"], str)
        assert isinstance(entry["name"], str)
        assert isinstance(entry["description"], str)
        assert isinstance(entry["criterion"], str)
