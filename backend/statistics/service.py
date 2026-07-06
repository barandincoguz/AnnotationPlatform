"""Aggregate user statistics from activity, versions, and gamification tables."""
from __future__ import annotations

import sqlite3
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.statistics.models import StatisticsMetrics


PERIODS = ("today", "last_7_days", "last_30_days", "all_time")
TR_TZ = ZoneInfo("Europe/Istanbul")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _period_start(period: str, *, now: datetime) -> str | None:
    if period == "all_time":
        return None
    today_local = now.astimezone(TR_TZ).date()
    if period == "today":
        start_date = today_local
    elif period == "last_7_days":
        start_date = today_local - timedelta(days=6)
    elif period == "last_30_days":
        start_date = today_local - timedelta(days=29)
    else:
        raise ValueError(f"unknown period: {period!r}")

    start_local = datetime.combine(start_date, time.min, tzinfo=TR_TZ)
    return start_local.astimezone(timezone.utc).isoformat()


def _zero_metrics() -> dict:
    return StatisticsMetrics().model_dump()


def _period_metrics() -> dict[str, dict]:
    return {period: _zero_metrics() for period in PERIODS}


def _created_filter(column: str, since: str | None) -> tuple[str, tuple[str, ...]]:
    if since is None:
        return "", ()
    return f" AND {column} >= ?", (since,)


def _add_if_known(
    users_by_id: dict[int, dict],
    user_id: int | None,
    period: str,
    values: dict[str, int],
) -> None:
    if user_id is None or user_id not in users_by_id:
        return
    metrics = users_by_id[user_id]["metrics"][period]
    for key, value in values.items():
        metrics[key] = int(value or 0)


def _load_base_users(db: sqlite3.Connection) -> dict[int, dict]:
    rows = db.execute(
        """
        SELECT u.id, u.username, u.role, u.avatar_color,
               COALESCE(g.total_xp, 0) AS xp_total,
               COALESCE(g.current_streak_days, 0) AS streak_current,
               g.last_active_date,
               COUNT(b.badge_id) AS badges_count
          FROM users u
          LEFT JOIN gamification_state g ON g.user_id = u.id
          LEFT JOIN badges_earned b ON b.user_id = u.id
         GROUP BY u.id
         ORDER BY lower(u.username), u.id
        """
    ).fetchall()

    out: dict[int, dict] = {}
    for row in rows:
        out[int(row["id"])] = {
            "user": {
                "id": row["id"],
                "username": row["username"],
                "role": row["role"],
                "avatar_color": row["avatar_color"],
            },
            "xp_total": int(row["xp_total"] or 0),
            "badges_count": int(row["badges_count"] or 0),
            "streak_current": int(row["streak_current"] or 0),
            "last_active_date": row["last_active_date"],
            "metrics": _period_metrics(),
        }
    return out


def _apply_distinct_documents(
    db: sqlite3.Connection,
    users_by_id: dict[int, dict],
    *,
    period: str,
    since: str | None,
) -> None:
    activity_filter, activity_params = _created_filter("created_at", since)
    version_filter, version_params = _created_filter("created_at", since)
    annotation_filter, annotation_params = _created_filter("updated_at", since)
    rows = db.execute(
        f"""
        SELECT user_id, COUNT(DISTINCT document_id) AS distinct_documents
          FROM (
                SELECT user_id, document_id
                  FROM activity_events
                 WHERE user_id IS NOT NULL
                   AND document_id IS NOT NULL
                   {activity_filter}
                UNION
                SELECT user_id, document_id
                  FROM annotation_versions
                 WHERE user_id IS NOT NULL
                   {version_filter}
                UNION
                SELECT completed_by_user_id AS user_id, document_id
                  FROM annotations
                 WHERE is_completed = 1
                   AND completed_by_user_id IS NOT NULL
                   {annotation_filter}
          )
         GROUP BY user_id
        """,
        (*activity_params, *version_params, *annotation_params),
    ).fetchall()
    for row in rows:
        _add_if_known(
            users_by_id,
            row["user_id"],
            period,
            {"distinct_documents": row["distinct_documents"]},
        )


def _apply_activity_metrics(
    db: sqlite3.Connection,
    users_by_id: dict[int, dict],
    *,
    period: str,
    since: str | None,
) -> None:
    where_filter, params = _created_filter("created_at", since)
    rows = db.execute(
        f"""
        SELECT user_id,
               SUM(CASE WHEN event_type='annotation_save' THEN 1 ELSE 0 END) AS save_events,
               SUM(CASE WHEN event_type='complete_mark' THEN 1 ELSE 0 END) AS complete_events,
               SUM(CASE WHEN event_type='uncomplete' THEN 1 ELSE 0 END) AS uncomplete_events,
               SUM(CASE WHEN event_type='annotation_skip' THEN 1 ELSE 0 END) AS skip_events
          FROM activity_events
         WHERE user_id IS NOT NULL
           {where_filter}
         GROUP BY user_id
        """,
        params,
    ).fetchall()
    for row in rows:
        _add_if_known(
            users_by_id,
            row["user_id"],
            period,
            {
                "save_events": row["save_events"],
                "complete_events": row["complete_events"],
                "uncomplete_events": row["uncomplete_events"],
                "skip_events": row["skip_events"],
            },
        )


def _apply_version_metrics(
    db: sqlite3.Connection,
    users_by_id: dict[int, dict],
    *,
    period: str,
    since: str | None,
) -> None:
    where_filter, params = _created_filter("created_at", since)
    rows = db.execute(
        f"""
        SELECT user_id,
               COUNT(*) AS version_events,
               SUM(CASE WHEN action='create' THEN 1 ELSE 0 END) AS create_versions,
               SUM(CASE WHEN action='edit' THEN 1 ELSE 0 END) AS edit_versions,
               SUM(CASE WHEN action='complete_mark' THEN 1 ELSE 0 END) AS complete_mark_versions,
               SUM(CASE WHEN is_diff_zero=1 THEN 1 ELSE 0 END) AS zero_diff_versions
          FROM annotation_versions
         WHERE user_id IS NOT NULL
           {where_filter}
         GROUP BY user_id
        """,
        params,
    ).fetchall()
    for row in rows:
        _add_if_known(
            users_by_id,
            row["user_id"],
            period,
            {
                "version_events": row["version_events"],
                "create_versions": row["create_versions"],
                "edit_versions": row["edit_versions"],
                "complete_mark_versions": row["complete_mark_versions"],
                "zero_diff_versions": row["zero_diff_versions"],
            },
        )


def _apply_final_completion_metrics(
    db: sqlite3.Connection,
    users_by_id: dict[int, dict],
    *,
    period: str,
    since: str | None,
) -> None:
    where_filter, params = _created_filter("updated_at", since)
    rows = db.execute(
        f"""
        SELECT completed_by_user_id AS user_id,
               COUNT(*) AS final_completed_documents
          FROM annotations
         WHERE is_completed = 1
           AND completed_by_user_id IS NOT NULL
           {where_filter}
         GROUP BY completed_by_user_id
        """,
        params,
    ).fetchall()
    for row in rows:
        _add_if_known(
            users_by_id,
            row["user_id"],
            period,
            {"final_completed_documents": row["final_completed_documents"]},
        )


def _apply_xp_delta_metrics(
    db: sqlite3.Connection,
    users_by_id: dict[int, dict],
    *,
    period: str,
    since: str | None,
) -> None:
    where_filter, params = _created_filter("created_at", since)
    rows = db.execute(
        f"""
        SELECT user_id, COALESCE(SUM(delta_xp), 0) AS xp_delta
          FROM gamification_ledger
         WHERE user_id IS NOT NULL
           {where_filter}
         GROUP BY user_id
        """,
        params,
    ).fetchall()
    for row in rows:
        _add_if_known(
            users_by_id,
            row["user_id"],
            period,
            {"xp_delta": row["xp_delta"]},
        )


def _summarize(users: list[dict]) -> dict[str, dict]:
    summary = _period_metrics()
    for user in users:
        for period in PERIODS:
            metrics = user["metrics"][period]
            for key, value in metrics.items():
                summary[period][key] += int(value or 0)
    return summary


def get_user_statistics(db: sqlite3.Connection) -> dict:
    """Return aggregate statistics for all users who have passed training."""
    now = _now_utc()
    users_by_id = _load_base_users(db)

    for period in PERIODS:
        since = _period_start(period, now=now)
        _apply_distinct_documents(db, users_by_id, period=period, since=since)
        _apply_activity_metrics(db, users_by_id, period=period, since=since)
        _apply_version_metrics(db, users_by_id, period=period, since=since)
        _apply_final_completion_metrics(db, users_by_id, period=period, since=since)
        _apply_xp_delta_metrics(db, users_by_id, period=period, since=since)

    users = list(users_by_id.values())
    return {
        "generated_at": now.isoformat(),
        "summary": _summarize(users),
        "users": users,
    }
