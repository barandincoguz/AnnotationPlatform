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


# ---------------------------------------------------------------------------
# Streak + today-counter management
# ---------------------------------------------------------------------------

from datetime import timedelta

VALID_ACTIONS = ("save_create", "save_edit", "complete", "uncomplete", "skip")
_TR_TZ = timezone(timedelta(hours=3))


def _today_tr() -> str:
    """Today in Turkey time (UTC+3) as YYYY-MM-DD."""
    return datetime.now(_TR_TZ).date().isoformat()


def _is_yesterday_tr(d: str) -> bool:
    """Is the YYYY-MM-DD string exactly one Turkey-time day before today?"""
    today = datetime.strptime(_today_tr(), "%Y-%m-%d").date()
    try:
        d_date = datetime.strptime(d, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    return (today - d_date).days == 1


def _maybe_reset_today_counters(state_row: dict) -> dict:
    """If the row's last_active_date is older than today (TR), zero the
    today_* counters in the returned dict. Caller writes the dict back."""
    today = _today_tr()
    out = dict(state_row)
    last = out.get("last_active_date")
    if last != today:
        out["today_save_count"] = 0
        out["today_complete_count"] = 0
        out["today_review_count"] = 0
        out["today_skip_count"] = 0
    return out


def _next_streak(last_active_date, current, longest):
    """Compute (new_last_active_date, new_current, new_longest) for a save
    action firing today (TR). Only call this when the action is a save."""
    today = _today_tr()
    if last_active_date == today:
        return today, current, longest
    if _is_yesterday_tr(last_active_date or ""):
        new_current = current + 1
        return today, new_current, max(new_current, longest)
    # gap or first ever
    return today, 1, max(1, longest)


def update_streak_and_counters(
    db: sqlite3.Connection,
    *,
    user_id: int,
    action: str,
) -> None:
    """Single state-write entry point covering streak transition and the
    today_* counter bumps for save/complete/skip events. Lazily resets all
    today_* counters when the day rolls over.

    `action` is one of:
      - 'save_create'  -> save count +1, streak transition
      - 'save_edit'    -> save count +1 AND review count +1, streak transition
      - 'complete'     -> complete count +1, no streak change
      - 'uncomplete'   -> no counter changes (clamp behavior — symmetric undo
                          would require a delta but spec doesn't mandate it)
      - 'skip'         -> use record_skip() instead; this raises if used here
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"unknown action: {action!r}")
    if action == "skip":
        raise ValueError("use record_skip() for skip events")

    ensure_state(db, user_id=user_id)
    row = db.execute(
        "SELECT * FROM gamification_state WHERE user_id=?", (user_id,)
    ).fetchone()
    state = _maybe_reset_today_counters(dict(row))

    # Streak transition only on save actions.
    if action in ("save_create", "save_edit"):
        new_last, new_streak, new_longest = _next_streak(
            state.get("last_active_date"),
            state.get("current_streak_days", 0),
            state.get("longest_streak_days", 0),
        )
        state["last_active_date"] = new_last
        state["current_streak_days"] = new_streak
        state["longest_streak_days"] = new_longest

    # Counter bump.
    if action == "save_create":
        state["today_save_count"] += 1
    elif action == "save_edit":
        state["today_save_count"] += 1
        state["today_review_count"] += 1
    elif action == "complete":
        state["today_complete_count"] += 1
    # uncomplete / skip handled separately

    db.execute(
        """
        UPDATE gamification_state SET
            last_active_date=?,
            current_streak_days=?,
            longest_streak_days=?,
            today_save_count=?,
            today_complete_count=?,
            today_review_count=?,
            today_skip_count=?,
            updated_at=?
         WHERE user_id=?
        """,
        (
            state["last_active_date"],
            state["current_streak_days"],
            state["longest_streak_days"],
            state["today_save_count"],
            state["today_complete_count"],
            state["today_review_count"],
            state["today_skip_count"],
            _now_utc_iso(),
            user_id,
        ),
    )


def record_skip(db: sqlite3.Connection, *, user_id: int) -> None:
    """Sync entry point for the skip route. Bumps today_skip_count, runs
    the lazy day-rollover reset, but does NOT touch streak or last_active_date
    (skip is not a 'save')."""
    ensure_state(db, user_id=user_id)
    row = db.execute(
        "SELECT * FROM gamification_state WHERE user_id=?", (user_id,)
    ).fetchone()
    state = _maybe_reset_today_counters(dict(row))
    state["today_skip_count"] += 1
    db.execute(
        """
        UPDATE gamification_state SET
            today_save_count=?,
            today_complete_count=?,
            today_review_count=?,
            today_skip_count=?,
            updated_at=?
         WHERE user_id=?
        """,
        (
            state["today_save_count"],
            state["today_complete_count"],
            state["today_review_count"],
            state["today_skip_count"],
            _now_utc_iso(),
            user_id,
        ),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

from backend.shared import settings as S
from backend.shared.sse import broker as sse_broker
from backend.gamification import badges as badges_module
from backend.notifications import service as notif_service


def _xp_for_save_action(db: sqlite3.Connection, action: str) -> int:
    if action == "create":
        return S.get_int(db, "gamification.xp_save", default=1)
    if action == "edit":
        return S.get_int(db, "gamification.xp_review", default=2)
    return 0


def _award_badges_and_notify(
    db: sqlite3.Connection, *, user_id: int, username: str,
) -> list[dict]:
    """Insert each newly-earned badge row and return the list of unlock
    payloads for SSE publishing. Caller does the publishes."""
    earned: list[dict] = []
    for badge_id in badges_module.check_badges(db, user_id=user_id):
        meta = badges_module.BADGE_DEFS.get(badge_id, {"name": badge_id, "description": ""})
        now = _now_utc_iso()
        db.execute(
            "INSERT OR IGNORE INTO badges_earned(user_id, badge_id, earned_at) "
            "VALUES (?, ?, ?)",
            (user_id, badge_id, now),
        )
        # Persist a notification row (also publishes 'notification' SSE event below)
        notif_service.create(
            db, user_id=user_id, kind="badge_unlocked",
            title=f"Yeni rozet: {meta['name']}",
            body=meta["description"],
            data={"badge_id": badge_id, "name": meta["name"],
                  "description": meta["description"], "earned_at": now},
        )
        earned.append({
            "badge_id": badge_id,
            "name": meta["name"],
            "description": meta["description"],
            "earned_at": now,
        })
    return earned


async def _publish_unlock_events(user_id: int, earned: list[dict]) -> None:
    for payload in earned:
        await sse_broker.publish_to([user_id], "badge_unlocked", payload)
        # Also publish a generic 'notification' event so the inbox indicator updates
        await sse_broker.publish_to(
            [user_id], "notification",
            {"kind": "badge_unlocked", "data": payload},
        )


def _prior_version_user_id(
    db: sqlite3.Connection, *, document_id: str, current_user_id: int,
) -> Optional[int]:
    """Return the second-most-recent annotation_versions.user_id for the doc
    (the version BEFORE the one the current save just inserted), if it
    belongs to a different user. None otherwise."""
    rows = db.execute(
        """
        SELECT user_id FROM annotation_versions
         WHERE document_id=?
         ORDER BY id DESC LIMIT 2
        """,
        (document_id,),
    ).fetchall()
    if len(rows) < 2:
        return None
    prior_user_id = rows[1]["user_id"]
    if prior_user_id == current_user_id:
        return None
    return prior_user_id


async def run_after_save(
    db: sqlite3.Connection,
    *,
    user_id: int,
    username: str,
    action: str,            # 'create' | 'edit'
    is_diff_zero: bool,
    document_id: str,
) -> None:
    """Run after annotations.service.save_annotation has committed.

    Awards XP (xp_save or xp_review), updates streak/today-counters, checks
    for badge unlocks, persists a notification per unlock, and publishes
    personal SSE events. If `action='edit'` and `is_diff_zero=True`, also
    awards the prior version's editor +3 (xp_review_kept) — except when
    that prior editor is the same user.

    Each step is independently fault-isolated. Caller must invoke AFTER
    the save commits."""
    # --- 1. XP award (own action) ---
    try:
        delta = _xp_for_save_action(db, action)
        if delta > 0:
            reason = "save" if action == "create" else "review"
            award_xp(db, user_id=user_id, delta_xp=delta, reason=reason,
                     related_doc_id=document_id)
    except Exception:
        log.exception("award_xp failed for user %s on %s", user_id, document_id)

    # --- 2. Streak + counter update ---
    try:
        sub_action = "save_create" if action == "create" else "save_edit"
        update_streak_and_counters(db, user_id=user_id, action=sub_action)
    except Exception:
        log.exception("streak update failed for user %s", user_id)

    # --- 3. Badge check + notify (own user) ---
    own_earned: list[dict] = []
    try:
        own_earned = _award_badges_and_notify(db, user_id=user_id, username=username)
    except Exception:
        log.exception("badge check failed for user %s", user_id)

    # --- 4. Post-hoc review_kept for prior editor (if applicable) ---
    prior_earned: list[dict] = []
    prior_user_id: Optional[int] = None
    if action == "edit" and is_diff_zero:
        try:
            prior_user_id = _prior_version_user_id(
                db, document_id=document_id, current_user_id=user_id,
            )
            if prior_user_id is not None:
                kept_xp = S.get_int(db, "gamification.xp_review_kept", default=3)
                award_xp(db, user_id=prior_user_id, delta_xp=kept_xp,
                         reason="review_kept", related_doc_id=document_id)
                prior_earned = _award_badges_and_notify(
                    db, user_id=prior_user_id, username="",
                )
        except Exception:
            log.exception(
                "review_kept post-hoc award failed for prior editor %s on %s",
                prior_user_id, document_id,
            )

    # --- 5. SSE publishes ---
    try:
        await _publish_unlock_events(user_id, own_earned)
        if prior_user_id is not None:
            await _publish_unlock_events(prior_user_id, prior_earned)
    except Exception:
        log.exception("badge_unlocked publish failed")


async def run_after_complete(
    db: sqlite3.Connection,
    *,
    user_id: int,
    username: str,
    completed: bool,
    document_id: str,
) -> None:
    """Run after annotations.service.set_complete has committed for a real
    state change (caller has already filtered out same-state no-ops).

    On `completed=True`: awards xp_complete (default 5), bumps today_complete_count,
    checks for first_completion badge.
    On `completed=False`: no XP, no counter bump (clamp), no badge check."""
    if not completed:
        return

    try:
        delta = S.get_int(db, "gamification.xp_complete", default=5)
        if delta > 0:
            award_xp(db, user_id=user_id, delta_xp=delta, reason="complete",
                     related_doc_id=document_id)
    except Exception:
        log.exception("complete xp award failed for user %s", user_id)

    try:
        update_streak_and_counters(db, user_id=user_id, action="complete")
    except Exception:
        log.exception("complete counter update failed for user %s", user_id)

    own_earned: list[dict] = []
    try:
        own_earned = _award_badges_and_notify(db, user_id=user_id, username=username)
    except Exception:
        log.exception("badge check failed for user %s on complete", user_id)

    try:
        await _publish_unlock_events(user_id, own_earned)
    except Exception:
        log.exception("badge_unlocked publish failed (complete path)")
