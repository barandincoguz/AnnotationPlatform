"""Unit tests for badge unlock detection."""
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.gamification import badges, service as gam


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


def _ledger(conn, user_id, reason, n):
    """Plant N ledger rows of the given reason for the user."""
    now = datetime.now(timezone.utc).isoformat()
    for _ in range(n):
        conn.execute(
            "INSERT INTO gamification_ledger(user_id, delta_xp, reason, created_at) "
            "VALUES (?, 1, ?, ?)",
            (user_id, reason, now),
        )


def test_first_annotation_unlocks_at_1_save(db):
    _ledger(db, 1, "save", 1)
    out = badges.check_badges(db, user_id=1)
    assert "first_annotation" in out


def test_first_annotation_does_not_unlock_at_zero(db):
    out = badges.check_badges(db, user_id=1)
    assert "first_annotation" not in out


def test_annotations_10_unlocks_at_10_saves(db):
    _ledger(db, 1, "save", 10)
    out = badges.check_badges(db, user_id=1)
    assert {"first_annotation", "annotations_10"}.issubset(set(out))


def test_review_count_counts_toward_save_thresholds(db):
    """save and review are both 'productive' actions for the cumulative thresholds."""
    _ledger(db, 1, "save", 5)
    _ledger(db, 1, "review", 5)  # 5+5 = 10 total
    out = badges.check_badges(db, user_id=1)
    assert "annotations_10" in out


def test_first_completion_unlocks_at_first_complete(db):
    _ledger(db, 1, "complete", 1)
    out = badges.check_badges(db, user_id=1)
    assert "first_completion" in out


def test_marathoner_unlocks_at_streak_7(db):
    gam.ensure_state(db, user_id=1)
    db.execute(
        "UPDATE gamification_state SET current_streak_days=7 WHERE user_id=1"
    )
    out = badges.check_badges(db, user_id=1)
    assert "marathoner" in out


def test_marathoner_does_not_unlock_at_streak_6(db):
    gam.ensure_state(db, user_id=1)
    db.execute(
        "UPDATE gamification_state SET current_streak_days=6 WHERE user_id=1"
    )
    out = badges.check_badges(db, user_id=1)
    assert "marathoner" not in out


def test_good_reviewer_requires_both_min_reviews_and_min_kept(db):
    """20 reviews + 15 kept by default. With 19 reviews + 15 kept: no unlock.
    With 20 reviews + 14 kept: no unlock. With both met: unlock."""
    _ledger(db, 1, "review", 19)
    _ledger(db, 1, "review_kept", 15)
    assert "good_reviewer" not in badges.check_badges(db, user_id=1)

    _ledger(db, 1, "review", 1)  # now 20 reviews + 15 kept
    out = badges.check_badges(db, user_id=1)
    assert "good_reviewer" in out


def test_idempotent_already_earned_excluded(db):
    """A badge already in badges_earned is NOT re-emitted."""
    _ledger(db, 1, "save", 1)
    earned_at = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO badges_earned(user_id, badge_id, earned_at) VALUES (1, 'first_annotation', ?)",
        (earned_at,),
    )
    out = badges.check_badges(db, user_id=1)
    assert "first_annotation" not in out


def test_badge_defs_metadata_complete(db):
    """Every badge_id check_badges can return must have a name + description in BADGE_DEFS."""
    _ledger(db, 1, "save", 1000)
    _ledger(db, 1, "complete", 1)
    _ledger(db, 1, "review_kept", 15)
    _ledger(db, 1, "review", 20)
    gam.ensure_state(db, user_id=1)
    db.execute("UPDATE gamification_state SET current_streak_days=7 WHERE user_id=1")

    out = badges.check_badges(db, user_id=1)
    for bid in out:
        assert bid in badges.BADGE_DEFS
        assert "name" in badges.BADGE_DEFS[bid]
        assert "description" in badges.BADGE_DEFS[bid]


def test_check_badges_settings_overrides(db):
    """Admin tunes good_reviewer min_reviews=3, min_kept=2 → unlocks earlier."""
    from backend.shared import settings as S
    S.set_value(db, "gamification.good_reviewer.min_reviews", 3, updated_by_user_id=None)
    S.set_value(db, "gamification.good_reviewer.min_kept", 2, updated_by_user_id=None)
    _ledger(db, 1, "review", 3)
    _ledger(db, 1, "review_kept", 2)
    out = badges.check_badges(db, user_id=1)
    assert "good_reviewer" in out


def test_badge_defs_have_imperative_criterion():
    """Each badge has an optional `criterion` field for the locked variant
    UI (imperative — 'X yap'). The earned variant continues to use the past-
    tense `description`. Catalog endpoint surfaces both."""
    expected_ids = {
        "first_annotation", "annotations_10", "annotations_100",
        "annotations_1000", "first_completion", "marathoner", "good_reviewer",
    }
    assert set(badges.BADGE_DEFS.keys()) == expected_ids
    for badge_id, meta in badges.BADGE_DEFS.items():
        assert "name" in meta, badge_id
        assert "description" in meta, badge_id
        assert "criterion" in meta, badge_id
        assert isinstance(meta["criterion"], str) and meta["criterion"], badge_id
