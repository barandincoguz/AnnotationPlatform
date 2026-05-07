"""CLI tests for `python -m backend.cli import-gold-docs <path>`."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


@pytest.fixture
def fresh_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # Run migrations to set up the schema
    db_path = tmp_path / "db" / "annotations.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    conn.close()
    return tmp_path


def _run_cli(*args, env_extra=None):
    env = {"PYTHONPATH": str(Path(__file__).parent.parent), **(env_extra or {})}
    return subprocess.run(
        [sys.executable, "-m", "backend.cli", *args],
        capture_output=True, text=True, env={**__import__("os").environ, **env},
    )


def test_import_creates_custom_overrides(fresh_data_dir):
    payload = {
        "gold_docs": [
            {
                "gold_id": "real_001",
                "content": "Gerçek özelge metni 1.",
                "expected_concepts": [{"kanun_no": "5520", "madde": "5"}],
                "min_concept_count": 1,
            },
            {
                "gold_id": "real_002",
                "content": "Gerçek özelge metni 2.",
                "expected_concepts": [
                    {"kanun_no": "3065", "madde": "29", "fikra": "1", "bent": "a"},
                ],
                "min_concept_count": 1,
            },
        ],
    }
    json_path = fresh_data_dir / "gold.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False))

    result = _run_cli("import-gold-docs", str(json_path), env_extra={"DATA_DIR": str(fresh_data_dir)})
    assert result.returncode == 0, result.stderr
    assert "imported 2" in result.stdout.lower() or "2" in result.stdout

    conn = connect(fresh_data_dir / "db" / "annotations.db")
    try:
        rows = conn.execute(
            "SELECT gold_id, source, content, expected_concepts, min_concept_count "
            "FROM training_gold_doc_overrides ORDER BY gold_id"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 2
    assert rows[0]["gold_id"] == "real_001"
    assert rows[0]["source"] == "custom"
    assert rows[0]["content"] == "Gerçek özelge metni 1."
    assert json.loads(rows[0]["expected_concepts"]) == [{"kanun_no": "5520", "madde": "5"}]
    assert rows[0]["min_concept_count"] == 1


def test_import_idempotent_overwrites_existing(fresh_data_dir):
    """Running import twice with the same gold_id replaces the row."""
    payload_v1 = {"gold_docs": [{
        "gold_id": "real_001", "content": "v1",
        "expected_concepts": [{"kanun_no": "1"}],
        "min_concept_count": 1,
    }]}
    payload_v2 = {"gold_docs": [{
        "gold_id": "real_001", "content": "v2",
        "expected_concepts": [{"kanun_no": "2"}],
        "min_concept_count": 2,
    }]}
    p = fresh_data_dir / "gold.json"
    p.write_text(json.dumps(payload_v1))
    _run_cli("import-gold-docs", str(p), env_extra={"DATA_DIR": str(fresh_data_dir)})
    p.write_text(json.dumps(payload_v2))
    result = _run_cli("import-gold-docs", str(p), env_extra={"DATA_DIR": str(fresh_data_dir)})
    assert result.returncode == 0

    conn = connect(fresh_data_dir / "db" / "annotations.db")
    try:
        row = conn.execute(
            "SELECT content, min_concept_count FROM training_gold_doc_overrides WHERE gold_id=?",
            ("real_001",),
        ).fetchone()
    finally:
        conn.close()
    assert row["content"] == "v2"
    assert row["min_concept_count"] == 2


def test_import_invalid_json_returns_nonzero(fresh_data_dir):
    p = fresh_data_dir / "bad.json"
    p.write_text("{not valid json}")
    result = _run_cli("import-gold-docs", str(p), env_extra={"DATA_DIR": str(fresh_data_dir)})
    assert result.returncode != 0
    assert "json" in result.stderr.lower() or "json" in result.stdout.lower()


def test_import_missing_required_field_returns_nonzero(fresh_data_dir):
    payload = {"gold_docs": [{"gold_id": "no_content_no_concepts"}]}
    p = fresh_data_dir / "bad.json"
    p.write_text(json.dumps(payload))
    result = _run_cli("import-gold-docs", str(p), env_extra={"DATA_DIR": str(fresh_data_dir)})
    assert result.returncode != 0
