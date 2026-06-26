"""v0014 — change GitHub backup default cadence to 24 hours."""
import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO site_settings (key, value, description, updated_at)
        VALUES (
            'backup.interval_seconds',
            '86400',
            'GitHub backup sıklığı (24 saat)',
            datetime('now')
        )
        """
    )
    conn.execute(
        """
        UPDATE site_settings
           SET value='86400',
               description='GitHub backup sıklığı (24 saat)',
               updated_at=datetime('now')
         WHERE key='backup.interval_seconds'
           AND value='600'
        """
    )
