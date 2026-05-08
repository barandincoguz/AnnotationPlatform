"""Verify v0002 migration creates training_quiz_overrides cleanly."""
import sqlite3

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    yield conn
    conn.close()


def test_v0002_creates_quiz_overrides_table(fresh_db):
    apply_migrations(fresh_db, discover_migrations())
    rows = fresh_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='training_quiz_overrides'"
    ).fetchall()
    assert len(rows) == 1


def test_v0002_quiz_overrides_columns(fresh_db):
    apply_migrations(fresh_db, discover_migrations())
    cols = {r[1]: r for r in fresh_db.execute("PRAGMA table_info(training_quiz_overrides)").fetchall()}
    assert "question_id" in cols
    assert "is_deleted" in cols
    assert "text" in cols
    assert "choices_json" in cols
    assert "correct_choice_idx" in cols
    assert "source" in cols
    assert "created_by_admin_id" in cols
    assert "created_at" in cols
    assert "updated_at" in cols
    pk_cols = [r[1] for r in cols.values() if r[5] > 0]
    assert pk_cols == ["question_id"]


def test_v0002_quiz_overrides_source_check(fresh_db):
    apply_migrations(fresh_db, discover_migrations())
    fresh_db.execute(
        "INSERT INTO training_quiz_overrides(question_id, source, created_at, updated_at) "
        "VALUES (?, 'override', ?, ?)",
        ("q01", "2026-05-08T00:00:00+00:00", "2026-05-08T00:00:00+00:00"),
    )
    fresh_db.commit()
    row = fresh_db.execute(
        "SELECT question_id, source FROM training_quiz_overrides WHERE question_id='q01'"
    ).fetchone()
    assert row is not None
    assert row["source"] == "override"
    with pytest.raises(sqlite3.IntegrityError):
        fresh_db.execute(
            "INSERT INTO training_quiz_overrides(question_id, source, created_at, updated_at) "
            "VALUES (?, 'invalid', ?, ?)",
            ("q02", "2026-05-08T00:00:00+00:00", "2026-05-08T00:00:00+00:00"),
        )


def test_v0002_idempotent(fresh_db):
    """Running discover+apply twice should be a no-op the second time."""
    apply_migrations(fresh_db, discover_migrations())
    second = apply_migrations(fresh_db, discover_migrations())
    assert second == []
