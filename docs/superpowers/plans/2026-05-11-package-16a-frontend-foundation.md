# Paket 16a — Frontend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the `frontend/` directory and implement the authentication-routing-testing foundation so paketler 16b-f can plug destination workflows into a working SPA shell.

**Architecture:** Vite-served React app with full TypeScript strict, a 4-state Zustand auth store, blocking `/api/auth/me` hydration before route render, four routing gates (auth, manual, training, admin), an openapi-typescript-generated typed fetch client with DI-based 401 interceptor, and Vitest + MSW v2 test infrastructure. Backend serves the production bundle via an env-gated extension-aware catch-all so tests stay deterministic. Each task is an atomic commit; TDD where unit-testable, manual smoke where structural.

**Tech Stack:** React 18.3, Vite 5.4, TypeScript 5.6 strict, React Router 6.27, TanStack Query 5.59, Zustand 4.5, openapi-typescript 7.4 + openapi-fetch ~0.13, Tailwind 3.4, shadcn/ui (Radix-based), Vitest 2.1, MSW 2.4, Node 22 LTS (engine-strict).

**Spec:** `docs/superpowers/specs/2026-05-11-paket-16a-foundation-design.md` (commit `b2b3615`, 1550 lines). The plan implements the spec verbatim — when in doubt, the spec wins.

**Backend test runner:** `.venv/bin/python -m pytest <path> -v` (system Python lacks fastapi).

**Frontend commands:** Always run from the `frontend/` directory unless noted.

**Git config for every commit:**
```
git -c user.email=maarkval@icloud.com -c user.name=baran commit ...
```
Footer line:
```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

NEVER use `--no-verify` or `--no-gpg-sign`.

---

## File Structure

| File | Role | Status | Task |
|---|---|---|---|
| `backend/config.py` | + `STATIC_DIR` constant | Modify | T1 |
| `backend/main.py` | + extension-aware SPA fallback gated on `DISABLE_SPA_MOUNT` | Modify | T1 |
| `backend/cli.py` | + `openapi-dump` Typer command | Modify | T1 |
| `tests/conftest.py` | Set `DISABLE_SPA_MOUNT=1` at module top | Modify | T1 |
| `tests/test_spa_mount_gate.py` | Verify gate keeps SPA out of TestClient | **Create** | T1 |
| `tests/test_openapi_dump.py` | Verify `openapi-dump` writes valid JSON | **Create** | T1 |
| Root `.gitignore` | + `backend/static/`, `frontend/node_modules/`, `frontend/dist/`, `openapi.json` | Modify | T1 |
| `frontend/package.json` | Deps + scripts | **Create** | T2 |
| `frontend/tsconfig.json` | Strict + path alias | **Create** | T2 |
| `frontend/tsconfig.node.json` | Node-context (vite.config) | **Create** | T2 |
| `frontend/tsconfig.eslint.json` | Type-aware lint scope | **Create** | T2 |
| `frontend/vite.config.ts` | Build + proxy + vitest | **Create** | T2 |
| `frontend/eslint.config.js` | 3-block flat config | **Create** | T2 |
| `frontend/.prettierrc`, `.editorconfig`, `.env.example`, `.gitignore`, `.npmrc`, `.nvmrc` | Standard | **Create** | T2 |
| `frontend/tailwind.config.ts`, `postcss.config.js`, `components.json` | Tailwind + shadcn | **Create** | T2 |
| `frontend/index.html` | Vite entry | **Create** | T2 |
| `frontend/public/favicon.svg`, `public/robots.txt` | Static | **Create** | T2 |
| `frontend/src/styles/globals.css` | Tailwind directives + tokens | **Create** | T2 |
| `frontend/src/lib/utils.ts` | shadcn `cn()` | **Create** | T2 |
| `frontend/src/lib/env.ts` | zod env validation | **Create** | T2 |
| `frontend/src/api/types.ts` | Generated from `/openapi.json` | **Create (generated)** | T3 |
| `frontend/src/api/client.ts` | openapi-fetch + DI setters + interceptor + `unwrap`/`unwrapVoid` + `ApiError` | **Create** | T4 |
| `frontend/src/api/client.test.ts` | TDD: 4 error shapes + 3 interceptor paths | **Create** | T4 |
| `frontend/src/stores/authStore.ts` | Zustand 4-state | **Create** | T5 |
| `frontend/src/stores/authStore.test.ts` | 4 transitions + 3 selectors | **Create** | T5 |
| `frontend/src/test/setup.ts` | MSW lifecycle + global resets | **Create** | T6 |
| `frontend/src/test/msw-server.ts` | `setupServer` | **Create** | T6 |
| `frontend/src/test/msw-handlers.ts` | Default handlers + `makeUser` | **Create** | T6 |
| `frontend/src/test/render.tsx` | `renderWithProviders` + destination stubs | **Create** | T6 |
| `frontend/src/components/ui/{button,input,label,form,card,sonner}.tsx` | shadcn primitives | **Create (generated)** | T7 |
| `frontend/src/components/ErrorBoundary.tsx` + test | Class component fallback | **Create** | T8 |
| `frontend/src/components/shell/LoadingScreen.tsx` + test | Loading + error modes | **Create** | T8 |
| `frontend/src/components/shell/AppShell.tsx` + test | Minimal header + Outlet | **Create** | T8 |
| `frontend/src/components/gates/{RequireAuth,RequireSeenManual,RequirePassedTraining,RequireAdmin}.tsx` + tests | 4 gates | **Create** | T9 |
| `frontend/src/api/queries/auth.ts` + test | `useMe`, `useLoginMutation`, `useRegisterMutation`, `useLogoutMutation` | **Create** | T10 |
| `frontend/src/hooks/useAuth.ts` + test | Wraps store + queries | **Create** | T11 |
| `frontend/src/routes/{Login,Register,NotFound}.tsx` + tests | Real routes | **Create** | T12 |
| `frontend/src/routes/{Annotate,Profile,Help,Training}.tsx`, `routes/admin/AdminLayout.tsx` | STUBs for 16b-e | **Create** | T12 |
| `frontend/src/App.tsx` + test | Hydration + gate composition | **Create** | T13 |
| `frontend/src/main.tsx` | Provider + Router entry | **Create** | T13 |
| `frontend/README.md` | Dev workflow | **Create** | T14 |
| Verification + integration smoke | — | — | T14 |

**Total:** ~62 new files + 4 backend modifications + 1 root `.gitignore` append.

---

## Verification gates that block each task

After every task:
- `.venv/bin/python -m pytest -x -q` → green (backend never regresses)
- For frontend tasks T2+: `cd frontend && npm run typecheck` → no errors
- For frontend tasks T4+: `cd frontend && npm run test:run` → green (only the tests created so far)

After T14:
- `cd frontend && npm run typecheck && npm run lint && npm run format:check && npm run test:coverage && npm run build` → all green, coverage ≥80% on each metric
- `.venv/bin/python -m pytest -x -q` → all backend tests still green
- Manual smoke: `cd frontend && npm run build && (cd .. && .venv/bin/uvicorn backend.main:app --port 8000)` then `curl -s http://127.0.0.1:8000/ | head` shows `<!doctype html>` and `curl -s http://127.0.0.1:8000/api/health` shows `{"status":"ok"...}`.

---

### Task 1: Backend touches — STATIC_DIR, SPA env gate, openapi-dump, conftest

**Why first:** T3 (`gen:openapi`) runs `python -m backend.cli openapi-dump`, which doesn't exist yet. The conftest env-gate must land before any subsequent backend test runs so the import-time SPA registration is suppressed in tests regardless of build state on disk.

**Files:**
- Modify: `backend/config.py` (add STATIC_DIR)
- Modify: `backend/main.py` (add SPA fallback block after `/api/*` routers, gated)
- Modify: `backend/cli.py` (add `openapi_dump` Typer command)
- Modify: `tests/conftest.py` (set `DISABLE_SPA_MOUNT=1` at module top)
- Create: `tests/test_spa_mount_gate.py`
- Create: `tests/test_openapi_dump.py`
- Modify: root `.gitignore` (append frontend + static + openapi.json)

#### Step 1.1: Read the current state of the files you'll modify

- [ ] Read `backend/config.py`, `backend/main.py`, `backend/cli.py`, `tests/conftest.py`, root `.gitignore` — locate the exact insertion points (top imports, last router include in main.py, last Typer command in cli.py, top of conftest.py).

#### Step 1.2: Write the failing SPA-gate test FIRST

- [ ] Create `tests/test_spa_mount_gate.py`:

```python
"""Verify the import-time DISABLE_SPA_MOUNT gate keeps SPA routes
out of the TestClient even when backend/static/ exists on disk.

The autouse-fixture approach (monkeypatching STATIC_DIR after import)
cannot work because FastAPI registers routes at module import time.
The env-flag at conftest module top is the only correct fix.
"""
import os

from fastapi.testclient import TestClient

from backend.main import app


def test_disable_spa_mount_env_var_is_set_for_tests():
    """conftest.py must set DISABLE_SPA_MOUNT=1 before backend.main imports."""
    assert os.environ.get("DISABLE_SPA_MOUNT") == "1"


def test_root_path_returns_404_not_index_html():
    """With SPA gated off, GET / should NOT serve index.html;
    it should fall through to FastAPI's default (404)."""
    client = TestClient(app)
    response = client.get("/")
    # SPA fallback would return 200 + text/html. Gate off ⇒ 404.
    assert response.status_code == 404


def test_assets_mount_does_not_exist_in_tests():
    """/assets/* should 404 when SPA mount is gated off."""
    client = TestClient(app)
    response = client.get("/assets/anything.js")
    assert response.status_code == 404


def test_api_health_still_works():
    """Sanity: API routes themselves are unaffected by the gate."""
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
```

#### Step 1.3: Run the gate test, confirm it FAILS

- [ ] Run: `.venv/bin/python -m pytest tests/test_spa_mount_gate.py -v`

Expected: `test_disable_spa_mount_env_var_is_set_for_tests` FAILS (env var not set yet). The other tests may pass coincidentally because there's no SPA mount at all yet — that's fine; we'll keep them as regression guards once the gate is implemented.

#### Step 1.4: Modify `backend/config.py` — add STATIC_DIR

- [ ] Find `PROJECT_ROOT` (or the closest equivalent) in `backend/config.py`. Below the existing path constants, add:

```python
STATIC_DIR = PROJECT_ROOT / "backend" / "static"
```

If `PROJECT_ROOT` is not defined there, derive it: `PROJECT_ROOT = Path(__file__).resolve().parent.parent`. Use the existing convention if a `BASE_DIR` or similar already exists.

#### Step 1.5: Modify `backend/cli.py` — add `openapi-dump` Typer command

- [ ] After the last existing `@app.command()` block in `backend/cli.py`, append:

```python
@app.command()
def openapi_dump(output: Path = Path("openapi.json")) -> None:
    """Export FastAPI OpenAPI spec to JSON (frontend type generation)."""
    import json

    from backend.main import app as fastapi_app

    output.write_text(json.dumps(fastapi_app.openapi(), indent=2))
    typer.echo(f"OpenAPI written to {output}")
```

Verify `from pathlib import Path` and `import typer` are already at module top. Add them if missing (preserve alphabetical ordering with existing imports).

#### Step 1.6: Modify `tests/conftest.py` — set DISABLE_SPA_MOUNT BEFORE any backend import

- [ ] Open `tests/conftest.py`. At the VERY TOP (before any `import backend.*` or `from backend.*`):

```python
import os
os.environ.setdefault("DISABLE_SPA_MOUNT", "1")
```

If the file already has top-level imports of backend modules, the new lines MUST precede them. Use `setdefault` so explicit CI overrides remain possible.

#### Step 1.7: Modify `backend/main.py` — add gated SPA fallback after all `/api/*` routers

- [ ] In `backend/main.py`, locate the LAST `app.include_router(...)` call (or the LAST module-level route registration). After that block, append:

```python
import os
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Route registration happens at import time. To keep tests deterministic
# (no SPA routes leaking into TestClient) we gate registration on an env
# flag in addition to the directory check. The test conftest sets this
# BEFORE backend.main is imported.
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
        """Root-level public files (favicon, robots) if exist; extension-
        but-missing → 404; extensionless paths → SPA index."""
        last = path.rsplit("/", 1)[-1] if path else ""
        has_ext = "." in last
        target = config.STATIC_DIR / path
        try:
            target.resolve().relative_to(config.STATIC_DIR.resolve())
        except ValueError:
            raise HTTPException(403)
        if has_ext:
            if target.is_file():
                return FileResponse(target)
            raise HTTPException(404)
        return FileResponse(INDEX_HTML)
```

Re-use existing `import os`, `from fastapi import ...` if already present (do not duplicate imports). `config` should already be imported as `from backend import config` or similar.

#### Step 1.8: Run the gate test, confirm all 4 cases PASS now

- [ ] Run: `.venv/bin/python -m pytest tests/test_spa_mount_gate.py -v`

Expected: All 4 PASS.

#### Step 1.9: Write + run the openapi-dump test

- [ ] Create `tests/test_openapi_dump.py`:

```python
"""Verify `python -m backend.cli openapi-dump` produces a valid OpenAPI
JSON document with the contract surfaces the frontend depends on."""
import json
import subprocess
import sys

import pytest


def test_openapi_dump_writes_valid_json(tmp_path):
    output = tmp_path / "openapi.json"
    result = subprocess.run(
        [sys.executable, "-m", "backend.cli", "openapi-dump", "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert output.exists()

    spec = json.loads(output.read_text())
    assert spec.get("openapi", "").startswith("3."), "Not an OpenAPI 3.x spec"
    assert "paths" in spec
    assert "/api/auth/login" in spec["paths"]
    assert "/api/auth/me" in spec["paths"]
    assert "/api/auth/logout" in spec["paths"]
    assert "/api/auth/register" in spec["paths"]
```

- [ ] Run: `.venv/bin/python -m pytest tests/test_openapi_dump.py -v`

Expected: PASS.

#### Step 1.10: Update root `.gitignore`

- [ ] Open the root `.gitignore`. Append (if not already present):

```
# Frontend (Paket 16a)
frontend/node_modules/
frontend/dist/
frontend/coverage/

# Backend frontend build output (owned by Vite; never committed)
backend/static/

# OpenAPI dump (regenerated on demand; not committed)
openapi.json
```

Verify the lines actually got appended:

```bash
tail -10 .gitignore
```

Expected: the new block is at the bottom.

#### Step 1.11: Run the full backend suite

- [ ] Run: `.venv/bin/python -m pytest -x -q`

Expected: ALL backend tests green (existing + 2 new). If any pre-existing test fails, it's a regression introduced by the conftest top-level env set or the main.py addition — investigate and fix the production code before continuing.

#### Step 1.12: Commit

- [ ] Run:

```bash
git add backend/config.py backend/main.py backend/cli.py \
        tests/conftest.py tests/test_spa_mount_gate.py tests/test_openapi_dump.py \
        .gitignore
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): backend touches for frontend foundation

Adds the backend hooks the frontend scaffold depends on:
- config.py STATIC_DIR pointing at backend/static/ (Vite build sink)
- main.py extension-aware SPA fallback after all /api/* routers,
  gated on DISABLE_SPA_MOUNT env var so import-time route registration
  stays inert in tests regardless of disk state
- cli.py openapi-dump Typer command (`python -m backend.cli openapi-dump`)
- tests/conftest.py sets DISABLE_SPA_MOUNT=1 at module top BEFORE any
  backend import (autouse fixture would be too late)
- New tests: test_spa_mount_gate.py (4 cases), test_openapi_dump.py
- Root .gitignore: backend/static/, frontend/node_modules/, frontend/dist/,
  frontend/coverage/, openapi.json

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Frontend scaffold — configs only, no source logic

**Why second:** Nothing else in `frontend/` can be created or tested until `package.json`, tsconfigs, vite.config, eslint.config, tailwind, and the project skeleton exist. This commit is large in file count but contains no application logic — every file is configuration.

**Files (all CREATE):**
- `frontend/package.json`
- `frontend/tsconfig.json`, `tsconfig.node.json`, `tsconfig.eslint.json`
- `frontend/vite.config.ts`
- `frontend/eslint.config.js`
- `frontend/.prettierrc`, `.editorconfig`, `.env.example`, `.gitignore`, `.npmrc`, `.nvmrc`
- `frontend/tailwind.config.ts`, `postcss.config.js`, `components.json`
- `frontend/index.html`
- `frontend/public/favicon.svg`, `public/robots.txt`
- `frontend/src/styles/globals.css`
- `frontend/src/lib/utils.ts`
- `frontend/src/lib/env.ts`

#### Step 2.1: Create `frontend/` directory and pin Node version

- [ ] Run:

```bash
mkdir -p frontend/src/lib frontend/src/styles frontend/public
echo "22" > frontend/.nvmrc
echo "engine-strict=true" > frontend/.npmrc
nvm use            # if nvm is available; otherwise verify `node --version` is v22.x
```

Expected: `node --version` reports `v22.x.y`.

#### Step 2.2: Create `frontend/package.json` (verbatim from spec §8)

- [ ] Create `frontend/package.json`:

```json
{
  "name": "anotasyon-platform-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "engines": {
    "node": ">=22.0.0 <24.0.0",
    "npm": ">=10.0.0"
  },
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "gen:openapi": "cd .. && python -m backend.cli openapi-dump --output openapi.json",
    "gen:types": "openapi-typescript http://127.0.0.1:8000/openapi.json -o src/api/types.ts",
    "gen:types:from-file": "openapi-typescript ../openapi.json -o src/api/types.ts",
    "gen:types:check": "npm run gen:openapi && npm run gen:types:from-file && git diff --exit-code src/api/types.ts",
    "test": "vitest",
    "test:run": "vitest run",
    "test:coverage": "vitest run --coverage",
    "test:ui": "vitest --ui",
    "lint": "eslint .",
    "lint:fix": "eslint . --fix",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@hookform/resolvers": "^3.9.0",
    "@tanstack/react-query": "^5.59.0",
    "@tanstack/react-virtual": "^3.10.0",
    "class-variance-authority": "~0.7.0",
    "clsx": "^2.1.1",
    "date-fns": "^3.6.0",
    "lucide-react": "~0.453.0",
    "openapi-fetch": "~0.13.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-hook-form": "^7.53.0",
    "react-router-dom": "^6.27.0",
    "sonner": "^1.5.0",
    "tailwind-merge": "^2.5.0",
    "tailwindcss-animate": "^1.0.7",
    "zod": "^3.23.0",
    "zustand": "^4.5.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/node": "^22.7.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "@vitest/coverage-v8": "^2.1.0",
    "@vitest/eslint-plugin": "^1.1.0",
    "@vitest/ui": "^2.1.0",
    "autoprefixer": "^10.4.0",
    "eslint": "^9.12.0",
    "eslint-config-prettier": "^9.1.0",
    "eslint-plugin-jsx-a11y": "^6.10.0",
    "eslint-plugin-react": "^7.37.0",
    "eslint-plugin-react-hooks": "^5.0.0",
    "eslint-plugin-react-refresh": "^0.4.0",
    "globals": "^15.10.0",
    "jsdom": "^25.0.0",
    "msw": "^2.4.0",
    "openapi-typescript": "^7.4.0",
    "postcss": "^8.4.0",
    "prettier": "^3.3.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.6.0",
    "typescript-eslint": "^8.8.0",
    "vite": "^5.4.0",
    "vitest": "^2.1.0"
  }
}
```

#### Step 2.3: Install dependencies (creates package-lock.json)

- [ ] Run:

```bash
cd frontend
npm install
```

Expected: completes with no errors; `package-lock.json` is created; `node_modules/` populates. Warnings about peer dep ranges are acceptable as long as install succeeds.

#### Step 2.4: Create the three tsconfigs

- [ ] Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "exactOptionalPropertyTypes": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "allowSyntheticDefaultImports": true,
    "useDefineForClassFields": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] Create `frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "allowSyntheticDefaultImports": true,
    "types": ["node"]
  },
  "include": ["vite.config.ts"]
}
```

- [ ] Create `frontend/tsconfig.eslint.json`:

```json
{
  "extends": "./tsconfig.json",
  "include": [
    "src/**/*.{ts,tsx}",
    "vite.config.ts"
  ],
  "compilerOptions": {
    "noEmit": true,
    "composite": false,
    "types": ["node", "vite/client"]
  }
}
```

#### Step 2.5: Create `frontend/vite.config.ts`

- [ ] Create `frontend/vite.config.ts`:

```ts
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      '/docs': 'http://127.0.0.1:8000',
      '/openapi.json': 'http://127.0.0.1:8000',
      '/redoc': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/test/**', 'src/**/*.test.{ts,tsx}', 'src/api/types.ts'],
      thresholds: {
        statements: 80,
        branches: 80,
        functions: 80,
        lines: 80,
      },
    },
  },
})
```

#### Step 2.6: Create `frontend/eslint.config.js` (3-block flat config from spec §8)

- [ ] Create `frontend/eslint.config.js`:

```js
import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import vitest from '@vitest/eslint-plugin'
import prettier from 'eslint-config-prettier'
import globals from 'globals'

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'node_modules', 'src/api/types.ts'] },
  // ----- Block 1: app code (type-aware) -----
  {
    files: ['src/**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommendedTypeChecked,
      ...tseslint.configs.stylisticTypeChecked,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.browser },
      parserOptions: {
        project: ['./tsconfig.eslint.json'],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      'jsx-a11y': jsxA11y,
    },
    settings: { react: { version: 'detect' } },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs['jsx-runtime'].rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      'react-refresh/only-export-components': ['error', { allowConstantExport: true }],
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
  // ----- Block 2: test files (loosen + vitest globals) -----
  {
    files: ['src/**/*.test.{ts,tsx}', 'src/test/**/*.{ts,tsx}'],
    plugins: { vitest },
    languageOptions: { globals: { ...globals.browser, ...vitest.environments.env.globals } },
    rules: {
      ...vitest.configs.recommended.rules,
      'react-refresh/only-export-components': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-non-null-assertion': 'off',
    },
  },
  // ----- Block 3: Node-context config files (no type-aware lint) -----
  {
    files: ['vite.config.ts', 'eslint.config.js', 'tailwind.config.ts', 'postcss.config.js'],
    languageOptions: {
      globals: { ...globals.node },
      parserOptions: { project: null },
    },
    rules: {
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-call': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
    },
  },
  prettier,
)
```

#### Step 2.7: Create the small config files

- [ ] Create `frontend/.prettierrc`:

```json
{
  "semi": false,
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2,
  "useTabs": false,
  "arrowParens": "always"
}
```

- [ ] Create `frontend/.editorconfig`:

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
indent_style = space
indent_size = 2
insert_final_newline = true
trim_trailing_whitespace = true
```

- [ ] Create `frontend/.env.example`:

```
# Frontend environment variables (all VITE_ prefix to be exposed at build time).
# Copy to .env.local for local overrides.

# Base URL for the API. Empty string in dev (Vite proxy handles routing).
# Production: same-origin (FastAPI serves SPA + API on one port).
VITE_API_BASE_URL=
```

- [ ] Create `frontend/.gitignore`:

```
node_modules
dist
coverage
.env
.env.local
*.log
.DS_Store
.vite
```

#### Step 2.8: Create Tailwind + shadcn config files

- [ ] Create `frontend/tailwind.config.ts`:

```ts
import type { Config } from 'tailwindcss'
import animate from 'tailwindcss-animate'

const config: Config = {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: { center: true, padding: '2rem', screens: { '2xl': '1400px' } },
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
  plugins: [animate],
}

export default config
```

- [ ] Create `frontend/postcss.config.js`:

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] Create `frontend/components.json` (shadcn config):

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/styles/globals.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

#### Step 2.9: Create `frontend/index.html`

- [ ] Create `frontend/index.html`:

```html
<!doctype html>
<html lang="tr">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Anotasyon Platformu</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

#### Step 2.10: Create `frontend/public/favicon.svg` + `robots.txt`

- [ ] Create `frontend/public/favicon.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#1f2937"/>
  <text x="16" y="22" text-anchor="middle" font-family="sans-serif" font-size="18" font-weight="700" fill="#e5e7eb">A</text>
</svg>
```

- [ ] Create `frontend/public/robots.txt`:

```
User-agent: *
Disallow: /
```

(Internal tool — never indexed.)

#### Step 2.11: Create `frontend/src/styles/globals.css`

- [ ] Create `frontend/src/styles/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 222.2 84% 4.9%;
    --radius: 0.5rem;
  }

  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground font-sans antialiased;
  }
}
```

#### Step 2.11.5: Create minimal test scaffolding (so vitest setupFiles resolves)

`vite.config.ts` declares `setupFiles: ['./src/test/setup.ts']`. Without that file, vitest fails to start — even for T4's tests that use a local MSW server. Create skeletons here; T6 expands them.

- [ ] Run `mkdir -p frontend/src/test`

- [ ] Create `frontend/src/test/msw-server.ts`:

```ts
import { setupServer } from 'msw/node'

// Shared MSW server. Default handlers land in T6's msw-handlers.ts.
// Individual tests add handlers via server.use(...).
export const server = setupServer()
```

- [ ] Create `frontend/src/test/msw-handlers.ts`:

```ts
// Default handlers land in T6 (after authStore + api/client exist).
// Kept as an empty export here so msw-server can import a stable name.
export const handlers = []
```

- [ ] Create `frontend/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest'
import { beforeAll, afterEach, afterAll } from 'vitest'
import { server } from './msw-server'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// T5 will add useAuthStore reset, T6 will add cleanup + DI client reset.
```

#### Step 2.12: Create `frontend/src/lib/utils.ts` and `frontend/src/lib/env.ts`

- [ ] Create `frontend/src/lib/utils.ts`:

```ts
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

- [ ] Create `frontend/src/lib/env.ts`:

```ts
import { z } from 'zod'

const envSchema = z.object({
  VITE_API_BASE_URL: z.string().default(''),
})

export const env = envSchema.parse({
  VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
})
```

#### Step 2.13: Verify the scaffold typechecks

- [ ] Run:

```bash
cd frontend
npm run typecheck
```

Expected: PASS (no `src/main.tsx` exists yet, so `npm run build` would fail — that's fine; typecheck only checks what's in `src/`, currently just `lib/`).

#### Step 2.14: Commit

- [ ] Run from repo root:

```bash
git add frontend/ .gitignore
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): frontend scaffold — configs, tooling, tailwind, lib

Creates the frontend/ directory with all build/lint/test/style
configuration but no application source yet:
- package.json with pinned deps (engine-strict Node 22)
- tsconfig.json (strict + exactOptionalPropertyTypes +
  noUncheckedIndexedAccess + verbatimModuleSyntax), tsconfig.node.json,
  tsconfig.eslint.json (type-aware lint scope)
- vite.config.ts: dev proxy to 127.0.0.1:8000, build outDir
  ../backend/static, vitest jsdom + coverage thresholds ≥80%
- eslint.config.js: 3-block flat config (app type-aware / test vitest
  globals / Node-context config files) + prettier last
- Tailwind + shadcn (components.json), postcss, globals.css with
  shadcn CSS-variable design tokens
- index.html, public/favicon.svg, public/robots.txt
- src/lib/utils.ts (cn helper), src/lib/env.ts (zod env validation)
- Standard small configs: .prettierrc, .editorconfig, .env.example,
  .gitignore, .npmrc (engine-strict), .nvmrc (22)

`npm run typecheck` passes. No source code yet — that lands in T3+.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Generate `src/api/types.ts` from backend OpenAPI

**Why third:** every later frontend file imports from `@/api/types`. Generating once and committing means subsequent tasks have a stable type surface.

**Files:**
- Create: `frontend/src/api/types.ts` (generated, committed)

#### Step 3.1: Start the backend in a separate terminal

- [ ] In terminal A, from repo root:

```bash
.venv/bin/uvicorn backend.main:app --port 8000
```

Wait for `Application startup complete.`

#### Step 3.2: Generate types

- [ ] In terminal B:

```bash
cd frontend
npm run gen:types
```

Expected: `src/api/types.ts` is created (typically a few hundred to a few thousand lines), no errors. Stop the uvicorn process in terminal A.

#### Step 3.3: Sanity-check the generated file

- [ ] Run:

```bash
grep -E "^export interface paths|UserOut|RegisterRequest|LoginRequest" frontend/src/api/types.ts | head
```

Expected: at least one match for `paths` and the auth schemas. If the file is empty or missing these, the backend wasn't running or `/openapi.json` is empty — diagnose before continuing.

#### Step 3.4: Run typecheck (types.ts compiles in isolation)

- [ ] Run:

```bash
cd frontend
npm run typecheck
```

Expected: PASS.

#### Step 3.5: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/api/types.ts
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): generated OpenAPI TypeScript types

Generated by `npm run gen:types` against the running backend's
/openapi.json. This file is COMMITTED so fresh clones can typecheck
and build without booting the backend first. Drift detection moves
to CI in Paket 17.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: API client — `openapi-fetch` + DI setters + interceptor + `unwrap`/`unwrapVoid`

**Why now:** every query and mutation imports `client` and the unwrap helpers. The interceptor's hydration-aware self-401 logic plus the three-shape error parser are the most adversarially-reviewed pieces of the spec — TDD them hard.

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/client.test.ts`

#### Step 4.1: Write the failing test file first

- [ ] Create `frontend/src/api/client.test.ts`:

```ts
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import {
  client,
  unwrap,
  unwrapVoid,
  ApiError,
  UnexpectedEmptyResponse,
  setNavigator,
  setAuthHandlers,
  markHydrated,
  _resetHydrationStateForTests,
} from './client'

// The shared `server` is listened/closed by setup.ts (T2 scaffold + T6 fill).
// Per-test handlers added via server.use(...); resetHandlers in afterEach
// is handled by setup.ts.

beforeEach(() => {
  setNavigator(null)
  setAuthHandlers(null)
  _resetHydrationStateForTests()
})
afterEach(() => {
  setNavigator(null)
  setAuthHandlers(null)
  _resetHydrationStateForTests()
})

describe('unwrap()', () => {
  it('returns data on 2xx with body', async () => {
    server.use(
      http.get('http://localhost/api/echo', () =>
        HttpResponse.json({ ok: true, value: 42 }),
      ),
    )
    const result = await client.GET('/api/auth/me' as never)
    // simulate by hand: just verify the helper shape
    const fake = {
      data: { value: 42 },
      response: new Response(null, { status: 200 }),
    }
    expect(await unwrap(fake)).toEqual({ value: 42 })
  })

  it('throws UnexpectedEmptyResponse when 2xx but no body', async () => {
    const fake = {
      data: undefined,
      response: new Response(null, { status: 200, statusText: 'OK' }),
    }
    await expect(unwrap(fake)).rejects.toBeInstanceOf(UnexpectedEmptyResponse)
  })

  it('parses FastAPI string detail shape', async () => {
    const fake = {
      error: { detail: 'kullanıcı bulunamadı' },
      response: new Response(null, { status: 404 }),
    }
    await expect(unwrap(fake)).rejects.toMatchObject({
      status: 404,
      code: '404',
      message: 'kullanıcı bulunamadı',
    })
  })

  it('parses object detail shape with error+message keys', async () => {
    const fake = {
      error: { detail: { error: 'invalid_credentials', message: 'Şifre hatalı' } },
      response: new Response(null, { status: 401 }),
    }
    await expect(unwrap(fake)).rejects.toMatchObject({
      status: 401,
      code: 'invalid_credentials',
      message: 'Şifre hatalı',
    })
  })

  it('parses validation array detail shape', async () => {
    const fake = {
      error: {
        detail: [
          { type: 'value_error', msg: 'password too short' },
          { type: 'value_error', msg: 'username required' },
        ],
      },
      response: new Response(null, { status: 422 }),
    }
    await expect(unwrap(fake)).rejects.toMatchObject({
      status: 422,
      code: 'value_error',
      message: 'password too short; username required',
    })
  })
})

describe('unwrapVoid()', () => {
  it('returns undefined on 2xx', async () => {
    const fake = {
      data: undefined,
      response: new Response(null, { status: 204 }),
    }
    await expect(unwrapVoid(fake)).resolves.toBeUndefined()
  })

  it('returns undefined on 2xx with body (caller does not care)', async () => {
    const fake = {
      data: { ok: true },
      response: new Response(null, { status: 200 }),
    }
    await expect(unwrapVoid(fake)).resolves.toBeUndefined()
  })

  it('throws ApiError on error', async () => {
    const fake = {
      error: { detail: 'session expired' },
      response: new Response(null, { status: 401 }),
    }
    await expect(unwrapVoid(fake)).rejects.toBeInstanceOf(ApiError)
  })
})

describe('401 interceptor', () => {
  it('pre-hydration self-401 on /api/auth/me does NOT trigger session-expired handler', async () => {
    const onSessionExpired = vi.fn()
    const navigate = vi.fn()
    setAuthHandlers({ onSessionExpired })
    setNavigator(navigate)
    // hydrated is false by default

    server.use(
      http.get('http://localhost/api/auth/me', () =>
        HttpResponse.json({ detail: 'unauth' }, { status: 401 }),
      ),
    )
    await client.GET('/api/auth/me')
    expect(onSessionExpired).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('post-hydration 401 on /api/auth/me DOES trigger session-expired', async () => {
    const onSessionExpired = vi.fn()
    const navigate = vi.fn()
    setAuthHandlers({ onSessionExpired })
    setNavigator(navigate)
    markHydrated()

    server.use(
      http.get('http://localhost/api/auth/me', () =>
        HttpResponse.json({ detail: 'unauth' }, { status: 401 }),
      ),
    )
    await client.GET('/api/auth/me')
    expect(onSessionExpired).toHaveBeenCalledTimes(1)
    expect(navigate).toHaveBeenCalledWith('/login')
  })

  it('401 on any other endpoint always triggers session-expired', async () => {
    const onSessionExpired = vi.fn()
    const navigate = vi.fn()
    setAuthHandlers({ onSessionExpired })
    setNavigator(navigate)
    // hydrated is false: still fires because not /api/auth/me

    server.use(
      http.get('http://localhost/api/something', () =>
        HttpResponse.json({ detail: 'unauth' }, { status: 401 }),
      ),
    )
    await client.GET('/api/something' as never)
    expect(onSessionExpired).toHaveBeenCalledTimes(1)
    expect(navigate).toHaveBeenCalledWith('/login')
  })

  it('non-401 statuses pass through without triggering handlers', async () => {
    const onSessionExpired = vi.fn()
    const navigate = vi.fn()
    setAuthHandlers({ onSessionExpired })
    setNavigator(navigate)
    markHydrated()

    server.use(
      http.get('http://localhost/api/auth/me', () =>
        HttpResponse.json({ detail: 'forbidden' }, { status: 403 }),
      ),
    )
    await client.GET('/api/auth/me')
    expect(onSessionExpired).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })
})
```

#### Step 4.2: Run the tests — confirm they fail (module not found)

- [ ] Run:

```bash
cd frontend
npm run test:run -- src/api/client.test.ts
```

Expected: FAILS with import error (`./client` doesn't exist yet).

#### Step 4.3: Implement `src/api/client.ts`

- [ ] Create `frontend/src/api/client.ts`:

```ts
import createClient, { type Middleware } from 'openapi-fetch'
import type { paths } from './types'

// DI setters — no store imports here to prevent circular dependency.
let navigateRef: ((path: string) => void) | null = null
let authHandlersRef: { onSessionExpired: () => void } | null = null
let hydrated = false

export function setNavigator(fn: typeof navigateRef) {
  navigateRef = fn
}
export function setAuthHandlers(h: typeof authHandlersRef) {
  authHandlersRef = h
}
export function markHydrated() {
  hydrated = true
}
/** Test-only: reset hydration flag for isolation. */
export function _resetHydrationStateForTests() {
  hydrated = false
}

const authInterceptor: Middleware = {
  async onResponse({ response, request }) {
    if (response.status !== 401) return
    const url = new URL(request.url)
    const isAuthMe = url.pathname === '/api/auth/me'
    // Pre-hydration self-401 is the normal "you are not logged in" signal;
    // do not redirect or fire session-expired.
    if (isAuthMe && !hydrated) return
    authHandlersRef?.onSessionExpired()
    navigateRef?.('/login')
  },
}

export const client = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '',
  credentials: 'include',
})
client.use(authInterceptor)

// ---- Typed error classes ----

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly raw?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export class UnexpectedEmptyResponse extends Error {
  constructor(message?: string) {
    super(message)
    this.name = 'UnexpectedEmptyResponse'
  }
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response }

function parseErrorDetail(
  detail: unknown,
  status: number,
): { code: string; message: string } {
  if (typeof detail === 'string') {
    return { code: String(status), message: detail }
  }
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>
    return {
      code: typeof d.error === 'string' ? d.error : String(status),
      message:
        typeof d.message === 'string' ? d.message : JSON.stringify(detail),
    }
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const msgs = detail
      .map((e: any) => e?.msg ?? String(e))
      .filter(Boolean)
      .join('; ')
    const firstType = (detail[0] as any)?.type
    return {
      code: typeof firstType === 'string' ? firstType : 'validation_error',
      message: msgs || 'Doğrulama hatası',
    }
  }
  return { code: String(status), message: 'Bilinmeyen hata' }
}

/** Unwrap a result where a body is expected. Throws on empty body or error. */
export async function unwrap<T>(result: FetchResult<T>): Promise<T> {
  if (result.error !== undefined) {
    const detail = (result.error as any)?.detail ?? result.error
    const { code, message } = parseErrorDetail(detail, result.response.status)
    throw new ApiError(result.response.status, code, message, result.error)
  }
  if (result.data === undefined) {
    throw new UnexpectedEmptyResponse(
      `Expected body for ${result.response.url} ${result.response.status}; use unwrapVoid() for empty responses.`,
    )
  }
  return result.data
}

/** Unwrap a result where no body is expected (204, {ok:true}). */
export async function unwrapVoid(
  result: FetchResult<unknown>,
): Promise<void> {
  if (result.error !== undefined) {
    const detail = (result.error as any)?.detail ?? result.error
    const { code, message } = parseErrorDetail(detail, result.response.status)
    throw new ApiError(result.response.status, code, message, result.error)
  }
}
```

#### Step 4.4: Run the tests — confirm they PASS

- [ ] Run:

```bash
cd frontend
npm run test:run -- src/api/client.test.ts
```

Expected: ALL PASS (14 tests).

#### Step 4.5: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/api/client.ts frontend/src/api/client.test.ts
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): API client — openapi-fetch + DI interceptor + unwrap

Typed minimal fetch client built on openapi-fetch:
- DI setter pattern (setNavigator, setAuthHandlers, markHydrated) prevents
  circular deps with stores/auth
- 401 interceptor: pre-hydration self-401 on /api/auth/me is suppressed
  (normal anon signal); post-hydration or any-other-endpoint 401 fires
  onSessionExpired() + navigate('/login')
- unwrap<T>() + unwrapVoid() + ApiError + UnexpectedEmptyResponse
- parseErrorDetail handles all 3 FastAPI detail shapes (string, object
  with error/message, validation array)
- _resetHydrationStateForTests() exposed for test isolation

14 tests cover all branches: 3 detail shapes, 4 interceptor paths,
unwrapVoid happy + error, UnexpectedEmptyResponse guard.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `authStore` (Zustand 4-state)

**Why now:** test infra and gates both consume the store. TDD keeps the state machine honest.

**Files:**
- Create: `frontend/src/stores/authStore.ts`
- Create: `frontend/src/stores/authStore.test.ts`

#### Step 5.1: Write the failing test

- [ ] Create `frontend/src/stores/authStore.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import {
  useAuthStore,
  selectUser,
  selectIsAuthed,
  selectIsAdmin,
  type User,
} from './authStore'

const makeUser = (overrides: Partial<User> = {}): User => ({
  id: 1,
  username: 'tester',
  email: 'tester@example.com',
  role: 'user',
  is_active: true,
  has_seen_manual: true,
  has_passed_training: true,
  avatar_color: '#3b82f6',
  created_at: '2026-05-01T00:00:00+00:00',
  ...overrides,
})

beforeEach(() => {
  useAuthStore.setState({ status: 'loading', user: null, error: null })
})

describe('authStore transitions', () => {
  it('defaults to loading/null/null on first import', () => {
    const s = useAuthStore.getState()
    expect(s.status).toBe('loading')
    expect(s.user).toBeNull()
    expect(s.error).toBeNull()
  })

  it('setUser → authed + clears error', () => {
    useAuthStore.setState({ status: 'error', error: 'previous fail' })
    useAuthStore.getState().setUser(makeUser())
    const s = useAuthStore.getState()
    expect(s.status).toBe('authed')
    expect(s.user?.username).toBe('tester')
    expect(s.error).toBeNull()
  })

  it('setError → error + keeps existing user untouched (renders LoadingScreen anyway)', () => {
    useAuthStore.setState({ status: 'authed', user: makeUser(), error: null })
    useAuthStore.getState().setError('network down')
    const s = useAuthStore.getState()
    expect(s.status).toBe('error')
    expect(s.error).toBe('network down')
  })

  it('setStatus("loading") flips status without altering user/error (used by retry)', () => {
    useAuthStore.setState({ status: 'error', error: 'fail', user: null })
    useAuthStore.getState().setStatus('loading')
    expect(useAuthStore.getState().status).toBe('loading')
    expect(useAuthStore.getState().error).toBe('fail') // not cleared
  })

  it('clear → anon + null user/error (used by logout AND 401 anon)', () => {
    useAuthStore.setState({ status: 'authed', user: makeUser(), error: null })
    useAuthStore.getState().clear()
    const s = useAuthStore.getState()
    expect(s.status).toBe('anon')
    expect(s.user).toBeNull()
    expect(s.error).toBeNull()
  })
})

describe('authStore selectors', () => {
  it('selectUser', () => {
    useAuthStore.getState().setUser(makeUser({ username: 'alice' }))
    expect(selectUser(useAuthStore.getState())?.username).toBe('alice')
  })

  it('selectIsAuthed is true only on status==="authed"', () => {
    useAuthStore.setState({ status: 'loading' })
    expect(selectIsAuthed(useAuthStore.getState())).toBe(false)
    useAuthStore.getState().setUser(makeUser())
    expect(selectIsAuthed(useAuthStore.getState())).toBe(true)
    useAuthStore.getState().clear()
    expect(selectIsAuthed(useAuthStore.getState())).toBe(false)
  })

  it('selectIsAdmin reflects user.role', () => {
    useAuthStore.getState().setUser(makeUser({ role: 'user' }))
    expect(selectIsAdmin(useAuthStore.getState())).toBe(false)
    useAuthStore.getState().setUser(makeUser({ role: 'admin' }))
    expect(selectIsAdmin(useAuthStore.getState())).toBe(true)
  })
})
```

#### Step 5.2: Run — confirm FAIL

- [ ] Run: `cd frontend && npm run test:run -- src/stores/authStore.test.ts`

Expected: FAIL (module not found).

#### Step 5.3: Implement the store

- [ ] Create `frontend/src/stores/authStore.ts`:

```ts
import { create } from 'zustand'

export type AuthStatus = 'loading' | 'authed' | 'anon' | 'error'

export interface User {
  id: number
  username: string
  email: string | null
  role: 'user' | 'admin'
  is_active: boolean
  has_seen_manual: boolean
  has_passed_training: boolean
  avatar_color: string | null
  created_at: string
}

interface AuthState {
  status: AuthStatus
  user: User | null
  error: string | null
  setUser: (user: User) => void
  setError: (message: string) => void
  setStatus: (status: AuthStatus) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  status: 'loading',
  user: null,
  error: null,
  setUser: (user) => set({ status: 'authed', user, error: null }),
  setError: (message) => set({ status: 'error', error: message }),
  setStatus: (status) => set({ status }),
  clear: () => set({ status: 'anon', user: null, error: null }),
}))

export const selectUser = (s: AuthState) => s.user
export const selectIsAuthed = (s: AuthState) => s.status === 'authed'
export const selectIsAdmin = (s: AuthState) => s.user?.role === 'admin'
```

#### Step 5.4: Run — confirm all PASS

- [ ] Run: `cd frontend && npm run test:run -- src/stores/authStore.test.ts`

Expected: 8 tests PASS.

#### Step 5.5: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/stores/
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): authStore — Zustand 4-state machine (loading|authed|anon|error)

Server-driven auth state with no localStorage persist (HttpOnly cookie
is the source of truth via /api/auth/me).

Transitions:
- setUser(user)       → authed + error=null
- setError(message)   → error  (status flipped; user untouched so the
                        existing tab can read what was last known)
- setStatus(status)   → status only (used by retry: loading flip)
- clear()             → anon  + user=null, error=null

Selectors: selectUser, selectIsAuthed, selectIsAdmin.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Test infrastructure — expand MSW handlers, finish setup.ts, create renderWithProviders

**Why now:** every UI test from here on imports from `@/test/render`. The factory + auto-cleanup + destination stubs need to be in place before gates, queries, routes, and App tests can run. T2 scaffolded the empty stubs; this task fills them in.

**Files:**
- Modify: `frontend/src/test/msw-server.ts` (rewire to consume default handlers)
- Modify: `frontend/src/test/msw-handlers.ts` (replace empty stub with full content)
- Modify: `frontend/src/test/setup.ts` (add cleanup + authStore reset + DI client reset)
- Create: `frontend/src/test/render.tsx`

#### Step 6.1: Rewrite `msw-server.ts` to seed default handlers

- [ ] Replace `frontend/src/test/msw-server.ts` with:

```ts
import { setupServer } from 'msw/node'
import { handlers } from './msw-handlers'

export const server = setupServer(...handlers)
```

#### Step 6.2: Rewrite `msw-handlers.ts` with the real default handlers

- [ ] Replace `frontend/src/test/msw-handlers.ts` with:

```ts
import { http, HttpResponse } from 'msw'
import type { components } from '@/api/types'

type User = components['schemas']['UserOut']

export function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    username: 'tester',
    email: 'tester@example.com',
    role: 'user',
    is_active: true,
    has_seen_manual: true,
    has_passed_training: true,
    avatar_color: '#3b82f6',
    created_at: '2026-05-01T00:00:00+00:00',
    ...overrides,
  } satisfies User
}

export const handlers = [
  http.get('/api/auth/me', () =>
    HttpResponse.json(
      { detail: { error: 'unauthorized', message: 'Not authenticated' } },
      { status: 401 },
    ),
  ),
  http.post('/api/auth/login', () => HttpResponse.json({ ok: true })),
  http.post('/api/auth/logout', () => HttpResponse.json({ ok: true })),
  // Backend register returns UserOut (201) but DOES NOT set a session
  // cookie (see backend/users/routes.py — no response.set_cookie call).
  // Frontend useRegisterMutation treats this as "account created, navigate
  // to /login with success toast" — NOT an authed transition.
  http.post('/api/auth/register', () =>
    HttpResponse.json(
      makeUser({ has_seen_manual: false, has_passed_training: false }),
      { status: 201 },
    ),
  ),
]

export function mockAuthedUser(overrides: Partial<User> = {}) {
  return http.get('/api/auth/me', () =>
    HttpResponse.json(makeUser(overrides)),
  )
}

export function mockAnonUser() {
  return http.get('/api/auth/me', () =>
    HttpResponse.json(
      { detail: { error: 'unauthorized', message: '' } },
      { status: 401 },
    ),
  )
}
```

#### Step 6.3: Expand `setup.ts` with cleanup + store/DI resets

- [ ] Replace `frontend/src/test/setup.ts` with:

```ts
import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { server } from './msw-server'
import { useAuthStore } from '@/stores/authStore'
import {
  setNavigator,
  setAuthHandlers,
  _resetHydrationStateForTests,
} from '@/api/client'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))

afterEach(() => {
  server.resetHandlers()
  cleanup()
  useAuthStore.setState({ status: 'loading', user: null, error: null })
  setNavigator(null)
  setAuthHandlers(null)
  _resetHydrationStateForTests()
  vi.restoreAllMocks()
})

afterAll(() => server.close())

/** Opt-in helper for tests that intentionally trigger React errors. */
export function silenceConsoleError() {
  return vi.spyOn(console, 'error').mockImplementation(() => {})
}
```

#### Step 6.4: Create `render.tsx`

- [ ] Create `frontend/src/test/render.tsx`:

```tsx
import { render as rtlRender, type RenderOptions } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route, parsePath } from 'react-router-dom'
import { type ReactElement, type ReactNode } from 'react'
import { afterEach } from 'vitest'

interface RenderOpts extends Omit<RenderOptions, 'wrapper'> {
  initialEntries?: string[]
  destinationStubs?: Array<{ path: string; testId: string }>
  extraDestinationStubs?: Array<{ path: string; testId: string }>
}

function makeTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, staleTime: Infinity },
      mutations: { retry: false },
    },
  })
}

const DEFAULT_STUBS = [
  { path: '/', testId: 'route-root' },
  { path: '/login', testId: 'route-login' },
  { path: '/register', testId: 'route-register' },
  { path: '/help', testId: 'route-help' },
  { path: '/training', testId: 'route-training' },
]

const activeQueryClients = new Set<QueryClient>()
afterEach(async () => {
  for (const qc of activeQueryClients) {
    try {
      await qc.cancelQueries()
    } catch (err) {
      console.warn('[test cleanup] cancelQueries failed:', err)
    } finally {
      qc.clear()
    }
  }
  activeQueryClients.clear()
})

/**
 * Test render helper. Wraps `ui` in QueryClientProvider + MemoryRouter +
 * a Routes tree with stub destinations so `<Navigate>` side-effects are
 * observable via `screen.findByTestId('route-...')`.
 *
 * LIMITATIONS:
 * - `ui` MUST NOT own its own `<BrowserRouter>` or `<Routes>`.
 * - Per-test fresh QueryClient is auto-cleaned in afterEach;
 *   `cleanupQueryClient()` is an escape hatch for mid-test teardown.
 */
export function renderWithProviders(
  ui: ReactElement,
  {
    initialEntries = ['/'],
    destinationStubs,
    extraDestinationStubs = [],
    ...rest
  }: RenderOpts = {},
) {
  const queryClient = makeTestQueryClient()
  activeQueryClients.add(queryClient)

  const routerEntries = initialEntries.length > 0 ? initialEntries : ['/']
  const firstEntry = routerEntries[0]!
  const entryPath = parsePath(firstEntry).pathname ?? '/'

  const stubs = destinationStubs ?? [...DEFAULT_STUBS, ...extraDestinationStubs]

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={routerEntries}>
        <Routes>
          <Route path={entryPath} element={children} />
          {stubs
            .filter((s) => s.path !== entryPath)
            .map((s) => (
              <Route
                key={s.path}
                path={s.path}
                element={<div data-testid={s.testId}>{s.path}</div>}
              />
            ))}
          <Route path="*" element={<div data-testid="route-notfound" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )

  const result = rtlRender(ui, { wrapper, ...rest })
  return {
    ...result,
    queryClient,
    cleanupQueryClient: async () => {
      try {
        await queryClient.cancelQueries()
      } catch (err) {
        console.warn('[test cleanup] cancelQueries failed:', err)
      } finally {
        queryClient.clear()
        activeQueryClients.delete(queryClient)
      }
    },
  }
}
```

#### Step 6.5: Add a smoke test that proves the harness boots

- [ ] Create `frontend/src/test/render.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from './render'

describe('renderWithProviders', () => {
  it('renders the ui element at the initialEntries pathname', () => {
    renderWithProviders(<div data-testid="hello">hi</div>, { initialEntries: ['/'] })
    expect(screen.getByTestId('hello')).toBeInTheDocument()
  })

  it('exposes destination stubs when Navigate fires (default stubs cover /, /login, /register, /help, /training)', async () => {
    function NavigateOnMount() {
      // Simulate a side-effect: just render a stub directly to /login.
      // Real Navigate tests come with the gates in T9.
      return <div data-testid="hello-from-root">root</div>
    }
    const { container } = renderWithProviders(<NavigateOnMount />, { initialEntries: ['/'] })
    expect(container.querySelector('[data-testid="hello-from-root"]')).not.toBeNull()
  })
})
```

#### Step 6.6: Run all frontend tests so far

- [ ] Run:

```bash
cd frontend
npm run test:run
```

Expected: All tests from T4 + T5 + T6 PASS. If any test from prior tasks regressed, the new `setup.ts` is interfering — diagnose.

#### Step 6.7: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/test/
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): test infrastructure — Vitest setup + MSW + render helper

Frontend test harness:
- src/test/setup.ts: MSW server lifecycle (listen/resetHandlers/close),
  auto-cleanup of authStore, DI setters, hydration flag, RTL cleanup
- src/test/msw-server.ts: setupServer instance
- src/test/msw-handlers.ts: default handlers (auth/me 401, login/logout
  ok:true, register UserOut 201 with no session) + makeUser typed
  factory + mockAuthedUser/mockAnonUser helpers
- src/test/render.tsx: renderWithProviders with per-test QueryClient,
  destination stubs (root, login, register, help, training) for
  observable <Navigate>, autouse afterEach cleanup of all clients

MSW register handler comment explicitly documents the backend contract:
returns UserOut but does NOT set a session. Frontend register flow
navigates to /login post-success.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: shadcn UI primitives — button, input, label, form, card, sonner

**Why now:** routes, shell, and ErrorBoundary all import from `@/components/ui/*`. shadcn generates these via CLI; no logic to TDD — just verify they render in place.

**Files (CREATE via shadcn CLI):**
- `frontend/src/components/ui/button.tsx`
- `frontend/src/components/ui/input.tsx`
- `frontend/src/components/ui/label.tsx`
- `frontend/src/components/ui/form.tsx`
- `frontend/src/components/ui/card.tsx`
- `frontend/src/components/ui/sonner.tsx`

#### Step 7.1: Run the shadcn add commands

- [ ] Run:

```bash
cd frontend
npx shadcn@latest add button input label form card sonner
```

When prompted, accept defaults (paths match `components.json`). If shadcn fails to detect React 18 vs 19, force the legacy install: `npx shadcn@latest add --overwrite button input label form card sonner` after a manual `npm install class-variance-authority` (already pinned).

Expected: 6 files appear under `src/components/ui/`. Each is a copy-paste Radix primitive wrapped with cva variants.

#### Step 7.2: Verify typecheck still passes

- [ ] Run:

```bash
cd frontend
npm run typecheck
```

Expected: PASS. If any shadcn primitive references a peer dep we don't have, install it (e.g., `@radix-ui/react-label` is pulled in by `npx shadcn` automatically).

#### Step 7.3: Verify the test suite still passes

- [ ] Run:

```bash
cd frontend
npm run test:run
```

Expected: PASS (no new tests, prior ones unchanged).

#### Step 7.4: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/components/ui/ frontend/package.json frontend/package-lock.json
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): shadcn/ui primitives — button, input, label, form, card, sonner

Generated via `npx shadcn@latest add`. Radix-based, design-token aware
(uses CSS variables from globals.css). Form is the react-hook-form +
zod wrapper; Sonner is the toast surface.

Lint-exempt by Block 1 of eslint.config.js (lives under src/components/ui).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Shell components — ErrorBoundary, LoadingScreen, AppShell

**Why now:** App.tsx renders LoadingScreen during hydration; the gate-wrapped routes render inside AppShell; main.tsx wraps everything in ErrorBoundary. All three are testable in isolation.

**Files:**
- Create: `frontend/src/components/ErrorBoundary.tsx` + `.test.tsx`
- Create: `frontend/src/components/shell/LoadingScreen.tsx` + `.test.tsx`
- Create: `frontend/src/components/shell/AppShell.tsx` + `.test.tsx`

#### Step 8.1: Write LoadingScreen test FIRST

- [ ] Create `frontend/src/components/shell/LoadingScreen.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import { LoadingScreen } from './LoadingScreen'

describe('LoadingScreen', () => {
  it('shows spinner + "Yükleniyor..." in default (loading) mode', () => {
    renderWithProviders(<LoadingScreen />)
    expect(screen.getByText('Yükleniyor…')).toBeInTheDocument()
  })

  it('shows error message + Retry + Çıkış buttons in error mode', () => {
    renderWithProviders(<LoadingScreen mode="error" onRetry={() => {}} />)
    expect(screen.getByText(/Sunucuya bağlanılamadı/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Tekrar dene/i })).toBeInTheDocument()
  })

  it('calls onRetry when the Retry button is clicked', () => {
    const onRetry = vi.fn()
    renderWithProviders(<LoadingScreen mode="error" onRetry={onRetry} />)
    fireEvent.click(screen.getByRole('button', { name: /Tekrar dene/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
```

#### Step 8.2: Run → confirm FAIL

- [ ] Run: `cd frontend && npm run test:run -- src/components/shell/LoadingScreen.test.tsx`

#### Step 8.3: Implement `LoadingScreen.tsx`

- [ ] Create `frontend/src/components/shell/LoadingScreen.tsx`:

```tsx
import { AlertCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface LoadingScreenProps {
  mode?: 'loading' | 'error'
  onRetry?: () => void
}

export function LoadingScreen({ mode = 'loading', onRetry }: LoadingScreenProps) {
  if (mode === 'error') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" aria-hidden />
        <p className="text-lg font-medium">Sunucuya bağlanılamadı</p>
        <p className="text-sm text-muted-foreground">
          Bağlantınızı kontrol edin veya tekrar deneyin.
        </p>
        {onRetry && (
          <Button onClick={onRetry} variant="default">
            Tekrar dene
          </Button>
        )}
      </div>
    )
  }
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">Yükleniyor…</p>
    </div>
  )
}
```

#### Step 8.4: Run → PASS

- [ ] Run: `cd frontend && npm run test:run -- src/components/shell/LoadingScreen.test.tsx`

Expected: 3 PASS.

#### Step 8.5: Write ErrorBoundary test

- [ ] Create `frontend/src/components/ErrorBoundary.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import { ErrorBoundary } from './ErrorBoundary'
import { silenceConsoleError } from '@/test/setup'

function Bomb(): JSX.Element {
  throw new Error('boom from Bomb')
}

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    renderWithProviders(
      <ErrorBoundary>
        <div data-testid="child">ok</div>
      </ErrorBoundary>,
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('renders fallback when a child throws', () => {
    silenceConsoleError() // React always console.errors caught errors
    renderWithProviders(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    )
    expect(screen.getByText(/bir şeyler ters gitti/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sayfayı yenile/i })).toBeInTheDocument()
  })
})
```

#### Step 8.6: Implement `ErrorBoundary.tsx`

- [ ] Create `frontend/src/components/ErrorBoundary.tsx`:

```tsx
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { AlertTriangle } from 'lucide-react'

interface State {
  hasError: boolean
  error: Error | null
}

interface Props {
  children: ReactNode
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Production: send to Sentry/etc. — Paket 17.
    console.error('ErrorBoundary caught:', error, info.componentStack)
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
          <AlertTriangle className="h-10 w-10 text-destructive" aria-hidden />
          <p className="text-lg font-medium">Bir şeyler ters gitti</p>
          <p className="text-sm text-muted-foreground">
            Beklenmeyen bir hata oluştu. Sayfayı yenileyerek tekrar deneyin.
          </p>
          <Button onClick={this.handleReload}>Sayfayı yenile</Button>
        </div>
      )
    }
    return this.props.children
  }
}
```

#### Step 8.7: Write AppShell test

- [ ] Create `frontend/src/components/shell/AppShell.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { Route, Routes, MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('renders an outlet so nested routes display below the header', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<div data-testid="child">child</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })
})
```

#### Step 8.8: Implement `AppShell.tsx`

- [ ] Create `frontend/src/components/shell/AppShell.tsx`:

```tsx
import { Outlet } from 'react-router-dom'

export function AppShell() {
  // Minimal in 16a — TopBar with XP/streak/online users lands in 16d.
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b px-4 py-2 flex items-center justify-between">
        <span className="font-semibold">Anotasyon Platformu</span>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  )
}
```

#### Step 8.9: Run all shell + boundary tests

- [ ] Run: `cd frontend && npm run test:run -- src/components`

Expected: ALL PASS (3 + 2 + 1).

#### Step 8.10: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/components/ErrorBoundary.tsx frontend/src/components/ErrorBoundary.test.tsx \
        frontend/src/components/shell/
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): shell components — ErrorBoundary, LoadingScreen, AppShell

ErrorBoundary: class component fallback for React render-time crashes,
with reload button. Logs to console.error in 16a; Sentry hook lands
in Paket 17.

LoadingScreen: dual-mode component used by App during hydration.
- Default mode: spinner + "Yükleniyor…"
- mode="error": AlertCircle + "Sunucuya bağlanılamadı" + Tekrar dene
  button calling onRetry prop. The retry handler is wired by App
  (retryNonce + status flip) in T13.

AppShell: minimal header + <Outlet/>. 16d expands header with XP,
streak, daily progress, online avatars.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Four routing gates — RequireAuth, RequireSeenManual, RequirePassedTraining, RequireAdmin

**Files (CREATE 4 × component + test):**
- `frontend/src/components/gates/RequireAuth.tsx` + `.test.tsx`
- `frontend/src/components/gates/RequireSeenManual.tsx` + `.test.tsx`
- `frontend/src/components/gates/RequirePassedTraining.tsx` + `.test.tsx`
- `frontend/src/components/gates/RequireAdmin.tsx` + `.test.tsx`

Pattern: every gate reads `useAuthStore`, renders `<Outlet />` when permitted, `<Navigate to=... replace />` when not. Tests use `renderWithProviders` and assert via destination stub `data-testid`.

#### Step 9.1: Write RequireAuth test

- [ ] Create `frontend/src/components/gates/RequireAuth.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { RequireAuth } from './RequireAuth'

beforeEach(() => {
  useAuthStore.setState({ status: 'loading', user: null, error: null })
})

function ProtectedTree() {
  return (
    <Routes>
      <Route element={<RequireAuth />}>
        <Route path="/" element={<div data-testid="protected">ok</div>} />
      </Route>
      <Route path="/login" element={<div data-testid="route-login">login</div>} />
    </Routes>
  )
}

describe('RequireAuth', () => {
  it('redirects to /login when anon', async () => {
    useAuthStore.setState({ status: 'anon' })
    renderWithProviders(<ProtectedTree />, {
      initialEntries: ['/'],
      destinationStubs: [{ path: '/login', testId: 'route-login' }],
    })
    expect(await screen.findByTestId('route-login')).toBeInTheDocument()
  })

  it('renders the outlet when authed', () => {
    useAuthStore.getState().setUser({
      id: 1, username: 'a', email: null, role: 'user',
      is_active: true, has_seen_manual: true, has_passed_training: true,
      avatar_color: null, created_at: '2026-05-01T00:00:00+00:00',
    })
    renderWithProviders(<ProtectedTree />, {
      initialEntries: ['/'],
      destinationStubs: [{ path: '/login', testId: 'route-login' }],
    })
    expect(screen.getByTestId('protected')).toBeInTheDocument()
  })
})
```

#### Step 9.2: Run → FAIL

- [ ] Run: `cd frontend && npm run test:run -- src/components/gates/RequireAuth`

#### Step 9.3: Implement `RequireAuth.tsx`

- [ ] Create `frontend/src/components/gates/RequireAuth.tsx`:

```tsx
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

export function RequireAuth() {
  const status = useAuthStore((s) => s.status)
  const location = useLocation()

  if (status === 'anon') {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  // status==='authed' OR (loading/error — App's LoadingScreen is rendered
  // OUTSIDE the route tree, so by the time this gate runs we are authed).
  return <Outlet />
}
```

#### Step 9.4: Run → PASS

- [ ] Run: `cd frontend && npm run test:run -- src/components/gates/RequireAuth`

Expected: 2 PASS.

#### Step 9.5: Write RequireSeenManual test

- [ ] Create `frontend/src/components/gates/RequireSeenManual.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { RequireSeenManual } from './RequireSeenManual'

const baseUser = {
  id: 1, username: 'u', email: null, role: 'user' as const,
  is_active: true, avatar_color: null, created_at: '2026-05-01T00:00:00+00:00',
}

beforeEach(() => useAuthStore.setState({ status: 'loading', user: null, error: null }))

function Tree() {
  return (
    <Routes>
      <Route element={<RequireSeenManual />}>
        <Route path="/" element={<div data-testid="ok">ok</div>} />
      </Route>
      <Route path="/help" element={<div data-testid="route-help">help</div>} />
    </Routes>
  )
}

describe('RequireSeenManual', () => {
  it('redirects to /help?first_time=true when has_seen_manual is false', async () => {
    useAuthStore.getState().setUser({
      ...baseUser, has_seen_manual: false, has_passed_training: true,
    })
    renderWithProviders(<Tree />, {
      initialEntries: ['/'],
      destinationStubs: [{ path: '/help', testId: 'route-help' }],
    })
    expect(await screen.findByTestId('route-help')).toBeInTheDocument()
  })

  it('renders outlet when has_seen_manual is true', () => {
    useAuthStore.getState().setUser({
      ...baseUser, has_seen_manual: true, has_passed_training: true,
    })
    renderWithProviders(<Tree />, {
      initialEntries: ['/'],
      destinationStubs: [{ path: '/help', testId: 'route-help' }],
    })
    expect(screen.getByTestId('ok')).toBeInTheDocument()
  })
})
```

#### Step 9.6: Implement `RequireSeenManual.tsx`

- [ ] Create `frontend/src/components/gates/RequireSeenManual.tsx`:

```tsx
import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

export function RequireSeenManual() {
  const user = useAuthStore((s) => s.user)
  if (user && !user.has_seen_manual) {
    return <Navigate to="/help?first_time=true" replace />
  }
  return <Outlet />
}
```

#### Step 9.7: Write RequirePassedTraining test

- [ ] Create `frontend/src/components/gates/RequirePassedTraining.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { RequirePassedTraining } from './RequirePassedTraining'

const baseUser = {
  id: 1, username: 'u', email: null, role: 'user' as const,
  is_active: true, avatar_color: null, created_at: '2026-05-01T00:00:00+00:00',
}

beforeEach(() => useAuthStore.setState({ status: 'loading', user: null, error: null }))

function Tree() {
  return (
    <Routes>
      <Route element={<RequirePassedTraining />}>
        <Route path="/" element={<div data-testid="ok">ok</div>} />
      </Route>
      <Route path="/training" element={<div data-testid="route-training">training</div>} />
    </Routes>
  )
}

describe('RequirePassedTraining', () => {
  it('redirects to /training when has_passed_training is false', async () => {
    useAuthStore.getState().setUser({
      ...baseUser, has_seen_manual: true, has_passed_training: false,
    })
    renderWithProviders(<Tree />, {
      initialEntries: ['/'],
      destinationStubs: [{ path: '/training', testId: 'route-training' }],
    })
    expect(await screen.findByTestId('route-training')).toBeInTheDocument()
  })

  it('renders outlet when has_passed_training is true', () => {
    useAuthStore.getState().setUser({
      ...baseUser, has_seen_manual: true, has_passed_training: true,
    })
    renderWithProviders(<Tree />, {
      initialEntries: ['/'],
      destinationStubs: [{ path: '/training', testId: 'route-training' }],
    })
    expect(screen.getByTestId('ok')).toBeInTheDocument()
  })
})
```

#### Step 9.8: Implement `RequirePassedTraining.tsx`

- [ ] Create `frontend/src/components/gates/RequirePassedTraining.tsx`:

```tsx
import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

export function RequirePassedTraining() {
  const user = useAuthStore((s) => s.user)
  if (user && !user.has_passed_training) {
    return <Navigate to="/training" replace />
  }
  return <Outlet />
}
```

#### Step 9.9: Write RequireAdmin test

- [ ] Create `frontend/src/components/gates/RequireAdmin.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { RequireAdmin } from './RequireAdmin'

const baseUser = {
  id: 1, username: 'u', email: null,
  is_active: true, has_seen_manual: true, has_passed_training: true,
  avatar_color: null, created_at: '2026-05-01T00:00:00+00:00',
}

beforeEach(() => useAuthStore.setState({ status: 'loading', user: null, error: null }))

describe('RequireAdmin', () => {
  it('renders 404 fallback when user is not admin (existence-hide)', () => {
    useAuthStore.getState().setUser({ ...baseUser, role: 'user' })
    renderWithProviders(<RequireAdmin><div data-testid="admin-page">admin</div></RequireAdmin>)
    expect(screen.queryByTestId('admin-page')).toBeNull()
    expect(screen.getByText(/sayfa bulunamadı/i)).toBeInTheDocument()
  })

  it('renders children when user is admin', () => {
    useAuthStore.getState().setUser({ ...baseUser, role: 'admin' })
    renderWithProviders(<RequireAdmin><div data-testid="admin-page">admin</div></RequireAdmin>)
    expect(screen.getByTestId('admin-page')).toBeInTheDocument()
  })
})
```

#### Step 9.10: Implement `RequireAdmin.tsx`

- [ ] Create `frontend/src/components/gates/RequireAdmin.tsx`:

```tsx
import { type ReactNode } from 'react'
import { useAuthStore } from '@/stores/authStore'

interface Props {
  children: ReactNode
}

export function RequireAdmin({ children }: Props) {
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin')
  if (!isAdmin) {
    // Existence-hide: render the 404 surface instead of redirecting,
    // matching the backend's policy that non-admins never learn /admin/* exists.
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3">
        <p className="text-lg font-medium">Sayfa bulunamadı</p>
      </div>
    )
  }
  return <>{children}</>
}
```

#### Step 9.11: Run all gate tests

- [ ] Run: `cd frontend && npm run test:run -- src/components/gates`

Expected: 8 PASS (4 gates × 2 tests).

#### Step 9.12: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/components/gates/
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): 4 routing gates — auth, manual, training, admin

Each gate reads useAuthStore and either renders Outlet (or children
for RequireAdmin) or Navigate to the appropriate destination.

- RequireAuth: anon → /login (preserves location.state.from for
  post-login return)
- RequireSeenManual: !user.has_seen_manual → /help?first_time=true
- RequirePassedTraining: !user.has_passed_training → /training
- RequireAdmin: non-admin renders a 404 surface inline (existence-hide:
  no redirect, no leakage that /admin/* exists)

All 4 gates are active in 16a; gated destinations are STUBs until 16c
(Help, Training content) and 16e (admin pages).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: `api/queries/auth.ts` — useMe + 3 mutations

**Files:**
- Create: `frontend/src/api/queries/auth.ts`
- Create: `frontend/src/api/queries/auth.test.tsx`

#### Step 10.1: Write the failing test

- [ ] Create `frontend/src/api/queries/auth.test.tsx`:

```tsx
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act, waitFor, screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { server } from '@/test/msw-server'
import { mockAuthedUser, makeUser } from '@/test/msw-handlers'
import { http, HttpResponse } from 'msw'
import {
  useMe,
  useLoginMutation,
  useRegisterMutation,
  useLogoutMutation,
} from './auth'

beforeEach(() => {
  useAuthStore.setState({ status: 'loading', user: null, error: null })
})

describe('useMe', () => {
  it('returns user data when authed status', async () => {
    server.use(mockAuthedUser({ username: 'alice' }))
    useAuthStore.setState({ status: 'authed' }) // enabled gate
    function Probe() {
      const q = useMe()
      return <div data-testid="result">{q.data?.username ?? 'pending'}</div>
    }
    renderWithProviders(<Probe />)
    await waitFor(() =>
      expect(screen.getByTestId('result').textContent).toBe('alice'),
    )
  })

  it('is disabled when status is anon', () => {
    useAuthStore.setState({ status: 'anon' })
    function Probe() {
      const q = useMe()
      return <div data-testid="state">{q.isPending && !q.isFetching ? 'idle' : 'active'}</div>
    }
    renderWithProviders(<Probe />)
    expect(screen.getByTestId('state').textContent).toBe('idle')
  })
})

describe('useRegisterMutation', () => {
  it('on success: shows toast and navigates to /login (NOT authed)', async () => {
    const Toaster = await import('sonner')
    const toastSpy = vi.spyOn(Toaster.toast, 'success')

    function Probe() {
      const m = useRegisterMutation()
      return (
        <button
          data-testid="trigger"
          onClick={() =>
            m.mutate({ username: 'new', password: 'Strong1!', invite_code: 'XYZ' })
          }
        >
          go
        </button>
      )
    }
    renderWithProviders(<Probe />, { initialEntries: ['/register'] })
    act(() => screen.getByTestId('trigger').click())
    await waitFor(() =>
      expect(screen.getByTestId('route-login')).toBeInTheDocument(),
    )
    expect(toastSpy).toHaveBeenCalled()
    // authStore must NOT be seeded — backend register did not set a session
    expect(useAuthStore.getState().status).not.toBe('authed')
  })
})

describe('useLogoutMutation', () => {
  it('clears authStore, clears queries, navigates to /login', async () => {
    useAuthStore.getState().setUser(makeUser())
    function Probe() {
      const m = useLogoutMutation()
      return (
        <button data-testid="trigger" onClick={() => m.mutate()}>
          go
        </button>
      )
    }
    renderWithProviders(<Probe />, { initialEntries: ['/'] })
    act(() => screen.getByTestId('trigger').click())
    await waitFor(() => expect(useAuthStore.getState().status).toBe('anon'))
    await waitFor(() =>
      expect(screen.getByTestId('route-login')).toBeInTheDocument(),
    )
  })
})

describe('useLoginMutation', () => {
  it('on success: makes a follow-up /me call, seeds authStore', async () => {
    server.use(
      http.post('/api/auth/login', () => HttpResponse.json({ ok: true })),
      mockAuthedUser({ username: 'bob' }),
    )
    function Probe() {
      const m = useLoginMutation()
      return (
        <button
          data-testid="trigger"
          onClick={() => m.mutate({ username: 'bob', password: 'pw' })}
        >
          go
        </button>
      )
    }
    renderWithProviders(<Probe />, { initialEntries: ['/login'] })
    act(() => screen.getByTestId('trigger').click())
    await waitFor(() => expect(useAuthStore.getState().status).toBe('authed'))
    expect(useAuthStore.getState().user?.username).toBe('bob')
  })

  it('on failure: surfaces ApiError, does NOT seed authStore', async () => {
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json(
          { detail: { error: 'invalid_credentials', message: 'Şifre hatalı' } },
          { status: 401 },
        ),
      ),
    )
    function Probe() {
      const m = useLoginMutation()
      return (
        <>
          <button data-testid="trigger" onClick={() => m.mutate({ username: 'x', password: 'y' })}>
            go
          </button>
          <div data-testid="state">{m.isError ? `err:${(m.error as any).code}` : '...'}</div>
        </>
      )
    }
    renderWithProviders(<Probe />, { initialEntries: ['/login'] })
    act(() => screen.getByTestId('trigger').click())
    await waitFor(() =>
      expect(screen.getByTestId('state').textContent).toBe('err:invalid_credentials'),
    )
    expect(useAuthStore.getState().status).not.toBe('authed')
  })
})
```

#### Step 10.2: Run → FAIL

- [ ] Run: `cd frontend && npm run test:run -- src/api/queries/auth.test.tsx`

#### Step 10.3: Implement `auth.ts`

- [ ] Create `frontend/src/api/queries/auth.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { client, unwrap, unwrapVoid } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import type { components } from '@/api/types'

type User = components['schemas']['UserOut']
type RegisterInput = components['schemas']['RegisterRequest']
type LoginInput = components['schemas']['LoginRequest']

export const authKeys = {
  me: ['auth', 'me'] as const,
}

export function useMe() {
  const status = useAuthStore((s) => s.status)
  return useQuery({
    queryKey: authKeys.me,
    queryFn: async ({ signal }) =>
      unwrap(await client.GET('/api/auth/me', { signal })),
    enabled: status !== 'anon' && status !== 'loading',
    refetchOnWindowFocus: true,
    staleTime: 60_000,
  })
}

export function useLoginMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: LoginInput): Promise<User> => {
      await unwrapVoid(await client.POST('/api/auth/login', { body: input }))
      // Backend returns {ok:true}; pull user via second /me call.
      return unwrap(await client.GET('/api/auth/me'))
    },
    onSuccess: (user) => {
      useAuthStore.getState().setUser(user)
      qc.setQueryData(authKeys.me, user)
    },
  })
}

export function useRegisterMutation() {
  const navigate = useNavigate()
  return useMutation({
    mutationFn: async (input: RegisterInput): Promise<User> =>
      // Backend /api/auth/register returns UserOut (201) but does NOT
      // establish a session cookie. Treat as "create account, log in next".
      unwrap(await client.POST('/api/auth/register', { body: input })),
    onSuccess: () => {
      toast.success('Hesabınız oluşturuldu. Lütfen giriş yapın.')
      navigate('/login')
    },
  })
}

export function useLogoutMutation() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => unwrapVoid(await client.POST('/api/auth/logout')),
    onSuccess: async () => {
      await qc.cancelQueries()
      qc.clear()
      useAuthStore.getState().clear()
      navigate('/login')
    },
  })
}
```

#### Step 10.4: Run → PASS

- [ ] Run: `cd frontend && npm run test:run -- src/api/queries/auth.test.tsx`

Expected: 6 PASS. If any fail, the most common cause is the `enabled: status !== 'anon' && status !== 'loading'` gate — verify the test sets status correctly before rendering.

#### Step 10.5: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/api/queries/
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): auth queries — useMe + login/register/logout mutations

- useMe: useQuery with status-driven enabled gate; refetchOnWindowFocus
  override for session-critical surface; threads {signal} for cancellation
- useLoginMutation: POST /api/auth/login ({ok:true}), then GET /api/auth/me
  for user payload; seeds authStore + primes query cache via qc.setQueryData
- useRegisterMutation: POST /api/auth/register; backend returns UserOut
  but does NOT set a session cookie, so onSuccess shows success toast
  and navigates to /login (does NOT seed authStore)
- useLogoutMutation: POST /api/auth/logout, cancel + clear queries,
  clear authStore, navigate to /login

All hooks use useQueryClient() (NEVER imports a queryClient symbol —
that would break test isolation).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: `useAuth` convenience hook

**Why now:** Login/Register routes consume `useAuth` for terse access to the store + mutations + status helpers.

**Files:**
- Create: `frontend/src/hooks/useAuth.ts`
- Create: `frontend/src/hooks/useAuth.test.tsx`

#### Step 11.1: Write the failing test

- [ ] Create `frontend/src/hooks/useAuth.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { type ReactNode } from 'react'
import { useAuth } from './useAuth'
import { useAuthStore } from '@/stores/authStore'

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>
    <MemoryRouter>{children}</MemoryRouter>
  </QueryClientProvider>
)

beforeEach(() => useAuthStore.setState({ status: 'loading', user: null, error: null }))

describe('useAuth', () => {
  it('exposes status, user, isAuthed, isAdmin', () => {
    useAuthStore.getState().setUser({
      id: 1, username: 'a', email: null, role: 'admin',
      is_active: true, has_seen_manual: true, has_passed_training: true,
      avatar_color: null, created_at: '2026-05-01T00:00:00+00:00',
    })
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.status).toBe('authed')
    expect(result.current.user?.username).toBe('a')
    expect(result.current.isAuthed).toBe(true)
    expect(result.current.isAdmin).toBe(true)
  })

  it('exposes loginMutation, registerMutation, logoutMutation', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(typeof result.current.loginMutation.mutate).toBe('function')
    expect(typeof result.current.registerMutation.mutate).toBe('function')
    expect(typeof result.current.logoutMutation.mutate).toBe('function')
  })
})
```

#### Step 11.2: Implement `useAuth.ts`

- [ ] Create `frontend/src/hooks/useAuth.ts`:

```ts
import { useAuthStore, selectIsAuthed, selectIsAdmin } from '@/stores/authStore'
import {
  useLoginMutation,
  useRegisterMutation,
  useLogoutMutation,
} from '@/api/queries/auth'

export function useAuth() {
  const status = useAuthStore((s) => s.status)
  const user = useAuthStore((s) => s.user)
  const error = useAuthStore((s) => s.error)
  const isAuthed = useAuthStore(selectIsAuthed)
  const isAdmin = useAuthStore(selectIsAdmin)

  const loginMutation = useLoginMutation()
  const registerMutation = useRegisterMutation()
  const logoutMutation = useLogoutMutation()

  return {
    status,
    user,
    error,
    isAuthed,
    isAdmin,
    loginMutation,
    registerMutation,
    logoutMutation,
  }
}
```

#### Step 11.3: Run → PASS

- [ ] Run: `cd frontend && npm run test:run -- src/hooks`

Expected: 2 PASS.

#### Step 11.4: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/hooks/
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): useAuth convenience hook

Single import surface for routes: status, user, error, isAuthed, isAdmin
selectors + the 3 mutations. Routes/components SHOULD prefer useAuth over
reaching into useAuthStore + each mutation hook directly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Routes — Login, Register, NotFound + 5 STUBs

**Files:**
- Create: `frontend/src/routes/Login.tsx` + `.test.tsx`
- Create: `frontend/src/routes/Register.tsx` + `.test.tsx`
- Create: `frontend/src/routes/NotFound.tsx`
- Create: `frontend/src/routes/Annotate.tsx`, `Profile.tsx`, `Help.tsx`, `Training.tsx`, `admin/AdminLayout.tsx` (STUBs)

#### Step 12.1: Write Login test

- [ ] Create `frontend/src/routes/Login.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/msw-server'
import { http, HttpResponse } from 'msw'
import { mockAuthedUser } from '@/test/msw-handlers'
import { useAuthStore } from '@/stores/authStore'
import { Login } from './Login'

describe('Login route', () => {
  it('on submit success: authed + navigates to /', async () => {
    server.use(
      http.post('/api/auth/login', () => HttpResponse.json({ ok: true })),
      mockAuthedUser({ username: 'baran' }),
    )
    const user = userEvent.setup()
    renderWithProviders(<Login />, { initialEntries: ['/login'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), 'baran')
    await user.type(screen.getByLabelText(/şifre/i), 'pw123456')
    await user.click(screen.getByRole('button', { name: /giriş yap/i }))
    await waitFor(() => expect(useAuthStore.getState().status).toBe('authed'))
    await waitFor(() => expect(screen.getByTestId('route-root')).toBeInTheDocument())
  })

  it('on invalid credentials: shows error, stays on form', async () => {
    server.use(
      http.post('/api/auth/login', () =>
        HttpResponse.json(
          { detail: { error: 'invalid_credentials', message: 'Şifre hatalı' } },
          { status: 401 },
        ),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<Login />, { initialEntries: ['/login'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), 'baran')
    await user.type(screen.getByLabelText(/şifre/i), 'wrongpw')
    await user.click(screen.getByRole('button', { name: /giriş yap/i }))
    await waitFor(() => expect(screen.getByText(/şifre hatalı/i)).toBeInTheDocument())
    expect(useAuthStore.getState().status).not.toBe('authed')
  })

  it('submit button is disabled when fields are empty (form-level validation)', () => {
    renderWithProviders(<Login />, { initialEntries: ['/login'] })
    expect(screen.getByRole('button', { name: /giriş yap/i })).toBeDisabled()
  })
})
```

#### Step 12.2: Implement `Login.tsx`

- [ ] Create `frontend/src/routes/Login.tsx`:

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ApiError } from '@/api/client'

export function Login() {
  const { loginMutation } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const disabled = username.length === 0 || password.length === 0

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    loginMutation.mutate(
      { username, password },
      { onSuccess: () => navigate('/') },
    )
  }

  const errorMessage =
    loginMutation.error instanceof ApiError
      ? loginMutation.error.message
      : loginMutation.isError
        ? 'Giriş yapılamadı'
        : null

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Giriş Yap</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Kullanıcı adı</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Şifre</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            {errorMessage && (
              <p className="text-sm text-destructive" role="alert">
                {errorMessage}
              </p>
            )}
            <Button type="submit" disabled={disabled || loginMutation.isPending} className="w-full">
              {loginMutation.isPending ? 'Giriş yapılıyor…' : 'Giriş yap'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
```

#### Step 12.3: Run Login tests → PASS

- [ ] Run: `cd frontend && npm run test:run -- src/routes/Login.test.tsx`

Expected: 3 PASS.

#### Step 12.4: Write Register test

- [ ] Create `frontend/src/routes/Register.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/msw-server'
import { http, HttpResponse } from 'msw'
import { useAuthStore } from '@/stores/authStore'
import { Register } from './Register'

describe('Register route', () => {
  it('on success: navigates to /login (does NOT auth)', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Register />, { initialEntries: ['/register'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), 'newone')
    await user.type(screen.getByLabelText(/şifre/i), 'StrongPw1!')
    await user.type(screen.getByLabelText(/davet kodu/i), 'XYZ')
    await user.click(screen.getByRole('button', { name: /kayıt ol/i }))
    await waitFor(() => expect(screen.getByTestId('route-login')).toBeInTheDocument())
    expect(useAuthStore.getState().status).not.toBe('authed')
  })

  it('on 409 username taken: shows error', async () => {
    server.use(
      http.post('/api/auth/register', () =>
        HttpResponse.json({ detail: "username 'newone' already taken" }, { status: 409 }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<Register />, { initialEntries: ['/register'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), 'newone')
    await user.type(screen.getByLabelText(/şifre/i), 'StrongPw1!')
    await user.type(screen.getByLabelText(/davet kodu/i), 'XYZ')
    await user.click(screen.getByRole('button', { name: /kayıt ol/i }))
    await waitFor(() => expect(screen.getByText(/already taken/i)).toBeInTheDocument())
  })

  it('on 403 invalid invite: shows error', async () => {
    server.use(
      http.post('/api/auth/register', () =>
        HttpResponse.json({ detail: 'invalid invite code' }, { status: 403 }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<Register />, { initialEntries: ['/register'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), 'newone')
    await user.type(screen.getByLabelText(/şifre/i), 'StrongPw1!')
    await user.type(screen.getByLabelText(/davet kodu/i), 'WRONG')
    await user.click(screen.getByRole('button', { name: /kayıt ol/i }))
    await waitFor(() => expect(screen.getByText(/invalid invite/i)).toBeInTheDocument())
  })
})
```

#### Step 12.5: Implement `Register.tsx`

- [ ] Create `frontend/src/routes/Register.tsx`:

```tsx
import { useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ApiError } from '@/api/client'

export function Register() {
  const { registerMutation } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const disabled = !username || !password || !inviteCode

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    registerMutation.mutate({ username, password, invite_code: inviteCode })
  }

  const errorMessage =
    registerMutation.error instanceof ApiError
      ? registerMutation.error.message
      : registerMutation.isError
        ? 'Kayıt başarısız'
        : null

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Kayıt Ol</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Kullanıcı adı</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Şifre</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="invite">Davet kodu</Label>
              <Input
                id="invite"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
              />
            </div>
            {errorMessage && (
              <p className="text-sm text-destructive" role="alert">
                {errorMessage}
              </p>
            )}
            <Button
              type="submit"
              disabled={disabled || registerMutation.isPending}
              className="w-full"
            >
              {registerMutation.isPending ? 'Gönderiliyor…' : 'Kayıt ol'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
```

#### Step 12.6: Run Register tests → PASS

- [ ] Run: `cd frontend && npm run test:run -- src/routes/Register.test.tsx`

Expected: 3 PASS.

#### Step 12.7: Create `NotFound.tsx` + 5 STUB routes

- [ ] Create `frontend/src/routes/NotFound.tsx`:

```tsx
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <p className="text-3xl font-semibold">404</p>
      <p className="text-muted-foreground">Sayfa bulunamadı</p>
      <Button asChild>
        <Link to="/">Ana sayfaya dön</Link>
      </Button>
    </div>
  )
}
```

- [ ] Create `frontend/src/routes/Annotate.tsx` (STUB for 16b):

```tsx
export function Annotate() {
  return (
    <div className="p-8" data-testid="stub-annotate">
      <h1 className="text-xl font-semibold">Annotate</h1>
      <p className="text-sm text-muted-foreground">
        16b'de aktive edilecek (DocList, DocViewer, ReferencePanel).
      </p>
    </div>
  )
}
```

- [ ] Create `frontend/src/routes/Profile.tsx` (STUB for 16d):

```tsx
export function Profile() {
  return (
    <div className="p-8" data-testid="stub-profile">
      <h1 className="text-xl font-semibold">Profil</h1>
      <p className="text-sm text-muted-foreground">16d'de doldurulacak.</p>
    </div>
  )
}
```

- [ ] Create `frontend/src/routes/Help.tsx` (STUB for 16c):

```tsx
export function Help() {
  return (
    <div className="p-8" data-testid="stub-help">
      <h1 className="text-xl font-semibold">Yardım</h1>
      <p className="text-sm text-muted-foreground">16c'de doldurulacak.</p>
    </div>
  )
}
```

- [ ] Create `frontend/src/routes/Training.tsx` (STUB for 16c):

```tsx
export function Training() {
  return (
    <div className="p-8" data-testid="stub-training">
      <h1 className="text-xl font-semibold">Eğitim</h1>
      <p className="text-sm text-muted-foreground">16c'de doldurulacak.</p>
    </div>
  )
}
```

- [ ] Create `frontend/src/routes/admin/AdminLayout.tsx` (STUB for 16e):

```tsx
export function AdminLayout() {
  return (
    <div className="p-8" data-testid="stub-admin">
      <h1 className="text-xl font-semibold">Yönetici Paneli</h1>
      <p className="text-sm text-muted-foreground">16e'de doldurulacak.</p>
    </div>
  )
}
```

#### Step 12.8: Run all frontend tests, verify no regressions

- [ ] Run: `cd frontend && npm run test:run`

Expected: all tests PASS.

#### Step 12.9: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/routes/
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): routes — Login, Register, NotFound + 5 STUBs

Real routes:
- Login: form (username/password), submits via useLoginMutation, on
  success navigates to /. Shows ApiError.message inline on failure.
- Register: form (username/password/invite_code), submits via
  useRegisterMutation. Mutation onSuccess shows toast and navigates
  to /login (backend register does not set a session). 409/403/422
  errors surface inline.
- NotFound: 404 surface with link back to /.

STUBs (each is a single component that confirms the route resolved;
content populates in later paketler):
- Annotate (16b), Profile (16d), Help (16c), Training (16c),
  admin/AdminLayout (16e)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: App.tsx (gates + hydration) + main.tsx (providers + Router)

**Why now:** this composes everything. App.tsx houses the route tree from spec §5, the retryNonce-driven hydration effect, and the DI wiring. main.tsx owns the only `<BrowserRouter>` (B-1 invariant) and creates the QueryClient.

**Files:**
- Create: `frontend/src/App.tsx` + `frontend/src/App.test.tsx`
- Create: `frontend/src/main.tsx`

#### Step 13.1: Write App test FIRST

- [ ] Create `frontend/src/App.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '@/test/msw-server'
import { http, HttpResponse } from 'msw'
import { mockAuthedUser, mockAnonUser, makeUser } from '@/test/msw-handlers'
import { useAuthStore } from '@/stores/authStore'
import { renderWithProviders } from '@/test/render'
import App from './App'

beforeEach(() => useAuthStore.setState({ status: 'loading', user: null, error: null }))

describe('App hydration', () => {
  it('starts in loading, transitions to authed, renders root', async () => {
    server.use(mockAuthedUser({ username: 'bob' }))
    renderWithProviders(<App />, { initialEntries: ['/'] })
    expect(screen.getByText('Yükleniyor…')).toBeInTheDocument()
    await waitFor(() => expect(useAuthStore.getState().status).toBe('authed'))
    await waitFor(() => expect(screen.getByTestId('stub-annotate')).toBeInTheDocument())
  })

  it('starts in loading, transitions to anon on 401, redirects /login', async () => {
    server.use(mockAnonUser())
    renderWithProviders(<App />, { initialEntries: ['/'] })
    await waitFor(() => expect(useAuthStore.getState().status).toBe('anon'))
    // RequireAuth redirects to /login; the Login form should render
    await waitFor(() => expect(screen.getByRole('button', { name: /giriş yap/i })).toBeInTheDocument())
  })

  it('on network error: shows error mode + retry button works', async () => {
    let callCount = 0
    server.use(
      http.get('/api/auth/me', () => {
        callCount += 1
        if (callCount === 1) {
          return HttpResponse.error()
        }
        return HttpResponse.json(makeUser({ username: 'recovered' }))
      }),
    )
    renderWithProviders(<App />, { initialEntries: ['/'] })
    await waitFor(() =>
      expect(screen.getByText(/Sunucuya bağlanılamadı/i)).toBeInTheDocument(),
    )

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /tekrar dene/i }))
    await waitFor(() => expect(useAuthStore.getState().status).toBe('authed'))
    expect(callCount).toBe(2)
  })
})
```

#### Step 13.2: Run → FAIL (App.tsx doesn't exist yet)

- [ ] Run: `cd frontend && npm run test:run -- src/App.test.tsx`

#### Step 13.3: Implement `App.tsx`

- [ ] Create `frontend/src/App.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { useNavigate, useQueryClient, Route, Routes } from 'react-router-dom'
import {
  client,
  setNavigator,
  setAuthHandlers,
  markHydrated,
} from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { authKeys } from '@/api/queries/auth'
import { LoadingScreen } from '@/components/shell/LoadingScreen'
import { AppShell } from '@/components/shell/AppShell'
import { RequireAuth } from '@/components/gates/RequireAuth'
import { RequireSeenManual } from '@/components/gates/RequireSeenManual'
import { RequirePassedTraining } from '@/components/gates/RequirePassedTraining'
import { RequireAdmin } from '@/components/gates/RequireAdmin'
import { Login } from '@/routes/Login'
import { Register } from '@/routes/Register'
import { NotFound } from '@/routes/NotFound'
import { Annotate } from '@/routes/Annotate'
import { Profile } from '@/routes/Profile'
import { Help } from '@/routes/Help'
import { Training } from '@/routes/Training'
import { AdminLayout } from '@/routes/admin/AdminLayout'

export default function App() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [retryNonce, setRetryNonce] = useState(0)

  useEffect(() => setNavigator(navigate), [navigate])
  useEffect(() => {
    setAuthHandlers({
      onSessionExpired: () => useAuthStore.getState().clear(),
    })
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    let cancelled = false
    ;(async () => {
      try {
        const result = await client.GET('/api/auth/me', { signal: ctrl.signal })
        if (cancelled) return
        if (result.error !== undefined || result.response.status === 401) {
          useAuthStore.getState().clear()
        } else {
          const user = result.data!
          useAuthStore.getState().setUser(user)
          qc.setQueryData(authKeys.me, user)
        }
        markHydrated()
      } catch (e: any) {
        if (cancelled) return
        if (e?.name === 'AbortError') return
        useAuthStore.getState().setError(String(e?.message ?? e))
      }
    })()
    return () => {
      cancelled = true
      ctrl.abort()
    }
  }, [qc, retryNonce])

  const status = useAuthStore((s) => s.status)
  const handleRetry = () => {
    useAuthStore.getState().setStatus('loading')
    setRetryNonce((n) => n + 1)
  }

  if (status === 'loading') return <LoadingScreen />
  if (status === 'error') return <LoadingScreen mode="error" onRetry={handleRetry} />

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route element={<RequireAuth />}>
        <Route path="/help" element={<Help />} />

        <Route element={<RequireSeenManual />}>
          <Route path="/training" element={<Training />} />

          <Route element={<RequirePassedTraining />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<Annotate />} />
              <Route path="/me" element={<Profile />} />
            </Route>
          </Route>
        </Route>

        <Route
          path="/admin/*"
          element={
            <RequireAdmin>
              <AdminLayout />
            </RequireAdmin>
          }
        />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
```

#### Step 13.4: Run App tests → PASS

- [ ] Run: `cd frontend && npm run test:run -- src/App.test.tsx`

Expected: 3 PASS.

#### Step 13.5: Implement `main.tsx`

- [ ] Create `frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from '@/components/ui/sonner'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ApiError } from '@/api/client'
import App from './App'
import '@/styles/globals.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, err) => {
        if (err instanceof ApiError && err.status >= 400 && err.status < 500) return false
        return failureCount < 1
      },
    },
    mutations: { retry: false },
  },
})

const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('Root element #root not found in index.html')

createRoot(rootEl).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
        <Toaster richColors closeButton />
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
```

#### Step 13.6: Run full frontend suite → PASS

- [ ] Run:

```bash
cd frontend
npm run test:run
```

Expected: all tests PASS. If anything related to React act warnings shows up, investigate but only fix if it blocks; otherwise these are noise.

#### Step 13.7: Verify typecheck + build

- [ ] Run:

```bash
cd frontend
npm run typecheck
npm run build
```

Expected: typecheck PASS, build produces `../backend/static/` with `index.html`, `assets/*.js`, `assets/*.css`, and `favicon.svg`.

#### Step 13.8: Commit

- [ ] Run from repo root:

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/main.tsx
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket-16a): App.tsx hydration + main.tsx provider entry

App.tsx:
- retryNonce-driven hydration effect (mount + Tekrar dene both fire the
  same /api/auth/me path; status flip plus nonce bump together provide
  immediate UI feedback AND re-run the effect)
- DI wiring: setNavigator (Router-bound), setAuthHandlers (clear on
  session expiry)
- Cache priming: qc.setQueryData(authKeys.me, user) on success avoids
  duplicate /me fetch right after hydration
- Full route tree from spec §5: 4 gate layers, AppShell wraps gated
  app routes, /admin/* wrapped in RequireAdmin (existence-hide)
- LoadingScreen for status==='loading' and 'error' (with onRetry)

main.tsx:
- The ONLY BrowserRouter in the app (App must not own one — would
  conflict with MemoryRouter in tests)
- QueryClient with global defaults (staleTime, gcTime,
  refetchOnWindowFocus=false, 4xx-no-retry retry policy)
- StrictMode + ErrorBoundary + Toaster outermost

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: Frontend README + integration smoke + final verification

**Files:**
- Create: `frontend/README.md`
- (verify, no source changes)

#### Step 14.1: Create `frontend/README.md`

- [ ] Create `frontend/README.md`:

```markdown
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
```

#### Step 14.2: Run the FULL quality gate sequence

- [ ] Run:

```bash
cd frontend
npm run typecheck
npm run lint
npm run format:check
npm run test:coverage
npm run build
```

Expected: all green. Coverage report shows ≥80% on each metric (statements, branches, lines, functions). If coverage falls short, identify the under-covered file and add at most one targeted test — DO NOT pad with tautology tests.

#### Step 14.3: Run the FULL backend suite

- [ ] Run from repo root:

```bash
.venv/bin/python -m pytest -x -q
```

Expected: all green, no regressions from T1 backend touches.

#### Step 14.4: Manual end-to-end smoke

- [ ] In terminal A:

```bash
.venv/bin/uvicorn backend.main:app --port 8000
```

- [ ] In terminal B (with `frontend/dist` already built):

```bash
curl -s http://127.0.0.1:8000/ | head -3
curl -s http://127.0.0.1:8000/api/health
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/login
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/assets/index-XXXXX.js  # replace with actual hashed asset
```

Expected:
- `/` returns `<!doctype html>` (SPA index)
- `/api/health` returns `{"status":"ok","version":"..."}`
- `/login` returns 200 with `<!doctype html>` (SPA fallback for client routes)
- `/assets/<hashed>.js` returns 200 with `application/javascript`

Stop the uvicorn process.

#### Step 14.5: Run integration contract checklist (spec §10)

- [ ] Verify manually:

```bash
ls frontend/src/api/types.ts                                    # exists, committed
grep -c "VITE_" frontend/.env.example                           # ≥1
grep "backend/static/" .gitignore                               # present
grep "DISABLE_SPA_MOUNT" backend/main.py                        # present
.venv/bin/python -m backend.cli openapi-dump --output /tmp/o.json && echo "ok"
grep "DISABLE_SPA_MOUNT" tests/conftest.py                      # present
grep -rn "queryFn.*signal\|queryFn:.*signal" frontend/src/api/queries/  # signal threaded
grep -rn "react-refresh/only-export-components" frontend/eslint.config.js  # rule present
```

Expected: each command produces evidence the spec contract is satisfied.

#### Step 14.6: Commit README + final state

- [ ] Run from repo root:

```bash
git add frontend/README.md
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
docs(paket-16a): frontend README — dev workflow + quality gates

Two-terminal dev recipe (backend uvicorn + Vite proxy), type regen
both with-backend and offline, shadcn add commands, production build
pipeline, quality-gate command sequence, dependency-pin policy.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

#### Step 14.7: Tag the final commit

- [ ] Run:

```bash
git tag paket-16a-frontend-foundation
git log --oneline | head -16
```

Expected: 14 paket-16a commits at the top of the log (T1..T14) plus the tag pointing at T14.

---

## Self-Review Checklist (run when plan is fully executed)

- [ ] All 14 tasks committed atomically
- [ ] Each task's tests added and green
- [ ] `npm run test:coverage` ≥80% on all 4 metrics
- [ ] `npm run typecheck && lint && format:check && build` green
- [ ] Backend `pytest -x -q` green (no regression from T1 touches)
- [ ] `backend/static/` is the Vite build output, not committed (root `.gitignore`)
- [ ] `frontend/src/api/types.ts` IS committed
- [ ] `DISABLE_SPA_MOUNT=1` is set at top of `tests/conftest.py`
- [ ] `frontend/src/App.tsx` does NOT wrap a `<BrowserRouter>` (Router is in main.tsx only)
- [ ] `useRegisterMutation` navigates to `/login` on success (does NOT seed authStore)
- [ ] `useLoginMutation` and `useRegisterMutation` use `useQueryClient()` (no imported `queryClient` symbol)
- [ ] Coverage thresholds present in `vite.config.ts`
- [ ] `eslint.config.js` is the 3-block flat config (inlined, not referenced)
- [ ] `gen:openapi` script uses `cd ..` so backend imports resolve

## Out of scope (deferred to 16b-f + later)

Documented in spec §13. Notable items NOT to be touched in this plan:
- Annotate workflow, DocList virtual scroll, SSE, lock heartbeat (→16b)
- Help markdown viewer, Training quiz (→16c)
- TopBar gamification, Profile XP/badges (→16d)
- Admin Users/Audit/Settings/Locks (→16e)
- Multi-stage Dockerfile reconcile (→16f)
- CI workflows, Playwright E2E (→Paket 17)
