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
from backend.shared import audit
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
        audit.log_admin_action(
            conn,
            admin_user_id=None,
            action_type="promote_admin_cli",
            target_kind="user",
            target_id=str(row["id"]),
            metadata={"source": "cli"},
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
        audit.log_admin_action(
            conn,
            admin_user_id=None,
            action_type="demote_admin_cli",
            target_kind="user",
            target_id=str(row["id"]),
            metadata={"source": "cli"},
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


def cmd_reset_password(args) -> int:
    config.ensure_dirs()
    if len(args.new_password) < 8:
        print("ERROR: password must be at least 8 characters", file=sys.stderr)
        return 5
    conn = connect(config.DB_PATH)
    try:
        apply_migrations(conn, discover_migrations())
        row = conn.execute("SELECT id FROM users WHERE username=?", (args.username,)).fetchone()
        if row is None:
            print(f"ERROR: user '{args.username}' not found", file=sys.stderr)
            return 2
        user_id = row["id"]

        from backend.shared import auth as auth_mod
        conn.execute(
            "UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
            (auth_mod.hash_password(args.new_password),
             datetime.now(timezone.utc).isoformat(),
             user_id),
        )
        cur = conn.execute("DELETE FROM user_sessions WHERE user_id=?", (user_id,))
        invalidated = cur.rowcount or 0

        audit.log_admin_action(
            conn,
            admin_user_id=None,
            action_type="reset_password_cli",
            target_kind="user",
            target_id=str(user_id),
            metadata={"source": "cli"},
        )
    finally:
        conn.close()
    print(f"Password reset for user {args.username!r} (id={user_id}); "
          f"{invalidated} session(s) invalidated.")
    return 0


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


def cmd_openapi_dump(args) -> int:
    """Export the FastAPI OpenAPI spec to JSON for frontend type generation.

    Imports backend.main lazily so that running `--help` (or any other CLI
    subcommand) does not trigger app construction / router import side
    effects. The output path defaults to ./openapi.json.
    """
    from backend.main import app as fastapi_app

    output = Path(args.output)
    output.write_text(json.dumps(fastapi_app.openapi(), indent=2))
    print(f"OpenAPI written to {output}")
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


def cmd_seed_e2e(args) -> int:
    """Reset the DB at $DB_PATH and seed minimal fixtures for Playwright
    e2e runs: one invite code, three pre-trained users, four sample
    documents. Always run against an ISOLATED test DB (DB_PATH env var)
    — refuses to touch the default production path without --force.
    """
    db_path = config.DB_PATH
    if str(db_path).endswith("annotations.db") and "anotasyon-e2e" not in str(db_path) and not args.force:
        print(
            f"refusing to seed default DB at {db_path}; set DB_PATH to an "
            "e2e-only path (e.g. /tmp/anotasyon-e2e.db), or pass --force",
            file=sys.stderr,
        )
        return 2

    config.ensure_dirs()
    if args.reset and db_path.exists():
        db_path.unlink()
        for suffix in ("-wal", "-shm"):
            sidecar = db_path.with_name(db_path.name + suffix)
            if sidecar.exists():
                sidecar.unlink()

    from backend.shared import auth
    from backend.documents import service as doc_svc

    conn = connect(db_path)
    try:
        apply_migrations(conn, discover_migrations())
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,?)",
            ("E2E-CODE", now),
        )
        # Password hashed via the prod auth module so a real
        # POST /api/auth/login round-trip succeeds.
        pw_hash = auth.hash_password("e2e-pass-123!")
        for username, role in (("alice", "user"), ("bob", "user"), ("admin", "admin")):
            conn.execute(
                """INSERT INTO users(
                    username, password_hash, role, is_active,
                    has_passed_training, has_seen_manual,
                    avatar_color, created_at, updated_at
                ) VALUES (?, ?, ?, 1, 1, 1, ?, ?, ?)""",
                (username, pw_hash, role, "#3b82f6", now, now),
            )
        conn.commit()
    finally:
        conn.close()

    docs = [
        {
            "evrakOid": "e2e-doc-alpha",
            "sayi": 101,
            "tarih": "20260115",
            "konu": "E2E test belgesi alpha — kira gelirinin vergilendirilmesi",
            "vergiTuru": "0001",
            "pdfText": (
                "T.C.\nGELIR IDARESI BASKANLIGI\n\n"
                "Kira gelirinin vergilendirilmesi hakkinda ozelge talebi.\n\n"
                "Konuyla ilgili aciklamalar asagida yer almaktadir."
            ),
            "kanunBilgileri": [
                {"kanunMaddesi": "37", "kanunKodu": "193 - GELIR VERGISI KANUNU",
                 "kanunMaddesiTuru": "ASIL"},
            ],
            "bkkTebligSirkuBilgileri": [],
        },
        {
            "evrakOid": "e2e-doc-bravo",
            "sayi": 102,
            "tarih": "20260116",
            "konu": "E2E test belgesi bravo — KDV iadesi",
            "vergiTuru": "0015",
            "pdfText": "KDV iadesi hakkinda ozelge govdesi.",
            "kanunBilgileri": [],
            "bkkTebligSirkuBilgileri": [],
        },
        {
            "evrakOid": "e2e-doc-charlie",
            "sayi": 103,
            "tarih": "20260117",
            "konu": "E2E test belgesi charlie — kurumlar vergisi",
            "vergiTuru": "0002",
            "pdfText": "Kurumlar vergisi hakkinda ozelge govdesi.",
            "kanunBilgileri": [],
            "bkkTebligSirkuBilgileri": [],
        },
        {
            "evrakOid": "e2e-doc-concurrency",
            "sayi": 104,
            "tarih": "20260118",
            "konu": "E2E concurrency belgesi — iki kullanıcı kilit testi",
            "vergiTuru": "0001",
            "pdfText": (
                "193 sayili Gelir Vergisi Kanununun 37. maddesi "
                "uyarinca ticari kazanc degerlendirilir."
            ),
            "kanunBilgileri": [],
            "bkkTebligSirkuBilgileri": [],
        },
    ]
    tmp_dir = Path(tempfile.mkdtemp(prefix="e2e-seed-"))
    tmp_path = tmp_dir / "docs.json"
    tmp_path.write_text(json.dumps(docs), encoding="utf-8")
    conn = connect(db_path)
    try:
        doc_svc.ingest_file(conn, tmp_path)
        conn.commit()
    finally:
        conn.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"E2E DB seeded at {db_path}")
    print("  invite code: E2E-CODE")
    print("  users: alice, bob, admin  (password: e2e-pass-123!)")
    print(f"  documents: {len(docs)}")
    return 0


COMMANDS = {
    "migrate": cmd_migrate,
    "promote-admin": cmd_promote_admin,
    "demote-admin": cmd_demote_admin,
    "create-invite": cmd_create_invite,
    "rotate-invite": cmd_rotate_invite,
    "reset-password": cmd_reset_password,
    "ingest": cmd_ingest,
    "import-gold-docs": cmd_import_gold_docs,
    "restore-from-github": cmd_restore_from_github,
    "openapi-dump": cmd_openapi_dump,
    "seed-e2e": cmd_seed_e2e,
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

    p_reset = sub.add_parser(
        "reset-password",
        help="Reset a user's password and invalidate their active sessions",
    )
    p_reset.add_argument("username")
    p_reset.add_argument("new_password")

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

    p_openapi = sub.add_parser(
        "openapi-dump",
        help="Dump FastAPI OpenAPI spec to JSON (frontend type generation)",
    )
    p_openapi.add_argument(
        "--output", default="openapi.json",
        help="Output path for the JSON file (default: openapi.json)",
    )

    p_seed = sub.add_parser(
        "seed-e2e",
        help="Reset + seed an isolated DB for Playwright e2e tests",
        description=(
            "Wipes the DB at $DB_PATH (sidecars too) and re-seeds with a "
            "single invite code, three users (alice/bob/admin, password "
            "'e2e-pass-123!'), and four sample documents. Refuses to "
            "run against the default production path unless --force."
        ),
    )
    p_seed.add_argument("--reset", action="store_true",
                        help="Drop the existing DB file before seeding")
    p_seed.add_argument("--force", action="store_true",
                        help="Allow seeding the default DB path (NOT recommended)")

    args = parser.parse_args(argv)
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.error(f"unknown command: {args.command}")  # raises SystemExit
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
