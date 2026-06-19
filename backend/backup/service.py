"""Backup primitives: dump tables to JSON, write snapshot files atomically,
rotate older snapshots. No git involvement here — that's git_remote.py."""
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend import config
from backend.backup import git_remote
from backend.shared import audit


log = logging.getLogger(__name__)


# Tables NOT dumped.
#   - schema_migrations is re-derived from migrations on the restored DB,
#     so persisting it would create version-skew risk.
#   - user_sessions contains token digests and operational metadata. Session
#     state has no restore value, so copying it into a backup repository would
#     only preserve stale authentication state. Re-login after restore is the
#     intentional contract.
EXCLUDED_TABLES = {
    "schema_migrations",
    "user_sessions",
    "document_locks",
    "_outbox",
}

# Snapshot format version. Stored under "__format_version" (double-underscore
# prefix marks payload-level metadata, distinct from table names). Bump when
# making breaking changes to snapshot shape; restore_from_snapshot ignores
# unknown __-prefixed keys so older code can still read newer snapshots
# (forward compat for additive metadata).
SNAPSHOT_FORMAT_VERSION = 1


def is_wal_busy(db: sqlite3.Connection) -> bool:
    """Cheap heuristic: WAL has uncommitted frames from another connection.

    Returns True if PRAGMA wal_checkpoint(PASSIVE) reports either the
    `busy` flag is set OR there are log frames not yet checkpointed.
    Conservative — false positives are fine (operator retries); false
    negatives risk corruption of the restored DB.
    """
    try:
        row = db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    except sqlite3.OperationalError:
        return True
    if row is None:
        return False
    busy, log_frames, ckpt_frames = row[0], row[1], row[2]
    return bool(busy) or (log_frames - ckpt_frames > 0)


def dump_all_tables_to_json(db: sqlite3.Connection) -> dict:
    """Return a snapshot dict {<table>: [{col: val, ...}, ...]} of every
    user table in the DB. Excludes schema_migrations.

    Reads under BEGIN IMMEDIATE so the snapshot is consistent across tables
    even if other writers are active.
    """
    db.execute("BEGIN")
    try:
        tables = [
            r["name"] for r in db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if r["name"] not in EXCLUDED_TABLES
        ]

        out: dict = {"__format_version": SNAPSHOT_FORMAT_VERSION}
        for table in tables:
            cols = [
                r["name"] for r in db.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            ]
            rows = db.execute(f"SELECT * FROM {table}").fetchall()
            out[table] = [
                {c: r[c] for c in cols}
                for r in rows
            ]
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    return out


def _snapshot_table_names(db: sqlite3.Connection) -> list[str]:
    return sorted(
        row["name"]
        for row in db.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if row["name"] not in EXCLUDED_TABLES
    )


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_database_snapshot(
    db: sqlite3.Connection,
    backup_dir: Path,
    ts: str,
) -> tuple[Path, int]:
    """Stream a transaction-consistent DB snapshot directly to disk."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    latest = backup_dir / "latest.json"
    timestamped = backup_dir / f"{ts}.json"
    timestamped_tmp = timestamped.with_suffix(".json.tmp")
    latest_tmp = latest.with_suffix(".json.tmp")

    db.execute("BEGIN")
    try:
        tables = _snapshot_table_names(db)
        with open(timestamped_tmp, "w", encoding="utf-8") as stream:
            stream.write("{")
            stream.write(json.dumps("__format_version"))
            stream.write(":")
            stream.write(str(SNAPSHOT_FORMAT_VERSION))

            for table in tables:
                stream.write(",")
                stream.write(json.dumps(table, ensure_ascii=False))
                stream.write(":[")
                columns = [
                    row["name"]
                    for row in db.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                ]
                first_row = True
                for row in db.execute(f"SELECT * FROM {table}"):
                    if not first_row:
                        stream.write(",")
                    first_row = False
                    stream.write(
                        json.dumps(
                            {column: row[column] for column in columns},
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
                stream.write("]")
            stream.write("}")
            stream.flush()
            os.fsync(stream.fileno())
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        timestamped_tmp.unlink(missing_ok=True)
        raise

    os.replace(timestamped_tmp, timestamped)
    _fsync_directory(backup_dir)
    try:
        with open(timestamped, "rb") as source, open(latest_tmp, "wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        os.replace(latest_tmp, latest)
        _fsync_directory(backup_dir)
    except Exception:
        latest_tmp.unlink(missing_ok=True)
        raise

    return timestamped, len(tables)


def write_snapshot(payload: dict, backup_dir: Path, ts: str) -> Path:
    """Atomically write `payload` to two files in `backup_dir`:
       - latest.json
       - <ts>.json
    Uses temp-file + os.replace for crash safety. Returns the timestamped path.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    latest = backup_dir / "latest.json"
    timestamped = backup_dir / f"{ts}.json"
    # sort_keys=True produces byte-stable JSON when rows are unchanged
    # between cycles, so git sees no diff and avoids meaningless commits.
    body = json.dumps(payload, ensure_ascii=False, indent=None, sort_keys=True)

    for target in (latest, timestamped):
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, target)

    return timestamped


def rotate_snapshots(backup_dir: Path, keep: int = 144) -> list[Path]:
    """Delete oldest timestamped snapshots, keeping the `keep` most recent
    by modification time. Never touches latest.json or directories
    (including .git/, which is excluded by the is_file() filter).

    Returns the list of paths that were actually deleted (excluding any
    that failed to unlink). Callers using the count for audit logging
    can trust the value matches reality.
    """
    candidates = [
        p for p in backup_dir.iterdir()
        if p.is_file() and p.name != "latest.json"
        and p.suffix == ".json"
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    to_delete = candidates[keep:]
    deleted: list[Path] = []
    for p in to_delete:
        try:
            p.unlink()
            deleted.append(p)
        except Exception:
            log.exception("failed to delete old snapshot %s", p)
    return deleted


def utc_timestamp() -> str:
    """Return UTC timestamp formatted as YYYYMMDD-HHMM. Used for snapshot
    filenames so lexicographic sort matches chronological sort."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")


def run_backup_cycle(
    db: sqlite3.Connection, *, trace_id: Optional[str] = None,
) -> dict:
    """Top-level orchestrator. Runs:
       dump → write → rotate → (git if env set) → log.

    Returns {snapshot_path, committed_sha, pushed, rotated_count}.

    On any step failure: logs system_events('backup_failed', severity='error')
    with extra_json={step, error} and re-raises so callers (the loop swallows;
    the manual route translates to 500). Missing BACKUP_REPO_URL/GITHUB_PAT
    is NOT a failure: dump+rotate still run, git is skipped, success event
    is event_type='backup_skipped_no_remote' (severity='info').

    trace_id: when set (e.g. by the admin run-now route), every emitted
    system_events row carries it for cross-table correlation. Background
    loop callers omit it → NULL.
    """
    backup_dir = config.BACKUP_DIR
    repo_url = config.BACKUP_REPO_URL
    pat = config.GITHUB_PAT

    # --- stream transaction-consistent snapshot ---
    ts = utc_timestamp()
    try:
        snapshot_path, table_count = write_database_snapshot(
            db,
            backup_dir,
            ts,
        )
    except Exception as e:
        audit.log_system_event(
            db, "backup_failed", "error",
            message="snapshot failed",
            extra={"step": "snapshot", "error": str(e)},
            trace_id=trace_id,
        )
        raise

    # --- rotate ---
    try:
        rotated = rotate_snapshots(backup_dir, keep=144)
    except Exception as e:
        audit.log_system_event(
            db, "backup_failed", "error",
            message="rotate failed",
            extra={"step": "rotate", "error": str(e)},
            trace_id=trace_id,
        )
        raise

    # --- git push (skip if no remote configured) ---
    if not repo_url or not pat:
        audit.log_system_event(
            db, "backup_skipped_no_remote", "info",
            message="BACKUP_REPO_URL or GITHUB_PAT not set; skipping git push",
            extra={"snapshot_path": str(snapshot_path), "rotated_count": len(rotated)},
            trace_id=trace_id,
        )
        return {
            "snapshot_path": str(snapshot_path),
            "committed_sha": None,
            "pushed": False,
            "rotated_count": len(rotated),
        }

    try:
        git_remote.ensure_initialized(backup_dir, repo_url, pat)
    except Exception as e:
        audit.log_system_event(
            db, "backup_failed", "error",
            message="git init failed",
            extra={"step": "init", "error": str(e)},
            trace_id=trace_id,
        )
        raise

    try:
        sha = git_remote.commit_and_push(backup_dir, f"auto-backup {ts}")
    except Exception as e:
        audit.log_system_event(
            db, "backup_failed", "error",
            message="git push failed",
            extra={"step": "push", "error": str(e)},
            trace_id=trace_id,
        )
        raise

    audit.log_system_event(
        db, "backup_success", "info",
        message=f"backed up {table_count} tables",
        extra={
            "snapshot_path": str(snapshot_path),
            "committed_sha": sha,
            "rotated_count": len(rotated),
        },
        trace_id=trace_id,
    )
    return {
        "snapshot_path": str(snapshot_path),
        "committed_sha": sha,
        "pushed": True,
        "rotated_count": len(rotated),
    }
