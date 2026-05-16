import subprocess
import sqlite3
import sys
from pathlib import Path


def _run_cli(tmp_path: Path, *args) -> subprocess.CompletedProcess:
    env = {
        "DATA_DIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(Path(__file__).resolve().parent.parent),
    }
    return subprocess.run(
        [sys.executable, "-m", "backend.cli", *args],
        capture_output=True, text=True, env=env,
    )


def _seed_invite_and_user(tmp_path: Path, username="root"):
    """Apply migrations, seed invite, register a user."""
    _run_cli(tmp_path, "migrate")
    db = sqlite3.connect(str(tmp_path / "db" / "annotations.db"))
    db.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
        ("BURSIYER-2026",),
    )
    # Insert user directly (bcrypt hash any value, since we just need the row)
    db.execute(
        """INSERT INTO users(username, password_hash, role, is_active, avatar_color,
                              created_at, updated_at)
           VALUES (?, '$2b$12$bogushash', 'user', 1, '#000000', datetime('now'), datetime('now'))""",
        (username,),
    )
    db.execute(
        "INSERT INTO gamification_state(user_id, updated_at) VALUES ((SELECT id FROM users WHERE username=?), datetime('now'))",
        (username,),
    )
    db.commit()
    db.close()


def test_cli_promote_admin_promotes_existing_user(tmp_path):
    _seed_invite_and_user(tmp_path, "root")
    result = _run_cli(tmp_path, "promote-admin", "root")
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "promoted" in result.stdout.lower() or "admin" in result.stdout.lower()
    db = sqlite3.connect(str(tmp_path / "db" / "annotations.db"))
    row = db.execute("SELECT role FROM users WHERE username=?", ("root",)).fetchone()
    db.close()
    assert row[0] == "admin"


def test_cli_promote_admin_unknown_user_fails(tmp_path):
    _run_cli(tmp_path, "migrate")
    result = _run_cli(tmp_path, "promote-admin", "ghost")
    assert result.returncode != 0


def test_cli_create_invite_creates_active_code(tmp_path):
    _run_cli(tmp_path, "migrate")
    result = _run_cli(tmp_path, "create-invite", "FIRST-CODE-2026")
    assert result.returncode == 0, result.stderr
    db = sqlite3.connect(str(tmp_path / "db" / "annotations.db"))
    row = db.execute(
        "SELECT code, is_active FROM invite_codes WHERE code=?", ("FIRST-CODE-2026",)
    ).fetchone()
    db.close()
    assert row is not None
    assert row[1] == 1


def test_cli_promote_admin_writes_audit_with_null_admin_user_id(tmp_path):
    """CLI promote-admin should log with admin_user_id=NULL (no authenticated operator)."""
    _seed_invite_and_user(tmp_path, "testuser")
    result = _run_cli(tmp_path, "promote-admin", "testuser")
    assert result.returncode == 0, f"stderr: {result.stderr}"

    db = sqlite3.connect(str(tmp_path / "db" / "annotations.db"))
    audit_row = db.execute(
        "SELECT admin_user_id, action_type, target_id, trace_id FROM admin_audit_log WHERE action_type='promote_admin_cli'"
    ).fetchone()
    db.close()

    assert audit_row is not None, "No audit entry found for promote_admin_cli"
    assert audit_row[0] is None, f"Expected admin_user_id=NULL, got {audit_row[0]}"
    assert audit_row[1] == "promote_admin_cli"
    assert audit_row[2] is not None, "target_id should be set"
    assert audit_row[3] is None, "trace_id should be NULL (not passed)"


def test_cli_demote_admin_writes_audit_with_null_admin_user_id(tmp_path):
    """CLI demote-admin should log with admin_user_id=NULL (no authenticated operator)."""
    # Setup: run migrate once, then add both users and invite in one go
    _run_cli(tmp_path, "migrate")
    db = sqlite3.connect(str(tmp_path / "db" / "annotations.db"))
    db.execute(
        "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
        ("BURSIYER-2026",),
    )
    for username in ("admin1", "admin2"):
        db.execute(
            """INSERT INTO users(username, password_hash, role, is_active, avatar_color,
                                  created_at, updated_at)
               VALUES (?, '$2b$12$bogushash', 'admin', 1, '#000000', datetime('now'), datetime('now'))""",
            (username,),
        )
        db.execute(
            "INSERT INTO gamification_state(user_id, updated_at) VALUES ((SELECT id FROM users WHERE username=?), datetime('now'))",
            (username,),
        )
    db.commit()
    db.close()

    # Demote one admin
    result = _run_cli(tmp_path, "demote-admin", "admin2")
    assert result.returncode == 0, f"stderr: {result.stderr}"

    db = sqlite3.connect(str(tmp_path / "db" / "annotations.db"))
    audit_row = db.execute(
        "SELECT admin_user_id, action_type, target_id, trace_id FROM admin_audit_log WHERE action_type='demote_admin_cli'"
    ).fetchone()
    db.close()

    assert audit_row is not None, "No audit entry found for demote_admin_cli"
    assert audit_row[0] is None, f"Expected admin_user_id=NULL, got {audit_row[0]}"
    assert audit_row[1] == "demote_admin_cli"
    assert audit_row[2] is not None, "target_id should be set"
    assert audit_row[3] is None, "trace_id should be NULL (not passed)"
