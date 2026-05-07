"""Unit tests for streak transitions and today_* counter resets.

Day boundary = UTC+3 calendar date. Tests directly seed last_active_date
to control transitions deterministically.
"""
from datetime import datetime, timezone, timedelta

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


def _seed_state(conn, *, last_active_date, current_streak=0, longest_streak=0,
                today_save=0, today_complete=0, today_review=0, today_skip=0):
    conn.execute("DELETE FROM gamification_state WHERE user_id=1")
    conn.execute(
        """
        INSERT INTO gamification_state(
            user_id, total_xp, current_streak_days, longest_streak_days,
            last_active_date, today_save_count, today_complete_count,
            today_review_count, today_skip_count, updated_at
        ) VALUES (1, 0, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (current_streak, longest_streak, last_active_date,
         today_save, today_complete, today_review, today_skip,
         datetime.now(timezone.utc).isoformat()),
    )


def _read_state(conn):
    return dict(conn.execute("SELECT * FROM gamification_state WHERE user_id=1").fetchone())


def test_first_save_ever_starts_streak_at_one(db):
    """No state row at all: first save creates row, streak=1, longest=1."""
    today = gam._today_tr()
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["last_active_date"] == today
    assert s["current_streak_days"] == 1
    assert s["longest_streak_days"] == 1
    assert s["today_save_count"] == 1


def test_multiple_saves_same_day_no_streak_change(db):
    today = gam._today_tr()
    _seed_state(db, last_active_date=today, current_streak=3, longest_streak=5,
                today_save=2)
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["current_streak_days"] == 3  # unchanged
    assert s["longest_streak_days"] == 5
    assert s["today_save_count"] == 3


def test_consecutive_day_increments_streak(db):
    today = gam._today_tr()
    yesterday_dt = datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)
    yesterday = yesterday_dt.strftime("%Y-%m-%d")
    _seed_state(db, last_active_date=yesterday, current_streak=4, longest_streak=4)
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["last_active_date"] == today
    assert s["current_streak_days"] == 5
    assert s["longest_streak_days"] == 5  # caught up


def test_consecutive_day_can_extend_longest(db):
    today = gam._today_tr()
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    _seed_state(db, last_active_date=yesterday, current_streak=7, longest_streak=7)
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["current_streak_days"] == 8
    assert s["longest_streak_days"] == 8


def test_gap_resets_current_streak_preserves_longest(db):
    today = gam._today_tr()
    two_days_ago = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d")
    _seed_state(db, last_active_date=two_days_ago, current_streak=10, longest_streak=10)
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["current_streak_days"] == 1
    assert s["longest_streak_days"] == 10


def test_today_counters_reset_on_day_change(db):
    today = gam._today_tr()
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    _seed_state(db, last_active_date=yesterday, current_streak=2, longest_streak=2,
                today_save=8, today_complete=3, today_review=2, today_skip=1)
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["today_save_count"] == 1     # reset to 0 then +1
    assert s["today_complete_count"] == 0  # reset
    assert s["today_review_count"] == 0
    assert s["today_skip_count"] == 0


def test_save_edit_increments_review_counter(db):
    gam.update_streak_and_counters(db, user_id=1, action="save_edit")
    s = _read_state(db)
    assert s["today_save_count"] == 1
    assert s["today_review_count"] == 1


def test_complete_increments_complete_counter_only_streak_unchanged(db):
    today = gam._today_tr()
    _seed_state(db, last_active_date=today, current_streak=3, longest_streak=3,
                today_save=5)
    gam.update_streak_and_counters(db, user_id=1, action="complete")
    s = _read_state(db)
    assert s["today_save_count"] == 5         # unchanged
    assert s["today_complete_count"] == 1
    assert s["current_streak_days"] == 3       # complete does NOT extend streak


def test_complete_on_first_ever_activity_does_not_seed_streak(db):
    """Spec: streak only updates on save events. A user who only completes
    has no streak. Their last_active_date stays None until they save."""
    gam.update_streak_and_counters(db, user_id=1, action="complete")
    s = _read_state(db)
    assert s["current_streak_days"] == 0
    assert s["last_active_date"] is None
    assert s["today_complete_count"] == 1


def test_record_skip_increments_skip_counter_only(db):
    """Skip path: sync function, just bumps the counter. No streak, no XP."""
    gam.record_skip(db, user_id=1)
    s = _read_state(db)
    assert s["today_skip_count"] == 1
    assert s["current_streak_days"] == 0
    assert s["last_active_date"] is None


def test_record_skip_resets_today_counters_on_day_change(db):
    today = gam._today_tr()
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    _seed_state(db, last_active_date=yesterday, today_save=4, today_skip=1)
    gam.record_skip(db, user_id=1)
    s = _read_state(db)
    # skip is NOT a save action, so last_active_date stays at yesterday
    assert s["last_active_date"] == yesterday
    # but today counters DID reset on read because we crossed the day boundary
    assert s["today_save_count"] == 0
    assert s["today_skip_count"] == 1
