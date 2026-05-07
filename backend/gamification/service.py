"""Gamification — XP, streak, counters, badges, orchestrator.

Public API (filled progressively across Paket 9 tasks):
  ensure_state(db, *, user_id)
  award_xp(db, *, user_id, delta_xp, reason, related_doc_id=None)
  get_xp_total(db, *, user_id) -> int
  update_streak_and_counters(db, *, user_id, action)  # Task 4
  record_skip(db, *, user_id)                         # Task 4
  run_after_save(db, *, user_id, username, action,    # Task 6
                 is_diff_zero, document_id)
  run_after_complete(db, *, user_id, username,        # Task 6
                     completed, document_id)
  get_profile_state(db, *, user_id) -> dict           # Task 8

Pure DB ops in this module; SSE publishes happen only inside the
orchestrator (Task 6).
"""
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional


log = logging.getLogger(__name__)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# State row management + XP
# ---------------------------------------------------------------------------

def ensure_state(db: sqlite3.Connection, *, user_id: int) -> None:
    """Insert a zero-state gamification_state row for the user if missing.
    Idempotent. Used by every write path that touches state."""
    db.execute(
        """
        INSERT OR IGNORE INTO gamification_state(
            user_id, total_xp, current_streak_days, longest_streak_days,
            last_active_date,
            today_save_count, today_complete_count,
            today_review_count, today_skip_count,
            updated_at
        ) VALUES (?, 0, 0, 0, NULL, 0, 0, 0, 0, ?)
        """,
        (user_id, _now_utc_iso()),
    )


def award_xp(
    db: sqlite3.Connection,
    *,
    user_id: int,
    delta_xp: int,
    reason: str,
    related_doc_id: Optional[str] = None,
) -> None:
    """Append a ledger row and update total_xp. Total clamps at 0 floor."""
    ensure_state(db, user_id=user_id)
    now = _now_utc_iso()
    db.execute(
        """
        INSERT INTO gamification_ledger(user_id, delta_xp, reason, related_doc_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, delta_xp, reason, related_doc_id, now),
    )
    db.execute(
        """
        UPDATE gamification_state
           SET total_xp = MAX(0, total_xp + ?),
               updated_at = ?
         WHERE user_id = ?
        """,
        (delta_xp, now, user_id),
    )


def get_xp_total(db: sqlite3.Connection, *, user_id: int) -> int:
    row = db.execute(
        "SELECT total_xp FROM gamification_state WHERE user_id=?", (user_id,)
    ).fetchone()
    return row["total_xp"] if row else 0
