"""Unit tests for gamification.service.award_xp."""
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.gamification import service as gam


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', ?, ?)",
        (now, now),
    )
    yield conn
    conn.close()


def test_first_award_creates_state_row_and_writes_ledger(db):
    gam.award_xp(db, user_id=1, delta_xp=5, reason="complete", related_doc_id="doc_a")
    state = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=1").fetchone()
    assert state is not None
    assert state["total_xp"] == 5

    ledger = db.execute(
        "SELECT user_id, delta_xp, reason, related_doc_id FROM gamification_ledger"
    ).fetchall()
    assert len(ledger) == 1
    assert ledger[0]["user_id"] == 1
    assert ledger[0]["delta_xp"] == 5
    assert ledger[0]["reason"] == "complete"
    assert ledger[0]["related_doc_id"] == "doc_a"


def test_multiple_awards_accumulate_total_xp(db):
    gam.award_xp(db, user_id=1, delta_xp=1, reason="save")
    gam.award_xp(db, user_id=1, delta_xp=5, reason="complete")
    gam.award_xp(db, user_id=1, delta_xp=2, reason="review")
    total = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=1").fetchone()
    assert total["total_xp"] == 8


def test_zero_delta_still_writes_ledger(db):
    """Defensive: zero-XP events (e.g. skip) still benefit from a ledger
    breadcrumb. But the orchestrator decides whether to call award_xp
    for zero-XP cases; this just shows award_xp doesn't no-op."""
    gam.award_xp(db, user_id=1, delta_xp=0, reason="probe")
    rows = db.execute("SELECT delta_xp FROM gamification_ledger").fetchall()
    assert len(rows) == 1
    assert rows[0]["delta_xp"] == 0


def test_negative_delta_decrements(db):
    """Defensive: future undo flows might subtract XP. Make sure the math
    handles it without going below zero (clamp at 0)."""
    gam.award_xp(db, user_id=1, delta_xp=10, reason="x")
    gam.award_xp(db, user_id=1, delta_xp=-3, reason="undo")
    total = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=1").fetchone()
    assert total["total_xp"] == 7


def test_negative_delta_clamps_at_zero(db):
    gam.award_xp(db, user_id=1, delta_xp=2, reason="x")
    gam.award_xp(db, user_id=1, delta_xp=-10, reason="undo")
    total = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=1").fetchone()
    assert total["total_xp"] == 0


def test_ensure_state_idempotent(db):
    gam.ensure_state(db, user_id=1)
    gam.ensure_state(db, user_id=1)
    rows = db.execute("SELECT COUNT(*) AS c FROM gamification_state WHERE user_id=1").fetchall()
    assert rows[0]["c"] == 1


def test_get_xp_total_returns_zero_for_unknown_user(db):
    assert gam.get_xp_total(db, user_id=999) == 0
