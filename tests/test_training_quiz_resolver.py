"""Hybrid resolver: code baseline + DB overrides for quiz questions."""
import json
from datetime import datetime, timezone

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect
from backend.training.quiz_data import QUIZ_QUESTIONS, get_active_quiz_questions


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def _insert_quiz_override(
    conn, question_id, *, is_deleted=0, text=None, choices_json=None,
    correct_choice_idx=None, source="override",
):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO training_quiz_overrides(
            question_id, is_deleted, text, choices_json, correct_choice_idx,
            source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (question_id, is_deleted, text, choices_json, correct_choice_idx, source, now, now),
    )


def test_resolver_returns_baseline_when_no_overrides(db):
    out = get_active_quiz_questions(db)
    assert len(out) == len(QUIZ_QUESTIONS)
    assert {q["id"] for q in out} == {q["id"] for q in QUIZ_QUESTIONS}


def test_override_replaces_baseline_text(db):
    _insert_quiz_override(
        db, "q01",
        text="Yeni soru metni",
        choices_json=json.dumps(["A", "B", "C", "D"]),
        correct_choice_idx=2,
    )
    out = get_active_quiz_questions(db)
    q01 = next(q for q in out if q["id"] == "q01")
    assert q01["text"] == "Yeni soru metni"
    assert q01["choices"] == ["A", "B", "C", "D"]
    assert q01["correct_choice_idx"] == 2


def test_override_with_null_fields_falls_back_to_baseline(db):
    _insert_quiz_override(db, "q01")
    out = get_active_quiz_questions(db)
    q01_baseline = next(q for q in QUIZ_QUESTIONS if q["id"] == "q01")
    q01_resolved = next(q for q in out if q["id"] == "q01")
    assert q01_resolved["text"] == q01_baseline["text"]
    assert q01_resolved["choices"] == q01_baseline["choices"]
    assert q01_resolved["correct_choice_idx"] == q01_baseline["correct_choice_idx"]


def test_tombstone_excludes_baseline_question(db):
    _insert_quiz_override(db, "q01", is_deleted=1)
    out = get_active_quiz_questions(db)
    assert "q01" not in {q["id"] for q in out}
    assert len(out) == len(QUIZ_QUESTIONS) - 1


def test_custom_question_appended(db):
    _insert_quiz_override(
        db, "custom_q01",
        text="Yeni özel soru",
        choices_json=json.dumps(["X", "Y", "Z", "W"]),
        correct_choice_idx=1,
        source="custom",
    )
    out = get_active_quiz_questions(db)
    assert len(out) == len(QUIZ_QUESTIONS) + 1
    custom = next(q for q in out if q["id"] == "custom_q01")
    assert custom["text"] == "Yeni özel soru"
    assert custom["correct_choice_idx"] == 1


def test_tombstone_blocks_custom_too(db):
    _insert_quiz_override(
        db, "custom_q01",
        is_deleted=1,
        text="Will not appear",
        choices_json=json.dumps(["A", "B", "C", "D"]),
        correct_choice_idx=0,
        source="custom",
    )
    out = get_active_quiz_questions(db)
    assert "custom_q01" not in {q["id"] for q in out}
