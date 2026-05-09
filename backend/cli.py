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
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

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


def _clone_backup_repo(pat_url: str, dest: Path) -> None:
    """Wrapper for `git clone <pat-url> <dest>`. Extracted as its own
    function so tests can patch it without spawning real git processes.

    Catches subprocess.TimeoutExpired and scrubs the PAT from the argv
    before re-raising as RuntimeError. Without scrubbing, the timeout
    exception's str() contains the raw PAT URL, which would leak into
    stderr/logs when the caller surfaces the error."""
    from backend.backup.git_remote import scrub_pat, CLONE_TIMEOUT
    cmd = ["git", "clone", pat_url, str(dest)]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=CLONE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        scrubbed_cmd = [scrub_pat(arg) for arg in cmd]
        raise RuntimeError(
            f"git clone timed out after {CLONE_TIMEOUT}s: {scrubbed_cmd}"
        ) from None
    if result.returncode != 0:
        stderr = scrub_pat(result.stderr or "")
        raise RuntimeError(f"git clone failed: {stderr}")


def cmd_restore_from_github(args) -> int:
    """Restore the local DB from a snapshot in the GitHub backup repo.

    Flow:
      1. Read BACKUP_REPO_URL + GITHUB_PAT from config (env-backed).
      2. Rename current DB to corrupt-<UTC ISO>.db.bak.
      3. Clone the backup repo to /tmp/restore-<ts>/.
      4. Pick the requested snapshot (default: latest.json).
      5. Confirmation prompt (skipped with --yes).
      6. Run migrations on the new (empty) DB, then restore.
      7. On error: rename corrupt-bak back to annotations.db.
      8. Clean up the /tmp clone.
    """
    if not config.BACKUP_REPO_URL or not config.GITHUB_PAT:
        print(
            "error: BACKUP_REPO_URL and GITHUB_PAT must both be set "
            "in the environment.",
            file=sys.stderr,
        )
        return 1

    db_path = config.DB_PATH
    bak_path = None
    if db_path.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bak_path = db_path.parent / f"corrupt-{ts}.db.bak"
        db_path.rename(bak_path)

    from backend.backup.git_remote import inject_pat
    pat_url = inject_pat(config.BACKUP_REPO_URL, config.GITHUB_PAT)
    # tempfile.mkdtemp gives a guaranteed-unique path; remove the empty dir
    # so `git clone` can create it fresh (git clone refuses non-empty targets).
    clone_parent = Path(tempfile.mkdtemp(prefix="restore-"))
    clone_dir = clone_parent / "repo"
    try:
        try:
            _clone_backup_repo(pat_url, clone_dir)
        except Exception as e:
            print(f"error: clone failed: {e}", file=sys.stderr)
            if bak_path is not None:
                bak_path.rename(db_path)
            return 1

        try:
            if args.snapshot:
                snap_path = clone_dir / f"{args.snapshot}.json"
            else:
                snap_path = clone_dir / "latest.json"
            if not snap_path.exists():
                print(f"error: snapshot not found: {snap_path.name}", file=sys.stderr)
                if bak_path is not None:
                    bak_path.rename(db_path)
                return 1

            if not args.yes:
                with open(snap_path, encoding="utf-8") as f:
                    preview = json.load(f)
                n_tables = len(preview)
                n_rows = sum(len(rows) for rows in preview.values())
                print(f"Will restore {n_tables} tables, {n_rows} total rows from {snap_path.name}.")
                answer = input("Continue? [y/N] ").strip().lower()
                if answer != "y":
                    print("aborted")
                    if bak_path is not None:
                        bak_path.rename(db_path)
                    return 1

            config.ensure_dirs()
            conn = connect(db_path)
            try:
                apply_migrations(conn, discover_migrations())

                from backend.backup.restore import restore_from_snapshot
                result = restore_from_snapshot(conn, snap_path)
            finally:
                conn.close()

            print(f"Restored {result['total_rows']} rows across {len(result['tables'])} tables:")
            for table, count in result["tables"].items():
                print(f"  {table}: {count}")
            if result.get("skipped_tables"):
                print("Skipped tables (not in current schema):")
                for t in result["skipped_tables"]:
                    print(f"  {t}")

        except Exception as e:
            print(f"error: restore failed: {e}", file=sys.stderr)
            if db_path.exists():
                db_path.unlink()
            if bak_path is not None:
                bak_path.rename(db_path)
            return 1

        bak_msg = str(bak_path) if bak_path is not None else "(none — DB did not exist before restore)"
        print(f"\nRestore complete. Pre-restore DB saved at: {bak_msg}")
        return 0
    finally:
        shutil.rmtree(clone_parent, ignore_errors=True)


COMMANDS = {
    "migrate": cmd_migrate,
    "promote-admin": cmd_promote_admin,
    "demote-admin": cmd_demote_admin,
    "create-invite": cmd_create_invite,
    "rotate-invite": cmd_rotate_invite,
    "ingest": cmd_ingest,
    "import-gold-docs": cmd_import_gold_docs,
    "restore-from-github": cmd_restore_from_github,
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

    p_restore = sub.add_parser(
        "restore-from-github",
        help="Restore DB from latest GitHub backup snapshot",
        description=(
            "Restore the local DB from a GitHub backup snapshot. "
            "WARNING: This is a destructive operation that overwrites the "
            "current DB. The CLI does NOT currently detect a running server's "
            "WAL lock — STOP THE SERVER before running this command, or you "
            "may corrupt the DB."
        ),
    )
    p_restore.add_argument(
        "--snapshot", default=None,
        help="Specific snapshot stamp (e.g. 20260509-1430); default uses latest.json",
    )
    p_restore.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    p_restore.add_argument("--force", action="store_true",
        help="Reserved for future WAL-lock detection bypass",
    )

    args = parser.parse_args(argv)
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.error(f"unknown command: {args.command}")  # raises SystemExit
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
