"""Admin-side service helpers for cross-cutting features.

Currently houses list_system_events. Future T9 polish may relocate
list_admin_audit here from backend/users/service.py."""
import sqlite3


def list_system_events(
    db: sqlite3.Connection, *,
    limit: int, offset: int,
    event_type: str | None = None,
    severity: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Paginated + filtered system_events query.
    Returns {items, total, has_more}.

    The system_events table has no user_id column; events are system-scoped.
    Severity filter accepts 'info' | 'warn' | 'error' (CHECK constraint
    on the table).
    """
    where = []
    params: list = []
    if event_type is not None:
        where.append("event_type = ?")
        params.append(event_type)
    if severity is not None:
        where.append("severity = ?")
        params.append(severity)
    if date_from is not None:
        where.append("created_at >= ?")
        params.append(f"{date_from}T00:00:00+00:00")
    if date_to is not None:
        where.append("created_at <= ?")
        params.append(f"{date_to}T23:59:59+00:00")
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = db.execute(
        f"SELECT COUNT(*) AS c FROM system_events {where_clause}", params
    ).fetchone()["c"]

    rows = db.execute(
        f"""SELECT id, event_type, severity, message, extra_json, created_at
            FROM system_events {where_clause}
            ORDER BY id DESC LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()

    items = [
        {
            "id": r["id"],
            "event_type": r["event_type"],
            "severity": r["severity"],
            "message": r["message"],
            "extra": r["extra_json"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": total,
        "has_more": offset + len(items) < total,
    }
