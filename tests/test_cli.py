import subprocess
import sys
from pathlib import Path


def test_cli_migrate_runs_on_empty_dir(tmp_path: Path):
    env = {
        "DATA_DIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
    }
    result = subprocess.run(
        [sys.executable, "-m", "backend.cli", "migrate"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "v0001" in result.stdout
    assert (tmp_path / "db" / "annotations.db").exists()


def test_cli_migrate_idempotent(tmp_path: Path):
    env = {
        "DATA_DIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
    }
    subprocess.run(
        [sys.executable, "-m", "backend.cli", "migrate"],
        capture_output=True, text=True, env=env, check=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "backend.cli", "migrate"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0
    assert "no pending" in result.stdout.lower() or "0 applied" in result.stdout.lower()


def test_cli_unknown_command_returns_nonzero(tmp_path: Path):
    env = {
        "DATA_DIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
    }
    result = subprocess.run(
        [sys.executable, "-m", "backend.cli", "bogus-command"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
