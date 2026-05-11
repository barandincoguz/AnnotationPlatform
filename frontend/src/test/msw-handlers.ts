import { http, HttpResponse } from 'msw'

// Default handlers — most are added in T6 after authStore + api/client land.
// Listed here so far:
// - GET /api/auth/me → 401 anon (so client.GET calls in tests without an
//   explicit handler don't blow up onUnhandledRequest:'error'). Individual
//   tests should still override via server.use(...) when they need a
//   specific response.
export const handlers = [
  http.get('http://localhost/api/auth/me', () =>
    HttpResponse.json({ detail: 'unauth' }, { status: 401 }),
  ),
]
