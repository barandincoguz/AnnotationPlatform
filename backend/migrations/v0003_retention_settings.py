"""v0003 — retention default settings.

Inserts 7 rows into site_settings: cycle_interval_seconds + one days
key per PURGE_POLICY entry (behavioral_events, activity_events,
system_events, user_sessions, notifications, drafts).

INSERT OR IGNORE so re-applying after a restore preserves operator
overrides written between v0003 application and the restore point.
"""
import sqlite3


SETTINGS_SQL = """
INSERT OR IGNORE INTO site_settings (key, value, updated_at) VALUES
  ('retention.cycle_interval_seconds', '86400',  datetime('now')),
  ('retention.behavioral_events.days', '30',     datetime('now')),
  ('retention.activity_events.days',   '90',     datetime('now')),
  ('retention.system_events.days',     '180',    datetime('now')),
  ('retention.user_sessions.days',     '30',     datetime('now')),
  ('retention.notifications.days',     '30',     datetime('now')),
  ('retention.drafts.days',            '14',     datetime('now'));
"""


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(SETTINGS_SQL)
