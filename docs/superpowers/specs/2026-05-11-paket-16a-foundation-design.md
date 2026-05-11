# Paket 16a — Frontend Foundation

**Status:** DESIGN APPROVED — ready for plan
**Date:** 2026-05-11
**Depends on:** Paket 1-15 (entire backend feature set + Docker single-stage)
**Tag at end:** `paket-16a-foundation`
**Part of:** Paket 16 decomposed into 6 sub-paketler (16a..16f); 16a is the foundation that all subsequent frontend paketler build upon.

---

## 1. Problem & Goal

The annotation platform backend ships 41 endpoints across 13 modules (auth, users, documents, annotations, locks, shuffle, training, notifications, admin, exports, backup, retention, SSE) but no frontend. End users currently access the system only via Swagger UI at `/docs`.

**Goal:** scaffold a production-grade React 18 + Vite SPA foundation that subsequent paketler (16b annotate, 16c onboarding, 16d gamification, 16e admin, 16f Docker reconcile) extend. 16a delivers a working but minimal vertical slice — Login → Register → "you are logged in" stub — so the architectural decisions (state management, API client, routing gates, test infra, build pipeline) are validated end-to-end before feature work begins.

---

## 2. Scope (locked)

**IN scope (16a):**

- `frontend/` directory greenfield scaffold (Vite + TS + Tailwind + shadcn/ui)
- API client + `openapi-typescript` type generation pipeline + `openapi-fetch` typed minimal client
- Auth flow: Login + Register routes, 4 routing gates (RequireAuth, RequireSeenManual, RequirePassedTraining, RequireAdmin) all wired into the route tree and active in 16a. The onboarding gates redirect to STUB pages (Help/Training) that 16c populates with real content — the routing structure is complete; only the destination page content is deferred.
- 4-state `authStore` (Zustand) with blocking hydration sequence via `/api/auth/me`
- TanStack Query 5 configured (per-query overrides for session-critical, global retry strategy)
- ErrorBoundary, LoadingScreen (loading + error retry modes), minimal AppShell
- Vitest + RTL + MSW v2 test infrastructure with custom render helper
- ESLint flat config (3 blocks: app, test, Node config) + Prettier
- Dev workflow: Vite 5173 + uvicorn 8000 with Vite proxy
- Build pipeline: `npm run build` → `backend/static/`
- Backend touches: SPA fallback in `main.py`, `STATIC_DIR` in `config.py`, `openapi-dump` CLI command, autouse test fixture
- STUB routes for 16b-e destinations (so route tree compiles + Navigate side-effects observable)
- README with dev workflow + shadcn CLI usage

**OUT of scope (deferred to 16b-f + later paketler):**

- Annotate workflow (DocList virtual scroll, DocViewer, ReferencePanel, draft auto-save, lock heartbeat, SSE) → **16b**
- Onboarding pages (Help markdown viewer, Training quiz + gold-doc) → **16c**
- Gamification UI (TopBar XP/streak/progress, Profile, badges, notifications, SSE personal events) → **16d**
- Admin panel (Users, AuditLog, SystemEvents, Settings, Locks, Training admin, Backup/Retention/Export viewers) → **16e**
- Docker multi-stage reconcile (Paket 15 single-stage → +node:22-slim frontend-build stage) → **16f**
- CI/CD (GitHub Actions workflow, lint/test/build pipeline, type drift detection) → Paket 17
- E2E tests (Playwright multi-user simulation) → Paket 17
- Observability (JSON logs, /metrics, Sentry frontend) → later
- Performance optimization (lazy route loading, bundle analyzer) → later
- a11y full audit (axe-core, screen reader testing) → later (16a does WCAG AA via shadcn/Radix + eslint-plugin-jsx-a11y)
- Cross-tab session sync (BroadcastChannel) → later
- Runtime env (currently build-time only) → later
- PWA / offline support → later
- Dark mode (next-themes integration) → later
- i18n framework (TR-only with `lib/strings.ts` constants in 16a) → later if needed

---

## 3. Locked Decisions

### Stack

| Layer | Choice | Version | Why |
|---|---|---|---|
| Build tool | Vite | ^5.4 | Industry default; HMR; native ESM; Vitest integration |
| Language | TypeScript | ^5.6 | strict + exactOptionalPropertyTypes + noUncheckedIndexedAccess + verbatimModuleSyntax |
| UI framework | React | ^18.3 | Project requirement; 18 stable (not 19 — boring choice) |
| Routing | React Router | ^6.27 | Codex-confirmed; v7 not adopted (boring choice) |
| Server state | TanStack Query | ^5.59 | Codex-confirmed; SSE-driven invalidation pattern fits |
| Client state | Zustand | ^4.5 | Codex-confirmed; auth/UI state only, server state via TQ |
| Form | react-hook-form + zod + @hookform/resolvers | ^7.53 + ^3.23 + ^3.9 | Type-safe forms across all paketler |
| Virtual scroll | @tanstack/react-virtual | ^3.10 | 18K doc list (16b); declared in 16a for future use |
| Toast | sonner | ^1.5 | shadcn-integrated; non-blocking notifications |
| Type gen | openapi-typescript + openapi-fetch | ^7.4 + ~0.13 | Codex addition: typed minimal fetch client + types |
| CSS | Tailwind + shadcn/ui | ^3.4 + components.json | Copy-paste Radix primitives; design tokens |
| Date | date-fns + tr locale | ^3.6 | Tree-shakable; TR formatting |
| Icons | lucide-react | ~0.453 | shadcn-default; tree-shakable |
| Package manager | npm + npm ci | npm >=10 | Codex-confirmed: boring choice, single-dev |
| Node base | Node 22 LTS | engine-strict | Codex: 20 EOL Apr 2026 |
| Test | Vitest + RTL + MSW + jsdom | ^2.1 + ^16 + ^2.4 + ^25 | Codex-confirmed: classic combo, PCT not canonical yet |
| Lint | ESLint flat + typescript-eslint + react + react-hooks + jsx-a11y + react-refresh | ^9 + ^8 + ^7 + ^5 + ^6 + ^0.4 | Codex: ESLint flat is boring choice; Biome/oxlint parity still incomplete |
| Format | Prettier | ^3.3 | Standard |
| Vitest plugin | @vitest/eslint-plugin | ^1.1 | Codex addition: vitest globals + recommended rules |

### Architecture

| Decision | Choice | Why |
|---|---|---|
| Auth state shape | 4-state: `loading \| authed \| anon \| error` | Codex: avoid silent fall to anon on network failure; explicit error retry UX |
| Auth hydration | **Blocking** app shell → `/api/auth/me` → route or redirect | Codex: HttpOnly cookie not JS-readable; optimistic mount risks flicker + stale state |
| Auth state persist | NO localStorage persist | Server-driven; stale-on-reload flicker prevented |
| Login response shape | Backend returns `{ok:true}`; frontend makes second `/api/auth/me` call | Avoid backend change; ~100ms extra is negligible |
| Register response shape | Backend returns `UserOut` (201) but does NOT establish a session (current `backend/users/routes.py` behavior). Frontend treats register as "create account → redirect to /login with success toast" — no auto-login | Avoids backend behavior change for 16a; auto-login can be added in a follow-up paket if UX research justifies it |
| SPA mount toggle | Backend `main.py` SPA registration gated on `DISABLE_SPA_MOUNT=1` env flag (in addition to `STATIC_DIR.exists()` check) | Routes register at import time; env-flag-at-conftest-top is the only way to keep tests deterministic regardless of whether a developer has run `npm run build` |
| API client | `openapi-fetch` + DI setter pattern (`setNavigator`, `setAuthHandlers`, `markHydrated`) | No circular dep; testable; type-safe |
| Hydration flag | Explicit `hydrated: boolean` (NOT `authHandlersRef === null` sentinel) | Test isolation: each test starts with hydrated=false; tests opt into post-hydration |
| Error shape | `ApiError` (status, code, message, raw) + `UnexpectedEmptyResponse` | Handles 3 FastAPI detail shapes (string, object, array) |
| Empty body | `unwrapVoid()` for 204/`{ok:true}` endpoints | Explicit; `unwrap<T>()` throws on unexpected empty |
| TanStack Query global defaults | `staleTime: 30s, gcTime: 5min, refetchOnWindowFocus: false, retry: 4xx→0 / network→1 + mutations retry:0` | Per-query override for session-critical (`useMe`: refetchOnWindowFocus=true) |
| Signal threading | ALL `queryFn` pass `{ signal }` to `openapi-fetch` | Real cancellation; Codex-flagged FRAGILE without |
| Cache priming | App hydration → `qc.setQueryData(authKeys.me, user)` | Avoids duplicate `/api/auth/me` fetch right after hydration |
| Logout flow | `cancelQueries` → `clear` → `clear authStore` → `navigate('/login')` | Codex: prevent race with in-flight queries leaking to next user |
| Routing | RR6 nested layout routes + 4 gates composed via `<Outlet>` | Codex-confirmed; loaders NOT used (TanStack Query owns server state) |
| Path alias | Single `@/` → `src/` | Codex: shadcn convention; granular alias is unnecessary complexity |
| TS strict | strict + exactOptionalPropertyTypes + noUncheckedIndexedAccess + noImplicitOverride + noFallthroughCasesInSwitch + noUnusedLocals + noUnusedParameters + verbatimModuleSyntax + isolatedModules | User: "kalite > size" |
| Generated types | `src/api/types.ts` COMMITTED; `gen:types:check` script for drift | Fresh clone works without backend; CI drift detection → Paket 17 |
| Test render | `renderWithProviders` with QueryClient + MemoryRouter + destination stubs | Navigate side-effects observable via `getByTestId('route-...')` |
| Test cleanup | `activeQueryClients` Set + autouse afterEach; try/finally per-client | Codex round 4 + 5: leak prevention + log non-blocking failure |
| MSW handlers | Default = unauthenticated; opt-in `mockAuthedUser()` factory | Each test reasons about its auth state explicitly |
| Console silence | Opt-in `silenceConsoleError()` helper, NOT global suppress | Codex: global suppress hides real warnings |

### Backend HTTP route contract

ALL backend-served HTTP endpoints MUST live under the `/api/*` prefix. SPA fallback (`backend/main.py` extension-aware catch-all) owns everything else: `/`, `/login`, `/me`, `/admin/*`, `/favicon.svg`, `/robots.txt`.

**Exempt** (FastAPI built-ins, NOT under `/api/*`):
- `/docs` (Swagger UI)
- `/redoc` (ReDoc)
- `/openapi.json` (OpenAPI schema)

These are FastAPI defaults registered BEFORE the SPA fallback. In production, consider `docs_url=None, redoc_url=None, openapi_url=None` for admin-only schema access — Paket 17 hardening item.

**Convention going forward:** never add a backend endpoint outside `/api/*` (a future `/health` must be `/api/health`). Current code follows: `/api/health`, `/api/health/db`.

### Soft preferences

| Preference | Choice | Rationale |
|---|---|---|
| Dark mode | Light-only v1 | YAGNI; design tokens dual-theme ready; `next-themes` later |
| i18n | TR-only, no framework | Spec scope; `lib/strings.ts` constant table sufficient for now |
| a11y baseline | WCAG AA | shadcn/Radix + `eslint-plugin-jsx-a11y`; full audit later |
| Browser support | Modern evergreen (ES2022+, last 2 Chrome/Edge/Firefox/Safari) | 30-user internal tool; no IE/legacy bundle bloat |
| Bundle budget | <250 KB initial JS gzipped | Core ~145 KB + app ~30-60 KB realistic |
| Lighthouse | Perf ≥90, a11y ≥95, best-practices ≥90 | Reference for smoke polish |
| Source maps prod | Enabled | Single-instance, no leak risk, debug value high |
| Code/JSDoc language | English | React/TS ecosystem norm |
| UI strings language | Turkish | User-facing |
| Spec/plan/README language | Turkish | Project convention |

---

## 4. Folder Structure

```
frontend/
├── .editorconfig
├── .env.example                  # VITE_API_BASE_URL doc
├── .gitignore                    # node_modules/, coverage/, *.local, .env.*.local, etc.
├── .npmrc                        # engine-strict=true
├── .nvmrc                        # 22
├── .prettierrc
├── components.json               # shadcn config
├── eslint.config.js              # flat config, 3 blocks
├── index.html                    # Türkçe lang, font preload
├── package.json
├── package-lock.json             # deterministic via npm ci
├── postcss.config.js             # Tailwind + autoprefixer
├── README.md                     # dev entry: scripts, conventions, shadcn CLI
├── tailwind.config.ts
├── tsconfig.json                 # strict, paths @/*
├── tsconfig.node.json            # Vite config types
├── tsconfig.eslint.json          # type-aware lint (allowJs, vite/client types)
├── vite.config.ts                # dev proxy + outDir=../backend/static + Vitest inline
├── public/
│   ├── favicon.svg
│   └── robots.txt
└── src/
    ├── main.tsx                  # mount + providers (QueryClient, Router, Toaster, ErrorBoundary)
    ├── App.tsx                   # Route tree + gate composition + hydration useEffect
    ├── routes/
    │   ├── Login.tsx
    │   ├── Register.tsx
    │   ├── NotFound.tsx
    │   ├── Annotate.tsx          # STUB — "16b'de aktive edilecek"
    │   ├── Profile.tsx           # STUB (16d)
    │   ├── Help.tsx              # STUB (16c)
    │   ├── Training.tsx          # STUB (16c)
    │   └── admin/
    │       └── AdminLayout.tsx   # STUB (16e)
    ├── components/
    │   ├── ui/                   # shadcn initial set
    │   │   ├── button.tsx
    │   │   ├── input.tsx
    │   │   ├── label.tsx
    │   │   ├── form.tsx          # react-hook-form + zod wrapper
    │   │   ├── card.tsx
    │   │   └── sonner.tsx
    │   ├── gates/
    │   │   ├── RequireAuth.tsx
    │   │   ├── RequireSeenManual.tsx
    │   │   ├── RequirePassedTraining.tsx
    │   │   └── RequireAdmin.tsx
    │   ├── shell/
    │   │   ├── AppShell.tsx      # minimal header + Outlet
    │   │   └── LoadingScreen.tsx # 4-state aware (loading + error retry)
    │   └── ErrorBoundary.tsx
    ├── hooks/
    │   └── useAuth.ts            # wraps authStore + login/logout/me actions
    ├── api/
    │   ├── client.ts             # openapi-fetch + DI setters + interceptor
    │   ├── types.ts              # GENERATED by openapi-typescript, COMMITTED
    │   └── queries/
    │       └── auth.ts           # useMe, useLoginMutation, useRegisterMutation, useLogoutMutation
    ├── stores/
    │   └── authStore.ts          # Zustand 4-state
    ├── lib/
    │   ├── utils.ts              # shadcn cn() helper
    │   └── env.ts                # zod env schema validation
    ├── styles/
    │   └── globals.css           # Tailwind directives + shadcn CSS vars + base typography
    └── test/
        ├── setup.ts              # Vitest + jest-dom + MSW lifecycle + store/DI reset
        ├── msw-handlers.ts       # shared handlers + makeUser typed factory + mockAuthedUser/mockAnonUser
        ├── msw-server.ts         # setupServer instance
        └── render.tsx            # renderWithProviders helper with destination stubs + auto-cleanup
```

### Backend touches (16a)

```
backend/
├── config.py                     # + STATIC_DIR constant
├── main.py                       # + extension-aware SPA fallback + /assets mount (after /api/* routers)
└── cli.py                        # + openapi_dump Typer command
tests/
└── conftest.py                   # + autouse fixture: disable_spa_mount
```

Plus root `.gitignore`: `backend/static/` ignored.

---

## 5. Auth + Routing + Gates

### Provider tree

**Critical invariant**: `<BrowserRouter>` is owned by **main.tsx** (the only Router instance in the app). `App.tsx` runs INSIDE the Router context and is therefore allowed to call `useNavigate`, `useQueryClient`, etc. at the top level of its function body. App.tsx must NEVER wrap its own `<BrowserRouter>` (would shadow the parent Router; useNavigate in App would still work but every test using MemoryRouter via `renderWithProviders` would conflict).

```tsx
// src/main.tsx
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

createRoot(document.getElementById('root')!).render(
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

### Routing tree (RR6 nested layout routes)

```tsx
// src/App.tsx — renders <Routes> only; BrowserRouter is in main.tsx
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
      element={<RequireAdmin><AdminLayout /></RequireAdmin>}
    />
  </Route>

  <Route path="*" element={<NotFound />} />
</Routes>
```

**Gate semantics:**
- Public: login, register
- `RequireAuth`: anon → `/login`
- `RequireSeenManual`: `!has_seen_manual` → `/help?first_time=true`
- `RequirePassedTraining`: `!has_passed_training` → `/training`
- `RequireAdmin`: `role !== 'admin'` → 404 (existence-hide, matches backend)
- Admin tree bypasses manual/training gating (admin onboarding mantıksız)

### 4-state auth hydration

```
App mount → authStore.status = 'loading' (default)
  → useEffect: client.GET('/api/auth/me') with AbortController
    ├── 200 → setUser + qc.setQueryData(authKeys.me, user) + markHydrated() → status='authed'
    ├── 401 → clear() + markHydrated() → status='anon'
    └── network error → setError(msg) → status='error' (markHydrated NOT called → retry safe)

LoadingScreen renders while status === 'loading' or 'error'
  - 'loading': spinner + "Yükleniyor…"
  - 'error': AlertCircle + "Sunucuya bağlanılamadı" + [Tekrar dene] [Çıkış yap]
    - Tekrar dene: App holds a `retryNonce` state; the hydration `useEffect` includes `retryNonce` in its dependency array. The retry button calls `setRetryNonce(n => n + 1)` AND `authStore.setStatus('loading')` (status flip is what re-renders LoadingScreen out of error mode; nonce bump is what re-fires the effect).
```

### `authStore` (Zustand)

```ts
export type AuthStatus = 'loading' | 'authed' | 'anon' | 'error'

interface AuthState {
  status: AuthStatus
  user: User | null
  error: string | null
  setUser: (user: User) => void   // status → 'authed', error → null
  setError: (msg: string) => void // status → 'error'
  setStatus: (s: AuthStatus) => void // for retry transition
  clear: () => void                // status → 'anon', user/error → null
}
```

**No `persist` middleware** — server-driven hydration prevents localStorage flicker.

### 401 interceptor (DI setter pattern)

```ts
// api/client.ts — store imports YOK (circular dep önlemi)
let navigateRef: ((path: string) => void) | null = null
let authHandlersRef: { onSessionExpired: () => void } | null = null
let hydrated = false

export function setNavigator(fn: typeof navigateRef) { navigateRef = fn }
export function setAuthHandlers(h: typeof authHandlersRef) { authHandlersRef = h }
export function markHydrated() { hydrated = true }
export function _resetHydrationStateForTests() { hydrated = false }

const authInterceptor: Middleware = {
  async onResponse({ response, request }) {
    if (response.status !== 401) return
    const url = new URL(request.url)
    const isAuthMe = url.pathname === '/api/auth/me'
    if (isAuthMe && !hydrated) return  // hydration self-401 normal anon
    authHandlersRef?.onSessionExpired()
    navigateRef?.('/login')
  },
}
```

App.tsx wires DI via `useEffect`:

```tsx
useEffect(() => setNavigator(navigate), [navigate])
useEffect(() => {
  setAuthHandlers({ onSessionExpired: () => useAuthStore.getState().clear() })
}, [])
```

### CSRF / cookie / security

- Cookie: HttpOnly + SameSite=Lax (backend-side). Frontend never reads.
- CSRF: SameSite=Lax blocks cross-site state-changing requests. No additional CSRF token.
- Auth state source of truth: `/api/auth/me` response.
- Same-origin in prod (FastAPI single port serves SPA + API). Dev: Vite proxy preserves origin.

---

## 6. API + Types Pipeline + TanStack Query

### Type generation pipeline

**Scripts** (frontend/package.json):

```json
{
  "gen:openapi": "cd .. && python -m backend.cli openapi-dump --output openapi.json",
  "gen:types": "openapi-typescript http://127.0.0.1:8000/openapi.json -o src/api/types.ts",
  "gen:types:from-file": "openapi-typescript ../openapi.json -o src/api/types.ts",
  "gen:types:check": "npm run gen:openapi && npm run gen:types:from-file && git diff --exit-code src/api/types.ts"
}
```

The `cd ..` prefix is necessary because `python -m backend.cli` needs `backend` on `sys.path` — i.e., the repo root as cwd. Running from `frontend/` would not find the `backend` package (no editable install assumed). Output is `openapi.json` at the repo root so `gen:types:from-file` can read `../openapi.json` from `frontend/`. POSIX-only (Windows would need `cross-env-shell` or split scripts) — acceptable for this project (single-dev Mac/Linux).

**Backend addition** (backend/cli.py):

```python
@app.command()
def openapi_dump(output: Path = Path("openapi.json")) -> None:
    """Export FastAPI OpenAPI spec to JSON (frontend type gen için)."""
    import json
    from backend.main import app as fastapi_app
    output.write_text(json.dumps(fastapi_app.openapi(), indent=2))
    typer.echo(f"OpenAPI written to {output}")
```

**Workflow:**
- Backend running: `npm run gen:types`
- Backend not running: `python -m backend.cli openapi-dump` + `npm run gen:types:from-file`
- Drift check (local sanity): `npm run gen:types:check`
- `src/api/types.ts` COMMITTED (fresh clone works without backend)
- CI drift gate: Paket 17 item

### `api/client.ts` (final, post-adversarial)

```ts
import createClient, { Middleware } from 'openapi-fetch'
import type { paths } from './types'

// DI setters (no store imports — circular dep prevention)
let navigateRef: ((path: string) => void) | null = null
let authHandlersRef: { onSessionExpired: () => void } | null = null
let hydrated = false

export function setNavigator(fn: typeof navigateRef) { navigateRef = fn }
export function setAuthHandlers(h: typeof authHandlersRef) { authHandlersRef = h }
export function markHydrated() { hydrated = true }
/** Test-only: reset hydration flag for isolation. */
export function _resetHydrationStateForTests() { hydrated = false }

const authInterceptor: Middleware = {
  async onResponse({ response, request }) {
    if (response.status !== 401) return
    const url = new URL(request.url)
    const isAuthMe = url.pathname === '/api/auth/me'
    if (isAuthMe && !hydrated) return  // pre-hydration self-401 normal anon
    authHandlersRef?.onSessionExpired()
    navigateRef?.('/login')
  },
}

export const client = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '',
  credentials: 'include',
})
client.use(authInterceptor)

// Typed error classes
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly raw?: unknown,
  ) { super(message) }
}

export class UnexpectedEmptyResponse extends Error {}

type FetchResult<T> = { data?: T; error?: unknown; response: Response }

function parseErrorDetail(detail: unknown, status: number): { code: string; message: string } {
  if (typeof detail === 'string') {
    return { code: String(status), message: detail }
  }
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>
    return {
      code: typeof d.error === 'string' ? d.error : String(status),
      message: typeof d.message === 'string' ? d.message : JSON.stringify(detail),
    }
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const msgs = detail.map((e: any) => e?.msg ?? String(e)).filter(Boolean).join('; ')
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
export async function unwrapVoid(result: FetchResult<unknown>): Promise<void> {
  if (result.error !== undefined) {
    const detail = (result.error as any)?.detail ?? result.error
    const { code, message } = parseErrorDetail(detail, result.response.status)
    throw new ApiError(result.response.status, code, message, result.error)
  }
}
```

### TanStack Query setup (main.tsx)

Defined inline in `main.tsx` and passed to `<QueryClientProvider>` — see the main.tsx skeleton in Section 5. Settings:

```ts
new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,  // global default; per-query override
      retry: (failureCount, err) => {
        if (err instanceof ApiError && err.status >= 400 && err.status < 500) return false
        return failureCount < 1
      },
    },
    mutations: { retry: false },
  },
})
```

The instance lives in `main.tsx`'s module scope. Components access it via `useQueryClient()` (NEVER by importing the symbol — that would couple file paths and break test isolation).

### `api/queries/auth.ts`

```ts
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
    refetchOnWindowFocus: true,  // per-query session-critical override
    staleTime: 60_000,
  })
}

export function useLoginMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: { username: string; password: string }) => {
      await unwrapVoid(await client.POST('/api/auth/login', { body: input }))
      // (b) yaklaşım: login response user payload taşımıyor → ikinci /me çağrısı
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
    mutationFn: async (input: RegisterInput) =>
      // Backend /api/auth/register returns UserOut (201) but does NOT
      // establish a session cookie (see backend/users/routes.py — no
      // session.set_cookie call on the register handler). Returning a
      // user payload here would be misleading: a follow-up /api/auth/me
      // would 401. Treat register as "create account, then prompt login".
      unwrap(await client.POST('/api/auth/register', { body: input })),
    onSuccess: () => {
      // Do NOT seed authStore — no session exists yet. Land the user on
      // /login with a success toast; they sign in to receive the cookie.
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

### App hydration with cache priming

```tsx
function App() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [retryNonce, setRetryNonce] = useState(0)

  useEffect(() => setNavigator(navigate), [navigate])
  useEffect(() => {
    setAuthHandlers({
      onSessionExpired: () => useAuthStore.getState().clear(),
    })
  }, [])

  // Hydration effect: runs on mount AND whenever retryNonce bumps.
  // qc is stable (provider-owned) — its dep is defensive, not load-bearing.
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
          qc.setQueryData(authKeys.me, user)  // PRIME cache
        }
        markHydrated()
      } catch (e: any) {
        if (cancelled) return
        if (e?.name === 'AbortError') return
        useAuthStore.getState().setError(String(e?.message ?? e))
        // markHydrated() NOT called on error — retry safe
      }
    })()
    return () => { cancelled = true; ctrl.abort() }
  }, [qc, retryNonce])

  const status = useAuthStore((s) => s.status)
  const handleRetry = () => {
    useAuthStore.getState().setStatus('loading')   // flip out of 'error'
    setRetryNonce((n) => n + 1)                     // re-fire hydration effect
  }

  if (status === 'loading') return <LoadingScreen />
  if (status === 'error') return <LoadingScreen mode="error" onRetry={handleRetry} />
  return <Routes>{/* see Section 5 for full tree */}</Routes>
}
```

**Why two-step retry (status flip + nonce bump):**
- Status flip alone wouldn't re-fire the effect (status is read by selector, not in deps).
- Nonce bump alone wouldn't unmount LoadingScreen's error mode (status would stay 'error' until /me succeeds).
- Both together: instant UI feedback (spinner returns) + the effect actually re-runs.

---

## 7. Zustand store + Test Infrastructure

### `stores/authStore.ts`

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

**No `persist`** — server-driven hydration via `/api/auth/me` only.

### Test infra files

```
src/test/
├── setup.ts             # Vitest global: MSW lifecycle, store/DI reset, opt-in silenceConsoleError
├── msw-handlers.ts      # Default handlers + makeUser factory + mockAuthedUser/mockAnonUser
├── msw-server.ts        # setupServer instance
└── render.tsx           # renderWithProviders + destination stubs + auto-cleanup queryClients
```

### `setup.ts`

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

export function silenceConsoleError() {
  return vi.spyOn(console, 'error').mockImplementation(() => {})
}
```

### `render.tsx`

```tsx
import { render as rtlRender, RenderOptions } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route, parsePath } from 'react-router-dom'
import { ReactElement, ReactNode } from 'react'
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
  { path: '/',         testId: 'route-root' },
  { path: '/login',    testId: 'route-login' },
  { path: '/register', testId: 'route-register' },
  { path: '/help',     testId: 'route-help' },
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

### `msw-handlers.ts`

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
  http.get('/api/auth/me', () => HttpResponse.json(
    { detail: { error: 'unauthorized', message: 'Not authenticated' } },
    { status: 401 },
  )),
  http.post('/api/auth/login', () => HttpResponse.json({ ok: true })),
  http.post('/api/auth/logout', () => HttpResponse.json({ ok: true })),
  // Backend register returns UserOut (201) but DOES NOT set a session
  // cookie (see backend/users/routes.py). Tests must assert that the
  // frontend treats this as "account created, redirect to /login" — NOT
  // an authed flow. See useRegisterMutation in api/queries/auth.ts.
  http.post('/api/auth/register', () => HttpResponse.json(
    makeUser({ has_seen_manual: false, has_passed_training: false }),
    { status: 201 },
  )),
]

export function mockAuthedUser(overrides: Partial<User> = {}) {
  return http.get('/api/auth/me', () => HttpResponse.json(makeUser(overrides)))
}

export function mockAnonUser() {
  return http.get('/api/auth/me', () => HttpResponse.json(
    { detail: { error: 'unauthorized', message: '' } },
    { status: 401 },
  ))
}
```

### Test coverage matrix

| Category | Test file | What it verifies |
|---|---|---|
| authStore | `stores/authStore.test.ts` | 4 state transitions + 3 selectors |
| API client | `api/client.test.ts` | Pre/post-hydration self-401, non-/me 401, 4 error detail shapes |
| Auth mutations | `api/queries/auth.test.tsx` | useLogin/Register/Logout success + error paths |
| Login form | `routes/Login.test.tsx` | Submit success → /, invalid_credentials, validation |
| Register form | `routes/Register.test.tsx` | Submit success → /login with success toast (backend register does not set session; user must sign in); error paths (409 username taken, 422 weak password, 403 invalid invite) |
| Gates | `components/gates/*.test.tsx` | 4 gates × redirect target verification |
| Hydration | `App.test.tsx` | Loading + anon → /login + authed → root + error retry |
| ErrorBoundary | `components/ErrorBoundary.test.tsx` | Child throw → fallback, reload mocked |
| LoadingScreen | `components/shell/LoadingScreen.test.tsx` | Both modes |

**Total target**: ~30-40 frontend tests + 3 backend tests for new touches. Coverage gate: ≥80% statements + branches.

---

## 8. Dev Pipeline + Build

### `package.json`

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

**0.x packages pinned with tilde** (~) for minor-breaking protection: `openapi-fetch`, `class-variance-authority`, `lucide-react`. Rationale documented in README.

### `tsconfig.json`

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

### `tsconfig.node.json`

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

### `tsconfig.eslint.json` (separate for type-aware lint)

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

### `vite.config.ts`

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
    target: 'es2022',
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
      // Section 7 declares "Coverage gate: ≥80% statements + branches".
      // Enforced here so `npm run test:coverage` fails CI when slipping.
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

### `eslint.config.js` (flat, 3 blocks)

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
      // Fast Refresh invariant — see Section 10 #8
      'react-refresh/only-export-components': ['error', { allowConstantExport: true }],
      // TS noise we accept (verbatim module syntax handles imports)
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
      // 0-error policy for unused; tsconfig also enforces
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
      // Tests legitimately export non-components (fixtures, helpers)
      'react-refresh/only-export-components': 'off',
      // Tests commonly use any in mocks/factories
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-non-null-assertion': 'off',
    },
  },
  // ----- Block 3: Node-context config files (no type-aware lint) -----
  {
    files: ['vite.config.ts', 'eslint.config.js', 'tailwind.config.ts', 'postcss.config.js'],
    languageOptions: {
      globals: { ...globals.node },
      // Override: do NOT run type-aware lint here (no parserOptions.project).
      parserOptions: { project: null },
    },
    rules: {
      // tsconfig.eslint.json includes vite.config.ts for the app block;
      // here we relax type-aware rules that don't apply to config code.
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-call': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
    },
  },
  // Disable rules that conflict with Prettier; MUST be last.
  prettier,
)
```

**3-block structure rationale:**
- **Block 1 (app)**: full type-aware lint via `tsconfig.eslint.json`. React + hooks + a11y + Fast Refresh invariants enforced.
- **Block 2 (tests)**: vitest globals; relaxes `only-export-components` (test files legitimately export helpers) and `no-explicit-any` (mock factories need it).
- **Block 3 (Node config)**: Node globals; type-aware rules disabled because config files aren't React code.
- `prettier` config disables formatting-conflict rules — must be the LAST entry to win.

**Ignores**: `dist`, `coverage`, `node_modules`, and `src/api/types.ts` (generated) should be ignored — add an `eslint.config.js` `{ ignores: [...] }` block at the top, or via `.eslintignore` (deprecated in flat config; use the config block).

### `.prettierrc`

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

### `.editorconfig`, `.env.example`, `.gitignore`, `.npmrc`, `.nvmrc`, `index.html`, `tailwind.config.ts`, `postcss.config.js`, `components.json`, `public/favicon.svg`, `public/robots.txt`

See Section 6 draft — all standard, no further variation.

### Dev workflow (README)

```markdown
# Anotasyon Platform — Frontend

## İlk kurulum

\`\`\`bash
cd frontend
nvm use            # .nvmrc → Node 22
npm ci             # deterministic via package-lock
cp .env.example .env.local  # if override needed
\`\`\`

## Dev workflow — 2 terminal

\`\`\`bash
# Terminal 1: backend
(repo root)$ DATA_DIR=$(pwd)/deneme-dev/data .venv/bin/uvicorn backend.main:app --reload --port 8000

# Terminal 2: frontend
(frontend/)$ npm run dev    # Vite 5173 → /api proxy → uvicorn 8000
\`\`\`

## Type regeneration

\`\`\`bash
# Backend açıkken:
(frontend/)$ npm run gen:types

# Backend kapalıyken (frontend dizininden tek script):
(frontend/)$ npm run gen:openapi          # cd .. && python -m backend.cli openapi-dump
(frontend/)$ npm run gen:types:from-file

# Drift kontrolü (lokal CI öncesi sanity):
(frontend/)$ npm run gen:types:check
\`\`\`

## shadcn/ui component ekleme

\`\`\`bash
(frontend/)$ npx shadcn@latest add button
(frontend/)$ npx shadcn@latest add dialog
\`\`\`

Generated files: `src/components/ui/<name>.tsx`. Commit alongside usage.

## Production build

\`\`\`bash
(frontend/)$ npm run build       # → ../backend/static/
(repo root)$ .venv/bin/uvicorn backend.main:app --port 8000
# SPA + API tek port: http://localhost:8000
\`\`\`

## Quality gates

\`\`\`bash
npm run typecheck   # tsc --noEmit
npm run lint        # eslint, error level fails
npm run format:check
npm test            # vitest watch
npm run test:run    # vitest single-run
npm run test:coverage
\`\`\`

## Dependency policy

`~` (tilde) pinned: `openapi-fetch`, `class-variance-authority`, `lucide-react` — these
are 0.x packages where minor versions may include breaking changes. Upgrade
deliberately with smoke test, then update the pin.

## Path alias

`@/` → `src/`. Configured in three places: `tsconfig.json` (paths),
`vite.config.ts` (resolve.alias), `tsconfig.eslint.json` (lint type-aware).
Vitest inherits from Vite automatically.
```

### Frontend-only CI ordering (Paket 17 implements; 16a documents)

```bash
npm ci                       # 1. install (engine-strict enforces Node 22)
npm run typecheck            # 2. tsc --noEmit
npm run lint                 # 3. eslint (error level fails CI)
npm run format:check         # 4. prettier
npm run test:coverage        # 5. vitest with coverage thresholds (≥80%)
npm run build                # 6. production bundle smoke
```

**Type drift detection** (separate full-stack CI job, Paket 17):

```bash
python -m backend.cli openapi-dump
npm run gen:types:from-file
git diff --exit-code src/api/types.ts  # fail if drift
```

### `backend/static/` ownership contract

This directory is **100% owned by Vite build output**. Any file manually placed in `backend/static/` will be deleted on the next `npm run build` because of `emptyOutDir: true` in `vite.config.ts`.

**Rules:**
- Never commit anything to `backend/static/` (already in root `.gitignore`).
- Backend-served static files (if ever needed) must live elsewhere — e.g., `backend/assets/` mounted separately in `backend/main.py`.
- Frontend `public/` → `backend/static/` root (favicon.svg, robots.txt).
- Frontend bundles → `backend/static/assets/` (hashed JS/CSS).

`backend/main.py` extension-aware SPA fallback (next section) ensures backend `/api/*` routes can never collide with the SPA.

---

## 9. Backend Touches

### `backend/config.py` — `STATIC_DIR` constant

```python
STATIC_DIR = PROJECT_ROOT / "backend" / "static"
```

### `backend/main.py` — extension-aware SPA fallback (after all `/api/*` routers)

```python
import os
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Route registration happens at import time. To keep tests deterministic
# (no SPA routes leaking into TestClient) we gate registration on an env
# flag in addition to the directory check. The test conftest sets this
# BEFORE backend.main is imported — see tests/conftest.py.
_SPA_DISABLED = os.getenv("DISABLE_SPA_MOUNT") == "1"

if config.STATIC_DIR.exists() and not _SPA_DISABLED:
    # Vite hashed bundles
    app.mount(
        "/assets",
        StaticFiles(directory=config.STATIC_DIR / "assets"),
        name="assets",
    )
    INDEX_HTML = config.STATIC_DIR / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        """Root-level public files (favicon, robots) if exist; uzantılı
        ama dosya yoksa 404; uzantısız path için SPA index."""
        last = path.rsplit("/", 1)[-1] if path else ""
        has_ext = "." in last
        target = config.STATIC_DIR / path
        # Path traversal koruması
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

**Ordering invariant**: this block MUST appear AFTER all `/api/*` router includes in `main.py`. FastAPI/Starlette matches routes in registration order; `/api/*` matches first, SPA fallback catches everything else.

**Import-time gating rationale**: SPA routes are registered when `backend.main` is imported (FastAPI's module-level decorator pattern). An autouse fixture that monkeypatches `config.STATIC_DIR` would run AFTER the import, leaving the routes registered. The env-flag check moves the decision to import time, which `tests/conftest.py` sets before any backend module is imported.

### `backend/cli.py` — `openapi_dump` Typer command

```python
@app.command()
def openapi_dump(output: Path = Path("openapi.json")) -> None:
    """Export FastAPI OpenAPI spec to JSON (frontend type gen için)."""
    import json
    from backend.main import app as fastapi_app
    output.write_text(json.dumps(fastapi_app.openapi(), indent=2))
    typer.echo(f"OpenAPI written to {output}")
```

### `tests/conftest.py` — disable SPA mount BEFORE backend imports

```python
# This MUST run before any test file imports backend.main — pytest
# evaluates conftest.py top-level code during collection, before
# any test module is imported. Setting the env var here guarantees
# the import-time SPA gate in backend/main.py sees DISABLE_SPA_MOUNT=1
# on first import.
import os
os.environ.setdefault("DISABLE_SPA_MOUNT", "1")

import pytest
```

**Why not an autouse fixture**: fixtures run at test execution time, but FastAPI registers routes at module import time. By the time an autouse fixture executes, `backend.main` has already been imported (typically by another conftest, a test module, or a TestClient construction earlier in the same module). The env-var-at-conftest-top approach intercepts the gate before any import occurs. The existing root `tests/conftest.py` is the earliest pytest reads — if a `backend/tests/conftest.py` also exists, set the env var there too (defensive duplication is safe because of `setdefault`).

### Root `.gitignore`

Append:
```
backend/static/
```

---

## 10. Integration Contract Checklist (16a complete kriteri)

| # | Check | Type |
|---|---|---|
| 1 | `frontend/src/api/types.ts` checked into git | manual |
| 2 | `frontend/.env.example` includes all `VITE_*` used in code | manual |
| 3 | `backend/static/` not in repo (root `.gitignore`) | manual |
| 4 | `backend/main.py` SPA fallback extension-aware (this spec §9) | manual |
| 5 | `backend/cli.py` `openapi-dump` works (`python -m backend.cli openapi-dump`) | manual |
| 6 | `tests/conftest.py` `disable_spa_mount` autouse fixture pinned | manual |
| 7 | Every `useQuery` in `src/api/queries/*` threads `{ signal }` | manual / future lint |
| 8 | All non-component exports outside `src/components/` (Fast Refresh invariant) | lint (`react-refresh/only-export-components: error`) |
| 9 | `npm run typecheck && lint && format:check && test:coverage && build` green (coverage gate ≥80% enforced) | CI |
| 10 | `python -m pytest -x -q` green (DISABLE_SPA_MOUNT=1 set by conftest before backend imports) | CI |

Auto-verifiable (8, 9, 10): CI gate. Manual (1-7): PR checklist.

---

## 11. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cookie SameSite=Lax + Vite proxy edge case (localhost vs 127.0.0.1) | Low | Medium | Vite proxy `target: 'http://127.0.0.1:8000'` (loopback IP), `changeOrigin: false`. README documents. |
| openapi-fetch v0.13.x patch-breaking | Low | Medium | `~0.13.0` pin; upgrade with smoke test |
| Type drift (backend OpenAPI changed, frontend regen forgotten) | Medium | Low | `gen:types:check` local script; CI drift gate in Paket 17 |
| Multi-tab login race (cookie shared between tabs) | Low | Low | Documented FRAGILE; BroadcastChannel deferred |
| Vitest jsdom CSS parse cost | Low | Low | `css: false` in vite.config test block |
| Build artifact in `backend/static/` accidentally wiping backend-owned files | Low | High | Contract: `backend/static/` is frontend-only; root `.gitignore` blocks accidental commit |
| Node 22 mismatch (dev vs CI) | Low | Medium | `.nvmrc` + `engines.node` + `.npmrc` engine-strict |
| FastAPI exempt paths (`/docs`, `/redoc`, `/openapi.json`) reach SPA fallback | None | None | Registered before SPA fallback by FastAPI default |
| Backend register session contract changes upstream (auto-login added) | Low | Medium | Single source of truth: `useRegisterMutation` in `api/queries/auth.ts`. If backend later sets a cookie on register, update mutation to seed authStore + navigate to `/help?first_time=true` (16c handoff). MSW handler + register test must change together. |
| Cross-tab session: register tab navigates to `/login`, but another tab is already authed | Low | Low | Register form mounts before authStore hydration check is relevant; existing authed session in another tab is not affected. Cross-tab sync deferred to BroadcastChannel paket. |

---

## 12. Implementation Estimate

| Element | Count | Notes |
|---|---|---|
| Frontend config files | 14 | package.json, tsconfig×3, vite.config, eslint.config, prettierrc, editorconfig, env.example, gitignore, npmrc, nvmrc, postcss, tailwind, components.json |
| HTML + entry | 2 | index.html, src/main.tsx |
| App + routes | 9 | App.tsx + Login + Register + NotFound + 5 STUBs |
| Components | ~12 | 4 gates + 2 shell + ErrorBoundary + shadcn ui (button, input, label, form, card, sonner) |
| Hooks + stores + lib | 4 | useAuth, authStore, utils, env |
| API layer | 3 | client.ts, types.ts (generated), queries/auth.ts |
| Test infra + tests | ~14 | 4 cross-cutting + ~10 test files |
| Public assets | 2 | favicon.svg, robots.txt |
| Backend touches | 4 | config.py, main.py, cli.py, tests/conftest.py |
| Root | 1 | .gitignore append |

**Total**: ~65 new files + 5 backend modifications.

**Commit estimate**: 12-15 atomic commits (TDD per layer, smoke gates at milestones).
**Time estimate**: 3-5 dev-days (single developer, focused).

---

## 13. Out of Spec / Deferred

**Subsequent paketler:**
- **16b** Annotate workflow — DocList virtual scroll, DocViewer, ReferencePanel, draft auto-save, lock heartbeat, SSE, LockConflict modal.
- **16c** Onboarding — Help markdown viewer, Training quiz + gold-doc, activate `RequireSeenManual` + `RequirePassedTraining`.
- **16d** Gamification UI — TopBar, Profile, notifications panel, SSE personal events.
- **16e** Admin panel — `/admin/*` routes + queries for all admin endpoints.
- **16f** Docker reconcile — Paket 15 single-stage → multi-stage with node:22-slim frontend-build, T6 smoke extended.

**Paket 17 and later:**
- GitHub Actions CI workflow (typecheck → lint → test → build, type drift detection)
- E2E tests (Playwright multi-user, lock contention, backup/restore drill)
- Observability (JSON logs, /metrics, Sentry frontend)
- Performance (lazy route loading, bundle analyzer)
- Full a11y audit (axe-core, screen reader)
- Cross-tab session sync (BroadcastChannel)
- Runtime env (currently build-time)
- PWA / offline
- Dark mode (next-themes)
- i18n framework
- Image vulnerability scan
- Multi-arch Docker build
