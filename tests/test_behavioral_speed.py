"""Unit tests for behavioral.service.detect_speed_warning.

Speed warning fires when a user has more saves in the configured window than
the configured threshold AND has not already been warned within that window.
"""
from datetime import datetime, timezone, timedelta

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared import audit, settings as S
from backend.behavioral import service as behavioral


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    # Insert a user
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', ?, ?)",
        (now, now),
    )
    yield conn
    conn.close()


def _insert_save(conn, user_id, ts):
    conn.execute(
        "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
        (user_id, "annotation_save", ts),
    )


def test_under_threshold_returns_none(db):
    """4 saves in 5min, threshold=5 → no warning."""
    now = datetime.now(timezone.utc)
    for i in range(4):
        _insert_save(db, 1, (now - timedelta(seconds=10 * i)).isoformat())
    assert behavioral.detect_speed_warning(db, user_id=1) is None


def test_over_threshold_returns_verdict(db):
    """6 saves in 5min, threshold=5 → warning verdict with payload."""
    now = datetime.now(timezone.utc)
    for i in range(6):
        _insert_save(db, 1, (now - timedelta(seconds=10 * i)).isoformat())
    verdict = behavioral.detect_speed_warning(db, user_id=1)
    assert verdict is not None
    assert verdict["recent_save_count"] == 6
    assert verdict["window_seconds"] == 300
    assert verdict["threshold"] == 5
    assert "message" in verdict


def test_old_saves_outside_window_are_ignored(db):
    """6 saves but spread over 1 hour → only those inside 5min window count."""
    now = datetime.now(timezone.utc)
    # 2 inside the window
    _insert_save(db, 1, (now - timedelta(seconds=30)).isoformat())
    _insert_save(db, 1, (now - timedelta(seconds=60)).isoformat())
    # 4 outside the window
    for i in range(4):
        _insert_save(db, 1, (now - timedelta(seconds=600 + i * 60)).isoformat())
    assert behavioral.detect_speed_warning(db, user_id=1) is None


def test_other_users_saves_do_not_count(db):
    """Bob's 10 saves don't affect Alice's count."""
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (2, 'bob', 'x', 'user', ?, ?)",
        (now.isoformat(), now.isoformat()),
    )
    for i in range(10):
        _insert_save(db, 2, (now - timedelta(seconds=10 * i)).isoformat())
    # alice has zero saves
    assert behavioral.detect_speed_warning(db, user_id=1) is None


def test_other_event_types_do_not_count(db):
    """document_open or annotation_skip don't count as saves."""
    now = datetime.now(timezone.utc)
    for i in range(10):
        db.execute(
            "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
            (1, "annotation_skip", (now - timedelta(seconds=10 * i)).isoformat()),
        )
    assert behavioral.detect_speed_warning(db, user_id=1) is None


def test_recent_warning_suppresses_re_fire(db):
    """If user already has a speed_warning behavioral_event in the window, suppress."""
    now = datetime.now(timezone.utc)
    for i in range(8):
        _insert_save(db, 1, (now - timedelta(seconds=10 * i)).isoformat())
    # Plant a recent warning (60s ago)
    audit.log_behavioral(
        db, user_id=1, detector="speed_warning",
        threshold_value=5, actual_value=7, context={"recent_save_count": 7},
    )
    assert behavioral.detect_speed_warning(db, user_id=1) is None


def test_old_warning_outside_window_does_not_suppress(db):
    """A warning older than window_seconds is no longer relevant — re-fire allowed."""
    now = datetime.now(timezone.utc)
    for i in range(7):
        _insert_save(db, 1, (now - timedelta(seconds=10 * i)).isoformat())
    # Plant an old warning (10 minutes ago — outside 5min window)
    old = (now - timedelta(seconds=700)).isoformat()
    db.execute(
        "INSERT INTO behavioral_events(user_id, detector, threshold_value, actual_value, context_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, "speed_warning", 5, 6, '{"recent_save_count":6}', old),
    )
    verdict = behavioral.detect_speed_warning(db, user_id=1)
    assert verdict is not None


def test_uses_settings_overrides(db):
    """Threshold and window are read from site_settings — admin can tune them."""
    S.set_value(db, "speed_warning.window_seconds", 60, updated_by_user_id=None)
    S.set_value(db, "speed_warning.max_saves_in_window", 2, updated_by_user_id=None)
    now = datetime.now(timezone.utc)
    for i in range(3):
        _insert_save(db, 1, (now - timedelta(seconds=5 * i)).isoformat())
    verdict = behavioral.detect_speed_warning(db, user_id=1)
    assert verdict is not None
    assert verdict["window_seconds"] == 60
    assert verdict["threshold"] == 2
    assert verdict["recent_save_count"] == 3
