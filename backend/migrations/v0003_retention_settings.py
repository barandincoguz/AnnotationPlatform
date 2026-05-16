"""v0003 — retention default settings.

Inserts 7 rows into site_settings: interval_seconds + one days key per
PURGE_POLICY entry (behavioral_events, activity_events, system_events,
user_sessions, notifications, drafts).

INSERT OR IGNORE so re-applying after a restore preserves operator
overrides written between v0003 application and the restore point.

Rename note: the original revision used retention.cycle_interval_seconds;
renamed to retention.interval_seconds to match the backup.interval_seconds
project idiom (cycle_ infix was gratuitous). A DELETE step cleans up the
legacy key on dev DBs that already applied the old v0003 revision.
"""
import sqlite3


SETTINGS_SQL = """
-- Drop the legacy key from the first revision of v0003 (renamed to
-- match backup.interval_seconds project idiom; cycle_ infix was
-- gratuitous). Safe no-op on fresh DBs.
DELETE FROM site_settings WHERE key='retention.cycle_interval_seconds';

INSERT OR IGNORE INTO site_settings (key, value, updated_at) VALUES
  ('retention.interval_seconds',       '86400',  datetime('now')),
  ('retention.behavioral_events.days', '30',     datetime('now')),
  ('retention.activity_events.days',   '90',     datetime('now')),
  ('retention.system_events.days',     '180',    datetime('now')),
  ('retention.user_sessions.days',     '30',     datetime('now')),
  ('retention.notifications.days',     '30',     datetime('now')),
  ('retention.drafts.days',            '14',     datetime('now'));
"""


def up(conn: sqlite3.Connection) -> None:
    import re as _re
    _SQL_KW = _re.compile(r"(CREATE|INSERT|DROP|ALTER|UPDATE|DELETE)\b", _re.IGNORECASE)
    for raw in SETTINGS_SQL.split(";"):
        no_comments = _re.sub(r"--[^\n]*", "", raw)
        m = _SQL_KW.search(no_comments)
        if not m:
            continue
        stmt = _SQL_KW.search(raw).start()
        conn.execute(raw[stmt:].strip())
