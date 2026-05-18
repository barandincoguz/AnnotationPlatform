---
phase: 04-neon-postgres-dual-write-mirror
plan: 4
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/migrations/v0005_outbox_schema.py
  - backend/migrations/v0006_install_outbox_triggers.py
  - backend/migrations/helpers/__init__.py
  - backend/migrations/helpers/schema_introspect.py
  - backend/migrations/helpers/postgres_ddl.py
  - backend/migrations/helpers/trigger_generator.py
  - backend/mirror/__init__.py
  - backend/mirror/config.py
  - backend/mirror/dispatcher.py
  - backend/mirror/neon_client.py
  - backend/mirror/health.py
  - backend/admin/routes.py
  - backend/main.py
  - migrations/postgres/001-baran-init.sql
  - scripts/neon_backfill.py
  - scripts/regen_neon_ddl.py
  - tests/test_mirror_outbox_schema.py
  - tests/test_mirror_trigger_generator.py
  - tests/test_mirror_postgres_ddl.py
  - tests/test_mirror_outbox_capture.py
  - tests/test_mirror_dispatcher_loop.py
  - tests/test_mirror_dispatcher_retry.py
  - tests/test_mirror_lifespan_integration.py
  - tests/test_mirror_backfill_idempotency.py
  - tests/test_mirror_admin_health.py
  - docs/neon-mirror.md
  - README.md
  - .env.example
autonomous: true
requirements:
  - MIRROR-01
  - MIRROR-02
  - MIRROR-03
  - MIRROR-04
  - MIRROR-05
  - MIRROR-06
  - MIRROR-07
  - MIRROR-08
  - MIRROR-09
  - MIRROR-10
user_setup:
  - service: neon-postgres
    why: "Phase 4 mirror writes go to a partner team's Neon Postgres database under baran_* tables. A read-write role is required (the existing NEON_RO_URL is read-only and must remain so)."
    env_vars:
      - name: NEON_MIRROR_URL
        source: "Neon Dashboard -> Project -> Roles -> create or reuse a read-write role; copy its connection string with sslmode=require"
      - name: NEON_MIRROR_BATCH_SIZE
        source: "Optional. Defaults to 100. Set in .env.local only if tuning."
    dashboard_config:
      - task: "Verify the role used for NEON_MIRROR_URL has CREATE + INSERT + UPDATE + DELETE on the target schema (default: public). baran_* tables will be created at first migration apply against Neon."
        location: "Neon Dashboard -> Roles & Databases"
      - task: "Run migrations/postgres/001-baran-init.sql once against Neon as part of Phase 4 cutover (Task 13 in this plan). This DDL is idempotent so it is safe to re-run."
        location: "Neon SQL Editor or `psql $NEON_MIRROR_URL -f migrations/postgres/001-baran-init.sql`"

must_haves:
  truths:
    - "Every committed INSERT/UPDATE/DELETE on any of the 23 in-scope project tables produces exactly one _outbox row in the same SQLite transaction."
    - "The dispatcher coroutine drains _outbox rows and writes them to Neon's baran_<table> mirror in commit order."
    - "A Neon outage (psycopg OperationalError / InterfaceError) never rolls back or fails the originating SQLite write — the originating HTTP request still returns 200/204."
    - "After max retries (default 5) the dispatcher dead-letters the row with a permanent error stamp; it never blocks the queue."
    - "The 17923 existing documents (plus denorms) reach Neon via the one-shot backfill script before any trigger-driven write fires for them."
    - "GET /api/admin/mirror/health returns outbox queue depth, oldest-undelivered-age, dead-letter count, last-delivered-at."
    - "Existing 872 backend + 511 frontend + 9 e2e tests stay green; new mirror tests pass."
    - "Request p95 latency on existing endpoints does not regress by more than 5 ms (background queue does not block the request path)."
  artifacts:
    - path: "backend/migrations/v0005_outbox_schema.py"
      provides: "Creates _outbox table + indexes idempotently."
      contains: "CREATE TABLE IF NOT EXISTS _outbox"
    - path: "backend/migrations/v0006_install_outbox_triggers.py"
      provides: "Installs 69 generated triggers (23 in-scope tables x INSERT/UPDATE/DELETE) at migration-apply time."
    - path: "backend/migrations/helpers/trigger_generator.py"
      provides: "Pure-Python generator producing the trigger SQL list plus the per-table PK-columns manifest from PRAGMA table_info introspection."
      exports: ["build_triggers_for_table", "build_all_triggers", "pk_columns_manifest"]
    - path: "backend/migrations/helpers/postgres_ddl.py"
      provides: "Maps SQLite schema -> baran_* Postgres DDL with the D-11 type rules."
      exports: ["build_pg_ddl_for_table", "build_all_pg_ddl"]
    - path: "backend/mirror/dispatcher.py"
      provides: "Async drain loop: select pending -> push to Neon -> mark delivered, with backoff and dead-letter."
      exports: ["run_dispatcher", "start", "stop"]
    - path: "backend/mirror/neon_client.py"
      provides: "Thin psycopg wrapper: connect(), apply(op, table, pk, payload). Hides connection retry semantics."
    - path: "backend/mirror/health.py"
      provides: "Pure functions returning outbox stats; consumed by the admin route and tests."
    - path: "migrations/postgres/001-baran-init.sql"
      provides: "Generated idempotent Postgres DDL for all 23 in-scope baran_* tables, indexes, FKs."
    - path: "scripts/neon_backfill.py"
      provides: "One-shot idempotent push of current SQLite state to Neon; FK-topological order."
    - path: "scripts/regen_neon_ddl.py"
      provides: "Operator script that re-runs postgres_ddl.py against the live SQLite schema and writes 001-baran-init.sql."
    - path: "docs/neon-mirror.md"
      provides: "Runbook: env setup, backfill procedure, health endpoint, dead-letter recovery."
  key_links:
    - from: "SQLite triggers (v0006)"
      to: "_outbox table (v0005)"
      via: "AFTER INSERT/UPDATE/DELETE triggers writing json_object(...) payload"
      pattern: "INSERT INTO _outbox"
    - from: "backend/mirror/dispatcher.py"
      to: "_outbox table"
      via: "SELECT ... WHERE delivered_at IS NULL AND retry_count < MAX_RETRIES ORDER BY id LIMIT N"
      pattern: "delivered_at IS NULL"
    - from: "backend/mirror/dispatcher.py"
      to: "Neon baran_* tables"
      via: "psycopg connection from neon_client.py; INSERT/UPDATE/DELETE per outbox row"
      pattern: "baran_"
    - from: "backend/main.py lifespan"
      to: "backend/mirror/dispatcher.py"
      via: "asyncio.create_task(run_dispatcher()) after migrations applied; cancel + drain on shutdown"
      pattern: "create_task.*run_dispatcher|mirror_dispatcher"
    - from: "backend/admin/routes.py"
      to: "backend/mirror/health.py"
      via: "GET /api/admin/mirror/health calls collect_health(conn)"
      pattern: "/admin/mirror/health"
---

<objective>
Implement an asynchronous one-way SQLite -> Neon Postgres mirror via the
outbox pattern, satisfying MIRROR-01 through MIRROR-10.

Purpose: Give the partner team a live mirror of the annotation database
under `baran_*` tables in their Neon Postgres, without changing the
service layer, without adding latency to the request path, and without
ever letting a Neon outage roll back a local SQLite write.

Output:
- New `_outbox` table + 69 triggers (23 in-scope tables x 3 ops) in SQLite.
- Generated idempotent Postgres DDL for all 23 in-scope mirror tables.
- Async dispatcher coroutine with retry + dead-letter.
- One-shot backfill script (idempotent via ON CONFLICT DO UPDATE).
- Admin health endpoint.
- New tests covering outbox lifecycle, retry semantics, schema
  conversion, lifespan integration, backfill idempotency, and admin
  health, with the existing 872 backend / 511 frontend / 9 e2e baseline
  preserved.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/04-neon-postgres-dual-write-mirror/4-CONTEXT.md

@CLAUDE.md
@backend/main.py
@backend/migrations/runner.py
@backend/migrations/__init__.py
@backend/migrations/v0004_trace_id.py
@backend/shared/audit.py
@scripts/neon_import.py

<interfaces>
Key existing contracts the executor must hold invariant.

From `backend/migrations/runner.py`:
- `Migration` dataclass: `version: str` (e.g. "v0005"), `name: str`, `up: Callable[[sqlite3.Connection], None]`.
- `apply_migrations(conn, migrations)` wraps each `up` in `BEGIN IMMEDIATE` and records the version in `schema_migrations`. Phase 4 migration files MUST conform.
- `_split_sql(sql)` strips `--` comments before splitting on `;`. Trigger SQL emitted by the generator MUST NOT rely on `--` for in-statement comments.
- CRITICAL: `sqlite3.Connection.executescript()` issues an implicit COMMIT before running its script, which would prematurely commit the runner's `BEGIN IMMEDIATE` transaction and leave the runner's subsequent `INSERT INTO schema_migrations` / `COMMIT` operating on no open transaction. Phase 4 migrations that need to emit multiple statements MUST iterate `conn.execute(stmt)` per statement (the v0004_trace_id.py pattern), NOT `conn.executescript(...)`.

From `backend/migrations/__init__.py`:
- `discover_migrations()` auto-imports any `v*.py` in this package. New migrations only need to live in this folder and expose `up(conn)`.

From `backend/main.py` lifespan:
- After `apply_migrations`, the lifespan starts background tasks via `*.start()` and stops them by `*.stop()` + awaiting the task. The dispatcher MUST follow the same start/stop shape (see `backend/locks/sweep.py`, `backend/backup/loop.py` for the canonical pattern).
- Lifespan uses `connect(config.DB_PATH)` for short-lived connections; the dispatcher gets its own long-lived connection.

From `backend/shared/audit.py`:
- `log_system_event(conn, event, severity, message=..., extra=...)`. Dispatcher cold-start and dead-letter use this exact signature.

From `backend/shared/db.py`:
- `connect(db_path)` — canonical SQLite connection helper. Applies the project's standard PRAGMAs (busy_timeout, WAL, foreign_keys, etc.). The dispatcher's long-lived SQLite connection MUST use this helper, not `sqlite3.connect()` directly, so it inherits the same PRAGMA setup as the request-path connections.

From `psycopg` (already installed; see `scripts/neon_import.py`):
- `psycopg.connect(NEON_MIRROR_URL, autocommit=True)` is the working pattern. Errors of interest: `psycopg.OperationalError`, `psycopg.InterfaceError`, `psycopg.errors.UniqueViolation` (latter treated as already-delivered).

SQLite tables in the database (24 total, confirmed via `.tables`):
`activity_events`, `admin_audit_log`, `annotation_references`,
`annotation_versions`, `annotations`, `badges_earned`,
`behavioral_events`, `document_bkk_refs`, `document_kanun_refs`,
`document_locks`, `documents_meta`, `drafts`, `gamification_ledger`,
`gamification_state`, `invite_codes`, `notifications`,
`schema_migrations`, `site_settings`, `system_events`,
`training_attempts`, `training_gold_doc_overrides`,
`training_quiz_overrides`, `user_sessions`, `users`.

Excluded from mirroring (D-06 + operator-discretion):
- `_outbox` itself (D-06 — no recursion).
- `schema_migrations` (operational metadata local to SQLite).

**In-scope project tables: 23** (24 listed above minus `schema_migrations`).
Trigger coverage: **23 × 3 = 69 triggers**. Baran table coverage: **23 baran_* tables**.
Final exclusion list is finalized in Task 3.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create `_outbox` SQLite schema migration (MIRROR-01)</name>
  <files>
    backend/migrations/v0005_outbox_schema.py
    tests/test_mirror_outbox_schema.py
  </files>
  <behavior>
    - After `apply_migrations` runs against a fresh DB, `_outbox` exists with the exact columns from D-04: `id INTEGER PRIMARY KEY AUTOINCREMENT`, `table_name TEXT NOT NULL`, `op TEXT NOT NULL`, `pk_value TEXT NOT NULL`, `payload_json TEXT NOT NULL`, `created_at TEXT NOT NULL`, `delivered_at TEXT NULL`, `error TEXT NULL`, `retry_count INTEGER NOT NULL DEFAULT 0`.
    - Index on `(delivered_at)` exists (drain query) and on `(created_at)` exists (archival).
    - Re-running the migration is a no-op (no `IF EXISTS` errors). Achieved via `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`.
    - `_outbox` is NOT mirrored: no trigger references this table after Task 5. Test asserts no future trigger has `_outbox` in its `INSERT INTO` clause's argument shape.
    - A CHECK constraint pins `op IN ('INSERT','UPDATE','DELETE')`.
  </behavior>
  <action>
    Create `backend/migrations/v0005_outbox_schema.py` following the `v0004_trace_id.py` shape: a module-level `SQL` string and an `up(conn)` function that splits on `;` and executes each statement via `conn.execute(stmt)` (NOT `executescript`, which would COMMIT the runner's `BEGIN IMMEDIATE`). Implement the columns and indexes from D-04 and D-05. No business logic; pure DDL. Write `tests/test_mirror_outbox_schema.py` covering: (a) table exists post-migration, (b) all 9 columns present with correct types via `PRAGMA table_info('_outbox')`, (c) both indexes exist via `PRAGMA index_list('_outbox')`, (d) re-applying `up()` against the same conn does not raise (idempotency), (e) inserting a row with `op = 'FOO'` raises an IntegrityError (CHECK constraint). Per CLAUDE.md surgical-changes rule: do not modify the runner, `__init__.py`, or any unrelated migration.
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/test_mirror_outbox_schema.py -x -v</automated>
  </verify>
  <done>5 new test cases pass; full backend suite still green (872 + 5 = 877 pass). Migration file is &lt; 50 lines of code.</done>
  <risk>Migration runner wraps `up()` in `BEGIN IMMEDIATE` — DDL inside an implicit transaction is fine in SQLite but the executor must NOT emit `BEGIN` or `COMMIT` in the SQL string (runner already handles transactions). Equally critical: do NOT call `conn.executescript()` — it issues an implicit COMMIT that breaks the runner's transaction boundary.</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 2: SQLite schema introspection helper</name>
  <files>
    backend/migrations/helpers/__init__.py
    backend/migrations/helpers/schema_introspect.py
    tests/test_mirror_postgres_ddl.py
  </files>
  <behavior>
    - `introspect_table(conn, table_name)` returns a structured `TableSchema(name, columns, primary_key, foreign_keys, indexes, checks)` dataclass.
    - `columns` is a list of `(name, sqlite_type, notnull, default, is_pk)` from `PRAGMA table_info`.
    - `foreign_keys` is a list of `(column, ref_table, ref_column, on_delete, on_update)` from `PRAGMA foreign_key_list`.
    - `indexes` is a list of `(name, columns, unique, partial_where)` from `PRAGMA index_list` + `PRAGMA index_info`. Auto-indexes (those starting `sqlite_autoindex_`) are excluded.
    - `checks` is parsed from the original `CREATE TABLE` text retrieved via `sqlite_master`. Regex-light: capture `CHECK (...)` clauses by paren-matching, not by naive split.
    - `list_project_tables(conn)` returns the 23 in-scope tables (excludes `_outbox`, `sqlite_sequence`, `schema_migrations`).
  </behavior>
  <action>
    Create `backend/migrations/helpers/__init__.py` (empty marker) and `backend/migrations/helpers/schema_introspect.py` implementing the dataclasses and PRAGMA-driven introspection. Pure functions, no I/O beyond the supplied connection. Test scope lives in this task's stub of `tests/test_mirror_postgres_ddl.py` (Task 3 fills out the postgres-DDL side; this task only adds the introspection cases). Cases: (a) introspecting `users` yields the right column list including `created_at TIMESTAMP`, (b) introspecting `drafts` returns the composite PK `(document_id, user_id)`, (c) introspecting `annotations` returns FKs to `users` and `documents_meta`, (d) `list_project_tables` excludes `_outbox` after Task 1 ran and excludes `schema_migrations` (asserts result length is 23).
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/test_mirror_postgres_ddl.py::test_introspect -x -v</automated>
  </verify>
  <done>Introspection tests pass against the real `data/db/annotations.db` schema; 4+ new cases. `list_project_tables(conn)` returns exactly 23 entries.</done>
  <risk>The CHECK-clause parser must handle nested parens correctly (e.g. `CHECK (severity IN ('info','warn','error'))`). Use a depth counter, not a regex.</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Postgres DDL generator with D-11 type mapping (MIRROR-03)</name>
  <files>
    backend/migrations/helpers/postgres_ddl.py
    tests/test_mirror_postgres_ddl.py
  </files>
  <behavior>
    - `build_pg_ddl_for_table(table_schema)` returns a list of SQL statements producing the `baran_<table>` Postgres equivalent.
    - Type mapping follows D-11 verbatim, with explicit handling for non-INTEGER primary keys:
      - `INTEGER PRIMARY KEY AUTOINCREMENT` -> `bigserial PRIMARY KEY` (rewrite to auto-incrementing surrogate).
      - **Non-`INTEGER PRIMARY KEY AUTOINCREMENT` primary keys preserve their column type and `PRIMARY KEY` clause.** Examples in the live schema: `annotations.document_id TEXT PRIMARY KEY` -> `text PRIMARY KEY`; `documents_meta.document_id TEXT PRIMARY KEY` -> `text PRIMARY KEY`; `document_locks.document_id TEXT PRIMARY KEY` -> `text PRIMARY KEY`; `site_settings.key TEXT PRIMARY KEY` -> `text PRIMARY KEY`; composite TEXT+INT PKs (`drafts (document_id TEXT, user_id INTEGER)`) emit `PRIMARY KEY (document_id, user_id)` with each column carrying its mapped type. **Only `INTEGER PRIMARY KEY AUTOINCREMENT` rewrites to `bigserial PRIMARY KEY`.**
      - `INTEGER` (non-PK) -> `bigint`
      - `TEXT` -> `text`
      - `REAL` -> `double precision`
      - `TIMESTAMP` (TEXT) -> `text` (NO tz parsing — preserves ISO-8601 strings)
      - Column names matching `*_json` or whose source CHECK asserts JSON validity -> `jsonb` (this includes `references_json`, `payload_json`, `extra_json`, etc.)
      - CHECK constraints copied verbatim onto the mirror column
      - `REFERENCES <table>` -> `REFERENCES baran_<table>` (FKs preserved across mirror)
    - Output is idempotent: every statement uses `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, etc.
    - Composite PKs emit `PRIMARY KEY (col_a, col_b)` (e.g. `baran_drafts`).
    - `build_all_pg_ddl(conn)` returns the full DDL script for all 23 in-scope tables, ordered by FK topological sort (parents first), with a leading SQL comment block listing generation timestamp + git SHA placeholder.
    - The `_outbox` and `schema_migrations` tables are NEVER in the output (D-06 + operator-discretion exclusion).
    - Generated SQL is valid Postgres syntax — verified by parsing (not executing) via `psycopg.sql` or simple statement-shape assertions in test.
  </behavior>
  <action>
    Implement `backend/migrations/helpers/postgres_ddl.py` consuming `TableSchema` from Task 2. Provide `build_pg_ddl_for_table(schema) -> list[str]` and `build_all_pg_ddl(conn) -> str`. Implement FK topological sort (Kahn's algorithm) to guarantee parent tables come first. Test cases in `tests/test_mirror_postgres_ddl.py` (extending the file from Task 2): (a) `users` -> `baran_users` with `bigserial PRIMARY KEY` for `id`, AND `annotations.document_id` (TEXT PRIMARY KEY) maps to `baran_annotations.document_id` declared as `text PRIMARY KEY` in the generated DDL (assert the literal substring `document_id text PRIMARY KEY` or equivalent shape appears), (b) `drafts` -> composite PK preserved with mixed types `(document_id text, user_id bigint)` and a trailing `PRIMARY KEY (document_id, user_id)` clause, (c) `annotations.last_editor_user_id REFERENCES users(id) ON DELETE SET NULL` becomes `baran_annotations.last_editor_user_id REFERENCES baran_users(id) ON DELETE SET NULL`, (d) `drafts.references_json` -> `jsonb`, (e) CHECK on `system_events.severity` copied verbatim, (f) topological order test: `baran_users` statement appears before `baran_annotations` in `build_all_pg_ddl(conn)`, (g) `_outbox` and `schema_migrations` absent from full DDL, (h) every CREATE TABLE statement contains `IF NOT EXISTS` (idempotency), (i) **`*_json` heuristic verification**: enumerate every column whose name ends in `_json` across all 23 in-scope tables and assert each maps to `jsonb` in the generated DDL (5-line iteration over `list_project_tables(conn)` + `introspect_table(...)` — prevents silent type drift if a new `_json` column is added in a future phase). Surgical: helpers live under `backend/migrations/helpers/`; nothing else moves.
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/test_mirror_postgres_ddl.py -x -v</automated>
  </verify>
  <done>9+ DDL test cases pass; `build_all_pg_ddl(conn)` produces a single SQL string that contains 23 `CREATE TABLE IF NOT EXISTS baran_*` statements. Every `*_json` column in the 23 in-scope tables maps to `jsonb`.</done>
  <risk>SQLite's `INTEGER PRIMARY KEY AUTOINCREMENT` detection requires reading the original CREATE TABLE text from `sqlite_master`, not just `PRAGMA table_info` (which doesn't surface AUTOINCREMENT). The introspect helper from Task 2 already exposes this. Equally important: TEXT primary keys (`annotations.document_id`, `documents_meta.document_id`, etc.) must NOT be rewritten to `bigserial` — only `INTEGER PRIMARY KEY AUTOINCREMENT` triggers the rewrite.</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Trigger generator + PK-columns manifest (MIRROR-01, MIRROR-02)</name>
  <files>
    backend/migrations/helpers/trigger_generator.py
    tests/test_mirror_trigger_generator.py
  </files>
  <behavior>
    - `build_triggers_for_table(table_schema)` returns 3 SQL `CREATE TRIGGER` statements (one each for INSERT, UPDATE, DELETE).
    - Each trigger body is `INSERT INTO _outbox(table_name, op, pk_value, payload_json, created_at) VALUES (...)`.
    - `payload_json` is built via `json_object('col_a', NEW.col_a, ...)` for INSERT/UPDATE, and `json_object('col_a', OLD.col_a, ...)` for DELETE. Use the SQLite `json_object()` function (already enabled; see `references_json` usage elsewhere).
    - `pk_value` is computed per D-03:
      - Single-column PK -> serialised as `CAST(NEW.<pk_col> AS TEXT)` (INSERT/UPDATE) or `CAST(OLD.<pk_col> AS TEXT)` (DELETE).
      - Composite PK -> `<col_a> || '::' || <col_b>` (e.g. `drafts.document_id || '::' || drafts.user_id`).
    - `created_at` -> `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` (ISO-8601 UTC, matches existing TIMESTAMP column convention).
    - Trigger names are deterministic: `_outbox_<table>_<op>` (e.g. `_outbox_annotations_ins`).
    - Each trigger SQL is `CREATE TRIGGER IF NOT EXISTS` so re-applying is safe.
    - `build_all_triggers(conn)` returns a list of trigger statements (or a single string split on `;`) covering all 23 in-scope tables × 3 ops = **exactly 69 statements**.
    - `_outbox` and `schema_migrations` are excluded from trigger generation.
    - **`pk_columns_manifest: dict[str, list[str]]` is a first-class module-level export** covering all 23 in-scope tables. Keys are bare table names (e.g. `"users"`, `"drafts"`, `"annotations"`); values are the ordered list of primary-key column names for that table (e.g. `["id"]` for `users`, `["document_id", "user_id"]` for `drafts`, `["document_id"]` for `annotations`, `["key"]` for `site_settings`). This manifest is the canonical source of truth consumed by T7 (NeonClient upsert SQL), T8 (dispatcher), and T11 (backfill) for both single-column and composite PKs — every consumer needs the PK column NAMES (not just the count) to emit `ON CONFLICT (<pk_cols>) DO UPDATE ...` correctly. Manifest is computed lazily on first access or eagerly at import time, but must be deterministic given a stable schema.
    - No `--` comments inside trigger bodies (the runner's `_split_sql` strips them and would break inline trigger SQL); use `/* */` blocks or omit comments inside trigger bodies entirely.
  </behavior>
  <action>
    Implement `backend/migrations/helpers/trigger_generator.py` consuming `TableSchema` from Task 2. Expose `build_triggers_for_table`, `build_all_triggers`, AND `pk_columns_manifest` (the dict mapping each of the 23 in-scope tables to its PK column list — derived from `TableSchema.primary_key`). Tests cover: (a) `users` table produces 3 triggers with the right names (NOTE: `users` has a single-column PK `id` of type INTEGER — INSERT trigger body contains `NEW.id` and `json_object('id', NEW.id, 'username', NEW.username, ...)` enumerating every column of the `users` table), (b) the `annotations` INSERT trigger uses `NEW.document_id` (TEXT PRIMARY KEY) and emits `CAST(NEW.document_id AS TEXT)` for `pk_value`, (c) DELETE trigger uses `OLD.*`, (d) `drafts` (composite PK) produces `OLD.document_id || '::' || OLD.user_id` on DELETE, (e) **`build_all_triggers(conn)` produces exactly 69 statements when split on `;` (23 in-scope tables × 3 ops)**, (f) running each generated trigger statement via `conn.execute(stmt)` (NOT `executescript` — see runner notes) inside an explicit `BEGIN IMMEDIATE` ... `COMMIT` against a fresh DB after v0005 succeeds and the resulting `sqlite_master` count for `name LIKE '_outbox_%'` returns 69, (g) trigger SQL contains no `--` line comments, (h) **`pk_columns_manifest` is exported and contains exactly 23 keys, one per in-scope table**, with `manifest["users"] == ["id"]`, `manifest["drafts"] == ["document_id", "user_id"]`, `manifest["annotations"] == ["document_id"]`, `manifest["site_settings"] == ["key"]`.
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/test_mirror_trigger_generator.py -x -v</automated>
  </verify>
  <done>8+ trigger-generator test cases pass; `build_all_triggers(conn)` produces exactly **69 statements** when split on `;`; running them against a freshly migrated DB installs 69 triggers verifiable by `SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE '_outbox_%'` returning **69**; `build_all_triggers(conn)` produces exactly 69 statements; `pk_columns_manifest` dictionary lists exactly 23 keys (one per in-scope table).</done>
  <risk>SQLite trigger semantics fire AFTER each statement, but rows committed inside `BEGIN IMMEDIATE` only become visible to other connections at COMMIT — so the outbox row and the originating write are atomically committed together. Test (f) must wrap the trigger fire in an explicit `BEGIN IMMEDIATE` ... `COMMIT` to mirror production behavior. Also: emit one statement per `conn.execute(stmt)` call — do NOT use `executescript`.</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Trigger install migration (MIRROR-01)</name>
  <files>
    backend/migrations/v0006_install_outbox_triggers.py
    tests/test_mirror_outbox_capture.py
  </files>
  <behavior>
    - `v0006_install_outbox_triggers.up(conn)` calls `build_all_triggers(conn)` from Task 4 and executes each generated trigger statement via `conn.execute(stmt)` after splitting on `;` (same pattern as `backend/migrations/v0004_trace_id.py`). It MUST NOT use `conn.executescript(...)` — `executescript` issues an implicit COMMIT that would prematurely terminate the runner's `BEGIN IMMEDIATE` transaction, and the runner's subsequent `INSERT INTO schema_migrations` + `COMMIT` would then fail because no transaction is open.
    - This migration runs AFTER v0005 (alphabetical ordering already enforces this) and AFTER all 23 in-scope project tables exist (they do; they were created in v0001).
    - End-to-end capture test: insert a row into `users` -> exactly one `_outbox` row exists with `table_name='users'`, `op='INSERT'`, `pk_value=<str(id)>`, `payload_json` parses to a dict containing every column of the inserted row, `delivered_at IS NULL`, `retry_count=0`.
    - Update + delete capture verified similarly.
    - Composite-PK capture (`drafts`) yields `pk_value` = `'<doc_id>::<user_id>'`.
    - Re-running v0006 is idempotent (`CREATE TRIGGER IF NOT EXISTS`).
    - Final trigger count assertion: `SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE '_outbox_%'` returns **69** after v0006 applies.
  </behavior>
  <action>
    Create `backend/migrations/v0006_install_outbox_triggers.py` with an `up(conn)` that calls into `backend.migrations.helpers.trigger_generator.build_all_triggers(conn)` and executes the result by iterating statements and calling `conn.execute(stmt)` per statement (the v0004_trace_id.py pattern). This is the FIRST migration that imports from `helpers/` — the `__init__.py` from Task 2 must already be present. Write `tests/test_mirror_outbox_capture.py` with the end-to-end capture cases above (INSERT/UPDATE/DELETE on users, annotations, drafts), plus a 69-trigger-count assertion. Each test uses a fresh in-memory DB through the same migration runner. Surgical: do NOT modify `discover_migrations()`; the auto-discovery already picks up `v0006_*`.
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/test_mirror_outbox_capture.py -x -v</automated>
  </verify>
  <done>End-to-end capture verified: writes to project tables produce correct `_outbox` rows. 6+ new test cases pass. Trigger-count assertion expects **69 triggers**. Existing 872 backend tests still green (verified by running full suite at end of task).</done>
  <risk>Existing tests that use `connect()` against a fresh DB will now also fire triggers. If any pre-existing test asserts `_outbox`-related behavior implicitly (e.g. "no extra tables exist") it must be updated. Run full suite at end of task to confirm green; if any test breaks, the fix is to add `_outbox` to that test's allowlist rather than alter trigger behavior. Equally critical: do NOT use `conn.executescript(...)` — it issues an implicit COMMIT and breaks the runner's `BEGIN IMMEDIATE` boundary.</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 6: Generate `migrations/postgres/001-baran-init.sql` (MIRROR-03)</name>
  <files>
    scripts/regen_neon_ddl.py
    migrations/postgres/001-baran-init.sql
  </files>
  <behavior>
    - `scripts/regen_neon_ddl.py` opens the current SQLite DB, calls `build_all_pg_ddl(conn)`, and writes `migrations/postgres/001-baran-init.sql`.
    - Running `python -m scripts.regen_neon_ddl` is deterministic: the output file is byte-identical on consecutive runs against the same schema (modulo the leading timestamp comment, which is omitted from the diff via a deterministic `0000-00-00` placeholder).
    - `001-baran-init.sql` contains **23 `CREATE TABLE IF NOT EXISTS baran_*` statements** (one per in-scope table) and all `CREATE INDEX IF NOT EXISTS` statements.
    - The file ends with a `COMMIT;` (idempotent re-execution).
    - The script also prints "OK — N tables, M indexes emitted" to stdout for operator confirmation.
  </behavior>
  <action>
    Implement `scripts/regen_neon_ddl.py` as a CLI invocable via `python -m scripts.regen_neon_ddl` or directly. Reads `config.DB_PATH`, calls `build_all_pg_ddl(conn)`, writes the output file. Run it once during this task to produce the actual `migrations/postgres/001-baran-init.sql` artifact. Commit both files. No new test file — the determinism is covered by Task 3's tests on the generator function; this task is the I/O wrapper. Do not modify `backend/main.py` here.
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && python -m scripts.regen_neon_ddl &amp;&amp; grep -c 'CREATE TABLE IF NOT EXISTS baran_' migrations/postgres/001-baran-init.sql</automated>
  </verify>
  <done>Verify command outputs `23`. File exists at `migrations/postgres/001-baran-init.sql`. Re-running `python -m scripts.regen_neon_ddl` produces a byte-identical file (`git diff --quiet` returns 0).</done>
  <risk>FK topological sort must be stable; if there's a cycle in the project schema (there shouldn't be), the script must fail loudly with the cycle's members listed. Implement Kahn's algorithm with cycle detection in Task 3 already.</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 7: Mirror config + Neon client wrapper (MIRROR-10)</name>
  <files>
    backend/mirror/__init__.py
    backend/mirror/config.py
    backend/mirror/neon_client.py
    .env.example
  </files>
  <behavior>
    - `backend/mirror/config.py` exposes:
      - `NEON_MIRROR_URL: str | None` (None if unset — degraded mode).
      - `NEON_MIRROR_BATCH_SIZE: int` (default 100, overridable via env).
      - `MAX_RETRIES: int` (default 5).
      - `BACKOFF_SECONDS: list[float]` (default `[1, 2, 4, 8, 16]`).
      - `EMPTY_QUEUE_SLEEP: float` (default 5.0).
      - `INTER_BATCH_SLEEP: float` (default 0.1).
    - `.env.example` documents the two new env vars with comments; the actual `.env.local` is operator-managed and NOT committed.
    - `backend/mirror/neon_client.py` exposes:
      - `class NeonClient` with methods `connect() -> bool` (returns False on OperationalError; does NOT raise), `apply(op: str, table: str, pk_value: str, payload: dict) -> None` (raises `NeonTransient` on retryable, `NeonPermanent` on schema/type errors; caller maps to retry vs dead-letter), `close()`.
      - `class NeonTransient(Exception)`, `class NeonPermanent(Exception)`.
    - `connect()` returning False on first attempt is the documented "Neon unreachable" boot path (MIRROR-10, D-14).
    - `apply()` translates each op to the right SQL: INSERT -> `INSERT INTO baran_<table> (...) VALUES (...) ON CONFLICT (<pk_cols>) DO UPDATE`; UPDATE -> same upsert (payloads carry the full row, so upsert is sufficient); DELETE -> `DELETE FROM baran_<table> WHERE <pk_cols> = ...`.
    - For both single-column and composite PKs, `pk_value` is split on `'::'` and mapped to the PK column names by importing `pk_columns_manifest` from `backend.migrations.helpers.trigger_generator` (Task 4's first-class export). Example: for `drafts`, `pk_columns_manifest["drafts"]` returns `["document_id", "user_id"]` and `pk_value = "doc123::42"` splits to `("doc123", "42")`, producing `ON CONFLICT (document_id, user_id) DO UPDATE ...`. For single-column PKs, `pk_columns_manifest["users"]` returns `["id"]` and the SQL becomes `ON CONFLICT (id) DO UPDATE ...` — same code path, no special case.
    - No tests yet for `NeonClient.apply()` against real Neon — Task 8 mocks it. This task only needs unit tests confirming the config defaults and env override behavior.
  </behavior>
  <action>
    Create `backend/mirror/__init__.py` (empty). Implement `backend/mirror/config.py` reading from env via `os.environ.get` with documented defaults. Implement `backend/mirror/neon_client.py` as the psycopg wrapper, modelled on `scripts/neon_import.py`'s connection pattern. The upsert-or-delete SQL builder MUST import `pk_columns_manifest` from `backend.migrations.helpers.trigger_generator` and consult it for every operation (single-column and composite PKs use the same lookup). Expose `NeonTransient` and `NeonPermanent` exceptions. Add `.env.example` entries for `NEON_MIRROR_URL` and `NEON_MIRROR_BATCH_SIZE` (commented placeholders). Test cases live in `tests/test_mirror_dispatcher_loop.py` (Task 8) — but a minimal `tests/test_mirror_outbox_capture.py::test_config_defaults` may be added here to assert env-default behavior.
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/test_mirror_outbox_capture.py::test_config_defaults -x -v</automated>
  </verify>
  <done>Config module loads cleanly with no env vars set (returns degraded defaults). `.env.example` lists `NEON_MIRROR_URL` and `NEON_MIRROR_BATCH_SIZE`. `NeonClient` is importable but is never instantiated by the import (lazy connect). `pk_columns_manifest` lookup wired in for both single and composite PKs.</done>
  <risk>`psycopg.connect()` blocks; calling it at module import would freeze backend startup if Neon is slow. The client must connect lazily (first call to `apply` or `connect`).</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 8: Dispatcher core loop with mocked Neon (MIRROR-02, MIRROR-05, MIRROR-07)</name>
  <files>
    backend/mirror/dispatcher.py
    tests/test_mirror_dispatcher_loop.py
  </files>
  <behavior>
    - `run_dispatcher(conn_factory, neon_client, *, batch_size, sleep_empty, sleep_batch)` is an `async def` coroutine that loops until cancelled.
    - Each iteration: `SELECT id, table_name, op, pk_value, payload_json, retry_count FROM _outbox WHERE delivered_at IS NULL AND retry_count < MAX_RETRIES ORDER BY id LIMIT :batch_size`.
    - For each row: deserialize `payload_json`, call `neon_client.apply(op, table_name, pk_value, payload)`. The dispatcher consults `pk_columns_manifest` (imported from `backend.migrations.helpers.trigger_generator`) when constructing or validating the per-table PK column list passed downstream. On success: `UPDATE _outbox SET delivered_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), error = NULL WHERE id = ?`. On `NeonTransient`: increment `retry_count`, set `error` to the message, do NOT mark delivered. On `NeonPermanent`: set `retry_count = MAX_RETRIES`, set `error`, do NOT mark delivered (dead-letter).
    - Empty result -> sleep `sleep_empty` (5 s). Non-empty -> sleep `sleep_batch` (100 ms).
    - Dispatcher is cancellable via `asyncio.CancelledError`: it finishes the current row, commits, then exits.
    - Background task does NOT hold a SQLite write lock between iterations (each iteration opens-uses-closes its own short transaction).
    - Dispatcher's long-lived SQLite connection uses the same `busy_timeout` + WAL `PRAGMA` setup as request-path connections (reuse the existing `connect()` helper from `backend/shared/db.py` — do NOT call `sqlite3.connect()` directly).
    - `start()` and `stop()` module-level helpers follow the `backend/locks/sweep.py` pattern: `start()` returns the task; `stop()` sets a flag; the caller awaits the task.
  </behavior>
  <action>
    Implement `backend/mirror/dispatcher.py` with `run_dispatcher`, `start`, `stop`. The dispatcher's SQLite connection MUST be obtained via the canonical `connect()` helper from `backend/shared/db.py` so it inherits the same `busy_timeout` and WAL PRAGMAs that the request path uses. Tests use `pytest.mark.asyncio` (already in the project; see existing async tests under `tests/`) and a `FakeNeonClient` that records `.applied` calls. Cases: (a) dispatcher drains 3 pending rows in commit order, marks all delivered, (b) on `NeonTransient`, row stays undelivered and `retry_count` increments by 1 per pass, (c) after MAX_RETRIES (5) passes, the dispatcher stops retrying that row (the `WHERE retry_count < MAX_RETRIES` filter drops it), (d) `NeonPermanent` jumps straight to `retry_count = MAX_RETRIES`, (e) empty queue triggers a `sleep_empty` (verified by patching `asyncio.sleep`), (f) cancellation mid-batch is clean (no half-committed row, no dropped row). Tests must NOT touch the network — `FakeNeonClient` is in-process. Use a fresh in-memory SQLite DB per test via the existing test fixtures.
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/test_mirror_dispatcher_loop.py -x -v</automated>
  </verify>
  <done>6+ dispatcher loop tests pass. Tests run in &lt; 5 s combined (mocked sleeps). Dispatcher's SQLite connection demonstrably uses `backend.shared.db.connect()` (assert via patching or by observing PRAGMA state on the connection).</done>
  <risk>Mixing `asyncio` with `sqlite3` (sync API): the dispatcher MUST run blocking SQLite calls inside `asyncio.to_thread` (or similar) so as not to block the event loop. Tests should verify this by running the dispatcher concurrently with a fake "request" coroutine and confirming the request is not starved.</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 9: Dispatcher retry, backoff, dead-letter (MIRROR-04, MIRROR-05)</name>
  <files>
    backend/mirror/dispatcher.py
    tests/test_mirror_dispatcher_retry.py
  </files>
  <behavior>
    - Failed rows skip the next `BACKOFF_SECONDS[retry_count]` seconds before the dispatcher considers them again. Implementation: the drain SELECT becomes `... AND (error IS NULL OR datetime(created_at, '+' || (1 << retry_count) || ' seconds') < datetime('now'))` — i.e. exponential gating built into the WHERE clause. (`1 << retry_count` reproduces the 1/2/4/8/16 schedule for retry_count = 0..4.) **Backoff gating semantics note (accepted behavior):** this clause gates against `created_at`, not the last attempt timestamp. As a result, a row that has accumulated several failures may be re-fired faster than the nominal per-failure backoff once `created_at + 2^retry_count seconds` lies in the past. This is acceptable for v1 because: (i) total backoff still bounds at ~31s for the 5-attempt schedule (1+2+4+8+16), (ii) the dead-letter rule (`retry_count >= MAX_RETRIES` drops the row from the drain query) provides a hard stop, and (iii) re-firing a transient failure slightly faster is harmless — the Neon endpoint is either reachable or not. **A `last_attempted_at` column is explicitly NOT added in v1** to keep the `_outbox` schema (D-04) frozen; revisit only if production telemetry shows a thrash problem.
    - When `retry_count` reaches `MAX_RETRIES` (5), the row is dead-lettered: `error` carries the last failure message, `delivered_at` remains NULL, `retry_count = MAX_RETRIES`. The drain query no longer picks it up.
    - On dead-letter, the dispatcher writes one `system_events` row via `audit.log_system_event(conn, "neon_mirror_dead_letter", "error", ..., extra={...})` (D-19).
    - On cold-start success (first successful Neon connect after a failed boot), the dispatcher writes one `system_events` row `("neon_mirror_connected", "info", ...)`.
    - Originating SQLite writes are NEVER affected: a test inserts a `users` row WHILE the dispatcher is repeatedly failing on Neon, and the INSERT must commit normally.
  </behavior>
  <action>
    Extend `backend/mirror/dispatcher.py` from Task 8 with the backoff WHERE-clause logic, dead-letter handling, and `system_events` writes. Tests: (a) a row that fails once is NOT picked up again for 1 s (mocked time), (b) after 5 failures the row is dead-lettered with the right `error` stamp, (c) a `system_events` "neon_mirror_dead_letter" row exists exactly once per dead-lettered outbox row, (d) a `system_events` "neon_mirror_connected" row appears on cold-start success only (not on subsequent successful drains), (e) the most important integration test: with `FakeNeonClient` raising `NeonTransient` every call, a parallel INSERT into `users` commits successfully within 50 ms — proving the request path is never blocked by Neon failures (MIRROR-04, MIRROR-07).
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/test_mirror_dispatcher_retry.py -x -v</automated>
  </verify>
  <done>5+ retry/dead-letter tests pass. Test (e) demonstrably proves zero blocking on the SQLite write path. The `created_at`-gated backoff (vs last-attempt-gated) is documented in `docs/neon-mirror.md` (Task 14) as accepted v1 behavior with the 31s total-bound rationale.</done>
  <risk>The "datetime + retry-count seconds" WHERE clause uses `(1 << retry_count)`. SQLite's `<<` operator returns an integer; that's fine, but the test must mock `now` via the existing time-injection convention (look for `freezegun` usage in the test suite or fall back to overriding `created_at` directly).</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 10: Lifespan integration — start/stop dispatcher (MIRROR-02, MIRROR-10)</name>
  <files>
    backend/main.py
    tests/test_mirror_lifespan_integration.py
  </files>
  <behavior>
    - In `lifespan`, after `apply_migrations` and after `seed_bootstrap_admin`, the dispatcher is started via the `start()` helper from Task 8 (mirrors the `locks_sweep.start()` / `backup_loop.start()` pattern already present).
    - The dispatcher start is wrapped in a try/except: if `NEON_MIRROR_URL` is unset OR initial `NeonClient.connect()` returns False, the lifespan emits a `system_events` "neon_mirror_unreachable" warn-severity row and continues startup. The dispatcher coroutine still launches — it will keep trying to connect (D-14).
    - On shutdown, `stop()` is called and the task is awaited (with a swallowed exception, matching the `locks_sweep` shape).
    - The lifespan changes are exactly 6 added lines (start), 4 added lines (stop), and 1 import. No other lifespan logic moves. Per CLAUDE.md surgical-changes rule.
    - Test boots the FastAPI app with `TestClient` and `NEON_MIRROR_URL` unset, asserts: (a) startup succeeds, (b) `_outbox` and 69 triggers exist, (c) a `system_events` row "neon_mirror_unreachable" exists, (d) the dispatcher task is alive (via a module-level handle exposed by `backend.mirror.dispatcher`).
  </behavior>
  <action>
    Modify `backend/main.py` lifespan to start the dispatcher after the migration apply + bootstrap-admin block. Add the import `from backend.mirror import dispatcher as mirror_dispatcher`. Use the same start/stop/await shape as `locks_sweep`. Write `tests/test_mirror_lifespan_integration.py` with the four assertions above plus one negative case (when `NEON_MIRROR_URL` is set to an unreachable value, startup STILL succeeds and the "unreachable" event is emitted).
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/test_mirror_lifespan_integration.py -x -v</automated>
  </verify>
  <done>Lifespan tests pass. The full backend suite (run via `pytest tests/ -x`) still completes with 872 + new tests all green.</done>
  <risk>Existing lifespan tests (e.g. `test_backup_lifespan.py`) may rely on a precise set of started tasks. Run them first to baseline, then re-run after this task; if any break, update those tests' allowlists to include the dispatcher task — do NOT remove or rename existing task starts.</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 11: Backfill script (MIRROR-06)</name>
  <files>
    scripts/neon_backfill.py
    tests/test_mirror_backfill_idempotency.py
  </files>
  <behavior>
    - `scripts/neon_backfill.py` reads every row from every in-scope SQLite table (23 tables) in FK-topological order (parents first; reuses Task 3's sort) and INSERTs it into the corresponding `baran_*` table using `INSERT INTO baran_<table> (...) VALUES (...) ON CONFLICT (<pk_cols>) DO UPDATE SET <non-pk-cols> = EXCLUDED.<col>` (D-15). The `<pk_cols>` list comes from `pk_columns_manifest` (Task 4's first-class export) — same lookup path as the dispatcher in Task 8.
    - Batches of 500 rows per table at a time (psycopg `execute_values` or `executemany`).
    - Idempotent: re-running against an already-populated Neon DB results in zero new rows and zero data drift (all rows resolved by `ON CONFLICT DO UPDATE` to the same values).
    - Progress is logged to stdout: `users: 0/4 done`, `documents_meta: 4096/17923 done`, etc.
    - On any psycopg error, the script aborts loudly with a non-zero exit code and a clear table+row context — backfill failures are operator-level (this is one-shot, not the runtime path).
    - Backfill is invoked as `python -m scripts.neon_backfill` with optional `--dry-run` (counts only, no writes) and `--table <name>` (single-table mode for retries).
    - The script does NOT touch `_outbox`. It runs against a Neon DB whose schema was already created via `001-baran-init.sql`.
    - **Backfill / trigger-install ordering (D-17 amendment):** D-17's preferred ordering is backfill → trigger install, but v0006 (Task 5) runs unconditionally on lifespan boot. We accept the resulting race: on first boot of the deployed system the triggers fire for any subsequent writes; the operator-run backfill then catches the 17923 pre-existing rows plus any post-trigger writes; the dispatcher's `ON CONFLICT DO UPDATE` semantics (D-15, same upsert SQL used by both the backfill and the runtime dispatcher) mask the duplicate-write race by resolving each PK to the same final state. No code gating is added; the upsert is the resolution mechanism.
    - Idempotency tests use an in-memory psycopg-compatible mock (or a `FakeNeonClient`-style accumulator) since the test suite cannot hit real Neon.
  </behavior>
  <action>
    Implement `scripts/neon_backfill.py`. Reuse `NeonClient` from Task 7 for the connection, `build_all_pg_ddl`'s topological sort from Task 3, and `pk_columns_manifest` from `backend.migrations.helpers.trigger_generator` (Task 4) for the `ON CONFLICT (<pk_cols>)` clause per table. For tests, write `tests/test_mirror_backfill_idempotency.py` using a `FakeNeonAccumulator` that captures INSERT/UPSERT calls and asserts: (a) backfill writes exactly N rows for each table when the accumulator starts empty (use a row in `annotations.references_json` with a non-trivial JSON payload and confirm the captured SQL casts it to `jsonb` correctly), (b) re-running the backfill against the same accumulator produces UPSERTs but no net row change (idempotency), (c) FK order respected: `baran_users` upserts before `baran_annotations`, (d) `--dry-run` writes zero rows but reports the row counts, (e) `--table users` only touches users, (f) `ON CONFLICT` clause for `drafts` includes both `(document_id, user_id)` from the manifest.
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/test_mirror_backfill_idempotency.py -x -v</automated>
  </verify>
  <done>6+ backfill tests pass. Operator can dry-run against real Neon manually as the runbook entry in Task 14 documents. First-boot trigger-fires-before-backfill race is acknowledged as resolved by the upsert semantics; no code gating added.</done>
  <risk>Some tables (e.g. `annotations.references_json`) carry data that must round-trip cleanly into Postgres `jsonb`. The backfill must pass JSON strings as text and rely on Postgres to cast to `jsonb` on insert. Test (a) must include a row with a non-trivial `references_json` payload and assert the captured SQL casts it correctly.</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 12: Admin health endpoint (MIRROR-09)</name>
  <files>
    backend/mirror/health.py
    backend/admin/routes.py
    tests/test_mirror_admin_health.py
  </files>
  <behavior>
    - `backend/mirror/health.py::collect_health(conn) -> dict` returns:
      - `queue_depth`: count of rows with `delivered_at IS NULL AND retry_count < MAX_RETRIES`.
      - `dead_letter_count`: count of rows with `delivered_at IS NULL AND retry_count >= MAX_RETRIES`.
      - `oldest_undelivered_age_seconds`: seconds since the oldest undelivered row's `created_at`, or `null` if queue is empty.
      - `last_delivered_at`: ISO-8601 string of the most recent `MAX(delivered_at)`, or `null` if nothing has ever delivered.
      - `dispatcher_alive`: bool — whether the module-level dispatcher task is non-null and not done. **Operational ergonomics, not strictly required by D-18** — included because surfacing the task liveness in the same payload is cheap (~3 lines) and lets the operator distinguish "queue is empty because dispatcher is healthy" from "queue is empty because dispatcher crashed silently."
      - `neon_reachable`: bool — based on the last successful or failed apply (the dispatcher should expose a `last_status: bool | None` module global). **Operational ergonomics, not strictly required by D-18** — included for the same reason as `dispatcher_alive`. The two boolean fields add ~5 lines of code total and zero additional auth surface; they exist to make the runbook in `docs/neon-mirror.md` actionable.
    - `GET /api/admin/mirror/health` (admin-only, follows the existing admin auth dependency in `backend/admin/routes.py`) returns the dict as JSON.
    - Endpoint follows the existing admin route registration pattern — no new router file.
    - Endpoint contributes ZERO new auth surface (reuses `require_admin`).
  </behavior>
  <action>
    Implement `backend/mirror/health.py` as pure functions (no I/O beyond the supplied connection). Modify `backend/admin/routes.py` (surgical: add one route + one import; no other route changes). Write `tests/test_mirror_admin_health.py` covering: (a) empty queue -> queue_depth=0 and oldest_age=null, (b) one pending row -> queue_depth=1 and a non-null oldest_age, (c) one dead-lettered row -> dead_letter_count=1, queue_depth=0 (dead-lettered rows are NOT in queue depth), (d) one delivered row -> last_delivered_at populated, (e) endpoint returns 401 / 403 for non-admin, 200 for admin (reuse existing admin-auth test fixture).
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/test_mirror_admin_health.py -x -v</automated>
  </verify>
  <done>5+ health tests pass. `GET /api/admin/mirror/health` returns the expected JSON shape including the two ergonomic booleans.</done>
  <risk>The admin auth dependency name varies by route group; use the same dependency the other `/api/admin/*` routes use. Read `backend/admin/routes.py` first to confirm the name (`require_admin` or `current_admin_user`).</risk>
</task>

<task type="auto" tdd="true">
  <name>Task 13: End-to-end smoke + full-suite baseline guard (MIRROR-07, MIRROR-08)</name>
  <files>
    tests/test_mirror_outbox_capture.py
  </files>
  <behavior>
    - Add one final end-to-end test extending `tests/test_mirror_outbox_capture.py`: spin up the FastAPI app via `TestClient`, hit a write endpoint (`POST /api/annotations/...` or any other existing write route that we know does an INSERT), assert: (a) the originating endpoint returns its normal success status, (b) exactly one `_outbox` row was created, (c) the row's `payload_json` matches the request data, (d) once a `FakeNeonClient` is wired in (via dependency override), the dispatcher drains the row and marks it delivered, (e) the round-trip end-to-end completes in &lt; 500 ms.
    - **Latency regression check (soft):** 100 sequential GET requests to a read endpoint with the dispatcher running compared against 100 GET requests with the dispatcher stopped — assert the p95 delta is **≤ 50 ms** (NOT 5 ms). The MIRROR-07 5 ms p95 budget is verified out-of-process via a manual `wrk`/`hey` smoke recorded in `4-SUMMARY.md` (see `<output>` block); the in-process assertion only acts as a coarse regression guard. The 5 ms threshold inside `pytest` is too tight given Python GIL noise and CI variance — a tight in-process test would be flaky and would get muted, which is worse than asserting a 10x looser bound and a separate documented manual smoke.
    - Run the FULL backend suite at the end of this task and confirm 872 baseline tests + all Phase 4 new tests pass.
  </behavior>
  <action>
    Append one or two end-to-end tests to `tests/test_mirror_outbox_capture.py` (no new file — keep the topical grouping). Use the existing fixtures for app + admin user + DB. The in-process latency check uses `time.perf_counter` and asserts the **soft 50 ms p95 regression bound** (not 5 ms). Document explicitly in the test docstring: "Strict 5 ms p95 verification is performed out-of-process via `wrk`/`hey` per the MIRROR-07 acceptance criterion; that result is recorded in `4-SUMMARY.md`. This in-process check is a coarse regression guard only." At the end of the task, run `pytest tests/ -x --ignore=tests/test_docker_smoke.py` (docker smoke skips when daemon down) and confirm 872 baseline + new tests = full green. Also: separately, record one `wrk`/`hey` run with the dispatcher running and one with it stopped in `4-SUMMARY.md` to satisfy the MIRROR-07 5 ms acceptance criterion at the phase level.
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme && pytest tests/ -x --ignore=tests/test_docker_smoke.py 2>&amp;1 | tail -20</automated>
  </verify>
  <done>Full backend suite: 872 + ~45 new mirror tests, all pass. **The in-process latency assertion uses a 50 ms p95 regression bound — DO NOT tighten this to 5 ms** (subject to CI flakiness; the 5 ms acceptance criterion is verified out-of-process via `wrk`/`hey` and recorded in `4-SUMMARY.md`). The 511 frontend tests are unchanged (no frontend mods this phase). The 9 e2e Playwright tests still pass (no API surface broken — only the `/api/admin/mirror/health` GET added).</done>
  <risk>If any existing test depends on "no triggers exist on this table," it will fail after v0006. The fix is to update that test's expectation; the trigger behavior is the new correct behavior. Also: do NOT tighten the in-process p95 to 5 ms — keep the 50 ms regression bound and rely on the manual `wrk`/`hey` smoke for the tight bound.</risk>
</task>

<task type="auto">
  <name>Task 14: Documentation + README architecture diagram update (operator-facing)</name>
  <files>
    docs/neon-mirror.md
    README.md
  </files>
  <behavior>
    - `docs/neon-mirror.md` documents:
      1. Setup: create read-write Neon role; set `NEON_MIRROR_URL` and optional `NEON_MIRROR_BATCH_SIZE`.
      2. One-time DDL apply: `psql $NEON_MIRROR_URL -f migrations/postgres/001-baran-init.sql` (or via Neon Console). Idempotent.
      3. One-time backfill: `python -m scripts.neon_backfill` (idempotent; run after DDL apply, before live dual-write).
      4. Migration apply sequence on the SQLite side: v0005 (outbox table), then v0006 (triggers — 69 triggers across 23 in-scope tables). Note that v0006 runs automatically on next backend startup.
      5. Health surface: `GET /api/admin/mirror/health` returns queue depth + dead-letter count + last-delivered + `dispatcher_alive` + `neon_reachable`.
      6. Dead-letter recovery: how to inspect rows with `retry_count = 5`, reset `retry_count` and `error` once Neon is healthy.
      7. Re-running `scripts/regen_neon_ddl.py` after future SQLite schema changes; the partner team must re-apply the DDL diff manually (out-of-scope auto-migration).
      8. Backoff semantics caveat: backoff gating is computed against `created_at`, not the last attempt — total bound ~31s for the 5-attempt schedule; dead-letter is the hard stop. Documented as v1 accepted behavior.
    - `README.md` Architecture mermaid diagram is extended with a "Neon Mirror" branch off the SQLite write path: `SQLite -> _outbox trigger -> async dispatcher -> Neon baran_*`. Keep the existing diagram intact — only add the new branch.
    - No code changes; pure docs.
  </behavior>
  <action>
    Create `docs/neon-mirror.md` covering the 8 sections above. Modify `README.md` to extend the architecture diagram only (surgical — do not rewrite surrounding prose). No tests required (docs).
  </action>
  <verify>
    <automated>cd /Users/barandincoguz/Desktop/deneme &amp;&amp; test -f docs/neon-mirror.md &amp;&amp; grep -q "neon_backfill" docs/neon-mirror.md &amp;&amp; grep -q "Neon Mirror\|baran_" README.md &amp;&amp; echo OK</automated>
  </verify>
  <done>`docs/neon-mirror.md` exists with all 8 sections (including the backoff-semantics caveat). README diagram extended.</done>
  <risk>Low — pure documentation. Just keep the README mermaid diagram syntactically valid (lint by re-rendering on github after push if uncertain).</risk>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| SQLite trigger -> _outbox | In-process; trusted boundary. Trigger SQL is generator-emitted and verified by tests. |
| _outbox -> dispatcher coroutine | In-process; trusted. SQL injection impossible since payload is bound, not interpolated. |
| Dispatcher -> Neon Postgres | Cross-network. psycopg over TLS. Credentials in env (never committed). Read-write role scoped to baran_* tables only. |
| GET /api/admin/mirror/health -> admin user | HTTP boundary. Reuses the existing admin-auth dependency — no new auth surface. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-01 | Tampering | Trigger SQL emitted by `build_all_triggers` | mitigate | Generator is pure-Python with unit tests (Task 4). No runtime user input flows into trigger DDL — table/column names come from `PRAGMA` introspection of the canonical schema. |
| T-04-02 | Information Disclosure | NEON_MIRROR_URL contains DB credentials | mitigate | Read from env only (Task 7); never logged. `.env.example` carries placeholders only. Audit `log_system_event` calls in Task 9 to confirm the URL is NEVER in the `extra` payload. |
| T-04-03 | Denial of Service | Dispatcher blocks event loop on slow Neon writes | mitigate | All SQLite + psycopg calls in the dispatcher loop run via `asyncio.to_thread` (Task 8 risk callout). Test (e) in Task 9 explicitly proves zero starvation. |
| T-04-04 | Denial of Service | Outbox grows unbounded if Neon is permanently down | accept | After `MAX_RETRIES` rows enter dead-letter state and stop being scanned (Task 9). Archival/purge policy explicitly deferred to v2 (REQUIREMENTS.md MIRROR-V2-02). Admin health endpoint surfaces queue depth so operator notices. |
| T-04-05 | Repudiation | Lost outbox row | mitigate | Trigger writes the outbox row inside the same `BEGIN IMMEDIATE` transaction as the originating write (D-01). Either both commit or both roll back. At-least-once delivery semantics are enforced by `delivered_at IS NULL` filter. |
| T-04-06 | Elevation of Privilege | Non-admin reading mirror health | mitigate | Endpoint reuses existing `require_admin` dependency in Task 12; tested in case (e). |
| T-04-07 | Spoofing | Dispatcher connecting to wrong Neon DB | accept | Operator-controlled env var; out-of-band verification by the partner team after first backfill. Documented in `docs/neon-mirror.md` Task 14. |
| T-04-08 | Tampering | Backfill double-inserts under retry | mitigate | All backfill writes use `ON CONFLICT (pk_cols) DO UPDATE` (D-15). Idempotency tested in Task 11. The same upsert semantics also mask the first-boot trigger-before-backfill race (FLAG-4). |
</threat_model>

<verification>
Phase-level checks (run after Task 13 completes):

- Full backend suite: `pytest tests/ -x --ignore=tests/test_docker_smoke.py` → all green (872 baseline + ~45 new mirror tests).
- Frontend suite untouched: `npm test --prefix frontend -- --run` → 511 / 511 still passing.
- e2e Playwright: `npm run e2e --prefix frontend` → 9 / 9 still passing.
- Lint clean: `ruff check backend/ scripts/` → no errors on changed files (per project's "ruff on changed files" convention).
- Trigger count: `sqlite3 data/db/annotations.db "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE '_outbox_%'"` → **69** (23 in-scope tables × 3 ops).
- DDL file integrity: `grep -c 'CREATE TABLE IF NOT EXISTS baran_' migrations/postgres/001-baran-init.sql` → **23**.
- DDL regeneration is deterministic: `python -m scripts.regen_neon_ddl && git diff --quiet migrations/postgres/001-baran-init.sql` → exit 0.
- Health endpoint smoke: with `NEON_MIRROR_URL` unset, `GET /api/admin/mirror/health` returns 200 with `dispatcher_alive=true`, `neon_reachable=false`.
- Out-of-process latency smoke (recorded in `4-SUMMARY.md`, not in CI): `wrk` / `hey` against a representative read endpoint shows p95 delta ≤ 5 ms between dispatcher-running and dispatcher-stopped runs.
</verification>

<success_criteria>

1. **MIRROR-01** ✓ — Every committed INSERT/UPDATE/DELETE on any of the 23 in-scope tables writes exactly one `_outbox` row inside the same transaction. Verified by `tests/test_mirror_outbox_capture.py` (Task 5 + Task 13). Trigger count: **69** (23 × 3).

2. **MIRROR-02** ✓ — `backend/mirror/dispatcher.py` async loop, started in lifespan (Task 10), drains `_outbox` and applies each row to Neon's `baran_<table>` mirror. Verified by `tests/test_mirror_dispatcher_loop.py` (Task 8).

3. **MIRROR-03** ✓ — All 23 in-scope mirror tables created with faithful type/PK/FK/index mapping (TEXT primary keys preserved, only `INTEGER PRIMARY KEY AUTOINCREMENT` rewrites to `bigserial`). Generated DDL in `migrations/postgres/001-baran-init.sql` (Task 6). Type-mapping rules verified by `tests/test_mirror_postgres_ddl.py` (Task 3).

4. **MIRROR-04** ✓ — Neon outage does not fail/roll back SQLite writes. Verified by Task 9 test (e): a parallel INSERT commits within 50 ms while the dispatcher is failing on Neon every call.

5. **MIRROR-05** ✓ — At-least-once delivery with dead-letter after MAX_RETRIES=5. Verified by `tests/test_mirror_dispatcher_retry.py` (Task 9).

6. **MIRROR-06** ✓ — `scripts/neon_backfill.py` populates `baran_*` from current SQLite state, idempotently via `ON CONFLICT DO UPDATE`. Verified by `tests/test_mirror_backfill_idempotency.py` (Task 11).

7. **MIRROR-07** ✓ — Request path never blocks on the dispatcher. Verified by Task 9 test (e) and Task 13's in-process 50 ms regression guard + out-of-process `wrk`/`hey` smoke recorded in 4-SUMMARY.md (the 5 ms p95 bound).

8. **MIRROR-08** ✓ — 872 backend + 511 frontend tests stay green. ~45 new mirror tests added across Tasks 1, 3, 4, 5, 8, 9, 10, 11, 12, 13. Verified by the full-suite run in Task 13.

9. **MIRROR-09** ✓ — `GET /api/admin/mirror/health` returns queue depth + dead-letter count + last-delivered-at + dispatcher_alive + neon_reachable. Verified by `tests/test_mirror_admin_health.py` (Task 12).

10. **MIRROR-10** ✓ — `NEON_MIRROR_URL` from env only; missing/unreachable Neon at boot is non-fatal — app boots with `neon_mirror_unreachable` system event. Verified by `tests/test_mirror_lifespan_integration.py` (Task 10).

Phase 4 complete when all 14 tasks land on `main`, the full backend + frontend + e2e suites are green, and the partner team confirms the first backfill landed in their Neon DB.

</success_criteria>

<output>
Create `.planning/phases/04-neon-postgres-dual-write-mirror/4-SUMMARY.md` when all 14 tasks are done. The SUMMARY must record:
- The 14 commits (one per task) with their SHAs.
- The final trigger count (expected **69** — 23 in-scope tables × 3 ops).
- The final `baran_*` table count (expected **23** in-scope tables).
- The final backend test count (expected 872 + ~45 new).
- The actual p95 latency delta on the request path measured **out-of-process via `wrk` or `hey`** (expected ≤ 5 ms; this is the canonical MIRROR-07 evidence, since the in-process pytest check uses a softer 50 ms regression bound).
- Any deviations from this plan (e.g. `execute_batch` vs `executemany` choice in `NeonClient`, which is a Claude's-Discretion item per CONTEXT.md).
</output>
