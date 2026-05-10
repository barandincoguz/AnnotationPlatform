# Anotasyon Platform

FastAPI-based annotation platform for legal/tax document references.
SQLite (WAL) storage, single-instance deployment.

## Development

Requires Python 3.11+ and a virtual environment in `.venv`.

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The dev DB lives under `data/db/annotations.db` (override via `DATA_DIR`).

## Docker

Build and run:

```bash
docker compose up -d --build
```

The app listens on `http://localhost:8000`. Swagger UI: `http://localhost:8000/docs`.

### Environment variables

Required for production:

- `SESSION_SECRET` — random 32+ characters. The default `dev-secret-change-me`
  is treated as dev-only and emits a WARN row in `system_events` on every
  startup. Set a real secret in production.

Optional:

- `BACKUP_REPO_URL` + `GITHUB_PAT` — enable automatic backup push to a
  GitHub repo (set both, or neither).
- `BOOTSTRAP_ADMIN_USERNAME` — username of an admin to seed on first boot.
- `SESSION_COOKIE_NAME` — defaults to `anotasyon_session`.

### Healthcheck

- Liveness: `GET /api/health` (process-up). Docker `HEALTHCHECK` uses this
  and only this — DB issues are surfaced separately to avoid restart loops
  on transient SQLite locks.
- Readiness / diagnostic: `GET /api/health/db` (returns migration + table
  counts; HTTP 500 if the DB is unreachable).

### Container user

Runs as `appuser` (UID 1000, GID 1000). When binding a host directory to
`/data`, chown it once on the host:

```bash
sudo chown -R 1000:1000 /path/to/host/data
```

### Smoke test

```bash
.venv/bin/python -m pytest tests/test_docker_smoke.py -v
```

Skips automatically when docker is not on PATH.
