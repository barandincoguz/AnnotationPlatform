"""Vendored dqcheck_core drift guard.

Two layers:
  * manifest integrity — always runs, catches accidental local edits.
  * upstream comparison — runs only when DQCHECK_UPSTREAM_PATH points at a
    checkout of the data-quality-checker repo (dev machines), so CI and the
    Docker build stay green without the sibling repo.
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

CORE_DIR = Path(__file__).resolve().parents[1] / "backend" / "quality" / "dqcheck_core"
MANIFEST_PATH = CORE_DIR / "upstream_manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_lists_every_vendored_module():
    vendored = {p.name for p in CORE_DIR.glob("*.py")} - {"__init__.py"}
    assert vendored == set(_manifest()["files"])


def test_vendored_files_match_manifest_hashes():
    for name, expected in _manifest()["files"].items():
        assert _sha256(CORE_DIR / name) == expected, (
            f"{name} vendored copy was edited; revert it or re-run the "
            "UPSTREAM.md update procedure"
        )


def test_vendored_core_imports_without_flask_or_mlx():
    import sys

    import backend.quality.dqcheck_core.router  # noqa: F401

    leaked = {m.split(".")[0] for m in sys.modules} & {"flask", "mlx", "mlx_lm"}
    assert leaked == set()


@pytest.mark.skipif(
    not os.environ.get("DQCHECK_UPSTREAM_PATH"),
    reason="DQCHECK_UPSTREAM_PATH not set (CI/Docker have no sibling checkout)",
)
def test_vendored_files_match_live_upstream():
    upstream = Path(os.environ["DQCHECK_UPSTREAM_PATH"]) / "src" / "data_quality_checker"
    for name in _manifest()["files"]:
        assert _sha256(CORE_DIR / name) == _sha256(upstream / name), (
            f"{name} drifted from upstream; re-vendor per UPSTREAM.md"
        )


@pytest.mark.skipif(
    not os.environ.get("DQCHECK_UPSTREAM_PATH"),
    reason="DQCHECK_UPSTREAM_PATH not set (CI/Docker have no sibling checkout)",
)
def test_manifest_hashes_exist_at_declared_upstream_commit():
    """The manifest must describe the named commit, not only today's files."""
    repo = Path(os.environ["DQCHECK_UPSTREAM_PATH"])
    manifest = _manifest()
    commit = manifest["upstream_commit"]
    package = manifest["upstream_package_path"]
    for name, expected in manifest["files"].items():
        content = subprocess.run(
            ["git", "show", f"{commit}:{package}/{name}"],
            cwd=repo,
            check=True,
            capture_output=True,
        ).stdout
        assert hashlib.sha256(content).hexdigest() == expected, (
            f"{name} hash does not exist at declared upstream commit {commit}"
        )
