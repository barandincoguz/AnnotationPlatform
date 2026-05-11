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

// MSW v2 in a jsdom environment matches against fully-qualified URLs.
// jsdom defaults `location.origin` to `http://localhost`, so handlers
// MUST use absolute URLs (relative paths silently fail to match —
// see client.test.ts for the established pattern).
const API = 'http://localhost'

export const handlers = [
  http.get(`${API}/api/auth/me`, () =>
    HttpResponse.json(
      { detail: { error: 'unauthorized', message: 'Not authenticated' } },
      { status: 401 },
    ),
  ),
  http.post(`${API}/api/auth/login`, () => HttpResponse.json({ ok: true })),
  http.post(`${API}/api/auth/logout`, () => HttpResponse.json({ ok: true })),
  // Backend register returns UserOut (201) but DOES NOT set a session
  // cookie (see backend/users/routes.py — no response.set_cookie call).
  // Frontend useRegisterMutation treats this as "account created, navigate
  // to /login with success toast" — NOT an authed transition.
  http.post(`${API}/api/auth/register`, () =>
    HttpResponse.json(
      makeUser({ has_seen_manual: false, has_passed_training: false }),
      { status: 201 },
    ),
  ),
]

export function mockAuthedUser(overrides: Partial<User> = {}) {
  return http.get(`${API}/api/auth/me`, () =>
    HttpResponse.json(makeUser(overrides)),
  )
}

export function mockAnonUser() {
  return http.get(`${API}/api/auth/me`, () =>
    HttpResponse.json(
      { detail: { error: 'unauthorized', message: '' } },
      { status: 401 },
    ),
  )
}
