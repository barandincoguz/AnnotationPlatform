"""Admin-side service helpers for cross-cutting features.

Houses list_system_events and list_admin_audit (paginated/filtered queries
over system_events and admin_audit_log respectively)."""
import json
import sqlite3


def _decode_json_blob(raw):
    """Parse a JSON-text DB blob into a dict/list/None. Returns None for
    null/empty input. Returns the raw string if it is not valid JSON
    so callers see the original cell content rather than `null`
    (helps debugging corrupted rows)."""
    if raw is None or raw == "":
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def list_system_events(
    db: sqlite3.Connection, *,
    limit: int, offset: int,
    event_type: str | None = None,
    event_type_prefix: str | None = None,
    severity: str | None = None,
    trace_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Paginated + filtered system_events query.
    Returns {items, total, has_more}."""
    where = []
    params: list = []
    if event_type is not None:
        where.append("event_type = ?")
        params.append(event_type)
    if event_type_prefix is not None:
        where.append("event_type LIKE ?")
        params.append(event_type_prefix + "%")
    if severity is not None:
        where.append("severity = ?")
        params.append(severity)
    if trace_id is not None:
        where.append("trace_id = ?")
        params.append(trace_id)
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
        f"""SELECT id, event_type, severity, message, extra_json, trace_id, created_at
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
            "extra": _decode_json_blob(r["extra_json"]),
            "trace_id": r["trace_id"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {"items": items, "total": total, "has_more": offset + len(items) < total}


def list_admin_audit(
    db: sqlite3.Connection, *,
    limit: int, offset: int,
    admin_id: int | None = None,
    action: str | None = None,
    trace_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Paginated + filtered admin_audit_log query.
    Returns {items, total, has_more}. Each item includes admin_username
    via LEFT JOIN users (NULL when admin was deleted)."""
    where = []
    params: list = []
    if admin_id is not None:
        where.append("a.admin_user_id = ?")
        params.append(admin_id)
    if action is not None:
        where.append("a.action_type = ?")
        params.append(action)
    if trace_id is not None:
        where.append("a.trace_id = ?")
        params.append(trace_id)
    if date_from is not None:
        where.append("a.created_at >= ?")
        params.append(f"{date_from}T00:00:00+00:00")
    if date_to is not None:
        where.append("a.created_at <= ?")
        params.append(f"{date_to}T23:59:59+00:00")
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = db.execute(
        f"SELECT COUNT(*) AS c FROM admin_audit_log a {where_clause}", params
    ).fetchone()["c"]

    rows = db.execute(
        f"""SELECT a.id, a.admin_user_id, u.username AS admin_username,
                   a.action_type, a.target_kind, a.target_id,
                   a.metadata_json, a.trace_id, a.created_at
            FROM admin_audit_log a
            LEFT JOIN users u ON u.id = a.admin_user_id
            {where_clause}
            ORDER BY a.id DESC LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()

    items = [
        {
            "id": r["id"],
            "admin_user_id": r["admin_user_id"],
            "admin_username": r["admin_username"],
            "action_type": r["action_type"],
            "target_kind": r["target_kind"],
            "target_id": r["target_id"],
            "metadata": _decode_json_blob(r["metadata_json"]),
            "trace_id": r["trace_id"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {"items": items, "total": total, "has_more": offset + len(items) < total}
