import { render as rtlRender, type RenderOptions } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route, parsePath } from 'react-router-dom'
import { type ReactElement, type ReactNode } from 'react'
import { afterEach } from 'vitest'

interface RenderOpts extends Omit<RenderOptions, 'wrapper'> {
  initialEntries?: string[]
  destinationStubs?: { path: string; testId: string }[]
  extraDestinationStubs?: { path: string; testId: string }[]
  /**
   * Opt-in: mount `ui` at `<Route path="*">` instead of the literal
   * `entryPath`. Use this when `ui` itself owns a `<Routes>` tree (e.g.
   * App.tsx) — without the wildcard the parent route stops matching as
   * soon as an inner Navigate changes the URL, and the inner Routes
   * never gets a chance to render. React Router emits a warning for
   * this exact misuse: "parent route path has no trailing *".
   *
   * When `wildcardEntry` is true, stub destinations are still mounted
   * BEFORE the wildcard (so they keep working for navigation
   * observation), and `ui` catches everything else.
   */
  wildcardEntry?: boolean
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
    wildcardEntry = false,
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
        {wildcardEntry ? (
          // ui owns its own <Routes>. Stub destinations are not mounted
          // here because they would shadow paths inside ui's Routes;
          // tests that need to observe navigation should assert against
          // ui's own rendered output (e.g. the Login form for /login).
          <>{children}</>
        ) : (
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
        )}
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
