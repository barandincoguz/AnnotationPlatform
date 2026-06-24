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
| `SESSION_MAX_AGE_SECONDS` | no | no | `2592000` | Absolute browser and server session lifetime; must be positive |
| `SESSION_COOKIE_SAMESITE` | no | no | `lax` | `lax`, `strict`, or `none`; use `none` only for required cross-site iframe embedding |
| `BOOTSTRAP_ADMIN_USERNAME` | no | recommended | `root` | First-admin seed; only acts when users table has no admin |
| `BOOTSTRAP_ADMIN_PASSWORD` | no | recommended | `<≥12 chars>` | Paired with the above; ≥12 chars in production |
| `BACKUP_REPO_URL` | no | recommended | `https://github.com/me/anotasyon-backup.git` | Empty → stderr WARN at boot, no backup |
| `GITHUB_PAT` | no | required if above set | `<fine-grained PAT, contents:write>` | Used for GitHub auth at runtime; not stored in `backup/.git/config` |
| `DATA_DIR` | no | no | `/data` | Container default; override only for non-Docker dev |
| `DISABLE_SPA_MOUNT` | no | no | `1` | Set in tests only; do not set in prod |
| `TRUST_FORWARDED_FOR` | no | no | `1` | Enable only behind a trusted reverse proxy |
| `TRUSTED_PROXY_CIDRS` | no | required with trust | `172.16.0.0/12` | Immediate proxy networks; never use `0.0.0.0/0` or `::/0` |
| `NEON_MIRROR_URL` | no | **yes for cross-team** | `postgresql://baran_writer:...@ep-xxx.neon.tech/neondb?sslmode=require` | **If unset, the Neon dispatcher boots in degraded mode and the partner team sees stale rows for an unbounded window.** Full setup: `docs/neon-mirror.md`. |
| `NEON_MIRROR_BATCH_SIZE` | no | no | `100` | Rows per dispatcher tick. Default `100`. |
| `NEON_MIRROR_MAX_RETRIES` | no | no | `5` | Per-row retry budget before dead-letter. Default `5`. |
| `NEON_MIRROR_EMPTY_SLEEP` | no | no | `5` | Dispatcher idle wait (seconds) when the outbox is empty. Default `5.0`. |

For existing Neon mirror databases, apply these migrations once, in order,
after the application deploy:

1. `migrations/postgres/002-remove-user-sessions.sql` removes legacy mirrored
   bearer tokens from deployments created before SQLite migration `v0009`.
2. `migrations/postgres/003-nullable-training-finished-at.sql` permits active
   training attempts to mirror with `finished_at = NULL`.

See `docs/neon-mirror.md` for connection and execution details.

Session tokens are stored only as SHA-256 digests. SQLite migration `v0012`
converts existing rows in place without invalidating the raw token already
held by the browser. Sessions are rejected server-side after
`SESSION_MAX_AGE_SECONDS`, so copying an old cookie cannot bypass browser
expiry.

## 3a. Cross-team coordination (Phase 6 ordering contract)

This deploy participates in a cross-team annotation contract with the
partner team's deploy (Zeynep). Both teams annotate the same Maliye
Bakanlığı özelge corpus from a shared source DB; the contract is that
every annotator on both sides processes documents in the **same**
`document_id` DESC order. The platform enforces this in two ways:

1. **Backend default sort.** `/api/feed` defaults to
   `sort=document_id&order=desc` on every tab (`new`, `review`,
   `verified`) — see `backend/shuffle/service.py::DEFAULT_SORT_FOR`.
2. **Frontend default sort.** The annotate store seeds the same
   default per tab — see `frontend/src/stores/annotateStore.ts::DEFAULT_SORT`.

**Operator implications:**

- **Do not advertise the dev SortMenu to users.** The trigger button
  is gated behind `localStorage.a11n.dev_sort=1` and is intended for
  the platform developer only. Setting it on an annotator's browser
  silently breaks the cross-team contract — that annotator will work
  documents in a different order than the partner team and downstream
  joins on `document_id` will drift.
- **The Neon mirror is one-way.** This deploy pushes rows under the
  `baran_*` prefix into the partner Neon instance. The partner team
  reads from their own Neon DB; this deploy never reads back. A long
  mirror outage (e.g. `NEON_MIRROR_URL` unset, partner Neon
  unreachable) does not block local annotation but makes the partner
  view stale. Monitor `/api/admin/mirror/health` and act on the
  thresholds documented in `runbooks/restore-drill.md`.
- **Partner-side ordering.** The partner team's UI reads
  `zeynepDB.public.documents ORDER BY evrak_id DESC`; `evrak_id` on
  their side equals `document_id` here. If you change the canonical
  sort key locally, coordinate with the partner team before deploy.

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

## 5. Admin surfaces (Phase 5)

After login as an admin, the following pages are available under `/admin/`.
The sidebar nav lists them in the "Operations" group:

| Path | Purpose |
|------|---------|
| `/admin/mirror` | Neon mirror health: outbox queue depth, dead-letter count, dispatcher state, last-delivered-at, oldest-undelivered. Auto-refresh every 10 s. When dead-letter count > 0, a confirm-gated button re-queues those rows for the dispatcher's next drain. |
| `/admin/backup` | Manual backup trigger + last 20 backup-related `system_events`. The "Şimdi yedek al" button calls `POST /api/admin/backup/run-now` and pushes the snapshot to the configured `BACKUP_REPO_URL` if set. |
| `/admin/retention` | Retention preview (per-table rows to purge + active policy) + confirm-modal-gated run-now. |
| `/admin/users`, `/admin/audit`, `/admin/settings`, `/admin/events`, `/admin/locks`, `/admin/training/*` | (existing — see prior sections) |

### Backup restore via HTTP

`POST /api/admin/backup/restore` accepts an uploaded snapshot JSON
(multipart form, field name `snapshot`) and replaces DB state. Refuses
with 409 `db_busy` when WAL has uncommitted frames from another writer.
Writes an `admin_audit_log` row on success.

For a guided restore procedure on a copy of production data, see
[runbooks/restore-drill.md](../runbooks/restore-drill.md) — copy-only
drill with two STOP gates.

## 6. Backup setup (GitHub remote)

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

You should see `backup_success` (info severity) within a few minutes.

## 7. Restore drill

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

### Recovery: if you can't login after restore

The restored DB carries whatever password hash existed at snapshot time.
If that hash predates a since-rotated password, you'll be locked out
with an apparently correct password. Recovery:

```bash
docker compose run --rm app python -m backend.cli reset-password <username> <new-password>
```

This rehashes the password, deletes all of that user's active session
rows (forcing fresh login), and writes a `reset_password_cli` audit
entry.

## 8. Reverse proxy

The app listens on port 8000 in the container and Compose binds it to
`127.0.0.1:8000` on the host. This prevents clients from bypassing the
HTTPS proxy. Do not change the host binding to `0.0.0.0` in production.
Terminate HTTPS at a proxy. Two minimal examples:

The application itself gzips normal HTTP responses but deliberately excludes
`/api/events` so SSE notifications are never buffered. Vite's content-hashed
`/assets/*` files are served with a one-year immutable cache; `index.html`,
`favicon.svg`, and `robots.txt` use `Cache-Control: no-cache` so a deployment
cannot strand clients on stale chunk names. Production builds do not publish
JavaScript source maps. Every `/api/*` response is forced to
`Cache-Control: no-store`; browser responses also carry clickjacking,
MIME-sniffing, referrer, permissions, opener, and HTML CSP protections.

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
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

### Security Note: IP Forwarding and `TRUST_FORWARDED_FOR`

Client IPs feed the login/register rate limiters and session audit hashes.
Enable forwarding only when the immediate peer is trusted:

```dotenv
TRUST_FORWARDED_FOR=1
TRUSTED_PROXY_CIDRS=172.16.0.0/12
```

Use the narrowest CIDR that contains the Docker bridge address observed by
the app. Production startup rejects trust without a CIDR, malformed CIDRs,
and whole-address-family values such as `0.0.0.0/0`.

The backend validates every forwarded value as an IP and walks the chain
from right to left to select the nearest untrusted address. The proxy must
still overwrite or correctly append `X-Forwarded-For`; the nginx example
above overwrites it. Caddy's default `reverse_proxy` behavior sets the
forwarding headers and ignores spoofed incoming values unless trusted
proxy handling is explicitly configured.

## 9. Logs and observability

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

## 10. Upgrade procedure

```bash
cd anotasyon
git pull
docker compose down
docker compose --env-file .env.production up -d --build
docker compose logs -f app          # confirm migrations applied
```

The container runs `python -m backend.cli migrate` on every start
(idempotent — `schema_migrations` table tracks applied versions).

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Container restart-loops with `FATAL: production mode enforcement failed` | `ENVIRONMENT=production` but `SESSION_SECRET` is default or short | Generate a real secret, redeploy |
| `RuntimeError: ENVIRONMENT must be one of: [...]` | Typo (e.g. `prod`, `PROD`) | Use exactly `production` (lowercase) |
| `WARNING: no backup configured` in logs | `BACKUP_REPO_URL` empty | Either set it or accept no backup (acknowledged) |
| `Bootstrap admin '<x>' created` never appears | Either env vars missing, or an active admin already exists | Check `users` table; reset env if intentional first seed |
| Container restart-loops with `RuntimeError: BOOTSTRAP_ADMIN_USERNAME=... conflicts with existing non-admin user` | A user with that username already exists (not as admin) | Either pick a different `BOOTSTRAP_ADMIN_USERNAME` and redeploy, or run `docker compose run --rm app python -m backend.cli promote-admin <existing-username>` to promote the existing user instead of seeding a new one |
| SSE updates stuck / not pushing | Reverse proxy is buffering | Set `proxy_buffering off` (nginx) or `flush_interval -1` (Caddy) for `/api/events` |
| Restore says `git clone timed out` | Network / PAT scope issue | Verify `GITHUB_PAT` has `contents:write` on the backup repo |

For deeper diagnosis, the `admin_audit_log` and `system_events` tables
are the authoritative source of what the server did and when.

## Appendix A — Hetzner Cloud CPX11

A typical low-cost VPS deploy. CPX11 ships ~€4.5/mo with 2 vCPU + 2 GB
RAM + 40 GB NVMe — well above this workload's requirements.

1. **Provision.** Hetzner Cloud Console → new project → new server →
   CPX11 → Ubuntu 24.04. Reserve a Floating IP if you want a stable
   address across reboots. SSH-key auth recommended.

2. **Install Docker.**
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER
   newgrp docker
   ```

3. **Install Caddy for TLS termination.**
   ```bash
   sudo apt update && sudo apt install -y caddy
   ```

   Caddyfile (`/etc/caddy/Caddyfile`):
   ```
   anotasyon.example.com {
     reverse_proxy 127.0.0.1:8000
     encode gzip
   }
   ```

4. **Clone + configure.**
   ```bash
   git clone <repo-url> anotasyon && cd anotasyon
   cp .env.example .env.production
   $EDITOR .env.production
   # Set SESSION_SECRET (openssl rand -hex 32),
   # BOOTSTRAP_ADMIN_USERNAME + BOOTSTRAP_ADMIN_PASSWORD,
   # ALLOWED_ORIGINS=https://anotasyon.example.com,
   # ENVIRONMENT=production
   ```

5. **Boot.**
   ```bash
   docker compose --env-file .env.production up -d
   docker compose logs -f app   # wait for "Bootstrap admin '<x>' created"
   sudo systemctl reload caddy
   ```

   Caddy provisions a Let's Encrypt cert automatically within a minute.

6. **First login** at `https://anotasyon.example.com/login` with the
   bootstrap admin credentials, then immediately:
   - Rotate the bootstrap password via `/admin/users`.
   - Remove `BOOTSTRAP_ADMIN_*` from `.env.production` (idempotent —
     a second boot is a no-op — but stale secrets in env files are
     bad practice; see [SEC-3 in audit/SEC.md](../audit/SEC.md) for
     why).

### Sizing notes

- 17,923 documents + ~62k rows mirror well under CPX11 disk budget.
- SQLite WAL + `workers=1` means horizontal scaling on Hetzner Cloud
  is **not** a path forward — the design is single-instance by
  contract.

## Appendix B — Oracle Cloud Always Free (A1.Flex / ARM)

Oracle's Always Free tier provides 4 OCPU + 24 GB RAM on the ARM
Ampere A1.Flex shape — generous for this workload, free forever.
Caveats: ARM image required, capacity availability is regional.

1. **Provision.** Oracle Cloud Console → Compute → Instances →
   Create. Shape = `VM.Standard.A1.Flex`. OCPUs 1-4 (free up to 4),
   memory 6-24 GB (free up to 24). Image = Canonical Ubuntu 24.04 ARM.
   If "Out of capacity" — retry in another region; capacity rotates.

2. **Open ports.** Oracle's VCN Security List defaults to closed.
   Add ingress rules for:
   - 80/tcp (Let's Encrypt HTTP-01 challenge)
   - 443/tcp (HTTPS)

   `ufw` on the VM also needs to allow these.

3. **Install Docker (ARM build of step 2 from Appendix A — same
   command works).**

4. **Build the image natively on the VM.** Docker on ARM will produce
   an ARM64 image automatically. Alternative: push a multi-arch
   image from a GitHub Actions build matrix that publishes
   `linux/amd64,linux/arm64`.

   ```bash
   git clone <repo-url> anotasyon && cd anotasyon
   docker build -t anotasyon-platform:local .
   # ... rest same as Appendix A steps 4-6.
   ```

5. **Caveat — A1.Flex capacity.** Oracle de-provisions A1.Flex VMs
   that go idle for extended periods. Set up a low-frequency
   uptime-monitor (any cron-pinger against `/api/health`) to keep
   the VM warm; otherwise expect to re-provision occasionally.
