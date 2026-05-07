"""Unit tests for the hybrid gold-doc resolver."""
import json
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.training import service as training_service
from backend.training import gold_docs as code_gold


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def _insert_override(
    conn, gold_id, *, source="override", is_deleted=0,
    content=None, expected_concepts=None, min_concept_count=None,
):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO training_gold_doc_overrides(
            gold_id, is_deleted, content, expected_concepts, min_concept_count,
            source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gold_id, is_deleted, content,
            json.dumps(expected_concepts) if expected_concepts is not None else None,
            min_concept_count, source, now, now,
        ),
    )


def test_no_overrides_returns_code_baseline(db):
    out = training_service.get_active_gold_docs(db)
    assert len(out) == len(code_gold.GOLD_DOCS)
    assert {d["gold_id"] for d in out} == {g["gold_id"] for g in code_gold.GOLD_DOCS}


def test_override_replaces_content_only(db):
    target = code_gold.GOLD_DOCS[0]["gold_id"]
    _insert_override(db, target, source="override", content="OVERRIDDEN TEXT")
    out = training_service.get_active_gold_docs(db)
    item = next(d for d in out if d["gold_id"] == target)
    assert item["content"] == "OVERRIDDEN TEXT"
    # expected_concepts and min_concept_count fall back to code baseline
    assert item["expected_concepts"] == code_gold.GOLD_DOCS[0]["expected_concepts"]


def test_override_replaces_expected_concepts(db):
    target = code_gold.GOLD_DOCS[0]["gold_id"]
    new_concepts = [{"kanun_no": "9999", "madde": "1"}]
    _insert_override(db, target, source="override", expected_concepts=new_concepts)
    out = training_service.get_active_gold_docs(db)
    item = next(d for d in out if d["gold_id"] == target)
    assert item["expected_concepts"] == new_concepts


def test_override_min_count_zero_is_honored(db):
    """min_concept_count=0 is a legitimate value (means: 'always pass'); the
    NULL fallback should NOT trigger when the override explicitly sets 0."""
    target = code_gold.GOLD_DOCS[0]["gold_id"]
    _insert_override(db, target, source="override", min_concept_count=0)
    out = training_service.get_active_gold_docs(db)
    item = next(d for d in out if d["gold_id"] == target)
    assert item["min_concept_count"] == 0


def test_is_deleted_excludes_baseline_entry(db):
    target = code_gold.GOLD_DOCS[0]["gold_id"]
    _insert_override(db, target, source="override", is_deleted=1)
    out = training_service.get_active_gold_docs(db)
    assert target not in {d["gold_id"] for d in out}
    # Other baseline entries still present
    assert len(out) == len(code_gold.GOLD_DOCS) - 1


def test_custom_entry_appended(db):
    _insert_override(
        db, "custom_001", source="custom",
        content="Custom doc content",
        expected_concepts=[{"kanun_no": "5520", "madde": "10"}],
        min_concept_count=1,
    )
    out = training_service.get_active_gold_docs(db)
    custom = next((d for d in out if d["gold_id"] == "custom_001"), None)
    assert custom is not None
    assert custom["content"] == "Custom doc content"
    assert custom["expected_concepts"] == [{"kanun_no": "5520", "madde": "10"}]
    assert custom["min_concept_count"] == 1


def test_custom_deleted_excluded(db):
    _insert_override(
        db, "custom_002", source="custom", is_deleted=1,
        content="x", expected_concepts=[{"kanun_no": "1"}], min_concept_count=1,
    )
    out = training_service.get_active_gold_docs(db)
    assert "custom_002" not in {d["gold_id"] for d in out}
