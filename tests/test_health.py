def test_health_returns_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_app_runs_migrations_on_startup(client):
    r = client.get("/api/health/db")
    assert r.status_code == 200
    body = r.json()
    assert body["migrations_applied"] >= 1
    assert body["table_count"] >= 19  # 19 + schema_migrations
