"""Docker image smoke test: build + start + /api/health + non-root assertion.

Skips when the docker CLI is absent (e.g., CI without docker-in-docker).
Default `pytest` includes these tests when docker is available; otherwise
they skip cleanly. Explicit selection: `pytest -m docker`. Exclusion:
`pytest -m "not docker"`.

Costs: image build is module-scoped (~30-60s cold, ~5s warm via layer
cache). Each test spins up a fresh container on a random host port,
waits up to 45s for /api/health to return 200, then runs its assertions.
"""
import json
import os
import shutil
import subprocess
import time
import urllib.request

import pytest

DOCKER = shutil.which("docker")
pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(DOCKER is None, reason="docker CLI not on PATH"),
]


IMAGE_TAG = "anotasyon-platform:test-smoke"


def _run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True, **kwargs)


@pytest.fixture(scope="module")
def built_image():
    """Build the image once per test module against the repo root."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    _run([DOCKER, "build", "-t", IMAGE_TAG, repo_root])
    yield IMAGE_TAG
    # Intentionally no `docker rmi` — keep the layer cache warm for the
    # next run. The image is tagged with `test-smoke`, easy to clean up
    # manually if disk pressure becomes an issue.


@pytest.fixture()
def running_container(built_image):
    """Start a fresh container on a random host port. Yield (cid, port).
    --rm + explicit `docker stop` covers cleanup even on test failure."""
    result = _run([
        DOCKER, "run", "-d", "--rm",
        "-p", "0:8000",
        "-e", "SESSION_SECRET=test-secret-smoke",
        built_image,
    ])
    cid = result.stdout.strip()
    try:
        # `docker run -d` returns once the container is created, but the
        # port mapping in the network namespace may take tens of ms to
        # become visible to `docker port`. Poll up to 5s before failing.
        port_out = ""
        for _ in range(10):
            port_out = _run(
                [DOCKER, "port", cid, "8000"], check=False,
            ).stdout.strip()
            if port_out:
                break
            time.sleep(0.5)
        if not port_out:
            raise RuntimeError(
                f"`docker port {cid} 8000` returned no mapping after 5s"
            )
        # Format: "0.0.0.0:NNNNN\n[::]:NNNNN" — take the first line, then
        # the integer after the last ':'. Both IPv4-first and IPv6-first
        # orderings are handled because rsplit(':', 1) takes the LAST ':',
        # which always sits directly before the port number.
        first_line = port_out.splitlines()[0]
        host_port = int(first_line.rsplit(":", 1)[1])
        yield cid, host_port
    finally:
        _run([DOCKER, "stop", cid], check=False)


def _wait_healthy(port: int, timeout_s: int = 45) -> dict:
    """Poll /api/health until 200 or timeout. Returns parsed body."""
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/health", timeout=3,
            ) as r:
                if r.status == 200:
                    return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            time.sleep(1)
    raise TimeoutError(
        f"/api/health did not become ready in {timeout_s}s; last err: {last_err}"
    )


def test_image_builds_and_health_endpoint_responds(running_container):
    """End-to-end: image starts, migrations apply, app binds 8000, /api/health 200."""
    _cid, port = running_container
    body = _wait_healthy(port, timeout_s=45)
    assert body["status"] == "ok"
    assert isinstance(body.get("version"), str)
    assert body["version"]  # non-empty


def test_health_db_endpoint_reports_migrations(running_container):
    """Migrations applied on startup. /api/health/db reports counts."""
    _cid, port = running_container
    _wait_healthy(port, timeout_s=45)
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}/api/health/db", timeout=3,
    ) as r:
        body = json.loads(r.read().decode("utf-8"))
    assert body["status"] == "ok"
    assert body["migrations_applied"] == 4  # v0001..v0004
    assert body["table_count"] >= 23


def test_container_runs_as_non_root(running_container):
    """Security baseline: PID 1 runs as appuser (UID 1000), not root."""
    cid, _port = running_container
    out = _run([DOCKER, "exec", cid, "id", "-u"]).stdout.strip()
    assert out == "1000", f"container ran as UID {out}, expected 1000 (appuser)"
