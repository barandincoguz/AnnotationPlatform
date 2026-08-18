import { http, HttpResponse } from 'msw'
import type { components } from '@/api/types'
import type {
  ProfileResponse, Notification, NotificationsList, BadgeCatalogItem,
  OnlineUser,
} from '@/lib/profileSchemas'
import type { StatisticsMetrics, StatisticsResponse } from '@/lib/statisticsSchemas'

type User = components['schemas']['UserOut']
type FeedItem = components['schemas']['FeedItem']
type DocumentDetail = components['schemas']['DocumentDetail']
type ReferenceItem = components['schemas']['ReferenceItem']
type FeedbackRow = components['schemas']['FeedbackRow']

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
    // Phase 1 canonical state — defaults to 'new' / no draft, callers
    // override per test scenario. has_annotation + is_completed are
    // retained for backward compat with pre-Phase-3 callers that
    // still set them; once everything reads workflow_state these can
    // simply be derived.
    workflow_state: 'new',
    has_draft: false,
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
    kanun_refs: [],
    bkk_refs: [],
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

export function makeFeedbackRow(overrides: Partial<FeedbackRow> = {}): FeedbackRow {
  return {
    id: 1,
    user_id: 1,
    username: 'tester',
    type: 'suggestion',
    message: 'Liste ekranına hızlı filtre eklenebilir.',
    created_at: '2026-07-07T12:00:00+00:00',
    ...overrides,
  } satisfies FeedbackRow
}

// MSW v2 in a jsdom environment matches against fully-qualified URLs.
// jsdom defaults `location.origin` to `http://localhost`, so handlers
// MUST use absolute URLs (relative paths silently fail to match —
// see client.test.ts for the established pattern).
const API = 'http://localhost'

// ----- 16d Gamification factories -----

export function makeProfile(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    user: { id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' },
    xp: { total: 1240 },
    streak: { current: 3, longest: 12, last_active_date: '2026-05-11' },
    today: { save: 3, complete: 1, review: 0, skip: 0, daily_target: 10 },
    badges: [{
      id: 'first_annotation', name: 'İlk Annotation',
      description: 'İlk kayıt başarıyla yapıldı.',
      earned_at: '2026-05-10T12:00:00+00:00',
    }],
    ...overrides,
  }
}

export function makeNotification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: 1, kind: 'admin_announcement', title: 'Test bildirimi',
    body: null, data: null, is_read: false,
    created_at: '2026-05-11T12:00:00+00:00',
    ...overrides,
  }
}

export function makeBadgeCatalogItem(
  overrides: Partial<BadgeCatalogItem> = {},
): BadgeCatalogItem {
  return {
    id: 'first_annotation', name: 'İlk Annotation',
    description: 'İlk kayıt başarıyla yapıldı.',
    criterion: 'İlk anotasyon kaydını yap.',
    ...overrides,
  }
}

export function defaultBadgesCatalog(): BadgeCatalogItem[] {
  return [
    makeBadgeCatalogItem({ id: 'first_annotation', name: 'İlk Annotation',
      description: 'İlk kayıt başarıyla yapıldı.',
      criterion: 'İlk anotasyon kaydını yap.' }),
    makeBadgeCatalogItem({ id: 'annotations_10', name: '10 Annotation',
      description: '10 kayıt biriktirdin.',
      criterion: '10 anotasyon kaydı biriktir.' }),
    makeBadgeCatalogItem({ id: 'annotations_100', name: '100 Annotation',
      description: '100 kayıt — istikrarlı çalışıyorsun.',
      criterion: '100 anotasyon kaydı biriktir.' }),
    makeBadgeCatalogItem({ id: 'annotations_1000', name: '1000 Annotation',
      description: 'Bin kayıt: ekibin omurgası oldun.',
      criterion: '1000 anotasyon kaydı biriktir.' }),
    makeBadgeCatalogItem({ id: 'first_completion', name: 'İlk Tamamlama',
      description: 'İlk dokümanı tamamlandı olarak işaretledin.',
      criterion: 'İlk dokümanı tamamlandı olarak işaretle.' }),
    makeBadgeCatalogItem({ id: 'marathoner', name: 'Maratoncu',
      description: '7 gün üst üste çalıştın.',
      criterion: '7 gün üst üste çalış.' }),
    makeBadgeCatalogItem({ id: 'good_reviewer', name: 'Good Reviewer',
      description: 'Yaptığın review\'lerin çoğu sonraki kullanıcılar tarafından korundu.',
      criterion: 'Review\'lerinin çoğunluğu korunsun (en az 20 review, 15+ kept).' }),
  ]
}

export function makeOnlineUser(overrides: Partial<OnlineUser> = {}): OnlineUser {
  return { id: 1, username: 'tester', avatar_color: '#3b82f6', ...overrides }
}

export function makeStatisticsMetrics(
  overrides: Partial<StatisticsMetrics> = {},
): StatisticsMetrics {
  return {
    distinct_documents: 0,
    save_events: 0,
    complete_events: 0,
    uncomplete_events: 0,
    skip_events: 0,
    version_events: 0,
    create_versions: 0,
    edit_versions: 0,
    complete_mark_versions: 0,
    zero_diff_versions: 0,
    final_completed_documents: 0,
    xp_delta: 0,
    ...overrides,
  }
}

export function makeStatisticsPeriodMetrics(
  overrides: Partial<Record<keyof StatisticsResponse['summary'], Partial<StatisticsMetrics>>> = {},
): StatisticsResponse['summary'] {
  return {
    today: makeStatisticsMetrics(overrides.today),
    last_7_days: makeStatisticsMetrics(overrides.last_7_days),
    last_30_days: makeStatisticsMetrics(overrides.last_30_days),
    all_time: makeStatisticsMetrics(overrides.all_time),
  }
}

export function makeStatisticsResponse(
  overrides: Partial<StatisticsResponse> = {},
): StatisticsResponse {
  const summary = makeStatisticsPeriodMetrics({
    today: { distinct_documents: 1, save_events: 1, xp_delta: 1 },
    last_7_days: { distinct_documents: 4, save_events: 3, complete_events: 1, xp_delta: 12 },
    last_30_days: { distinct_documents: 8, save_events: 7, complete_events: 2, xp_delta: 30 },
    all_time: { distinct_documents: 12, save_events: 10, complete_events: 4, xp_delta: 75 },
  })
  return {
    generated_at: '2026-07-06T12:00:00+00:00',
    summary,
    users: [
      {
        user: { id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' },
        xp_total: 1240,
        badges_count: 1,
        streak_current: 3,
        last_active_date: '2026-07-06',
        metrics: summary,
      },
    ],
    ...overrides,
  }
}

const GAMIFICATION_DEFAULTS = [
  http.get(`${API}/api/me/profile`, () => HttpResponse.json(makeProfile())),

  http.get(`${API}/api/me/notifications`, ({ request }) => {
    const url = new URL(request.url)
    const unreadOnly = url.searchParams.get('unread_only') !== 'false'
    const items: Notification[] = [
      makeNotification({
        id: 1, is_read: false, kind: 'admin_announcement',
        title: 'Bir bildirim',
      }),
      ...(unreadOnly
        ? []
        : [
            makeNotification({
              id: 2, is_read: true, kind: 'training_passed',
              title: 'Eğitim geçildi', body: null,
              created_at: '2026-05-10T00:00:00+00:00',
            }),
          ]),
    ]
    return HttpResponse.json({ items } satisfies NotificationsList)
  }),

  http.post(`${API}/api/me/notifications/:id/read`, () =>
    HttpResponse.json({ ok: true }),
  ),

  http.post(`${API}/api/me/notifications/read-all`, () =>
    HttpResponse.json({ marked_count: 1 }),
  ),

  http.get(`${API}/api/badges/catalog`, () =>
    HttpResponse.json(defaultBadgesCatalog()),
  ),

  http.get(`${API}/api/users/online`, () =>
    HttpResponse.json([makeOnlineUser({ id: 1, username: 'tester', avatar_color: '#3b82f6' })]),
  ),

  http.get(`${API}/api/statistics/users`, () =>
    HttpResponse.json(makeStatisticsResponse()),
  ),
]

const HELP_DEFAULT_SECTIONS = [
  { id: '01-welcome', order: 1, title: 'Hoş geldin', body: '# Hoş geldin\n\nMerhaba.' },
  { id: '02-getting-started', order: 2, title: 'Başlarken', body: '# Başlarken\n\nİlk adım.' },
  { id: '03-annotation-guide', order: 3, title: 'Anotasyon', body: '# Anotasyon\n\nReferans ekle.' },
]

export function makeHelpResponse(overrides?: { sections?: typeof HELP_DEFAULT_SECTIONS }) {
  return { sections: overrides?.sections ?? HELP_DEFAULT_SECTIONS }
}

const HELP_DEFAULT_HANDLER = http.get(`${API}/api/help`, () =>
  HttpResponse.json(makeHelpResponse()),
)

export const LAW_ABBREVIATIONS_DEFAULT = {
  laws: [
    { name: 'Gelir Vergisi Kanunu', number: '193', abbrevs: ['GVK'] },
    { name: 'Vergi Usul Kanunu', number: '213', abbrevs: ['VUK'] },
    { name: 'Katma Değer Vergisi Kanunu', number: '3065', abbrevs: ['KDV', 'KDVK'] },
    { name: 'Kurumlar Vergisi Kanunu', number: '5520', abbrevs: ['KVK'] },
  ],
}

const LAW_ABBREVIATIONS_HANDLER = http.get(`${API}/api/law-abbreviations`, () =>
  HttpResponse.json(LAW_ABBREVIATIONS_DEFAULT),
)

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

// ----- Training -----

export function makeStartResponse(overrides: Partial<{ attempt_id: number; attempt_number: number }> = {}) {
  return {
    attempt_id: overrides.attempt_id ?? 100,
    attempt_number: overrides.attempt_number ?? 1,
    questions: [
      { id: 'q01', text: 'Soru 1', choices: ['a', 'b', 'c', 'd'] },
      { id: 'q02', text: 'Soru 2', choices: ['a', 'b', 'c', 'd'] },
      { id: 'q03', text: 'Soru 3', choices: ['a', 'b', 'c', 'd'] },
      { id: 'q04', text: 'Soru 4', choices: ['a', 'b', 'c', 'd'] },
      { id: 'q05', text: 'Soru 5', choices: ['a', 'b', 'c', 'd'] },
    ],
    gold_docs: [
      { gold_id: 'gold_a', content: 'Doc A içeriği' },
      { gold_id: 'gold_b', content: 'Doc B içeriği' },
      { gold_id: 'gold_c', content: 'Doc C içeriği' },
    ],
  }
}

const TRAINING_DEFAULT_HANDLERS = [
  http.post(`${API}/api/training/start`, () => HttpResponse.json(makeStartResponse())),
  http.post(`${API}/api/training/quiz/submit`, () => HttpResponse.json({
    score: 4, total: 5,
    results: [
      { question_id: 'q01', user_choice: 0, correct_choice: 0, is_correct: true },
      { question_id: 'q02', user_choice: 1, correct_choice: 1, is_correct: true },
      { question_id: 'q03', user_choice: 0, correct_choice: 2, is_correct: false },
      { question_id: 'q04', user_choice: 3, correct_choice: 3, is_correct: true },
      { question_id: 'q05', user_choice: 1, correct_choice: 1, is_correct: true },
    ],
  })),
  http.post(`${API}/api/training/annotate/submit`, () =>
    HttpResponse.json({
      passed: true,
      matched_count: 2,
      expected_count: 2,
      min_concept_count: 1,
      expected_concepts: [{ kanun_no: '5520', madde: '5' }],
    }),
  ),
  http.post(`${API}/api/me/seen-manual`, () => HttpResponse.json({ ok: true })),
]

export function mockTrainingStartLockedOut() {
  return http.post(`${API}/api/training/start`, () =>
    HttpResponse.json({ detail: { error: 'max_attempts_reached', message: 'too many' } }, { status: 403 }),
  )
}

export function mockTrainingStartAlreadyPassed() {
  return http.post(`${API}/api/training/start`, () =>
    HttpResponse.json({ detail: { error: 'already_passed', message: 'already' } }, { status: 409 }),
  )
}

export function mockQuizSubmitAlreadySubmitted() {
  return http.post(`${API}/api/training/quiz/submit`, () =>
    HttpResponse.json({ detail: { error: 'quiz_already_submitted', message: 'dup' } }, { status: 409 }),
  )
}

export function mockAnnotateSubmitAlreadySubmitted() {
  return http.post(`${API}/api/training/annotate/submit`, () =>
    HttpResponse.json({ detail: { error: 'gold_doc_already_submitted', message: 'dup' } }, { status: 409 }),
  )
}

export function mockAnnotateSubmitFail() {
  return http.post(`${API}/api/training/annotate/submit`, () =>
    HttpResponse.json({
      passed: false,
      matched_count: 0,
      expected_count: 2,
      min_concept_count: 1,
      expected_concepts: [{ kanun_no: '5520', madde: '5' }],
    }),
  )
}

// ---- 16e admin handlers ----

export const adminAuditLogHandler = http.get(`${API}/api/admin/audit-log`, () => {
  return HttpResponse.json({ items: [], total: 0, has_more: false })
})

export const adminSystemEventsHandler = http.get(`${API}/api/admin/system-events`, () => {
  return HttpResponse.json({ items: [], total: 0, has_more: false })
})

export const adminSettingsHandler = http.get(`${API}/api/admin/settings`, () => {
  return HttpResponse.json({
    'training.quiz_pass_threshold': 4,
    'training.annotation_pass_threshold': 2,
    'gamification.xp_doc_save': 5,
  })
})

export const adminUsersHandler = http.get(`${API}/api/admin/users`, () => {
  return HttpResponse.json({
    users: [{
      id: 1, username: 'root', email: null, role: 'admin', is_active: true,
      has_seen_manual: true, has_passed_training: true,
      avatar_color: null, created_at: '2026-05-01T00:00:00+00:00',
    }],
    total: 1,
  })
})

export const adminGoldDocsHandler = http.get(`${API}/api/admin/training/gold-docs`, () => {
  return HttpResponse.json({ resolved: [], overrides: [] })
})

export const adminQuizHandler = http.get(`${API}/api/admin/training/quiz`, () => {
  return HttpResponse.json({ resolved: [], overrides: [] })
})

export const adminFeedbackHandler = http.get(`${API}/api/admin/feedback`, () => {
  return HttpResponse.json([makeFeedbackRow()])
})

export const adminHandlers = [
  adminAuditLogHandler,
  adminSystemEventsHandler,
  adminSettingsHandler,
  adminUsersHandler,
  adminGoldDocsHandler,
  adminQuizHandler,
  adminFeedbackHandler,
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
  HELP_DEFAULT_HANDLER,
  LAW_ABBREVIATIONS_HANDLER,
  ...TRAINING_DEFAULT_HANDLERS,
  ...ANNOTATE_DEFAULTS,
  ...GAMIFICATION_DEFAULTS,
  ...adminHandlers,
]

export function mockAuthedUser(overrides: Partial<User> = {}) {
  return http.get(`${API}/api/auth/me`, () => HttpResponse.json(makeUser(overrides)))
}

export function mockAnonUser() {
  return http.get(`${API}/api/auth/me`, () =>
    HttpResponse.json({ detail: { error: 'unauthorized', message: '' } }, { status: 401 }),
  )
}
