"""Hybrid resolver: code baseline + DB overrides for quiz questions."""
import json
import sqlite3
from datetime import datetime, timezone

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect
from backend.training.quiz_data import QUIZ_QUESTIONS, get_active_quiz_questions


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_resolver_returns_baseline_when_no_overrides(db):
    out = get_active_quiz_questions(db)
    assert len(out) == len(QUIZ_QUESTIONS)
    assert {q["id"] for q in out} == {q["id"] for q in QUIZ_QUESTIONS}


def test_override_replaces_baseline_text(db):
    db.execute(
        """INSERT INTO training_quiz_overrides(question_id, is_deleted, text, choices_json, correct_choice_idx, source, created_at, updated_at)
           VALUES (?, 0, ?, ?, ?, 'override', ?, ?)""",
        ("q01", "Yeni soru metni", json.dumps(["A", "B", "C", "D"]), 2, _now(), _now()),
    )
    out = get_active_quiz_questions(db)
    q01 = next(q for q in out if q["id"] == "q01")
    assert q01["text"] == "Yeni soru metni"
    assert q01["choices"] == ["A", "B", "C", "D"]
    assert q01["correct_choice_idx"] == 2


def test_override_with_null_fields_falls_back_to_baseline(db):
    db.execute(
        """INSERT INTO training_quiz_overrides(question_id, is_deleted, text, choices_json, correct_choice_idx, source, created_at, updated_at)
           VALUES (?, 0, NULL, NULL, NULL, 'override', ?, ?)""",
        ("q01", _now(), _now()),
    )
    out = get_active_quiz_questions(db)
    q01_baseline = next(q for q in QUIZ_QUESTIONS if q["id"] == "q01")
    q01_resolved = next(q for q in out if q["id"] == "q01")
    assert q01_resolved["text"] == q01_baseline["text"]
    assert q01_resolved["choices"] == q01_baseline["choices"]
    assert q01_resolved["correct_choice_idx"] == q01_baseline["correct_choice_idx"]


def test_tombstone_excludes_baseline_question(db):
    db.execute(
        """INSERT INTO training_quiz_overrides(question_id, is_deleted, source, created_at, updated_at)
           VALUES (?, 1, 'override', ?, ?)""",
        ("q01", _now(), _now()),
    )
    out = get_active_quiz_questions(db)
    assert "q01" not in {q["id"] for q in out}
    assert len(out) == len(QUIZ_QUESTIONS) - 1


def test_custom_question_appended(db):
    db.execute(
        """INSERT INTO training_quiz_overrides(question_id, is_deleted, text, choices_json, correct_choice_idx, source, created_at, updated_at)
           VALUES (?, 0, ?, ?, ?, 'custom', ?, ?)""",
        ("custom_q01", "Yeni özel soru", json.dumps(["X", "Y", "Z", "W"]), 1, _now(), _now()),
    )
    out = get_active_quiz_questions(db)
    assert len(out) == len(QUIZ_QUESTIONS) + 1
    custom = next(q for q in out if q["id"] == "custom_q01")
    assert custom["text"] == "Yeni özel soru"
    assert custom["correct_choice_idx"] == 1


def test_tombstone_blocks_custom_too(db):
    db.execute(
        """INSERT INTO training_quiz_overrides(question_id, is_deleted, text, choices_json, correct_choice_idx, source, created_at, updated_at)
           VALUES (?, 1, ?, ?, ?, 'custom', ?, ?)""",
        ("custom_q01", "Will not appear", json.dumps(["A", "B", "C", "D"]), 0, _now(), _now()),
    )
    out = get_active_quiz_questions(db)
    assert "custom_q01" not in {q["id"] for q in out}
