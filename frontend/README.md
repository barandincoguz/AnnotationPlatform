# Anotasyon Platformu — Frontend

React 18 + Vite 5 + TypeScript strict + Tailwind + shadcn/ui.

## İlk kurulum

```bash
cd frontend
nvm use            # .nvmrc → Node 22
npm ci             # deterministic via package-lock
cp .env.example .env.local  # if override needed
```

## Dev workflow — 2 terminal

```bash
# Terminal 1: backend (repo root)
DATA_DIR=$(pwd)/data .venv/bin/uvicorn backend.main:app --reload --port 8000

# Terminal 2: frontend
npm run dev    # Vite 5173 → /api proxy → uvicorn 8000
```

`DATA_DIR` defaults to `data/` under the repo root when unset. Override only
when you need an isolated dev database.

## Type regeneration

```bash
# Backend açıkken:
npm run gen:types

# Backend kapalıyken (frontend/ içinden tek script):
npm run gen:openapi          # cd .. && python -m backend.cli openapi-dump
npm run gen:types:from-file

# Drift kontrolü (lokal CI öncesi sanity):
npm run gen:types:check
```

## shadcn/ui component ekleme

```bash
npx shadcn@latest add button
npx shadcn@latest add dialog
```

Generated files: `src/components/ui/<name>.tsx`. Commit alongside usage.

## Production build

```bash
npm run build       # → ../backend/static/
# repo root:
.venv/bin/uvicorn backend.main:app --port 8000
# SPA + API tek port: http://localhost:8000
```

## Quality gates

```bash
npm run typecheck      # tsc --noEmit
npm run lint           # eslint, error level fails
npm run format:check
npm test               # vitest watch
npm run test:run       # vitest single-run (596 tests)
npm run test:coverage  # ≥80% statements/branches/lines/functions
npm run e2e            # Playwright (14 tests in e2e/)
```

Live counts drift; run `npm run test:run` for truth.

## Dependency policy

`~` (tilde) pinned: `openapi-fetch`, `class-variance-authority`, `lucide-react` — these
are 0.x packages where minor versions may include breaking changes. Upgrade
deliberately with smoke test, then update the pin.

## Path alias

`@/` → `src/`. Configured in three places: `tsconfig.json` (paths),
`vite.config.ts` (resolve.alias), `tsconfig.eslint.json` (lint type-aware).
Vitest inherits from Vite automatically.

## Annotate workflow

### URL structure

- `/` — Empty editor (DocList visible left, "Listeden bir doküman seçin" right)
- `/docs/:docId` — 3-col editor (DocList | DocViewer | ReferencePanel)
- `/feedback` — User complaint/suggestion form
- `/admin/feedback` — Admin feedback list (type filter)

### Tab state

The current tab (`new` | `review` | `verified`) is persisted to `sessionStorage`
under `annotate.currentTab`. URL stays clean (no `?tab=` query param).

### Lock lifecycle

- Eager: navigating to `/docs/:docId` triggers `POST /api/locks/{id}/acquire`
- Heartbeat: every 30s while the route is mounted (server TTL is 5 minutes,
  swept every 60s — see `backend/locks/service.py::DEFAULT_LOCK_EXPIRES_SECONDS`)
- Release: best-effort `fetch(..., { keepalive: true })` on cleanup, plus
  explicit release after save. The 5-minute server TTL is the correctness
  backstop if the keepalive POST never lands.
- 409 on acquire → `LockConflictModal`. Different wording when the conflicting
  user is the current user (same-user-cross-tab case).

### Draft auto-save

- Debounced 2s after the last reference edit
- Full body replacement (`PUT /api/drafts/{id}`)
- Drafts loaded silently on doc open (draft > annotation > empty)
- Cleared on successful save commit

### Save flow

1. Block all draft writes (`isSavingRef`)
2. `POST /api/annotations`
3. `DELETE /api/drafts/{id}` (best-effort)
4. `POST /api/locks/{id}/release` (best-effort)
5. Refetch feed
6. Pick next doc in current tab → `navigate('/docs/:next', { replace: true })`
7. If no next doc → toast + `navigate('/', { replace: true })`

### SSE events

Feed invalidation (`src/hooks/sse/feedHandlers.ts`):

- `lock_acquired` / `lock_released`
- `annotation_saved` / `annotation_completed`

Notifications (`src/hooks/sse/notificationHandlers.ts`):

- `badge_unlocked` — celebration toast + profile/notifications refresh
- `speed_warning` / `char_limit_warning` — behavioral detector toasts

### Dev-only sort menu

`SortMenu` is hidden unless `localStorage.a11n.dev_sort=1`. Default feed sort
is `document_id DESC` on all tabs (Phase 6 cross-team contract). See root
`README.md` and `docs/deployment.md` §3a.
