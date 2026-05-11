"""Verify the import-time DISABLE_SPA_MOUNT gate keeps SPA routes
out of the TestClient even when backend/static/ exists on disk.

The autouse-fixture approach (monkeypatching STATIC_DIR after import)
cannot work because FastAPI registers routes at module import time.
The env-flag at conftest module top is the only correct fix.
"""
import os

from fastapi.testclient import TestClient

from backend.main import app


def test_disable_spa_mount_env_var_is_set_for_tests():
    """conftest.py must set DISABLE_SPA_MOUNT=1 before backend.main imports."""
    assert os.environ.get("DISABLE_SPA_MOUNT") == "1"


def test_root_path_returns_404_not_index_html():
    """With SPA gated off, GET / should NOT serve index.html;
    it should fall through to FastAPI's default (404)."""
    client = TestClient(app)
    response = client.get("/")
    # SPA fallback would return 200 + text/html. Gate off ⇒ 404.
    assert response.status_code == 404


def test_assets_mount_does_not_exist_in_tests():
    """/assets/* should 404 when SPA mount is gated off."""
    client = TestClient(app)
    response = client.get("/assets/anything.js")
    assert response.status_code == 404


def test_api_health_still_works():
    """Sanity: API routes themselves are unaffected by the gate."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
