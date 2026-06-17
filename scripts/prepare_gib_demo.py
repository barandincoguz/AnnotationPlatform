#!/usr/bin/env python3
"""Prepare two isolated, pre-trained accounts for the GIB concurrency demo.

The password is read from GIB_DEMO_PASSWORD so credentials never need to be
stored in the repository. The operation is idempotent and does not alter
documents or shared annotations.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import config
from backend.gamification import service as gamification_service
from backend.shared import auth
from backend.shared.db import connect


DEFAULT_USERS = ("gib_demo_a", "gib_demo_b")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _upsert_demo_user(db, username: str, password_hash: str) -> int:
    row = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    now = _now()
    if row:
        user_id = int(row["id"])
        db.execute(
            """
            UPDATE users
               SET password_hash=?, role='user', is_active=1,
                   has_seen_manual=1, has_passed_training=1, updated_at=?
             WHERE id=?
            """,
            (password_hash, now, user_id),
        )
    else:
        cursor = db.execute(
            """
            INSERT INTO users(
                username, password_hash, role, is_active,
                has_seen_manual, has_passed_training,
                avatar_color, created_at, updated_at
            ) VALUES (?, ?, 'user', 1, 1, 1, ?, ?, ?)
            """,
            (
                username,
                password_hash,
                "#2563eb" if username.endswith("_a") else "#059669",
                now,
                now,
            ),
        )
        user_id = int(cursor.lastrowid)

    db.execute("DELETE FROM document_locks WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM drafts WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM training_attempts WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM badges_earned WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM gamification_ledger WHERE user_id=?", (user_id,))
    db.execute(
        """
        UPDATE gamification_state
           SET total_xp=0, current_streak_days=0, longest_streak_days=0,
               last_active_date=NULL, today_save_count=0,
               today_complete_count=0, today_review_count=0,
               today_skip_count=0, updated_at=?
         WHERE user_id=?
        """,
        (now, user_id),
    )
    db.execute(
        "UPDATE user_sessions SET ended_at=? WHERE user_id=? AND ended_at IS NULL",
        (now, user_id),
    )
    gamification_service.ensure_state(db, user_id=user_id)
    return user_id


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare two pre-trained users for the GIB live demo."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=config.DB_PATH,
        help=f"SQLite database path (default: {config.DB_PATH})",
    )
    parser.add_argument(
        "--users",
        nargs=2,
        metavar=("USER_A", "USER_B"),
        default=DEFAULT_USERS,
        help="Exactly two usernames used in the concurrency rehearsal.",
    )
    args = parser.parse_args()

    password = os.environ.get("GIB_DEMO_PASSWORD", "")
    if len(password) < 12:
        print(
            "error: set GIB_DEMO_PASSWORD to a password of at least 12 characters",
            file=sys.stderr,
        )
        return 2

    db_path = args.db.expanduser().resolve()
    if not db_path.exists():
        print(f"error: database not found: {db_path}", file=sys.stderr)
        return 2

    password_hash = auth.hash_password(password)
    db = connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        user_ids = [
            _upsert_demo_user(db, username.strip(), password_hash)
            for username in args.users
        ]
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    finally:
        db.close()

    print(f"database: {db_path}")
    for username, user_id in zip(args.users, user_ids, strict=True):
        print(f"ready: {username} (id={user_id}, manual=seen, training=passed)")
    print("account-local drafts, progress, active sessions and held locks were cleared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
