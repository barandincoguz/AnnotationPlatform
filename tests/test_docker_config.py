"""Static checks for deploy-critical Docker wiring.

These are intentionally cheap and non-Docker: they catch clean-checkout
packaging mistakes before the slower image smoke tests run.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_builds_frontend_assets_in_image():
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "AS frontend-builder" in dockerfile
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "COPY --from=frontend-builder" in dockerfile


def test_dockerignore_forces_fresh_frontend_build_and_excludes_test_package():
    ignored = (ROOT / ".dockerignore").read_text().splitlines()

    assert "backend/static/" in ignored
    assert "backend/tests/" in ignored
    assert "frontend/node_modules/" in ignored
