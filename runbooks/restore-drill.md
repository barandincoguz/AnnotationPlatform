# Restore Drill — Copy-Only Runbook

**Purpose:** Verify the restore pipeline end-to-end without touching production data.
Every command in this runbook operates on a temporary copy of the database.
The production DB is never opened for writing.

---

## ⚠️ STOP GATE 1 — Read Before Proceeding

```
THIS DRILL MUST NEVER WRITE TO THE PRODUCTION DATABASE.

The drill copies annotations.db to a temp directory ($DRILL_DIR).
Every subsequent command — snapshot generation, restore, verification —
operates against $DRILL_DIR/db/annotations.db, not the live path.

Before running any command, confirm:
  [ ] $DRILL_DIR is set to a path under /tmp, NOT under the project data/ tree.
  [ ] You have NOT started a dev server that points at the production DATA_DIR.
  [ ] The production container is stopped (or you are on a dev machine with no
      running server accessing the live DB).

If any box is unchecked — STOP HERE.
```

---

## Pre-flight: Copy DB to a Temp Directory

```bash
# 1. Create a throwaway work area.
DRILL_DIR=$(mktemp -d -t restore-drill-XXXXXX)
echo "DRILL_DIR=$DRILL_DIR"

# 2. Reproduce the directory layout the app expects.
mkdir -p "$DRILL_DIR/db" "$DRILL_DIR/backup"

# 3. Copy the DB files (WAL sidecars too, if present).
cp /path/to/project/data/db/annotations.db     "$DRILL_DIR/db/annotations.db"
cp /path/to/project/data/db/annotations.db-wal "$DRILL_DIR/db/annotations.db-wal" 2>/dev/null || true
cp /path/to/project/data/db/annotations.db-shm "$DRILL_DIR/db/annotations.db-shm" 2>/dev/null || true

# 4. Confirm the copy lives under /tmp, NOT under the live data/ tree.
COPY_PATH=$(realpath "$DRILL_DIR/db/annotations.db")
LIVE_PATH=$(realpath /path/to/project/data/db/annotations.db)
echo "copy: $COPY_PATH"
echo "live: $LIVE_PATH"
[ "$COPY_PATH" != "$LIVE_PATH" ] && echo "OK — paths differ" || echo "ERROR — paths are the same; abort"
```

Replace `/path/to/project` with the actual project root (e.g. `~/Desktop/deneme`).

---

## Section 1 — Baseline Checksum (Row Counts Before Restore)

Record row counts for the critical tables that the restore will touch.

```bash
sqlite3 "$DRILL_DIR/db/annotations.db" "
SELECT 'users',              COUNT(*) FROM users
UNION ALL
SELECT 'annotations',        COUNT(*) FROM annotations
UNION ALL
SELECT 'documents_meta',     COUNT(*) FROM documents_meta
UNION ALL
SELECT 'annotation_versions',COUNT(*) FROM annotation_versions
UNION ALL
SELECT 'admin_audit_log',    COUNT(*) FROM admin_audit_log
UNION ALL
SELECT 'invite_codes',       COUNT(*) FROM invite_codes;
" > "$DRILL_DIR/baseline.txt"

cat "$DRILL_DIR/baseline.txt"
```

Save the output; you will compare against it in Section 4.

---

## Section 2 — Generate a Snapshot from the Copy

Point `DATA_DIR` at the drill directory so `run_backup_cycle` writes the snapshot
there and reads only the copy.

```bash
# From the project root (virtual env active):
DATA_DIR="$DRILL_DIR" python - <<'EOF'
import sqlite3, json, pathlib, os
from backend import config
from backend.backup.service import dump_all_tables_to_json, write_snapshot, utc_timestamp

db_path = pathlib.Path(os.environ["DATA_DIR"]) / "db" / "annotations.db"
backup_dir = pathlib.Path(os.environ["DATA_DIR"]) / "backup"
backup_dir.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
payload = dump_all_tables_to_json(conn)
conn.close()

ts = utc_timestamp()
snap = write_snapshot(payload, backup_dir, ts=ts)
print(f"snapshot written: {snap}")
EOF

# Alias for use in later sections.
SNAPSHOT="$DRILL_DIR/backup/latest.json"
ls -lh "$SNAPSHOT"
```

Verify that `$SNAPSHOT` exists and has a non-zero size before continuing.

---

## ⚠️ STOP GATE 2 — Confirm You Are on the Copy

```
Before running the restore, double-check:

  realpath "$DRILL_DIR/db/annotations.db"   # must start with /tmp/...
  realpath "$SNAPSHOT"                       # must start with /tmp/...

If either path resolves to something inside the project's data/ tree — STOP.
Do not proceed until the paths are correct.
```

Run the check:

```bash
echo "DB:       $(realpath "$DRILL_DIR/db/annotations.db")"
echo "Snapshot: $(realpath "$SNAPSHOT")"
```

Both must begin with `/tmp/`.

---

## Section 3 — Restore via the U1 HTTP Route

The U1 route is `POST /api/admin/backup/restore` (added in Wave 2.5, commit `7991d3f`).
It accepts a multipart upload of the snapshot JSON and requires an admin session cookie.

**Start a throwaway dev server pointed at the copy:**

```bash
# In a separate terminal — do NOT use the production server.
DATA_DIR="$DRILL_DIR" uvicorn backend.main:app --port 8765 --no-access-log &
SERVER_PID=$!
sleep 2   # wait for startup

# Confirm the server is using the drill DB, not the live one:
curl -s http://localhost:8765/api/health | python3 -m json.tool
```

**Obtain an admin session cookie from the throwaway server:**

```bash
# Replace 'admin' / 'your-password' with credentials that exist in the COPY.
curl -s -c "$DRILL_DIR/cookies.txt" -X POST http://localhost:8765/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"your-password"}' | python3 -m json.tool
```

**Run the restore:**

```bash
curl -s -b "$DRILL_DIR/cookies.txt" \
  -X POST http://localhost:8765/api/admin/backup/restore \
  -F "snapshot=@$SNAPSHOT" | python3 -m json.tool
```

Expected response shape:

```json
{
  "ok": true,
  "total_rows": <integer>,
  "tables": { "<table_name>": <row_count>, "..." : "..." },
  "skipped_tables": [],
  "trace_id": "<uuid>"
}
```

A `409 db_busy` response means the WAL has uncommitted frames from another writer.
Stop the throwaway server cleanly and retry. See Section 7 for other failure modes.

**Alternative — CLI restore (no HTTP server needed):**

If you have a snapshot from a GitHub backup repo, the CLI subcommand exercises
the identical `restore_from_snapshot` code path directly:

```bash
# Stop any server using $DRILL_DIR first.
DB_PATH="$DRILL_DIR/db/annotations.db" \
  python -m backend.cli restore-from-github \
  --snapshot <YYYYMMDD-HHMM>   # or omit for latest.json
```

The CLI renames the existing DB to a `corrupt-<ts>.db.bak` file before restoring,
giving you an automatic rollback target.

---

## Section 4 — Verify Identity (Row Counts After Restore)

```bash
sqlite3 "$DRILL_DIR/db/annotations.db" "
SELECT 'users',              COUNT(*) FROM users
UNION ALL
SELECT 'annotations',        COUNT(*) FROM annotations
UNION ALL
SELECT 'documents_meta',     COUNT(*) FROM documents_meta
UNION ALL
SELECT 'annotation_versions',COUNT(*) FROM annotation_versions
UNION ALL
SELECT 'admin_audit_log',    COUNT(*) FROM admin_audit_log
UNION ALL
SELECT 'invite_codes',       COUNT(*) FROM invite_codes;
" > "$DRILL_DIR/after.txt"

diff "$DRILL_DIR/baseline.txt" "$DRILL_DIR/after.txt" && echo "PASS — counts match" || echo "FAIL — counts differ"
```

The diff must be empty. If any table count differs, the restore did not reproduce
the snapshot faithfully. See Section 7.

Note: `user_sessions` is intentionally excluded from snapshots (`EXCLUDED_TABLES`
in `backend/backup/service.py`), so it will be empty after restore. This is
correct behaviour — re-login is required after every restore.

---

## Section 5 — Teardown

```bash
# Stop the throwaway server if it is still running.
kill $SERVER_PID 2>/dev/null || true

# Remove all drill artefacts.
rm -rf "$DRILL_DIR"
echo "Drill directory removed."
```

Confirm `$DRILL_DIR` no longer exists before signing off.

---

## Section 6 — Sign-off Table

| Date       | Operator | Snapshot used | Observations / anomalies | Pass/Fail |
|------------|----------|---------------|--------------------------|-----------|
|            |          |               |                          |           |
|            |          |               |                          |           |
|            |          |               |                          |           |

---

## Section 7 — Failure Modes and Fallback

### `409 db_busy` from the restore endpoint

The WAL has uncommitted frames. Either another connection is mid-write, or a
previous writer crashed without checkpointing. Stop all connections to the drill
DB and re-run:

```bash
sqlite3 "$DRILL_DIR/db/annotations.db" "PRAGMA wal_checkpoint(TRUNCATE);"
```

Then retry the restore.

### Restore partially applied before an error

`restore_from_snapshot` runs inside a single `BEGIN IMMEDIATE` transaction.
Any failure triggers a full `ROLLBACK`, so the DB is left in its pre-restore
state. The function re-raises after rollback, and the HTTP route returns `500`
with `error: restore_failed`.

Check `system_events` for the failure details:

```bash
sqlite3 "$DRILL_DIR/db/annotations.db" \
  "SELECT created_at, event_type, message, extra_json FROM system_events ORDER BY id DESC LIMIT 10;"
```

Look for rows where `event_type LIKE 'backup%'` or `severity = 'error'`.

### CLI restore fails mid-flight

`cmd_restore_from_github` renames the current DB to `corrupt-<ts>.db.bak`
before attempting the restore. If the restore errors, it renames the backup
file back to `annotations.db`. The pre-restore DB is preserved automatically.

### Column mismatch (`400 restore_invalid_columns`)

A snapshot row contains columns that do not exist in the current schema.
This indicates schema drift between the snapshot and the running migration level.
Run `python -m backend.cli migrate` against the drill DB first, then retry.

### Snapshot JSON is malformed (`400 invalid_json`)

The uploaded file is not valid JSON. Verify the snapshot was written correctly:

```bash
python3 -m json.tool "$SNAPSHOT" > /dev/null && echo "valid JSON" || echo "corrupt"
```
