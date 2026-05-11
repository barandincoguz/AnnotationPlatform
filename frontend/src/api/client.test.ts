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
    // Exercise the wired client; result is intentionally unused — the
    // assertion below verifies the helper shape via a synthetic object.
    await client.GET('/api/auth/me' as never)
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
