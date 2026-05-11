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
  // Resolve fetch at call time, not at module-import time. This lets MSW's
  // server.listen() (which runs in beforeAll) install its interceptor by
  // replacing globalThis.fetch, and our calls still see the patched version.
  // Costs one extra function call per request in prod; negligible.
  fetch: (...args) => globalThis.fetch(...args),
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
