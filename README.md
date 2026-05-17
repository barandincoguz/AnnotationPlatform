# Anotasyon Platform

FastAPI-based annotation platform for Turkish tax-ruling (özelge) legal-reference extraction. Bursiyer (scholarship) annotators extract law citations from documents; tax practitioners search the resulting index.

- **Backend:** Python 3.11+, FastAPI, SQLite (WAL + FK + busy timeout), Pydantic v2
- **Frontend:** React 18 + Vite + TypeScript strict + TanStack Query + Zustand + Tailwind + shadcn/ui
- **Deployment:** Single-container Docker, single-worker uvicorn (SQLite write lock), named volume `/data`

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest                   # backend tests
cd frontend && npm install && npm test       # frontend tests
```

The dev DB lives under `data/db/annotations.db` (override via `DATA_DIR`).

Default `ENVIRONMENT=development` keeps secret enforcement off so dev defaults work. Tests run with `ENVIRONMENT=test` (set in `tests/conftest.py`).

## Production deployment

See **[docs/deployment.md](docs/deployment.md)** for the full runbook: prerequisites, quickstart, env reference, first-admin walkthrough, backup/restore drills, reverse-proxy (Caddy + nginx) configs, upgrade procedure, and troubleshooting table.

### Quick reference

```bash
cp .env.example .env.production
# edit .env.production: set ENVIRONMENT=production, generate strong SESSION_SECRET,
#                       set BOOTSTRAP_ADMIN_USERNAME + BOOTSTRAP_ADMIN_PASSWORD
docker compose --env-file .env.production up -d
```

The lifespan startup:
1. Validates `ENVIRONMENT` is one of `development`, `test`, `production`.
2. In production: hard-fails on default `SESSION_SECRET`, `SESSION_SECRET` < 32 chars, or `BOOTSTRAP_ADMIN_PASSWORD` < 12 chars.
3. Applies pending migrations idempotently.
4. Seeds the first admin user from `BOOTSTRAP_ADMIN_USERNAME`/`BOOTSTRAP_ADMIN_PASSWORD` when the users table has no active admin.

### Environment variables

| Var | Required | Prod-required | Notes |
|---|---|---|---|
| `ENVIRONMENT` | no | **yes** | One of `development`, `test`, `production` |
| `SESSION_SECRET` | yes | **yes** | ≥32 chars in production; generate with `openssl rand -hex 32` |
| `SESSION_COOKIE_NAME` | no | no | Defaults to `anotasyon_session` |
| `BOOTSTRAP_ADMIN_USERNAME` | no | recommended | First-admin seed username |
| `BOOTSTRAP_ADMIN_PASSWORD` | no | recommended | First-admin password (≥12 chars in production) |
| `BACKUP_REPO_URL` | no | recommended | GitHub repo for off-host backup snapshots |
| `GITHUB_PAT` | no | required if backup set | Fine-grained PAT, `contents:write` only |
| `DATA_DIR` | no | no | `/data` in the container |

See `.env.example` for the full annotated template.

### Healthcheck

- Liveness: `GET /api/health` (process-up). Docker `HEALTHCHECK` uses only this — DB issues are surfaced separately to avoid restart loops on transient SQLite locks.
- Readiness / diagnostic: `GET /api/health/db` (migration + table counts; HTTP 500 if DB unreachable).

### Container user

Runs as `appuser` (UID 1000, GID 1000). When binding a host directory to `/data`, chown it once on the host:

```bash
sudo chown -R 1000:1000 /path/to/host/data
```

### Smoke test

```bash
.venv/bin/python -m pytest tests/test_docker_smoke.py -v
```

Skips automatically when `docker` is not on PATH.

## Test status

Counts drift constantly; run these to read the live numbers instead:

```bash
.venv/bin/python -m pytest tests -q | tail -3       # backend
cd frontend && npm run test:run -- --reporter=basic | tail -3   # frontend
```

The 3 Docker-smoke cases skip automatically when the Docker daemon is
unreachable (CLI on PATH alone is not enough — see
`tests/test_docker_smoke.py::_docker_daemon_reachable`).

## Release tags

Latest: **`paket-16f-production-bootstrap`** (production bootstrap: ENVIRONMENT enforcement, first-admin seed in lifespan, deployment runbook).

See `git tag` for the full chronology.
