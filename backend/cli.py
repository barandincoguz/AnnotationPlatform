"""Command-line interface.

Usage:
  python -m backend.cli migrate
  python -m backend.cli promote-admin <username>
  python -m backend.cli demote-admin <username>
  python -m backend.cli create-invite <code>
  python -m backend.cli rotate-invite <new_code>
"""
import argparse
import json
import sys
from datetime import datetime, timezone

from backend import config
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


def cmd_migrate(_args) -> int:
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        applied = apply_migrations(conn, discover_migrations())
    finally:
        conn.close()
    if applied:
        print(f"Applied {len(applied)} migrations: {', '.join(applied)}")
    else:
        print("No pending migrations.")
    return 0


def cmd_promote_admin(args) -> int:
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        apply_migrations(conn, discover_migrations())
        row = conn.execute("SELECT id FROM users WHERE username=?", (args.username,)).fetchone()
        if row is None:
            print(f"ERROR: user '{args.username}' not found", file=sys.stderr)
            return 2
        conn.execute(
            "UPDATE users SET role='admin', updated_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        conn.execute(
            """
            INSERT INTO admin_audit_log(admin_user_id, action_type, target_kind, target_id, metadata_json, created_at)
            VALUES (?, 'promote_admin_cli', 'user', ?, ?, ?)
            """,
            (
                row["id"], str(row["id"]),
                '{"source":"cli"}',
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    finally:
        conn.close()
    print(f"User '{args.username}' promoted to admin.")
    return 0


def cmd_demote_admin(args) -> int:
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        apply_migrations(conn, discover_migrations())
        row = conn.execute(
            "SELECT id, role FROM users WHERE username=?", (args.username,)
        ).fetchone()
        if row is None:
            print(f"ERROR: user '{args.username}' not found", file=sys.stderr)
            return 2
        if row["role"] != "admin":
            print(f"ERROR: user '{args.username}' is not an admin", file=sys.stderr)
            return 3
        active_admins = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role='admin' AND is_active=1"
        ).fetchone()["c"]
        if active_admins <= 1:
            print("ERROR: cannot demote the last active admin", file=sys.stderr)
            return 4
        conn.execute(
            "UPDATE users SET role='user', updated_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        conn.execute(
            """
            INSERT INTO admin_audit_log(admin_user_id, action_type, target_kind, target_id, metadata_json, created_at)
            VALUES (?, 'demote_admin_cli', 'user', ?, ?, ?)
            """,
            (
                row["id"], str(row["id"]),
                '{"source":"cli"}',
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    finally:
        conn.close()
    print(f"User '{args.username}' demoted to user.")
    return 0


def cmd_create_invite(args) -> int:
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        apply_migrations(conn, discover_migrations())
        # Deactivate existing active code (if any) — only one can be active
        conn.execute(
            "UPDATE invite_codes SET is_active=0, rotated_at=? WHERE is_active=1",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?, 1, ?)",
            (args.code, datetime.now(timezone.utc).isoformat()),
        )
    finally:
        conn.close()
    print(f"Invite code '{args.code}' created and activated.")
    return 0


def cmd_rotate_invite(args) -> int:
    return cmd_create_invite(args)  # same logic


def cmd_ingest(args) -> int:
    from pathlib import Path
    from backend.documents import service

    config.ensure_dirs()
    target = Path(args.path)
    if not target.exists():
        print(f"ERROR: path does not exist: {target}", file=sys.stderr)
        return 2

    conn = connect(config.DB_PATH)
    try:
        apply_migrations(conn, discover_migrations())
        if target.is_dir():
            count = service.ingest_directory(conn, target)
        else:
            count = service.ingest_file(conn, target)
    finally:
        conn.close()
    print(f"Ingested {count} document(s).")
    return 0


def cmd_import_gold_docs(args) -> int:
    path = args.path
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in {path}: {e}", file=sys.stderr)
        return 1

    docs = payload.get("gold_docs")
    if not isinstance(docs, list):
        print("error: payload must have a top-level 'gold_docs' list", file=sys.stderr)
        return 1

    required = ("gold_id", "content", "expected_concepts", "min_concept_count")
    for i, d in enumerate(docs):
        for k in required:
            if k not in d:
                print(f"error: gold_docs[{i}] missing required field '{k}'", file=sys.stderr)
                return 1

    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        apply_migrations(conn, discover_migrations())
        now = datetime.now(timezone.utc).isoformat()
        for d in docs:
            conn.execute(
                """
                INSERT OR REPLACE INTO training_gold_doc_overrides(
                    gold_id, is_deleted, content, expected_concepts,
                    min_concept_count, source, created_at, updated_at
                ) VALUES (?, 0, ?, ?, ?, 'custom', ?, ?)
                """,
                (
                    d["gold_id"], d["content"],
                    json.dumps(d["expected_concepts"]),
                    d["min_concept_count"],
                    now, now,
                ),
            )
    finally:
        conn.close()

    print(f"imported {len(docs)} gold-doc(s) into training_gold_doc_overrides")
    return 0


COMMANDS = {
    "migrate": cmd_migrate,
    "promote-admin": cmd_promote_admin,
    "demote-admin": cmd_demote_admin,
    "create-invite": cmd_create_invite,
    "rotate-invite": cmd_rotate_invite,
    "ingest": cmd_ingest,
    "import-gold-docs": cmd_import_gold_docs,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="backend.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply pending DB migrations")

    p_promote = sub.add_parser("promote-admin", help="Promote a user to admin")
    p_promote.add_argument("username")

    p_demote = sub.add_parser("demote-admin", help="Demote an admin to user")
    p_demote.add_argument("username")

    p_create = sub.add_parser("create-invite", help="Create / replace active invite code")
    p_create.add_argument("code")

    p_rotate = sub.add_parser("rotate-invite", help="Rotate active invite code")
    p_rotate.add_argument("code")

    p_ingest = sub.add_parser("ingest", help="Ingest JSON file or directory")
    p_ingest.add_argument("path", help="JSON file or directory containing *.json files")

    p_import_gold = sub.add_parser(
        "import-gold-docs",
        help="Import gold docs from a JSON file into training_gold_doc_overrides as source='custom'.",
    )
    p_import_gold.add_argument("path", help="path to gold-docs JSON file")

    args = parser.parse_args(argv)
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.error(f"unknown command: {args.command}")  # raises SystemExit
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
