"""Admin-side service helpers for cross-cutting features.

Houses list_system_events and list_admin_audit (paginated/filtered queries
over system_events and admin_audit_log respectively)."""
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


def list_admin_audit(
    db: sqlite3.Connection, *,
    limit: int, offset: int,
    admin_id: int | None = None,
    action: str | None = None,
    date_from: str | None = None,  # ISO date "2026-05-08"
    date_to: str | None = None,
) -> dict:
    """Paginated + filtered admin_audit_log query.
    Returns {items, total, has_more}."""
    where = []
    params: list = []
    if admin_id is not None:
        where.append("admin_user_id = ?")
        params.append(admin_id)
    if action is not None:
        where.append("action_type = ?")
        params.append(action)
    if date_from is not None:
        where.append("created_at >= ?")
        params.append(f"{date_from}T00:00:00+00:00")
    if date_to is not None:
        where.append("created_at <= ?")
        params.append(f"{date_to}T23:59:59+00:00")
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = db.execute(
        f"SELECT COUNT(*) AS c FROM admin_audit_log {where_clause}", params
    ).fetchone()["c"]

    rows = db.execute(
        f"""SELECT id, admin_user_id, action_type, target_kind, target_id,
                   metadata_json, created_at
            FROM admin_audit_log {where_clause}
            ORDER BY id DESC LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()

    items = [
        {
            "id": r["id"],
            "admin_user_id": r["admin_user_id"],
            "action_type": r["action_type"],
            "target_kind": r["target_kind"],
            "target_id": r["target_id"],
            "metadata": r["metadata_json"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": total,
        "has_more": offset + len(items) < total,
    }
