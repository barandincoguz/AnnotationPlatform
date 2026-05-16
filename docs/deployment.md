# Deployment Runbook — Anotasyon Platform

This is the production deployment guide. It assumes you have shell
access to a Linux host with Docker installed. The platform ships as
a single container backed by a named volume; HTTPS termination and
DNS are handled by a reverse proxy (Caddy or nginx) in front of it.

## 1. Prerequisites

| Requirement | Why |
|---|---|
| Docker 24+ with Compose v2 | Container runtime, multi-stage build |
| Linux host (Ubuntu 22.04 LTS+ recommended) | Tested base; macOS works for dev only |
| 5 GB free disk | Image + volume + backups |
| Domain name + DNS | Required for HTTPS reverse proxy |
| GitHub PAT (optional) | For off-host backup to private repo |

## 2. Quick start (5 steps)

```bash
# 1. Clone + cd into the repo
git clone <url> anotasyon && cd anotasyon

# 2. Copy + edit env template
cp .env.example .env.production
$EDITOR .env.production

# 3. Generate a strong SESSION_SECRET
openssl rand -hex 32   # paste output into SESSION_SECRET in .env.production

# 4. In .env.production, set:
#   ENVIRONMENT=production
#   BOOTSTRAP_ADMIN_USERNAME=<your-admin-username>
#   BOOTSTRAP_ADMIN_PASSWORD=<≥12 chars>

# 5. Launch
docker compose --env-file .env.production up -d
docker compose logs -f app   # watch for "Bootstrap admin '<x>' created"
```

After healthcheck passes, login at `https://<your-domain>/login` with
the username + password you set, then rotate the password from the
admin panel.

## 3. Environment reference

| Var | Required | Prod-required | Example | Notes |
|---|---|---|---|---|
| `ENVIRONMENT` | no | **yes** | `production` | Must be one of: `development`, `test`, `production` |
| `SESSION_SECRET` | yes | **yes** | `<64 hex chars>` | Must be ≥32 chars in production; never use default |
| `SESSION_COOKIE_NAME` | no | no | `anotasyon_session` | Override if running multiple instances on same host |
| `BOOTSTRAP_ADMIN_USERNAME` | no | recommended | `root` | First-admin seed; only acts when users table has no admin |
| `BOOTSTRAP_ADMIN_PASSWORD` | no | recommended | `<≥12 chars>` | Paired with the above; ≥12 chars in production |
| `BACKUP_REPO_URL` | no | recommended | `https://github.com/me/anotasyon-backup.git` | Empty → stderr WARN at boot, no backup |
| `GITHUB_PAT` | no | required if above set | `<fine-grained PAT, contents:write>` | Inject into `BACKUP_REPO_URL` clone URL at runtime |
| `DATA_DIR` | no | no | `/data` | Container default; override only for non-Docker dev |
| `DISABLE_SPA_MOUNT` | no | no | `1` | Set in tests only; do not set in prod |

## 4. First admin walkthrough

The lifespan startup looks for two conditions:
1. `users` table has zero rows with `role='admin' AND is_active=1`
2. Both `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` are set

When both hold, a single admin user is inserted with
`has_passed_training=1` and `has_seen_manual=1` (no onboarding gate),
and an entry is written to `admin_audit_log` with
`action_type='bootstrap_admin_seed'`.

After the first successful boot:
- Login at `/login` with those credentials.
- Open `/admin/users` and rotate the password (or create a new admin
  account and disable the bootstrap one).
- Remove `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD`
  from `.env.production` for hygiene. (Idempotency means leaving them
  in does nothing, but stale secrets in env are bad practice.)

## 5. Backup setup (GitHub remote)

Set up off-host snapshots so a host failure does not destroy data.

```bash
# 1. Create an empty private GitHub repo, e.g. "anotasyon-backup"

# 2. Generate a fine-grained PAT scoped to that repo only:
#    Settings → Developer settings → Personal access tokens →
#    Fine-grained tokens → New token
#    Repository access: "Only select repositories" → <your-backup-repo>
#    Permissions: Contents = Read and write
#    Copy the token immediately.

# 3. In .env.production:
BACKUP_REPO_URL=https://github.com/<you>/anotasyon-backup.git
GITHUB_PAT=github_pat_<...>

# 4. Restart
docker compose --env-file .env.production down
docker compose --env-file .env.production up -d
```

Verify the first backup landed (typically within the backup window):
```bash
docker compose exec app sqlite3 /data/db/annotations.db \
  "SELECT event_type, severity, message FROM system_events \
   WHERE event_type LIKE 'backup_%' ORDER BY id DESC LIMIT 5"
```

You should see `backup_pushed` (info severity) within a few minutes.

## 6. Restore drill

⚠️ **STOP THE APP CONTAINER FIRST.** The CLI does not currently detect
a running server's WAL lock; running restore against a hot DB risks
corruption. See `paket-16f.1` (deferred) for the planned safety
interlock.

```bash
# 1. Stop the app (WAL safety)
docker compose stop app

# 2. Run restore (interactive — prompts for confirmation)
docker compose run --rm \
  -e BACKUP_REPO_URL="$BACKUP_REPO_URL" \
  -e GITHUB_PAT="$GITHUB_PAT" \
  app python -m backend.cli restore-from-github

# 3. Verify
docker compose run --rm app sqlite3 /data/db/annotations.db \
  "SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM annotations;"

# 4. Restart
docker compose --env-file .env.production up -d
```

The pre-restore DB is renamed `corrupt-<timestamp>.db.bak` in `/data/db/`
and kept until you delete it manually.

## 7. Reverse proxy

The app listens on port 8000 in the container, mapped to host 8000 by
default. Terminate HTTPS at a proxy. Two minimal examples:

### Caddy

```caddyfile
your-domain.example.com {
  encode zstd gzip
  reverse_proxy localhost:8000 {
    flush_interval -1            # SSE: do not buffer
  }
}
```

### nginx

```nginx
server {
  listen 443 ssl http2;
  server_name your-domain.example.com;

  ssl_certificate     /etc/letsencrypt/live/your-domain.example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/your-domain.example.com/privkey.pem;

  location /api/events {       # SSE endpoint
    proxy_pass http://127.0.0.1:8000;
    proxy_buffering off;
    proxy_read_timeout 24h;
    proxy_set_header Connection '';
  }

  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

## 8. Logs and observability

```bash
docker compose logs -f app          # follow stdout/stderr
docker compose ps                    # container status + health
docker compose exec app sqlite3 /data/db/annotations.db \
  "SELECT * FROM system_events ORDER BY id DESC LIMIT 50"
```

Health endpoints:
- `GET /api/health` — liveness (200 if process up; used by Docker HEALTHCHECK)
- `GET /api/health/db` — readiness (200 if DB query succeeds; manual use)

The `system_events` table is the structured-event log for everything the
backup loop, retention loop, and lifespan do. Filter by severity:
```sql
SELECT * FROM system_events WHERE severity='error' ORDER BY id DESC LIMIT 20;
```

## 9. Upgrade procedure

```bash
cd anotasyon
git pull
docker compose down
docker compose --env-file .env.production up -d --build
docker compose logs -f app          # confirm migrations applied
```

The container runs `python -m backend.cli migrate` on every start
(idempotent — `schema_migrations` table tracks applied versions).

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Container restart-loops with `FATAL: production mode enforcement failed` | `ENVIRONMENT=production` but `SESSION_SECRET` is default or short | Generate a real secret, redeploy |
| `RuntimeError: ENVIRONMENT must be one of: [...]` | Typo (e.g. `prod`, `PROD`) | Use exactly `production` (lowercase) |
| `WARNING: no backup configured` in logs | `BACKUP_REPO_URL` empty | Either set it or accept no backup (acknowledged) |
| `Bootstrap admin '<x>' created` never appears | Either env vars missing, or an active admin already exists | Check `users` table; reset env if intentional first seed |
| Login returns 401 with correct password | Username taken by older non-admin user | Choose a different `BOOTSTRAP_ADMIN_USERNAME`, redeploy |
| SSE updates stuck / not pushing | Reverse proxy is buffering | Set `proxy_buffering off` (nginx) or `flush_interval -1` (Caddy) for `/api/events` |
| Restore says `git clone timed out` | Network / PAT scope issue | Verify `GITHUB_PAT` has `contents:write` on the backup repo |

For deeper diagnosis, the `admin_audit_log` and `system_events` tables
are the authoritative source of what the server did and when.
