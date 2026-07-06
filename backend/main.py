"""FastAPI application entry point.

On startup:
  1. Ensure data directories exist
  2. Apply pending migrations
  3. Log startup system event

Domain routers (users, documents, ...) are mounted in their respective packages.
"""
import os
import json
import mimetypes
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, HTTPException

# Explicitly register common MIME types to prevent python-slim images
# from serving CSS/JS assets as text/plain under strict MIME sniffing policies.
mimetypes.init()
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

from backend import config
from backend.shared.db import connect
from backend.shared import audit
from backend.shared.csrf import OriginCheckMiddleware
from backend.shared.prod_enforce import DEV_SESSION_SECRETS, enforce_production_secrets
from backend.shared.security_headers import SecurityHeadersMiddleware
from backend.shared.static_serving import (
    ImmutableStaticFiles,
    SelectiveGZipMiddleware,
    revalidating_file_response,
)
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.users.service import seed_bootstrap_admin
from backend.admin.routes import router as admin_router
from backend.users.routes import router as users_router
from backend.docs_help.routes import router as help_router
from backend.documents.routes import router as documents_router
from backend.annotations.routes import router as annotations_router
from backend.locks.routes import router as locks_router
from backend.gamification.routes import router as gamification_router
from backend.notifications.routes import router as notifications_router
from backend.shuffle.routes import router as shuffle_router
from backend.sse.routes import router as sse_router
from backend.statistics.routes import router as statistics_router
from backend.training.routes import router as training_router, admin_router as training_admin_router
from backend.backup.routes import router as backup_router
from backend.retention.routes import router as retention_router
from backend.exports.routes import router as exports_router
from backend.locks import sweep as locks_sweep
from backend.backup import loop as backup_loop
from backend.retention import loop as retention_loop
from backend.mirror import dispatcher as mirror_dispatcher
from backend.mirror import config as mirror_config

VERSION = "0.1.0"

# Durable application state that may be restored from the Neon mirror.
# Bearer sessions and document locks are intentionally local-only runtime
# state: restoring either would revive stale access or stale ownership.
MIRROR_RESTORE_TABLES = (
    "users",
    "invite_codes",
    "site_settings",
    "gamification_state",
    "gamification_ledger",
    "badges_earned",
    "training_attempts",
    "notifications",
    "training_gold_doc_overrides",
    "training_quiz_overrides",
    "annotations",
    "annotation_versions",
    "annotation_references",
    "drafts",
    "activity_events",
    "behavioral_events",
    "admin_audit_log",
)

ANNOTATION_STATE_TABLES = (
    "annotations",
    "annotation_versions",
    "annotation_references",
    "drafts",
)


def _translate_mirror_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _local_annotation_state_empty(conn) -> bool:
    for table in ANNOTATION_STATE_TABLES:
        count = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        if count:
            return False
    return True


def _mirror_annotation_state_available(pg_conn) -> bool:
    for table in ANNOTATION_STATE_TABLES:
        pg_cur = pg_conn.cursor()
        try:
            pg_cur.execute(f"SELECT COUNT(*) FROM baran_{table}")
            row = pg_cur.fetchone()
        finally:
            pg_cur.close()
        if row and row[0] > 0:
            return True
    return False


def _restore_mirrored_state(conn, pg_conn) -> dict[str, int]:
    """Atomically replace durable local state from an already-open PG connection."""
    foreign_keys_enabled = bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    if foreign_keys_enabled:
        conn.execute("PRAGMA foreign_keys=OFF")

    restored_counts: dict[str, int] = {}
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Runtime credentials and ownership never survive an ephemeral restore.
        conn.execute("DELETE FROM user_sessions")
        conn.execute("DELETE FROM document_locks")

        for table in MIRROR_RESTORE_TABLES:
            pg_cur = pg_conn.cursor()
            try:
                pg_cur.execute(f"SELECT * FROM baran_{table}")
                rows = pg_cur.fetchall()
            except Exception as exc:
                raise RuntimeError(f"failed to read required mirror table baran_{table}") from exc
            finally:
                pg_cur.close()

            conn.execute(f"DELETE FROM {table}")
            restored_counts[table] = len(rows)
            if not rows:
                continue

            columns = list(rows[0].keys())
            placeholders = ",".join("?" for _ in columns)
            sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
            for row in rows:
                values = [
                    None if table == "activity_events" and column == "session_id"
                    else _translate_mirror_value(row[column])
                    for column in columns
                ]
                conn.execute(sql, values)

        conn.commit()
        return restored_counts
    except Exception:
        conn.rollback()
        raise
    finally:
        if foreign_keys_enabled:
            conn.execute("PRAGMA foreign_keys=ON")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.validate_environment()
    enforce_production_secrets()
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        applied = apply_migrations(conn, discover_migrations())
        user_count_before = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        is_fresh_db = (user_count_before == 0)
        seed_bootstrap_admin(
            conn,
            username=config.BOOTSTRAP_ADMIN_USERNAME,
            password=config.BOOTSTRAP_ADMIN_PASSWORD,
        )
        # Ensure BURSIYER-2026 is seeded as the active invite code if no active invite code exists (skip in test environment)
        if config.ENVIRONMENT != "test":
            from datetime import datetime, timezone
            active_code = conn.execute("SELECT code FROM invite_codes WHERE is_active=1").fetchone()
            if active_code is None:
                conn.execute(
                    "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?, 1, ?)",
                    ("BURSIYER-2026", datetime.now(timezone.utc).isoformat()),
                )
            
            # One-off outbox cleanup to purge redundant document sync outbox entries from previous boots
            conn.execute(
                "DELETE FROM _outbox WHERE table_name IN ('documents_meta', 'document_kanun_refs', 'document_bkk_refs') AND delivered_at IS NULL"
            )
            conn.commit()

        # Automatic Neon Postgres schema migration (auto-sync schema) before sync starts
        from backend.mirror import config as mirror_config
        mirror_config.reload_from_env()
        if config.ENVIRONMENT != "test" and mirror_config.NEON_MIRROR_URL:
            from backend.mirror.schema_sync import sync_postgres_schema
            sync_postgres_schema(conn, mirror_config.NEON_MIRROR_URL)

        # Automatic document replication and full user state sync from Neon Postgres on first boot (Phase 6 + Ephemeral Sync)
        user_count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        doc_count = conn.execute("SELECT COUNT(*) AS c FROM documents_meta").fetchone()["c"]
        local_annotation_state_empty = _local_annotation_state_empty(conn)
        if (
            config.ENVIRONMENT != "test"
            and mirror_config.NEON_MIRROR_URL
            and (is_fresh_db or doc_count == 0 or local_annotation_state_empty)
        ):
            import psycopg
            
            # Drop all outbox triggers temporarily to avoid generating useless queue writes (59,000+ rows)
            triggers = [row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE '_outbox_%'"
            ).fetchall()]
            for t in triggers:
                conn.execute(f"DROP TRIGGER IF EXISTS {t}")
                
            try:
                # 1. Replicate documents from Neon partner DB
                if doc_count == 0:
                    from backend.documents.parser import parse_document, ParseError
                    from backend.documents.service import _upsert_meta, _replace_kanun_refs, _replace_bkk_refs
                    
                    audit.log_system_event(
                        conn, "neon_sync_start", "info",
                        message="Local documents database is empty. Starting automatic sync from Neon Postgres...",
                    )
                    print("Local documents database is empty. Starting automatic sync from Neon Postgres...")
                    
                    try:
                        with psycopg.connect(mirror_config.NEON_MIRROR_URL) as pg_conn:
                            with pg_conn.cursor(name="startup_docs_sync") as pg_cur:
                                pg_cur.itersize = 1000
                                pg_cur.execute("SELECT evrak_id, display_text, raw_metadata_json FROM documents ORDER BY id")
                                
                                synced_count = 0
                                skipped_count = 0
                                conn.execute("BEGIN IMMEDIATE")
                                try:
                                    for evrak_id, display_text, raw_meta in pg_cur:
                                        if not evrak_id or not display_text:
                                            skipped_count += 1
                                            continue
                                        
                                        PARSER_KEYS = {
                                            "evrakOid", "pdfText", "htmlText", "sayi", "tarih", "basvuruTarihi",
                                            "vergiTuru", "vergiDonemi", "konu", "mukellefiyetTuru", "kanunBilgileri",
                                            "bkkTebligSirkuBilgileri",
                                        }
                                        meta_doc = {k: v for k, v in (raw_meta or {}).items() if k in PARSER_KEYS}
                                        meta_doc["evrakOid"] = evrak_id
                                        meta_doc["pdfText"] = display_text
                                        
                                        try:
                                            parsed = parse_document(meta_doc, file_path="neon_postgres")
                                            meta = parsed["meta"]
                                            _upsert_meta(conn, meta)
                                            _replace_kanun_refs(conn, meta["document_id"], parsed["kanun_refs"])
                                            _replace_bkk_refs(conn, meta["document_id"], parsed["bkk_refs"])
                                            synced_count += 1
                                        except ParseError:
                                            skipped_count += 1
                                            continue
                                    conn.commit()
                                except Exception:
                                    conn.rollback()
                                    raise
                                    
                        audit.log_system_event(
                            conn, "neon_sync_success", "info",
                            message=f"Successfully synced {synced_count} documents from Neon Postgres! (skipped {skipped_count})",
                        )
                        print(f"Successfully synced {synced_count} documents from Neon Postgres! (skipped {skipped_count})")
                    except Exception as e:
                        audit.log_system_event(
                            conn, "neon_sync_failed", "error",
                            message=f"Failed to auto-sync documents from Neon: {e}",
                        )
                        print(f"Failed to auto-sync documents from Neon: {e}")

                # 2. Sync durable user/annotation state if the DB is fresh, or
                # if documents exist locally but annotation state is empty while
                # Neon has annotation work. Never overwrite local annotation work.
                should_restore_state = is_fresh_db
                if not should_restore_state and local_annotation_state_empty:
                    try:
                        with psycopg.connect(mirror_config.NEON_MIRROR_URL) as pg_conn:
                            should_restore_state = _mirror_annotation_state_available(pg_conn)
                    except Exception as e:
                        audit.log_system_event(
                            conn, "neon_user_sync_failed", "error",
                            message=f"Failed to check Neon annotation state: {e}",
                        )
                        print(f"Failed to check Neon annotation state: {e}")

                if should_restore_state:
                    from psycopg.rows import dict_row

                    try:
                        with psycopg.connect(mirror_config.NEON_MIRROR_URL, row_factory=dict_row) as pg_conn:
                            audit.log_system_event(
                                conn, "neon_user_sync_start", "info",
                                message="Local users database is empty. Starting automatic state restoration from Neon Postgres...",
                            )
                            print("Local users database is empty. Starting automatic state restoration from Neon Postgres...")

                            restored_counts = _restore_mirrored_state(conn, pg_conn)
                            for table, count in restored_counts.items():
                                print(f"Successfully restored {count} rows to table {table}")
                                
                        audit.log_system_event(
                            conn, "neon_user_sync_success", "info",
                            message="Successfully restored durable users, annotations, and system state from Neon Postgres; sessions and locks were invalidated.",
                        )
                        print("Successfully restored durable users, annotations, and system state from Neon Postgres; sessions and locks were invalidated.")
                    except Exception as e:
                        audit.log_system_event(
                            conn, "neon_user_sync_failed", "error",
                            message=f"Failed to auto-restore state from Neon: {e}",
                        )
                        print(f"Failed to auto-restore state from Neon: {e}")
            finally:
                # Re-create all outbox triggers (always run to ensure DB is never left unprotected)
                from backend.migrations.helpers.trigger_generator import build_triggers_for_table, _collect_schemas
                for s in _collect_schemas(conn):
                    for trigger_sql in build_triggers_for_table(s):
                        conn.execute(trigger_sql)

        # Enforce admin credentials *after* Neon restore to ensure they match BOOTSTRAP_ADMIN_PASSWORD
        seed_bootstrap_admin(
            conn,
            username=config.BOOTSTRAP_ADMIN_USERNAME,
            password=config.BOOTSTRAP_ADMIN_PASSWORD,
        )

        audit.log_system_event(
            conn, "startup", "info",
            message=f"app v{VERSION} started; migrations applied: {applied}",
            extra={"version": VERSION, "migrations_applied": applied},
        )
        if not config.is_production() and config.SESSION_SECRET in DEV_SESSION_SECRETS:
            audit.log_system_event(
                conn, "session_secret_dev_default", "warn",
                message="SESSION_SECRET is set to a dev default; set a real "
                        "secret via env var for production.",
            )
    finally:
        conn.close()


    sweep_task     = locks_sweep.start(interval_seconds=60)
    backup_task    = backup_loop.start()
    retention_task = retention_loop.start()

    # Phase 4: Neon mirror dispatcher. Failure to reach Neon at boot is
    # non-fatal (MIRROR-10, D-14) — we log a warn event and let the
    # dispatcher keep retrying connect in its loop.
    mirror_config.reload_from_env()
    mirror_task = mirror_dispatcher.start()
    if not mirror_config.NEON_MIRROR_URL:
        c = connect(config.DB_PATH)
        try:
            audit.log_system_event(
                c, "neon_mirror_unreachable", "warn",
                message="NEON_MIRROR_URL is unset; dispatcher running in degraded mode",
            )
        finally:
            c.close()

    yield

    locks_sweep.stop()
    try:
        await sweep_task
    except Exception:
        pass

    backup_loop.stop()
    try:
        await backup_task
    except Exception:
        pass

    retention_loop.stop()
    try:
        await retention_task
    except Exception:
        pass

    mirror_dispatcher.stop()
    try:
        await mirror_task
    except Exception:
        pass

    conn = connect(config.DB_PATH)
    try:
        audit.log_system_event(conn, "shutdown", "info", message=f"app v{VERSION} shutting down")
    finally:
        conn.close()


app = FastAPI(title="Anotasyon Platform", version=VERSION, lifespan=lifespan)

# Compress direct-origin traffic too. The SSE endpoint is excluded by the
# middleware so event delivery remains immediate and proxy-safe.
app.add_middleware(SelectiveGZipMiddleware, minimum_size=500, compresslevel=6)

# CSRF defense — must sit BEFORE the routers so every state-changing
# request hits the Origin allowlist first. Active in production only; see
# backend/shared/csrf.py for the rationale and operator setup.
#
# NOTE: any future `CORSMiddleware` install MUST NOT use
# `allow_origins=["*"]` together with `allow_credentials=True`. The
# Origin allowlist below is the *only* CSRF defense beyond SameSite=Lax;
# a permissive CORS config silently re-opens the surface.
app.add_middleware(OriginCheckMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(users_router)
app.include_router(help_router)
app.include_router(documents_router)
app.include_router(annotations_router)
app.include_router(locks_router)
app.include_router(notifications_router)
app.include_router(gamification_router)
app.include_router(shuffle_router)
app.include_router(sse_router)
app.include_router(statistics_router)
app.include_router(training_router)
app.include_router(training_admin_router)
app.include_router(admin_router)
app.include_router(backup_router)
app.include_router(retention_router)
app.include_router(exports_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": VERSION}


@app.get("/api/health/db")
def health_db():
    conn = connect(config.DB_PATH)
    try:
        migrations_count = conn.execute("SELECT COUNT(*) AS c FROM schema_migrations").fetchone()["c"]
        tables_count = conn.execute(
            "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()["c"]
    finally:
        conn.close()
    return {
        "status": "ok",
        "migrations_applied": migrations_count,
        "table_count": tables_count,
    }


# === SPA fallback (Paket 16a) =================================================
#
# Route registration happens at import time. To keep tests deterministic
# (no SPA routes leaking into TestClient) we gate registration on an env
# flag in addition to the directory check. The test conftest sets this
# BEFORE backend.main is imported.
#
# MUST stay below every /api/* router include — FastAPI matches routes
# in registration order, and the catch-all `/{path:path}` would otherwise
# swallow legitimate API routes.
_SPA_DISABLED = os.getenv("DISABLE_SPA_MOUNT") == "1"

if config.STATIC_DIR.exists() and not _SPA_DISABLED:
    app.mount(
        "/assets",
        ImmutableStaticFiles(directory=config.STATIC_DIR / "assets"),
        name="assets",
    )
    INDEX_HTML = config.STATIC_DIR / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        """Serve root-level public files (favicon, robots.txt) if they
        exist; extensioned-but-missing paths → 404; extensionless paths
        → SPA index (client-side router takes over)."""
        last = path.rsplit("/", 1)[-1] if path else ""
        has_ext = "." in last
        target = config.STATIC_DIR / path
        # Path-traversal guard: resolved target must stay inside STATIC_DIR.
        try:
            target.resolve().relative_to(config.STATIC_DIR.resolve())
        except ValueError:
            raise HTTPException(403)
        if has_ext:
            if target.is_file():
                return revalidating_file_response(target)
            raise HTTPException(404)
        return revalidating_file_response(INDEX_HTML)
