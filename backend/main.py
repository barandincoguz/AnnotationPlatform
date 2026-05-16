"""FastAPI application entry point.

On startup:
  1. Ensure data directories exist
  2. Apply pending migrations
  3. Log startup system event

Domain routers (users, documents, ...) are mounted in their respective packages.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import config
from backend.shared.db import connect
from backend.shared import audit
from backend.shared.prod_enforce import enforce_production_secrets
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
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
from backend.training.routes import router as training_router, admin_router as training_admin_router
from backend.backup.routes import router as backup_router
from backend.retention.routes import router as retention_router
from backend.exports.routes import router as exports_router
from backend.locks import sweep as locks_sweep
from backend.backup import loop as backup_loop
from backend.retention import loop as retention_loop

VERSION = "0.1.0"

DEV_SESSION_SECRETS = {
    "dev-secret-DO-NOT-USE-IN-PROD",  # backend/config.py default
    "dev-secret-change-me",            # docker-compose.yml default
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.validate_environment()
    enforce_production_secrets()
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        applied = apply_migrations(conn, discover_migrations())
        audit.log_system_event(
            conn, "startup", "info",
            message=f"app v{VERSION} started; migrations applied: {applied}",
            extra={"version": VERSION, "migrations_applied": applied},
        )
        if config.SESSION_SECRET in DEV_SESSION_SECRETS:
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

    conn = connect(config.DB_PATH)
    try:
        audit.log_system_event(conn, "shutdown", "info", message=f"app v{VERSION} shutting down")
    finally:
        conn.close()


app = FastAPI(title="Anotasyon Platform", version=VERSION, lifespan=lifespan)
app.include_router(users_router)
app.include_router(help_router)
app.include_router(documents_router)
app.include_router(annotations_router)
app.include_router(locks_router)
app.include_router(notifications_router)
app.include_router(gamification_router)
app.include_router(shuffle_router)
app.include_router(sse_router)
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
        StaticFiles(directory=config.STATIC_DIR / "assets"),
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
                return FileResponse(target)
            raise HTTPException(404)
        return FileResponse(INDEX_HTML)
