---
title: Anotasyon Platform
emoji: 📝
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

<div align="center">

# Annotation Platform

**A collaborative web app for annotating Turkish tax-authority rulings (*özelge*)
with structured legal references — built for scholarship annotators, queried by
tax practitioners.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![TanStack Query](https://img.shields.io/badge/TanStack-Query%205-FF4154?logo=react-query&logoColor=white)](https://tanstack.com/query)
[![Tests](https://img.shields.io/badge/tests-946%20backend%20%2F%20511%20frontend-success)](#-tests)

<p>
  <img src="docs/screenshots/hero.png" alt="Annotation workspace screenshot" width="850"/>
  <br/>
  <sub><i>Drop screenshots into <code>docs/screenshots/</code> — placeholders are referenced throughout this README.</i></sub>
</p>

</div>

---

## What is this?

Tax-ruling annotation is the painful inverse of legal drafting: a human reads
an opinion letter, identifies every statute / regulation / decree it relies on,
and pins each citation to a structured record (`kanun_no`, `madde`, `fıkra`,
`bent`, `source_text`). At scale — tens of thousands of rulings — this only
works as a coordinated team activity with locking, attribution, and a verifiable
change history.

This platform does that:

- **Multi-user concurrent editing** with leased document locks + lease renewal (5-minute default, configurable via `lock.expires_seconds` site setting).
- **Draft autosave** at 2 s debounce so a closed tab never loses work.
- **Tab-based feed** (`Yeni` / `Devam Eden` / `Tamamlanan`) with deterministic
  per-user daily shuffle so the same operator gets the same order all day —
  and a different one tomorrow.
- **Append-only version chain** (`create` → `edit` → `complete_mark` →
  `uncomplete` → …) with diff-from-previous on every save.
- **Gamification** (XP, streak, badges, post-hoc review_kept) to keep
  scholarship annotators motivated without warping incentives.
- **Admin panel** for user provisioning, training quiz administration, audit
  log, system events, retention controls, GitHub-backed off-host backups.

---

## Features at a glance

| Area | Highlights |
|------|------------|
| **Annotation** | Reference cards with `kanun_no` + `kanun_ad` validation, source-text quoting, set-semantic diff |
| **Concurrency** | 300 s leased locks (configurable), heartbeat every 30 s, BEGIN IMMEDIATE for writers |
| **Drafts** | Per-user, per-doc, autosaved with debounce + AbortController + rev counter |
| **Feed** | 4-state canonical `workflow_state` (`new`/`draft`/`review`/`verified`), per-user mutual exclusion |
| **Training** | Mandatory quiz → 3-doc training → pass / fail flow before live annotation |
| **Auth** | Cookie session, bcrypt(rounds=12) password hashing, Origin/Referer CSRF middleware in prod |
| **Rate limiting** | In-memory sliding-window per-IP, namespaced (login / register / save) |
| **Backups** | SQLite snapshot → GitHub repo via fine-grained PAT; user_sessions excluded |
| **Observability** | `activity_events`, `system_events`, `admin_audit_log` tables; SSE broker for live updates |

---

## Architecture

```mermaid
flowchart LR
    subgraph Client["React 18 + TS strict"]
        UI["Annotation UI<br/>(DocViewer + ReferencePanel)"]
        QC["TanStack Query<br/>(cache + invalidation)"]
        SSE["EventSource<br/>(feed + lock + notif handlers)"]
    end

    subgraph Server["FastAPI + uvicorn (1 worker)"]
        Routes["HTTP routes<br/>/api/*"]
        Services["Service layer<br/>(annotations, locks, drafts, shuffle)"]
        Broker["SSE broker<br/>(per-user queues)"]
    end

    subgraph Storage["SQLite — WAL + FK + busy-timeout"]
        Annots[("annotations<br/>+ annotation_versions<br/>+ annotation_references")]
        Drafts[("drafts<br/>(per user, per doc)")]
        Locks[("document_locks<br/>(lease + heartbeat)")]
        Audit[("activity_events<br/>+ admin_audit_log")]
        Outbox[("_outbox<br/>(mirror queue, 69 triggers)")]
    end

    subgraph Mirror["Neon mirror (async, one-way)"]
        Dispatcher["asyncio dispatcher<br/>(lifespan task)"]
        Neon[("Neon Postgres<br/>baran_* tables")]
    end

    UI --> QC --> Routes
    UI <-.live updates.- SSE
    SSE <--- Broker
    Routes --> Services --> Annots
    Services --> Drafts
    Services --> Locks
    Services --> Audit
    Services -.publish.-> Broker
    Annots -.trigger.-> Outbox
    Drafts -.trigger.-> Outbox
    Locks -.trigger.-> Outbox
    Audit -.trigger.-> Outbox
    Outbox --> Dispatcher --> Neon
```

**Why these choices?** SQLite + a single uvicorn worker eliminates an entire
class of distributed-systems failures the project doesn't need — and `BEGIN
IMMEDIATE` plus document-level locks keep the multi-user concurrency story
honest. The full design notes live in [`docs/superpowers/`](docs/superpowers/).

---

## Annotation workflow — canonical state model

Every document the platform knows about lives in exactly one of four states
per user, computed server-side and returned as `FeedItem.workflow_state`:

| State | Meaning | Tab | Icon |
|-------|---------|-----|------|
| `new` | No annotation row, no non-empty caller draft | Yeni | ○ |
| `draft` | Caller has ≥1 reference in their draft, no shared annotation yet | Devam Eden | ◉ |
| `review` | Shared annotation exists, not yet completed | Devam Eden | ◌ |
| `verified` | Annotation completed (`is_completed = 1`) | Tamamlanan | ✓ |

State transitions are atomic:

- **Save:** `new` → `review` (creates annotation row + version + clears draft)
- **Complete with refs (atomic):** `new`/`draft`/`review` → `verified` in **one** `BEGIN IMMEDIATE`
- **Uncomplete:** `verified` → `review` (clears `is_completed`, preserves refs)
- **Skip:** clears caller's draft + releases lock (doc returns to its server-side state)

Pre-Phase-3 the frontend ran `save → complete → delete_draft` as a 3-call
chain; a single `BEGIN IMMEDIATE` on the backend now collapses all three into
one round-trip with no intermediate-failure surface.

---

## Tech stack

<table>
<tr>
<td valign="top" width="50%">

### Backend
- **Runtime:** Python 3.11+, FastAPI, uvicorn (1 worker)
- **DB:** SQLite (`journal_mode=WAL`, foreign keys, busy_timeout)
- **Validation:** Pydantic v2 + model_validator
- **Auth:** Cookie session, bcrypt(rounds=12), Origin/Referer middleware
- **Rate limiting:** in-memory sliding window
- **Migrations:** Pure-SQL idempotent files in `backend/migrations/`
- **SSE:** Per-user `asyncio.Queue` broker

</td>
<td valign="top" width="50%">

### Frontend
- **Framework:** React 18 + Vite 5 + TypeScript strict
- **Routing:** React Router v6
- **Server state:** TanStack Query 5 (useInfiniteQuery + invalidate)
- **Client state:** Zustand
- **Forms:** react-hook-form + zod resolver
- **UI:** Tailwind CSS + shadcn/ui (Radix primitives)
- **Markdown:** react-markdown + rehype-sanitize (no `rehype-raw`)

</td>
</tr>
</table>

---

## Screenshots

> Drop your screenshots into `docs/screenshots/` and they will render here.

<table>
<tr>
<td align="center">
  <img src="docs/screenshots/feed.png" alt="Document feed with 3-tab classification" width="100%"/>
  <br/><sub><b>Feed</b> — workflow_state-driven status icons</sub>
</td>
<td align="center">
  <img src="docs/screenshots/annotate.png" alt="Annotation workspace" width="100%"/>
  <br/><sub><b>Annotate</b> — split viewer + reference cards</sub>
</td>
</tr>
<tr>
<td align="center">
  <img src="docs/screenshots/training.png" alt="Training quiz" width="100%"/>
  <br/><sub><b>Training</b> — mandatory quiz + 3-doc gate</sub>
</td>
<td align="center">
  <img src="docs/screenshots/admin.png" alt="Admin panel" width="100%"/>
  <br/><sub><b>Admin</b> — users / audit / settings</sub>
</td>
</tr>
</table>

---

## Quick start

### Development

```bash
# 1. Backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn backend.main:app --reload

# 2. Frontend (separate shell)
cd frontend
npm install
npm run dev
```

The dev backend listens on `http://127.0.0.1:8000`, the frontend on
`http://localhost:5173`. The dev DB lives at `data/db/annotations.db`
(override via `DATA_DIR`).

`ENVIRONMENT=development` keeps secret enforcement off so the defaults work.

### Production (Docker)

```bash
cp .env.example .env.production
# edit .env.production: set ENVIRONMENT=production,
# generate a strong SESSION_SECRET (openssl rand -hex 32),
# set BOOTSTRAP_ADMIN_USERNAME + BOOTSTRAP_ADMIN_PASSWORD (≥12 chars)
docker compose --env-file .env.production up -d
```

The lifespan startup:

1. Validates `ENVIRONMENT ∈ {development, test, production}`.
2. In production: hard-fails on unsafe secrets, invalid/non-HTTPS origins,
   and unsafe forwarded-IP trust configuration.
3. Applies pending migrations idempotently.
4. Seeds the first admin user when the users table has no active admin.

The full production runbook (prerequisites, env reference, first-admin
walkthrough, backup/restore drills, reverse-proxy configs, upgrade, troubleshooting)
lives in **[docs/deployment.md](docs/deployment.md)**.

---

## Environment variables

| Var | Required | Prod-required | Notes |
|-----|----------|---------------|-------|
| `ENVIRONMENT` | no | **yes** | One of `development`, `test`, `production` |
| `SESSION_SECRET` | yes | **yes** | ≥32 chars in production; `openssl rand -hex 32` |
| `SESSION_COOKIE_NAME` | no | no | Defaults to `anotasyon_session` |
| `SESSION_MAX_AGE_SECONDS` | no | no | Browser and server session lifetime; default 30 days |
| `SESSION_COOKIE_SAMESITE` | no | no | Defaults to `lax`; `none` only for cross-site embedding |
| `BOOTSTRAP_ADMIN_USERNAME` | no | recommended | First-admin seed username |
| `BOOTSTRAP_ADMIN_PASSWORD` | no | recommended | First-admin password (≥12 chars in production) |
| `BACKUP_REPO_URL` | no | recommended | GitHub repo for off-host backup snapshots; default cadence is 24h |
| `GITHUB_PAT` | no | required if backup set | Fine-grained PAT, `contents:write` only |
| `DATA_DIR` | no | no | `/data` in the container |
| `ALLOWED_ORIGINS` | no | **yes** | Comma-separated origins for CSRF middleware |
| `TRUST_FORWARDED_FOR` | no | no | Enable only behind a trusted reverse proxy |
| `TRUSTED_PROXY_CIDRS` | no | with forwarded trust | Immediate trusted proxy networks |

See `.env.example` for the annotated template.

---

## Tests

Backend uses pytest with a per-test SQLite fixture; frontend uses Vitest with
MSW-mocked endpoints and Playwright for e2e smoke flows.

```bash
.venv/bin/python -m pytest tests -q                              # backend
cd frontend && npm run test:run -- --reporter=basic              # frontend unit
cd frontend && npm run e2e                                       # Playwright e2e
```

Current counts: **946 backend** (3 Docker-smoke skips when daemon is down) +
**511 frontend** + **9 e2e**.

Numbers drift; run the commands above for live truth.

### Healthcheck

- **Liveness:** `GET /api/health` — process-up. Docker `HEALTHCHECK` uses only
  this, so transient SQLite locks don't trigger restart loops.
- **Readiness:** `GET /api/health/db` — migration state + table counts.

---

## Project structure

```
deneme/
├── backend/
│   ├── annotations/          # save / complete / draft / version chain
│   ├── locks/                # 300 s leased document locks + heartbeat
│   ├── shuffle/              # 3-tab feed + per-user daily shuffle
│   ├── documents/            # ingest + metadata + storage
│   ├── training/             # quiz + 3-doc training flow
│   ├── gamification/         # XP, streaks, badges
│   ├── behavioral/           # post-save detectors (speed / char warnings)
│   ├── admin/                # users / audit / settings / system events
│   ├── notifications/        # in-app notification persistence
│   ├── backup/               # SQLite snapshot → GitHub
│   ├── retention/            # row-level data lifecycle
│   ├── exports/              # CSV / JSONL annotation exports
│   ├── docs_help/            # in-app help content
│   ├── sse/                  # per-user event broker
│   ├── shared/               # db, audit, csrf, rate_limit, validators
│   ├── migrations/           # pure-SQL idempotent files
│   ├── users/                # auth + session deps
│   └── main.py               # FastAPI app factory + lifespan
├── frontend/
│   ├── src/
│   │   ├── api/              # openapi-typescript types + queries + client
│   │   ├── components/       # annotation/ shell/ training/ admin/ ui/
│   │   ├── routes/           # AnnotateDoc / Training / Admin / etc.
│   │   ├── hooks/            # useLock / useDraft / useReferencesState / sse
│   │   ├── stores/           # Zustand (auth, annotate, sort)
│   │   └── lib/              # formatters / validators / utils
│   └── tests/e2e/            # Playwright smoke
├── tests/                    # backend pytest (~110 files, 946 tests)
├── data/                     # gitignored; SQLite DB + uploaded JSON
├── docs/
│   ├── deployment.md         # production runbook
│   ├── screenshots/          # README image assets (drop yours here)
│   └── superpowers/          # design specs + ADRs
├── requirements.txt          # backend runtime
├── requirements-dev.txt      # + pytest + ruff + pyright
├── pyproject.toml
└── docker-compose.yml
```

---

## Security notes

- **CSRF:** Origin/Referer middleware, production-only enforcement, allowlist
  via `ALLOWED_ORIGINS`.
- **Sessions:** Cookie + bcrypt(rounds=12); `__Host-` prefix planned post-staging audit.
- **CSV exports:** Leading `=` / `+` / `-` / `@` quoted to defang spreadsheet
  injection.
- **Markdown:** `rehype-sanitize` only — `rehype-raw` is forbidden (XSS bypass).
- **Backups:** `user_sessions` excluded from dump; backup repo uses a
  fine-grained PAT scoped to `contents:write`.

---

## Releases & tags

Latest tag: **`paket-16g-hardening`**. Most recent shipped milestone: **Phase 4 — Neon Postgres dual-write mirror** (commits `1f33a53 .. 9fb4a17`). Earlier production bootstrap
with `ENVIRONMENT` enforcement, first-admin seed in lifespan, and the full
deployment runbook. See `git tag` for the full chronology.

---

<div align="center">

Made with the help of [Claude Code](https://claude.com/claude-code).

</div>
