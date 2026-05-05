"""FastAPI application entry point.

On startup:
  1. Ensure data directories exist
  2. Apply pending migrations
  3. Log startup system event

Domain routers (users, documents, ...) are mounted in their respective packages.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI

from backend import config
from backend.shared.db import connect
from backend.shared import audit
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.users.routes import router as users_router
from backend.docs_help.routes import router as help_router
from backend.documents.routes import router as documents_router
from backend.annotations.routes import router as annotations_router

VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        applied = apply_migrations(conn, discover_migrations())
        audit.log_system_event(
            conn, "startup", "info",
            message=f"app v{VERSION} started; migrations applied: {applied}",
            extra={"version": VERSION, "migrations_applied": applied},
        )
    finally:
        conn.close()
    yield
    # Shutdown — log clean exit
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
