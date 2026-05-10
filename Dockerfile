# ============================================================
# Stage 1 — builder
# Installs Python deps into an isolated target dir we can copy from.
# build-essential is here as a fallback for any wheel that needs to
# compile from source; it never reaches the runtime image.
# ============================================================
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
COPY backend/ ./backend/

# --target=/install collects all packages + console scripts under one
# directory the runtime stage copies in a single layer.
# --no-deps on the editable install is safe: pyproject.toml does NOT
# declare [project.dependencies]; all runtime deps come from requirements.txt.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --target=/install -r requirements.txt && \
    pip install --no-cache-dir --target=/install --no-deps .

# ============================================================
# Stage 2 — runtime
# Lean image, non-root, git for backup_loop's optional GitHub push,
# app code only.
# ============================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/site-packages \
    PATH=/app/site-packages/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

# Non-root user with explicit UID 1000 — predictable for host bind mounts.
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home --shell /bin/bash appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /install /app/site-packages
COPY --chown=appuser:appuser backend/ /app/backend/

RUN mkdir -p /data && chown appuser:appuser /data
VOLUME ["/data"]
ENV DATA_DIR=/data

USER appuser

EXPOSE 8000

# Apply migrations (idempotent via schema_migrations), then exec uvicorn so
# it becomes PID 1 and receives SIGTERM directly. workers=1 is explicit:
# SQLite write contention makes multi-worker counter-productive.
CMD ["sh", "-c", "python -m backend.cli migrate && exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1"]

# Liveness probe: app process up. DB issues surface via /api/health/db
# (manual/readiness use) and via system_events log rows — coupling liveness
# to DB risks transient-lock restart loops.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)" || exit 1
