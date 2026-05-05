def test_app_imports_users_router(client):
    """Smoke: app boots after mounting users router."""
    r = client.get("/api/health")
    assert r.status_code == 200
