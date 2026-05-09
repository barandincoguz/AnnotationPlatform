# Paket 12 — Backup + Restore Design

**Status:** Approved (brainstorming complete 2026-05-09)
**Predecessors:** Paket 1-11 complete (`paket-11-admin-panel` tag at `1522d4b`; tech-debt polish at `653cce3`)
**Successor:** Paket 13 (retention) consumes the same backup format for selective restore tests

## Goal

Add automated periodic backup of the entire SQLite database to a private GitHub repository, plus a manual CLI restore tool. Backup runs as an in-process asyncio task driven by FastAPI's lifespan; restore is a one-shot CLI command that wipes and rebuilds the local DB from a chosen snapshot. No new schema; observability via the existing `system_events` table.

## Scope

Comparable in size to Paket 9-10-11 (~9 tasks, ~35-40 new tests). Backend-only paket: no UI work.

## Non-Goals

- **Restoring individual rows or tables.** Restore is whole-DB replacement only. Selective restore is Paket 13's domain (retention deletes specific users/rows; not driven by backup snapshots).
- **Backing up the document corpus** (`<DATA_DIR>/documents/*.json`). Documents are read-only ingested files; the source-of-truth is the original ingestion process. The backup intentionally captures only the DB, which holds annotation work and admin state.
- **Cross-region replication** or any storage other than the configured GitHub repo.
- **Restore via HTTP endpoint.** Restore is CLI-only and requires shell access — this is intentional (it's a destructive operation; gating it behind a CLI prevents accidental admin-panel clicks).
- **Encryption of backup contents at rest.** The repo is private and the PAT is fine-grained; the JSON is plain text. Field-level encryption (e.g. password hashes are already bcrypt-stored, but session tokens / future secrets) is out of scope.
- **Frontend admin button for "backup now."** The endpoint exists for tooling but no UI is wired in this paket. Frontend Paket 16 may consume `POST /api/admin/backup/run-now` later.

## Decisions Locked During Brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Trigger mechanism | `asyncio.create_task` in FastAPI lifespan | Single process; cancellable on shutdown; no extra threads; pytest-friendly |
| What gets backed up | All tables → single JSON dump (per parent spec line 800) | Documents are ingestion-derived; DB holds the irreplaceable work |
| Snapshot rotation | Keep 144 most recent timestamped snapshots (24h × 10min) | Per parent spec line 804 |
| Failure handling | Log to `system_events` (success / fail), no in-process retry | Loop sleeps `interval_seconds` and tries again; observable via Paket 11 admin viewer |
| Missing env vars | Skip backup cycle silently with `event_type='backup_skipped_no_remote'` | Dev environments without `BACKUP_REPO_URL` shouldn't break startup |
| Manual trigger | `POST /api/admin/backup/run-now` (admin-only, synchronous) | Useful for testing + admin emergency push; not exposed to frontend yet |
| Restore mechanism | CLI only: `python -m backend.cli restore-from-github` | Destructive; requires shell access by design |
| Restore confirmation | Stdin prompt `[y/N]` unless `--yes` flag passed | Default safe; `--yes` for automation |
| Manual trigger blocking | Admin endpoint blocks until cycle completes | Admin-only, low call rate; simpler than async-status polling |

## Architecture Overview

```
backend/backup/                    # NEW package
├── __init__.py                    # empty
├── service.py                     # dump_all_tables_to_json, write_snapshot, rotate, run_backup_cycle
├── git_remote.py                  # PAT URL injection, init/commit/push wrappers (subprocess)
├── loop.py                        # async backup_loop() — runs forever; cancellable
├── models.py                      # Pydantic response schemas for the admin endpoint
├── routes.py                      # POST /api/admin/backup/run-now
└── restore.py                     # restore_from_snapshot logic (consumed by CLI)

backend/main.py                    # MODIFIED: lifespan starts backup task; mounts backup router
backend/cli.py                     # MODIFIED: + restore-from-github subcommand
```

All new code paths use `Depends(require_admin)` for the HTTP surface; the loop runs without auth (it's an in-process task).

## Endpoint Surface

```
POST /api/admin/backup/run-now
  Body: {} (none)
  Auth: require_admin
  200: {ok: true, snapshot_path: str, committed_sha: str | null, pushed: bool}
       - committed_sha is null if BACKUP_REPO_URL is unset (dump + rotation still ran)
       - pushed is false if BACKUP_REPO_URL is unset
  500: {detail: {error: "backup_failed", message: str}}
       - any step (dump | rotate | git) raised; system_events row already written
  Side effects:
    - Runs the same code path as the periodic loop (run_backup_cycle)
    - Writes admin_audit_log row: action_type='backup_run_now',
      target_kind='backup', target_id=<snapshot_filename>,
      metadata={pushed: bool, committed_sha: str | null}
    - Writes system_events row (success or failure)
```

The endpoint blocks until `run_backup_cycle` returns (or raises). Synchronous response; no polling needed.

## CLI Surface

```
$ python -m backend.cli restore-from-github [--snapshot <YYYYMMDD-HHMM>] [--yes]

Behavior:
  1. Read BACKUP_REPO_URL + GITHUB_PAT from env. Exit 1 if either missing.
  2. Move current DB aside: <DATA_DIR>/db/corrupt-<UTC ISO timestamp>.db.bak
     (literal hardcoded substring 'corrupt' so operators can find these
     files even if they don't remember the name)
  3. Clone the backup repo to /tmp/restore-<UTC ts>/. (If clone fails, restore
     the corrupt-*.db.bak file in place and exit 1.)
  4. Select snapshot: --snapshot <stamp> picks <stamp>.json; default picks
     latest.json. Exit 1 if file missing.
  5. Print summary: "Will restore N tables, M total rows. Continue? [y/N]"
     Skip prompt if --yes given.
  6. After step 2 the original DB file is gone (renamed aside). SQLite will
     create a new file at <DATA_DIR>/db/annotations.db on first connection.
     Run migrations on the new DB so the full schema is in place, then:
       BEGIN IMMEDIATE
       DELETE FROM <table> -- defensive (no-op on fresh DB; ensures idempotency
                              if step 2 was somehow skipped)
       INSERT ... VALUES ... -- bulk insert per table from snapshot
       COMMIT
     On any error: ROLLBACK, restore the corrupt-*.db.bak to its original
     path, exit 1.
  7. Print row-count diff: snapshot vs DB after restore (should match).
  8. Clean up /tmp/restore-<UTC ts>/.
  9. Exit 0.

Notes:
  - schema_migrations is NOT restored from snapshot — re-derived from migrations
    at the new DB. Dropping it from the snapshot avoids version-mismatch issues
    if Paket 12+ added a new migration since the backup was taken.
  - Server should be stopped before running restore (the corrupt-*.db.bak rename
    requires no open file handles). The CLI prints a warning if it detects a
    sqlite3 lock and refuses to proceed unless --force is also passed.
```

## Schema

**No new tables, no migration.** Paket 12 reuses:
- `system_events` (v0001) — backup outcome logging.
- `admin_audit_log` (v0001) — manual trigger audit.

Schema files added on disk (not in DB):
- `<DATA_DIR>/backup/.git/` — git working tree
- `<DATA_DIR>/backup/latest.json` — most recent dump
- `<DATA_DIR>/backup/<UTC YYYYMMDD-HHMM>.json` — timestamped snapshots
- `<DATA_DIR>/db/corrupt-<UTC ISO>.db.bak` — pre-restore safety backups (created by restore CLI)

`config.py:ensure_dirs()` already creates `<DATA_DIR>/backup/` (Paket 1). No change needed.

## Service Layer

| Module | Function | Notes |
|---|---|---|
| `backup/service.py` | `dump_all_tables_to_json(db) -> dict` | Reads `PRAGMA table_info` for each non-system table; SELECT * with column order; returns `{table: [row_dicts]}`. **Excludes `schema_migrations`** (re-derived on restore). Uses `BEGIN IMMEDIATE` for read consistency. |
| `backup/service.py` | `write_snapshot(payload, backup_dir, ts) -> Path` | Atomic write via temp + rename: `latest.json` + `<ts>.json`. |
| `backup/service.py` | `rotate_snapshots(backup_dir, keep=144) -> list[Path]` | Sort by mtime DESC; delete `<stamp>.json` files past index 143. Skip `latest.json` and `.git/`. Returns deleted paths. |
| `backup/service.py` | `run_backup_cycle(db) -> dict` | Top-level orchestrator. Reads env, calls dump → write → rotate → git (if env set) → log. Returns `{snapshot_path, committed_sha, pushed}`. Raises on dump/write/git failure (loop catches; route translates to 500). |
| `backup/git_remote.py` | `inject_pat(url, pat) -> str` | `https://github.com/owner/repo.git` → `https://x-access-token:<pat>@github.com/owner/repo.git`. Pure function, unit-testable. |
| `backup/git_remote.py` | `ensure_initialized(backup_dir, remote_url) -> None` | If `.git` missing: `git init`, `git config user.email/user.name`, `git remote add origin`. Idempotent. |
| `backup/git_remote.py` | `commit_and_push(backup_dir, message) -> str` | `git add . && git commit -m <message> --allow-empty` (allow-empty so empty cycles still produce a HEAD). Returns commit SHA. Then `git push origin main` (or `master` if main fails — fall back). |
| `backup/loop.py` | `async backup_loop()` | Wraps `service.run_backup_cycle` in `asyncio.to_thread`. Re-reads `backup.interval_seconds` from settings each iteration so live admin tuning works. Catches `asyncio.CancelledError` and re-raises (graceful shutdown). All other exceptions logged via `log.exception` and the loop continues. |
| `backup/restore.py` | `restore_from_snapshot(db, snapshot_path) -> dict` | Reads JSON, opens BEGIN IMMEDIATE, DELETE+INSERT per table, COMMIT. Returns `{tables: {<name>: row_count}, total_rows}`. Raises on any error (CLI catches and rolls back the corrupt-bak rename). |
| `cli.py` | `cmd_restore_from_github` | Drives env validation, clone, prompt, dispatch to restore.py, cleanup. |

## Patterns Reused

- **Per-step fault isolation** (Paket 9 finalize, Paket 10 lifecycle): each side-effect (dump, write, git push, log) wrapped so that one failure produces a clean event but doesn't corrupt later steps.
- **Atomic file write** (Paket 5 annotations chain): write to `<file>.tmp` then `os.replace` for crash-safe snapshot writes.
- **`BEGIN IMMEDIATE` transaction** (Paket 11 reset_user_training): consistent reads across multi-table dump.
- **Existence-hide via `require_admin`** (Paket 2): admin-only HTTP endpoint returns 404 to non-admins.
- **`asyncio.to_thread` for blocking work in async loop** (none in prior paketler — first use, but standard FastAPI pattern).
- **Subprocess for git** (none in prior paketler — first use). Run with `subprocess.run(check=True, capture_output=True, timeout=30)` so hung pushes don't deadlock the loop.

## Auth Gating

- `POST /api/admin/backup/run-now`: `Depends(require_admin)` → 404 existence-hide for non-admins.
- Backup loop: runs without auth (in-process, no request context).
- Restore CLI: no HTTP at all; security is "shell access required."

## Error Handling

- **Missing `BACKUP_REPO_URL` or `GITHUB_PAT`:** Loop and endpoint both proceed through dump+rotation; skip git step; log `event_type='backup_skipped_no_remote', severity='info'`. Endpoint returns 200 with `pushed: false, committed_sha: null`.
- **Git push auth failure (bad PAT):** Log `event_type='backup_failed', severity='error', extra_json={step: 'push', error: <captured stderr>}`. Endpoint returns 500. Loop continues.
- **Git push network failure:** Same as above. Note: subprocess timeout = 30s.
- **Disk full / FS write failure:** Log `event_type='backup_failed', severity='error', extra_json={step: 'write', error: ...}`. Endpoint returns 500.
- **SQLite lock during dump:** `BEGIN IMMEDIATE` blocks for ~5s default; if it can't acquire, raises and is logged as `event_type='backup_failed', severity='error', extra_json={step: 'dump', error: 'database is locked'}`. Loop will try again next cycle.
- **Concurrent admin manual trigger + scheduled cycle:** Both grab `BEGIN IMMEDIATE`; one will block on the other. Both succeed sequentially. Acceptable.
- **Restore CLI failure (any step):** Roll back any uncommitted DB transaction, restore the `corrupt-*.db.bak` to `<DATA_DIR>/db/annotations.db`, clean up `/tmp/restore-*`, exit 1 with stderr message.

## Testing Plan

Each task ships with failing tests first (TDD), then implementation, then green.

| Task | Test count (estimate) | Coverage |
|---|---|---|
| 1 | 6-8 | dump_all_tables_to_json: empty DB, non-empty, schema_migrations excluded, JSON-serializable types (datetime, bool, None), BEGIN IMMEDIATE behavior |
| 2 | 4-5 | git_remote: inject_pat URL forms, ensure_initialized idempotent, commit_and_push writes commit (mock subprocess), main→master fallback |
| 3 | 5-6 | run_backup_cycle: full happy path with no remote (skip), full path with stub remote, system_events written on success and failure, fault isolation across steps |
| 4 | 3-4 | backup_loop: cancellation produces graceful shutdown, settings tuning takes effect, exception in cycle does not stop loop |
| 5 | 2 | lifespan smoke: server startup creates the task; shutdown cancels cleanly |
| 6 | 4-5 | POST /api/admin/backup/run-now: success, no-remote, audit row, require_admin (404), 500 on git failure |
| 7 | 5-6 | restore.restore_from_snapshot: full happy path, malformed snapshot, schema_migrations not restored, rowcount validation |
| 8 | 4-5 | restore CLI: env validation, prompt confirmation (--yes flag), corrupt-bak rename + restore on error, --snapshot flag |
| 9 | 0 | Polish; full suite green; tag |

Total ≈ 33-41 new tests. Final suite ≈ 548-556.

**Test harness convention:** Tests set `BACKUP_REPO_URL=""` (or unset env) to disable git push entirely. The dump + rotation paths are exercised against a real tmp_path. Git wrappers are tested in isolation by mocking `subprocess.run`.

## Verification

After all 9 tasks land:
1. `.venv/bin/python -m pytest -q` — all green
2. Fresh DB: `DATA_DIR=/tmp/p12-fresh python -m backend.cli migrate` applies v0001 + v0002 cleanly (no v0003 — Paket 12 has no migration)
3. With `BACKUP_REPO_URL` and `GITHUB_PAT` set against a real test repo:
   - Start server → wait one interval → verify a commit landed on the test repo
   - Hit `POST /api/admin/backup/run-now` → response includes `committed_sha`, audit row in `admin_audit_log`, system_events row written
4. Restore drill: stop server → `python -m backend.cli restore-from-github --yes` → row counts match snapshot, server restarts cleanly
5. Tag `paket-12-backup`

## Risks & Open Questions

- **None blocking.** All architectural decisions resolved during brainstorming.
- **Latent risk:** Subprocess git operations on HF Spaces / Docker image — the image must include `git` binary. Add to `Dockerfile` in Paket 15. Track this as a Paket 15 dependency note (this spec doesn't add the Dockerfile, but Paket 15's plan must reference it).
- **Latent risk:** First-run on a fresh `<DATA_DIR>/backup/` produces an empty `git log` → `git push origin main` would fail. Solution: `git commit --allow-empty -m "init"` after `git init` so the branch exists before first real backup. Encoded into `ensure_initialized`.
- **Latent risk:** PAT leakage in subprocess error output. Solution: `git_remote` wrappers strip the PAT from any captured stderr/stdout before logging or returning.
- **Latent risk:** Restore CLI overwriting an active server's DB. Mitigation: detect WAL lock via `PRAGMA quick_check` before starting; require `--force` to override. Documented in CLI help text.
- **Snapshot file size:** 18K documents + N annotations × ~20K rows of audit/event = single JSON could grow to several MB after 6 months. Acceptable for a private repo; revisit in Paket 13 if retention is implemented (older audit rows pruned).

## Out-of-Scope Notes for Future Pakets

- **Paket 13 (retention):** Will use this snapshot format for "restore-then-delete-old-rows" testing flow. Verify backup snapshot can round-trip a DB with retained-only data.
- **Paket 14 (export):** CSV/JSON export of annotations is a different concern (user-facing data extraction, not disaster recovery). Won't reuse this code path.
- **Paket 15 (Docker):** Dockerfile must include `git` binary in the runtime stage, not just the build stage.
- **Paket 16 (frontend):** May surface a "backup now" button in the admin panel that calls `POST /api/admin/backup/run-now`. Endpoint contract is stable.
