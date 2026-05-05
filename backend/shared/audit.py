"""Single entry point for all event logging.

Four log channels:
- activity_events: high-frequency user actions (save, skip, open_doc, ...)
- behavioral_events: trigger-based detectors (speed warning, char limit, ...)
- admin_audit_log: sensitive admin operations (immutable record)
- system_events: backup/sync/error logs (sysadmin)
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

VALID_SEVERITIES = {"info", "warn", "error"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_activity(
    conn: sqlite3.Connection,
    user_id: int,
    event_type: str,
    *,
    session_id: Optional[int] = None,
    document_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    extra: Optional[dict] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO activity_events(
            user_id, session_id, event_type, document_id,
            duration_ms, extra_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, session_id, event_type, document_id,
            duration_ms,
            json.dumps(extra) if extra is not None else None,
            _now(),
        ),
    )


def log_behavioral(
    conn: sqlite3.Connection,
    user_id: int,
    detector: str,
    *,
    threshold_value: Optional[float] = None,
    actual_value: Optional[float] = None,
    context: Optional[dict] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO behavioral_events(
            user_id, detector, threshold_value, actual_value,
            context_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, detector, threshold_value, actual_value,
            json.dumps(context) if context is not None else None,
            _now(),
        ),
    )


def log_admin_action(
    conn: sqlite3.Connection,
    admin_user_id: int,
    action_type: str,
    *,
    target_kind: Optional[str] = None,
    target_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO admin_audit_log(
            admin_user_id, action_type, target_kind, target_id,
            metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            admin_user_id, action_type, target_kind, target_id,
            json.dumps(metadata) if metadata is not None else None,
            _now(),
        ),
    )


def log_system_event(
    conn: sqlite3.Connection,
    event_type: str,
    severity: str,
    *,
    message: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"invalid severity: {severity!r} (must be one of {VALID_SEVERITIES})")
    conn.execute(
        """
        INSERT INTO system_events(
            event_type, severity, message, extra_json, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            event_type, severity, message,
            json.dumps(extra) if extra is not None else None,
            _now(),
        ),
    )
