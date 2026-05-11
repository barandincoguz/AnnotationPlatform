# Anotasyon Platformu — Frontend

React 18 + Vite + TypeScript + Tailwind + shadcn/ui foundation for Paket 16a.

## İlk kurulum

```bash
cd frontend
nvm use            # .nvmrc → Node 22
npm ci             # deterministic via package-lock
cp .env.example .env.local  # if override needed
```

## Dev workflow — 2 terminal

```bash
# Terminal 1: backend
(repo root)$ DATA_DIR=$(pwd)/deneme-dev/data .venv/bin/uvicorn backend.main:app --reload --port 8000

# Terminal 2: frontend
(frontend/)$ npm run dev    # Vite 5173 → /api proxy → uvicorn 8000
```

## Type regeneration

```bash
# Backend açıkken:
(frontend/)$ npm run gen:types

# Backend kapalıyken (frontend/ içinden tek script):
(frontend/)$ npm run gen:openapi          # cd .. && python -m backend.cli openapi-dump
(frontend/)$ npm run gen:types:from-file

# Drift kontrolü (lokal CI öncesi sanity):
(frontend/)$ npm run gen:types:check
```

## shadcn/ui component ekleme

```bash
(frontend/)$ npx shadcn@latest add button
(frontend/)$ npx shadcn@latest add dialog
```

Generated files: `src/components/ui/<name>.tsx`. Commit alongside usage.

## Production build

```bash
(frontend/)$ npm run build       # → ../backend/static/
(repo root)$ .venv/bin/uvicorn backend.main:app --port 8000
# SPA + API tek port: http://localhost:8000
```

## Quality gates

```bash
npm run typecheck   # tsc --noEmit
npm run lint        # eslint, error level fails
npm run format:check
npm test            # vitest watch
npm run test:run    # vitest single-run
npm run test:coverage  # ≥80% statements/branches/lines/functions
```

## Dependency policy

`~` (tilde) pinned: `openapi-fetch`, `class-variance-authority`, `lucide-react` — these
are 0.x packages where minor versions may include breaking changes. Upgrade
deliberately with smoke test, then update the pin.

## Path alias

`@/` → `src/`. Configured in three places: `tsconfig.json` (paths),
`vite.config.ts` (resolve.alias), `tsconfig.eslint.json` (lint type-aware).
Vitest inherits from Vite automatically.
