"""Tests for backend/retention/service.py — compute_cutoffs (Task 2),
purge_single_table (Task 3), run_purge (Task 4)."""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


# ---------------- compute_cutoffs ----------------


def test_compute_cutoffs_uses_code_default_when_no_db_override(fresh_db):
    """If site_settings has no retention.<table>.days override, the
    PolicyEntry's default_days is used."""
    from backend.retention.service import compute_cutoffs, PURGE_POLICY

    # Wipe defaults inserted by v0003 so the resolver falls through to code.
    fresh_db.execute("DELETE FROM site_settings WHERE key LIKE 'retention.%'")
    fresh_db.commit()

    cutoffs = compute_cutoffs(fresh_db)
    now = datetime.now(timezone.utc)
    for entry in PURGE_POLICY:
        expected = now - timedelta(days=entry.default_days)
        actual = cutoffs[entry.table]
        # Allow 5-second wiggle for clock skew between compute and assertion.
        assert abs((actual - expected).total_seconds()) < 5, (
            f"cutoff for {entry.table}: expected {expected}, got {actual}"
        )


def test_compute_cutoffs_prefers_db_override(fresh_db):
    """If site_settings has retention.<table>.days, that value wins over default."""
    from backend.retention.service import compute_cutoffs

    # v0003 sets 30 by default; override to 60.
    fresh_db.execute(
        "UPDATE site_settings SET value=? WHERE key=?",
        ("60", "retention.behavioral_events.days"),
    )
    fresh_db.commit()

    cutoffs = compute_cutoffs(fresh_db)
    now = datetime.now(timezone.utc)
    expected = now - timedelta(days=60)
    assert abs((cutoffs["behavioral_events"] - expected).total_seconds()) < 5


def test_compute_cutoffs_treats_zero_days_as_kill_switch(fresh_db):
    """retention.<table>.days = 0 → entry is omitted from the cutoff dict
    entirely. Caller must skip the table for this cycle."""
    from backend.retention.service import compute_cutoffs

    fresh_db.execute(
        "UPDATE site_settings SET value='0' WHERE key='retention.drafts.days'"
    )
    fresh_db.commit()

    cutoffs = compute_cutoffs(fresh_db)
    assert "drafts" not in cutoffs


def test_compute_cutoffs_raises_on_negative_days(fresh_db):
    """Negative days is operator error; raise ValueError so the cycle fails
    fast and the system_events row records the misconfiguration."""
    from backend.retention.service import compute_cutoffs

    fresh_db.execute(
        "UPDATE site_settings SET value='-1' WHERE key='retention.notifications.days'"
    )
    fresh_db.commit()

    with pytest.raises(ValueError) as exc:
        compute_cutoffs(fresh_db)
    assert "negative" in str(exc.value).lower() or "-1" in str(exc.value)


def test_compute_cutoffs_raises_on_non_numeric_value(fresh_db):
    """Non-JSON-numeric value (e.g. 'abc') yields a ValueError carrying the
    key name, so the eventual retention_failed audit log is actionable
    rather than a raw json.JSONDecodeError fragment."""
    from backend.retention.service import compute_cutoffs

    fresh_db.execute(
        "UPDATE site_settings SET value='abc' WHERE key='retention.drafts.days'"
    )
    fresh_db.commit()

    with pytest.raises(ValueError) as exc:
        compute_cutoffs(fresh_db)
    assert "retention.drafts.days" in str(exc.value)


# ---------------- purge_single_table ----------------


def _seed_behavioral_event(db, *, days_ago: int) -> int:
    """Insert a behavioral_events row dated `days_ago` days in the past.
    Uses Python datetime bound as isoformat (matching production write
    format from backend.shared.audit) so test data is byte-identical
    to what real flows produce."""
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    cur = db.execute(
        """
        INSERT INTO behavioral_events
            (user_id, detector, threshold_value, actual_value, context_json, created_at)
        VALUES (1, 'test', 1.0, 1.0, '{}', ?)
        """,
        (ts,),
    )
    db.commit()
    return cur.lastrowid


def _seed_user(db, user_id: int = 1):
    """Insert a row into users so behavioral_events FK is satisfied."""
    db.execute(
        """
        INSERT INTO users (id, username, password_hash, role, is_active,
                           has_seen_manual, has_passed_training,
                           avatar_color, created_at, updated_at)
        VALUES (?, 'u', 'x', 'user', 1, 1, 1, '#000', datetime('now'), datetime('now'))
        """,
        (user_id,),
    )
    db.commit()


def test_purge_single_table_deletes_rows_older_than_cutoff(fresh_db):
    """A row dated 31 days ago is deleted when retention is 30 days."""
    from backend.retention.service import (
        purge_single_table, PURGE_POLICY,
    )
    from datetime import datetime, timedelta, timezone

    _seed_user(fresh_db)
    old_id = _seed_behavioral_event(fresh_db, days_ago=31)

    entry = next(p for p in PURGE_POLICY if p.table == "behavioral_events")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    fresh_db.execute("BEGIN IMMEDIATE")
    count = purge_single_table(fresh_db, entry, cutoff)
    fresh_db.execute("COMMIT")

    assert count == 1
    row = fresh_db.execute(
        "SELECT id FROM behavioral_events WHERE id=?", (old_id,)
    ).fetchone()
    assert row is None


def test_purge_single_table_keeps_rows_younger_than_cutoff(fresh_db):
    """A row dated 5 days ago is preserved when retention is 30 days."""
    from backend.retention.service import (
        purge_single_table, PURGE_POLICY,
    )
    from datetime import datetime, timedelta, timezone

    _seed_user(fresh_db)
    young_id = _seed_behavioral_event(fresh_db, days_ago=5)

    entry = next(p for p in PURGE_POLICY if p.table == "behavioral_events")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    fresh_db.execute("BEGIN IMMEDIATE")
    count = purge_single_table(fresh_db, entry, cutoff)
    fresh_db.execute("COMMIT")

    assert count == 0
    row = fresh_db.execute(
        "SELECT id FROM behavioral_events WHERE id=?", (young_id,)
    ).fetchone()
    assert row is not None


def test_purge_single_table_respects_extra_where(fresh_db):
    """notifications has extra_where='is_read=1' so unread rows are NEVER
    purged regardless of age."""
    from backend.retention.service import (
        purge_single_table, PURGE_POLICY,
    )
    from datetime import datetime, timedelta, timezone

    _seed_user(fresh_db)
    sixty_days_ago = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    # Insert two old (60-day) notifications: one read, one unread.
    fresh_db.execute(
        """INSERT INTO notifications (user_id, kind, title, body, data_json,
           is_read, created_at)
           VALUES (1, 't', 'old read', 'b', '{}', 1, ?)""",
        (sixty_days_ago,),
    )
    fresh_db.execute(
        """INSERT INTO notifications (user_id, kind, title, body, data_json,
           is_read, created_at)
           VALUES (1, 't', 'old unread', 'b', '{}', 0, ?)""",
        (sixty_days_ago,),
    )
    fresh_db.commit()

    entry = next(p for p in PURGE_POLICY if p.table == "notifications")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    fresh_db.execute("BEGIN IMMEDIATE")
    count = purge_single_table(fresh_db, entry, cutoff)
    fresh_db.execute("COMMIT")

    assert count == 1  # only the read one
    rows = fresh_db.execute(
        "SELECT title, is_read FROM notifications ORDER BY title"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["title"] == "old unread"
    assert rows[0]["is_read"] == 0


def test_purge_single_table_uses_correct_cutoff_column(fresh_db):
    """user_sessions uses ended_at (not created_at). Verify by inserting
    an old started_at + recent ended_at row — it must NOT be purged."""
    from backend.retention.service import (
        purge_single_table, PURGE_POLICY,
    )
    from datetime import datetime, timedelta, timezone

    _seed_user(fresh_db)
    now_utc = datetime.now(timezone.utc)
    started_60 = (now_utc - timedelta(days=60)).isoformat()
    ended_1    = (now_utc - timedelta(days=1)).isoformat()
    started_90 = (now_utc - timedelta(days=90)).isoformat()
    ended_60   = (now_utc - timedelta(days=60)).isoformat()
    # Old started_at, recent ended_at → should be kept.
    fresh_db.execute(
        """INSERT INTO user_sessions
           (user_id, session_token, ip_hash, user_agent,
            started_at, ended_at, last_activity_at)
           VALUES (1, 'tok-recent', '', '', ?, ?, ?)""",
        (started_60, ended_1, ended_1),
    )
    # Old started_at AND old ended_at → should be purged.
    fresh_db.execute(
        """INSERT INTO user_sessions
           (user_id, session_token, ip_hash, user_agent,
            started_at, ended_at, last_activity_at)
           VALUES (1, 'tok-old', '', '', ?, ?, ?)""",
        (started_90, ended_60, ended_60),
    )
    fresh_db.commit()

    entry = next(p for p in PURGE_POLICY if p.table == "user_sessions")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    fresh_db.execute("BEGIN IMMEDIATE")
    count = purge_single_table(fresh_db, entry, cutoff)
    fresh_db.execute("COMMIT")

    assert count == 1
    rows = fresh_db.execute(
        "SELECT session_token FROM user_sessions ORDER BY session_token"
    ).fetchall()
    assert [r["session_token"] for r in rows] == ["tok-recent"]


def test_purge_single_table_spares_active_sessions_with_null_ended_at(fresh_db):
    """user_sessions extra_where='ended_at IS NOT NULL' must spare active
    sessions (NULL ended_at) regardless of how old started_at is. Without
    this guard, every active long-running session would be deleted on
    every cycle, instantly logging out every user."""
    from backend.retention.service import (
        purge_single_table, PURGE_POLICY,
    )
    from datetime import datetime, timedelta, timezone

    _seed_user(fresh_db)
    very_old_started = (
        datetime.now(timezone.utc) - timedelta(days=365)
    ).isoformat()
    fresh_db.execute(
        """INSERT INTO user_sessions
           (user_id, session_token, ip_hash, user_agent,
            started_at, ended_at, last_activity_at)
           VALUES (1, 'tok-active', '', '', ?, NULL, ?)""",
        (very_old_started, very_old_started),
    )
    fresh_db.commit()

    entry = next(p for p in PURGE_POLICY if p.table == "user_sessions")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    fresh_db.execute("BEGIN IMMEDIATE")
    count = purge_single_table(fresh_db, entry, cutoff)
    fresh_db.execute("COMMIT")

    assert count == 0
    row = fresh_db.execute(
        "SELECT session_token FROM user_sessions WHERE session_token=?",
        ("tok-active",),
    ).fetchone()
    assert row is not None


def test_run_purge_closes_expired_active_sessions_for_future_cleanup(
    fresh_db,
    monkeypatch,
):
    from backend import config
    from backend.retention.service import run_purge
    from datetime import datetime, timedelta, timezone
    import json

    monkeypatch.setattr(config, "SESSION_MAX_AGE_SECONDS", 60)
    _seed_user(fresh_db)
    expired = (datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat()
    fresh_db.execute(
        """
        INSERT INTO user_sessions(
            user_id, session_token, started_at, last_activity_at
        ) VALUES (1, 'expired-active', ?, ?)
        """,
        (expired, expired),
    )

    result = run_purge(fresh_db)

    assert result["purged"]["user_sessions"] == 0
    row = fresh_db.execute(
        "SELECT ended_at FROM user_sessions WHERE session_token='expired-active'"
    ).fetchone()
    assert row["ended_at"] is not None
    event = fresh_db.execute(
        "SELECT extra_json FROM system_events "
        "WHERE event_type='retention_success' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert json.loads(event["extra_json"])["expired_sessions_closed"] == 1


def test_close_expired_sessions_fails_closed_on_malformed_timestamp(fresh_db):
    from backend.retention.service import close_expired_sessions

    _seed_user(fresh_db)
    fresh_db.execute(
        """
        INSERT INTO user_sessions(
            user_id, session_token, started_at, last_activity_at
        ) VALUES (1, 'malformed-active', 'not-a-date', datetime('now'))
        """
    )

    assert close_expired_sessions(fresh_db) == 1
    assert fresh_db.execute(
        "SELECT ended_at FROM user_sessions "
        "WHERE session_token='malformed-active'"
    ).fetchone()["ended_at"] is not None


# ---------------- run_purge ----------------


def test_run_purge_writes_retention_success_event_with_counts(fresh_db):
    """Successful cycle writes one system_events row with event_type=
    'retention_success', severity='info', extra_json containing per-table
    purge counts."""
    from backend.retention.service import run_purge

    _seed_user(fresh_db)
    _seed_behavioral_event(fresh_db, days_ago=31)
    _seed_behavioral_event(fresh_db, days_ago=5)  # young, must survive

    out = run_purge(fresh_db)

    assert out["ok"] is True
    assert out["purged"]["behavioral_events"] == 1
    assert out["total"] >= 1

    row = fresh_db.execute(
        """SELECT event_type, severity, extra_json FROM system_events
           WHERE event_type='retention_success' ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    assert row is not None
    assert row["severity"] == "info"
    import json
    extra = json.loads(row["extra_json"])
    assert extra["purged"]["behavioral_events"] == 1


def test_run_purge_atomic_rollback_on_mid_cycle_failure(fresh_db, monkeypatch):
    """If purge_single_table raises mid-cycle, all DELETEs roll back,
    a retention_failed event is recorded, and the exception propagates."""
    from backend.retention import service as svc

    _seed_user(fresh_db)
    old_id = _seed_behavioral_event(fresh_db, days_ago=60)

    call_count = [0]
    real_purge = svc.purge_single_table

    def flaky(db, entry, cutoff):
        call_count[0] += 1
        if call_count[0] == 2:
            raise sqlite3.OperationalError("simulated mid-cycle failure")
        return real_purge(db, entry, cutoff)

    monkeypatch.setattr(svc, "purge_single_table", flaky)

    with pytest.raises(sqlite3.OperationalError):
        svc.run_purge(fresh_db)

    # First entry's DELETE was rolled back; old_id must still exist.
    row = fresh_db.execute(
        "SELECT id FROM behavioral_events WHERE id=?", (old_id,)
    ).fetchone()
    assert row is not None  # rolled back

    # retention_failed event recorded with step + error in extra_json.
    fail = fresh_db.execute(
        """SELECT event_type, severity, extra_json FROM system_events
           WHERE event_type='retention_failed' ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    assert fail is not None
    assert fail["severity"] == "error"
    import json
    extra = json.loads(fail["extra_json"])
    assert extra["step"] == "purge"
    assert "simulated mid-cycle failure" in extra["error"]


def test_run_purge_skips_table_when_kill_switch_set(fresh_db):
    """retention.behavioral_events.days=0 means that table is skipped
    entirely; count is reported as 0 (not absent), so admin UI shows
    'this table not purged this cycle'."""
    from backend.retention.service import run_purge

    fresh_db.execute(
        "UPDATE site_settings SET value='0' WHERE key='retention.behavioral_events.days'"
    )
    fresh_db.commit()

    _seed_user(fresh_db)
    old_id = _seed_behavioral_event(fresh_db, days_ago=60)

    out = run_purge(fresh_db)

    assert out["purged"]["behavioral_events"] == 0
    row = fresh_db.execute(
        "SELECT id FROM behavioral_events WHERE id=?", (old_id,)
    ).fetchone()
    assert row is not None  # kill switch preserved it


def test_run_purge_failed_event_records_failing_table(fresh_db, monkeypatch):
    """When purge_single_table raises mid-cycle, retention_failed extra_json
    must record which table failed so operators can debug from audit logs
    without reading exception traces."""
    from backend.retention import service as svc

    _seed_user(fresh_db)
    _seed_behavioral_event(fresh_db, days_ago=60)

    real = svc.purge_single_table

    def flaky(db, entry, cutoff):
        if entry.table == "activity_events":
            raise sqlite3.OperationalError("simulated activity_events failure")
        return real(db, entry, cutoff)

    monkeypatch.setattr(svc, "purge_single_table", flaky)

    with pytest.raises(sqlite3.OperationalError):
        svc.run_purge(fresh_db)

    fail = fresh_db.execute(
        """SELECT extra_json FROM system_events
           WHERE event_type='retention_failed' ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    import json
    extra = json.loads(fail["extra_json"])
    assert extra["table"] == "activity_events"
    assert extra["step"] == "purge"


def test_run_purge_preserves_original_exception_when_rollback_fails(tmp_path, monkeypatch):
    """If db.execute('ROLLBACK') itself raises (e.g., transaction already
    auto-rolled back by SQLite on COMMIT failure), the original purge
    exception must still propagate — operator needs to see the real
    failure, not a misleading 'no transaction is active' rollback error.

    sqlite3.Connection.execute is read-only in CPython 3.13+, so we wrap
    the connection in a thin proxy that intercepts ROLLBACK calls.
    """
    from backend.retention import service as svc
    from backend.migrations import discover_migrations
    from backend.migrations.runner import apply_migrations
    from backend.shared.db import connect

    db_path = tmp_path / "test.db"
    real_conn = connect(db_path)
    apply_migrations(real_conn, discover_migrations())

    _seed_user(real_conn)
    _seed_behavioral_event(real_conn, days_ago=60)

    class RollbackBombProxy:
        """Proxy that delegates all attribute access to the wrapped connection
        but raises on 'ROLLBACK' execute calls — simulating the case where
        SQLite already auto-rolled-back (e.g., after a COMMIT failure) and the
        explicit ROLLBACK would raise 'no transaction is active'."""

        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *args, **kwargs):
            if sql == "ROLLBACK":
                raise sqlite3.OperationalError("simulated rollback failure")
            return self._conn.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    proxy = RollbackBombProxy(real_conn)

    real_purge = svc.purge_single_table

    def flaky(db, entry, cutoff):
        if entry.table == "activity_events":
            raise RuntimeError("real purge failure")
        return real_purge(db, entry, cutoff)

    monkeypatch.setattr(svc, "purge_single_table", flaky)

    try:
        with pytest.raises(RuntimeError) as exc:
            svc.run_purge(proxy)
        # The ORIGINAL exception ("real purge failure") must propagate, NOT
        # the rollback failure. If this assertion fails, the rollback
        # exception masked the original.
        assert "real purge failure" in str(exc.value)
    finally:
        real_conn.close()
