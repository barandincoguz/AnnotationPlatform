/**
 * Developer-only feature flags. Read from localStorage so they survive
 * across page loads but never persist to the server or affect any other
 * user. Production users never see surfaces gated by these flags; a
 * developer enables one by opening DevTools and running:
 *
 *   localStorage.setItem('a11n.dev_sort', '1')
 *
 * then reloading. To disable: `localStorage.removeItem('a11n.dev_sort')`.
 *
 * Why localStorage and not env vars: env vars require a rebuild and bake
 * the flag into every user's bundle. We want a runtime toggle scoped to
 * a single browser, with no server roundtrip. localStorage is exactly
 * that — and is safe to read because the flags only relax UI gates;
 * they never bypass server-side authorization.
 */

const DEV_SORT_KEY = 'a11n.dev_sort'

export function isDevSortEnabled(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return window.localStorage.getItem(DEV_SORT_KEY) === '1'
  } catch {
    // Some browsers raise on localStorage access (private mode, etc.).
    // Treat unreachable storage as "flag off" — the safer default.
    return false
  }
}
