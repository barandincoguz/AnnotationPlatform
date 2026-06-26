# Neon Postgres dual-write mirror — operator runbook

Phase 4 ships an asynchronous **one-way SQLite → Neon Postgres mirror**.
Every committed write on the project's local SQLite database is also
applied to the partner team's Neon database under the `baran_<table>`
prefix. Mirror writes never block the request thread; if Neon is
unreachable the originating SQLite write still succeeds, the row stays
in a local outbox, and the dispatcher retries on a back-off schedule.

This document is operator-facing. Implementation rationale lives in
`.planning/phases/04-neon-postgres-dual-write-mirror/4-CONTEXT.md` and
`4-PLAN.md`.

---

## 1. Setup

1. Ask the partner team for a read-write Neon role scoped to the database
   that should receive the mirror tables. The role needs `CREATE` (for
   the one-time DDL apply) and `INSERT/UPDATE/DELETE` on the `baran_*`
   tables.
2. Add the connection string to your local `.env.local` (gitignored)
   under `NEON_MIRROR_URL`. Optionally set `NEON_MIRROR_BATCH_SIZE`
   (default `100`), `NEON_MIRROR_MAX_RETRIES` (default `5`), and
   `NEON_MIRROR_EMPTY_SLEEP` (default `5` seconds — the dispatcher idle
   sleep when the queue is empty).
3. Production: set the same env vars via the deployment platform's
   secrets store. The `.env.example` template lists the keys with
   comments.

   ```bash
   # .env.local (development) — never commit
   NEON_MIRROR_URL=postgresql://baran_writer:<password>@ep-xxx.neon.tech/neondb?sslmode=require
   NEON_MIRROR_BATCH_SIZE=100
   NEON_MIRROR_MAX_RETRIES=5
   NEON_MIRROR_EMPTY_SLEEP=5
   ```

If `NEON_MIRROR_URL` is unset, the dispatcher boots in a degraded
"Neon unreachable" state — the local app and outbox triggers keep
working, but nothing is mirrored. This is intentional: missing
credentials must never block backend startup.

---

## 2. Automated Schema Sync (Auto-Migrations)

On application startup, the platform automatically compares the local SQLite schema with the remote Neon Postgres database and synchronizes any missing tables, columns, or indexes under the `baran_*` prefix. 

Therefore, you do not need to run manual SQL migrations on the Neon Postgres database; they are applied automatically when the container boots (if `NEON_MIRROR_URL` is set and `ENVIRONMENT` is not `test`).

### Manual DDL Apply (Fallback / One-time setup)

If you need to manually apply or verify the schema, you can generate the mirror schema from SQLite and apply it to Neon:

```bash
# Regenerate the file from all committed SQLite migrations. Idempotent.
python -m scripts.regen_neon_ddl

# Apply to Neon. Idempotent — re-running is safe.
psql "$NEON_MIRROR_URL" -f migrations/postgres/001-baran-init.sql
```

The committed `001-baran-init.sql` is automatically regenerated whenever the SQLite schema changes. You can also apply it through the Neon Console SQL editor if `psql` isn't installed locally.

### Legacy Migrations (Historical)

For existing deployments from earlier phases:
1. `migrations/postgres/002-remove-user-sessions.sql` removed legacy mirrored bearer tokens from deployments created before SQLite migration `v0009`.
2. `migrations/postgres/003-nullable-training-finished-at.sql` permitted active training attempts to mirror with `finished_at = NULL`.

These are now handled automatically by the auto-sync system.

---

## 3. One-time backfill

After the DDL apply, push the current SQLite state into the partner
Neon database. The script uses `INSERT ... ON CONFLICT DO UPDATE`
upserts everywhere, so re-running is safe:

```bash
# Dry-run first — counts only, no writes.
python -m scripts.neon_backfill --dry-run

# Full backfill.
python -m scripts.neon_backfill

# Recover a single table after a partial failure.
python -m scripts.neon_backfill --table documents_meta
```

The script walks tables in FK-topological order (`users` →
`documents_meta` → `annotations` → …) so foreign-key constraints on
the Neon side hold during the upsert. Progress is logged to stdout per
table.

---

## 4. SQLite migration sequence

The Phase 4 SQLite-side schema changes are two migration files applied
automatically on backend startup by the existing `apply_migrations`
runner:

| File | What it does |
|------|--------------|
| `backend/migrations/v0005_outbox_schema.py` | Creates the `_outbox` table + its two supporting indexes. |
| `backend/migrations/v0006_install_outbox_triggers.py` | Installs **66 triggers** across the 22 in-scope project tables (22 × 3 ops). Operational metadata and bearer sessions are excluded. |
| `backend/migrations/v0009_exclude_user_sessions_from_mirror.py` | Drops legacy session triggers and purges every local outbox row containing session payloads. |
| `backend/migrations/v0010_redact_activity_session_ids.py` | Rebuilds activity triggers so local session IDs are emitted as `null`, and scrubs queued activity payloads for rolling-upgrade compatibility. |
| `backend/migrations/v0011_nullable_training_finished_at.py` | Makes `training_attempts.finished_at` nullable so an active attempt is distinguishable from a completed attempt. |

These run on backend boot via the lifespan startup. Every migration is
idempotent.

---

## 5. Health surface

```
GET /api/admin/mirror/health
```

Admin-only (reuses `require_admin`). Returns:

```json
{
  "queue_depth": 0,
  "dead_letter_count": 0,
  "oldest_undelivered_age_seconds": null,
  "last_delivered_at": "2026-05-19T00:00:00+00:00",
  "dispatcher_alive": true,
  "neon_reachable": true
}
```

| Field | Meaning |
|-------|---------|
| `queue_depth` | Undelivered outbox rows with `retry_count < MAX_RETRIES` (i.e. still in active retry). |
| `dead_letter_count` | Undelivered rows that hit `MAX_RETRIES` and are awaiting operator attention. |
| `oldest_undelivered_age_seconds` | Seconds since the oldest still-in-queue row's `created_at`. `null` when the queue is empty. |
| `last_delivered_at` | ISO-8601 timestamp of the most recent successful apply (or `null` if nothing has ever delivered). |
| `dispatcher_alive` | True when the lifespan task is still running. *Ergonomic field*. |
| `neon_reachable` | True/False from the dispatcher's last apply outcome; `null` until the first attempt. *Ergonomic field*. |

Use the queue-depth metric in alerting — a depth that climbs and
doesn't drain points at a dispatcher issue or a Neon outage. The
dead-letter count climbing points at a permanent error (e.g., DDL
drift, FK violation) that operator action must clear.

---

## 6. Dead-letter recovery

When a row hits `MAX_RETRIES` (default 5), the dispatcher stops
retrying it and logs a `system_event` of severity `error`. To replay
after fixing the underlying issue (e.g., schema drift, network):

```sql
-- Inspect dead-lettered rows.
SELECT id, table_name, op, pk_value, error, retry_count, created_at
FROM _outbox
WHERE delivered_at IS NULL AND retry_count >= 5;

-- Reset specific rows so the dispatcher picks them up again.
UPDATE _outbox
SET retry_count = 0, error = NULL
WHERE id IN (123, 124, 125);
```

Then either let the dispatcher pick them up on its next pass, or
restart the backend to re-arm a known-good Neon connection.

---

## 7. Schema evolution

When the SQLite schema changes (new migration file added under
`backend/migrations/`), the mirror needs to be kept in sync manually:

1. Run `python -m scripts.regen_neon_ddl` to regenerate
   `migrations/postgres/001-baran-init.sql`.
2. Commit the regenerated file.
3. Apply the diff to Neon via `psql` or the Neon Console.

If a new table is added, also confirm that `v0006_install_outbox_triggers`
picks it up (the migration uses dynamic introspection, so new tables
are covered automatically on the next boot — but verify against the
69→70+ trigger count delta).

Schema-drift auto-migration on Neon is **out of scope** for Phase 4.

---

## 8. Backoff semantics caveat

Backoff retry timing is gated against the row's `created_at`, not the
last-attempt timestamp. After the row's first failure, the
re-attempt schedule looks like:

| Attempt | Retry-at (approx) |
|---------|-------------------|
| 1 | `created_at + 1s` |
| 2 | `created_at + 2s` |
| 3 | `created_at + 4s` |
| 4 | `created_at + 8s` |
| 5 | `created_at + 16s` (after which the row is dead-lettered) |

After ~31 s of total backoff the dispatcher will re-fire the row
on every drain pass until it lands in dead-letter. This is documented
as accepted v1 behavior — the dead-letter rule (`retry_count >= MAX_RETRIES`
drops the row from the drain query) provides the hard stop, and a
re-firing transient failure does no harm beyond a few extra Neon round
trips. A `last_attempted_at` column will be added only if production
telemetry shows a thrash problem; the `_outbox` schema (D-04) stays
frozen otherwise.

---

## Quick reference

| Action | Command |
|--------|---------|
| Apply Neon DDL | `psql "$NEON_MIRROR_URL" -f migrations/postgres/001-baran-init.sql` |
| Remove legacy session mirror | `psql "$NEON_MIRROR_URL" -f migrations/postgres/002-remove-user-sessions.sql` |
| Allow active training attempts | `psql "$NEON_MIRROR_URL" -f migrations/postgres/003-nullable-training-finished-at.sql` |
| Regenerate DDL | `python -m scripts.regen_neon_ddl` |
| Backfill (dry) | `python -m scripts.neon_backfill --dry-run` |
| Backfill (full) | `python -m scripts.neon_backfill` |
| Backfill (single table) | `python -m scripts.neon_backfill --table <name>` |
| Health check | `curl -u admin:... http://localhost:8000/api/admin/mirror/health` |
| Inspect outbox | `sqlite3 data/db/annotations.db 'SELECT count(*), op FROM _outbox GROUP BY op'` |
