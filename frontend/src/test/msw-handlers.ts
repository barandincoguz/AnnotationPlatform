import { http, HttpResponse } from 'msw'
import type { components } from '@/api/types'

type User = components['schemas']['UserOut']
type FeedItem = components['schemas']['FeedItem']
type DocumentDetail = components['schemas']['DocumentDetail']
type ReferenceItem = components['schemas']['ReferenceItem']

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

export function makeFeedItem(overrides: Partial<FeedItem> = {}): FeedItem {
  return {
    document_id: 'doc-1',
    sayi: 1234,
    tarih: '2025-05-22',
    konu: 'Vergi Usul Kanunu uyarınca düzenlenen rapor',
    vergi_turu: 'KDV',
    estimated_difficulty: 'orta',
    word_count: 850,
    has_annotation: false,
    is_completed: false,
    last_editor_user_id: null,
    last_editor_username: null,
    edit_count: 0,
    unique_users_count: 0,
    updated_at: null,
    ...overrides,
  } satisfies FeedItem
}

export function makeDocumentDetail(overrides: Partial<DocumentDetail> = {}): DocumentDetail {
  return {
    document_id: 'doc-1',
    sayi: 1234,
    tarih: '2025-05-22',
    basvuru_tarihi: null,
    vergi_donemi: null,
    konu: 'Vergi Usul Kanunu uyarınca düzenlenen rapor',
    vergi_turu: 'KDV',
    mukellefiyet_turu: null,
    word_count: 850,
    sentence_count: 42,
    text_density: 0.85,
    estimated_difficulty: 'orta',
    topic_category: null,
    created_at: '2026-05-01T00:00:00+00:00',
    pdf_text: 'Sahte fatura düzenlediği iddia edilen yükümlü hakkında...',
    html_text: null,
    ...overrides,
  } satisfies DocumentDetail
}

export function makeReferenceItem(overrides: Partial<ReferenceItem> = {}): ReferenceItem {
  return {
    kanun_no: '213',
    kanun_ad: 'Vergi Usul Kanunu',
    madde: '359',
    fikra: 'b',
    bent: '1',
    source_text: 'Sahte belge düzenlemek...',
    ...overrides,
  } satisfies ReferenceItem
}

// MSW v2 in a jsdom environment matches against fully-qualified URLs.
// jsdom defaults `location.origin` to `http://localhost`, so handlers
// MUST use absolute URLs (relative paths silently fail to match —
// see client.test.ts for the established pattern).
const API = 'http://localhost'

const ANNOTATE_DEFAULTS = [
  http.get(`${API}/api/feed`, () => HttpResponse.json({ items: [makeFeedItem()], total: 1 })),
  http.get(`${API}/api/documents/:docId`, ({ params }) =>
    HttpResponse.json(makeDocumentDetail({ document_id: String(params.docId) })),
  ),
  http.get(`${API}/api/documents/:docId/annotation`, () =>
    HttpResponse.json({ annotation: null, chain: [] }),
  ),
  http.get(`${API}/api/drafts/:docId`, () =>
    HttpResponse.json(
      { detail: { error: 'not_found', message: 'Draft not found' } },
      { status: 404 },
    ),
  ),
  http.put(`${API}/api/drafts/:docId`, () => HttpResponse.json({ ok: true })),
  http.delete(`${API}/api/drafts/:docId`, () => HttpResponse.json({ ok: true })),
  http.post(`${API}/api/locks/:docId/acquire`, ({ params }) =>
    HttpResponse.json({
      document_id: String(params.docId),
      user_id: 1,
      by_username: 'tester',
      acquired_at: '2026-05-11T10:00:00+00:00',
      expires_at: '2026-05-11T10:01:30+00:00',
    }),
  ),
  http.post(`${API}/api/locks/:docId/heartbeat`, ({ params }) =>
    HttpResponse.json({
      document_id: String(params.docId),
      user_id: 1,
      by_username: 'tester',
      acquired_at: '2026-05-11T10:00:00+00:00',
      expires_at: '2026-05-11T10:01:30+00:00',
    }),
  ),
  http.post(`${API}/api/locks/:docId/release`, () => HttpResponse.json({ ok: true })),
  http.post(`${API}/api/annotations`, () =>
    HttpResponse.json({
      is_new: true,
      is_diff_zero: false,
      current_references: [makeReferenceItem()],
    }),
  ),
  http.post(`${API}/api/annotations/:docId/skip`, () => HttpResponse.json({ ok: true })),
  http.post(`${API}/api/annotations/:docId/complete`, () => HttpResponse.json({ ok: true })),
]

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
    HttpResponse.json(makeUser({ has_seen_manual: false, has_passed_training: false }), {
      status: 201,
    }),
  ),
  ...ANNOTATE_DEFAULTS,
]

export function mockAuthedUser(overrides: Partial<User> = {}) {
  return http.get(`${API}/api/auth/me`, () => HttpResponse.json(makeUser(overrides)))
}

export function mockAnonUser() {
  return http.get(`${API}/api/auth/me`, () =>
    HttpResponse.json({ detail: { error: 'unauthorized', message: '' } }, { status: 401 }),
  )
}
