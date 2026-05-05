import json
import subprocess
import sqlite3
import sys
from pathlib import Path


def _run_cli(tmp_path: Path, *args, extra_env=None) -> subprocess.CompletedProcess:
    env = {
        "DATA_DIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "backend.cli", *args],
        capture_output=True, text=True, env=env,
    )


def test_cli_ingest_single_file(tmp_path):
    _run_cli(tmp_path, "migrate")
    sample = {
        "evrakOid": "cli_test_doc",
        "pdfText": "Bu bir CLI testidir.",
        "sayi": 1,
    }
    f = tmp_path / "doc.json"
    f.write_text(json.dumps(sample))

    result = _run_cli(tmp_path, "ingest", str(f))
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "1" in result.stdout

    db = sqlite3.connect(str(tmp_path / "db" / "annotations.db"))
    row = db.execute("SELECT document_id FROM documents_meta").fetchone()
    db.close()
    assert row[0] == "cli_test_doc"


def test_cli_ingest_directory(tmp_path):
    _run_cli(tmp_path, "migrate")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    for i in range(3):
        (docs_dir / f"doc_{i}.json").write_text(json.dumps({
            "evrakOid": f"d{i}",
            "pdfText": f"Doc {i}",
        }))

    result = _run_cli(tmp_path, "ingest", str(docs_dir))
    assert result.returncode == 0
    assert "3" in result.stdout


def test_cli_ingest_nonexistent_path_fails(tmp_path):
    _run_cli(tmp_path, "migrate")
    result = _run_cli(tmp_path, "ingest", "/does/not/exist")
    assert result.returncode != 0
