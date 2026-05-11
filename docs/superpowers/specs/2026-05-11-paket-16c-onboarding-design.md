# Paket 16c — Onboarding: Help Viewer + Training Quiz (Design)

**Status**: Draft — design phase
**Date**: 2026-05-11
**Builds on**: Paket 16a (frontend foundation, tag `paket-16a-frontend-foundation`), Paket 16b (annotate workflow, tag `paket-16b-annotate-workflow`)
**Backend dependencies (already shipped)**: Paket 3 (`docs_help` endpoints, 9 markdown sections), Paket 10 (`training` endpoints, 5 quiz Q + 3 gold doc per attempt)
**Backend touches in 16c**: **zero**

---

## 1. Goal & Scope

Activate the onboarding gates wired but bypassed in 16a:
- `RequireSeenManual` → `/help?first_time=true`
- `RequirePassedTraining` → `/training`

These currently redirect to STUB routes. Paket 16c replaces both STUBs with production content:

1. **`/help`** — markdown viewer presenting 9 onboarding sections (welcome, getting-started, annotation-guide, chain-review, keyboard-shortcuts, rules, gamification, faq, thanks). First-time mode adds a bottom CTA that flips `has_seen_manual=1` and routes the user to training.
2. **`/training`** — 5-step wizard:
   - Step 1: Quiz (5 multiple-choice questions, threshold ≥4)
   - Steps 2-4: Annotate 3 gold-standard documents (threshold ≥2 pass)
   - Step 5: Summary screen with overall verdict
   - Sub-state: `locked-out` after 3 failed attempts (`max_attempts_reached`)

After a successful training pass, the user enters the main annotation surface (`/`) — gates re-evaluate against the updated `/auth/me` payload.

**Out of scope**:
- Markdown TOC / search / filter — accordion is the chosen affordance
- Coaching feedback ("which concept was missed") — opt-in for a future package
- Mid-attempt backend resume endpoint — backend remains untouched
- "Attempts remaining" counter UI — backend does not expose it; UI relies on the `/start 403` response for lockout truth
- TopBar `/help` link — arrives in Paket 16d
- Admin email override / runtime config for lockout screen — arrives in Paket 16e (static placeholder for now)
- Training analytics / engagement instrumentation — opt-in for future

---

## 2. Tech Stack Additions

Existing 16a/16b stack continues unchanged. New runtime dependencies:

| Package | Version | Purpose |
|---|---|---|
| `react-markdown` | ^9.0.0 | Render markdown bodies (`/help` sections) |
| `remark-gfm` | ^4.0.0 | Tables, task lists, autolinks |
| `rehype-sanitize` | ^6.0.0 | Strict element whitelist; XSS defense-in-depth |

`zod` is already a dependency (`^3.25.76`) — used here for runtime validation of `/help` and `/training/start` payloads (see §11).

**Forbidden additions**: `rehype-raw` is explicitly banned. Adding it bypasses sanitization. Spec calls this out so future PRs do not regress.

No new dev dependencies. ESLint config and TypeScript settings unchanged.

---

## 3. Backend Contract (Locked — Do Not Modify)

### 3.1 Help

```
GET /api/help
  Auth: required (has_seen_manual NOT required — chicken-and-egg by design)
  Response 200: { sections: [{ id: str, order: int, title: str, body: str }, …] }
  Sorted by `order` ascending. 9 sections currently shipped.
```

### 3.2 Manual flag

```
POST /api/me/seen-manual
  Auth: required
  Response 200: { ok: true }
  Side effect: UPDATE users SET has_seen_manual=1 WHERE id=?
  Idempotent.
```

### 3.3 Training

```
GET /api/training/start
  Auth: require_seen_manual (409 manual_not_seen if not)
  Response 200: {
    attempt_id: int,
    attempt_number: int,             # 1-based; counts ALL attempts including abandoned
    questions: [5 × { id, text, choices: str[] }],
    gold_docs: [3 × { gold_id: str, content: str }],
  }
  Error 409 already_passed   — has_passed_training already 1
  Error 403 max_attempts_reached — admin reset required
  *** EVERY successful call creates a NEW attempt. Abandoned attempts COUNT. ***

POST /api/training/quiz/submit
  Body: { attempt_id: int, answers: Record<question_id, choice_idx> }
  Response 200: { score: int, total: int }
  Error 409 quiz_already_submitted — this attempt already has quiz scored
  Side effect: writes quiz_score to attempt; triggers finalize_if_complete

POST /api/training/annotate/submit
  Body: { attempt_id: int, gold_id: str, references: ReferenceItem[] }
  Response 200: { passed: bool, matched_count: int, expected_count: int, min_concept_count: int }
  Error 409 gold_doc_already_submitted — this attempt already has this gold doc
  Side effect: writes annotation result to attempt; triggers finalize_if_complete
                On 3rd distinct doc submit, server computes:
                  overall_pass = (quiz_score >= settings.training.quiz_pass_threshold default 4)
                              AND (annotation_pass_count >= settings.training.annotation_pass_threshold default 2)
                If overall_pass: UPDATE users SET has_passed_training=1; award XP; create notification.
```

`ReferenceItem` shape (shared with 16b annotations):

```ts
{
  kanun_no: str | null,
  kanun_ad: str | null,
  madde: str | null,
  fikra: str | null,
  bent: str | null,
  source_text: str,   // non-null, may be empty
}
```

---

## 4. Locked Design Decisions

Each decision below was confirmed in user Q&A during the brainstorming phase.

| # | Decision | Rationale |
|---|---|---|
| D1 | Help layout = shadcn `Accordion`, `type="multiple"`, Welcome open by default | User chose over TOC sidebar and wizard pagination. Scannable; persistent state per session. |
| D2 | `has_seen_manual=1` flips only on explicit "Anladım, eğitime geç" CTA click | Auto-flip on visit is too cheap (gameable); scroll/all-opened heuristics are fragile. Explicit intent is the only honest contract. |
| D3 | `/training` = 5-step wizard (Quiz → Doc1 → Doc2 → Doc3 → Sonuç) | Mirrors backend's 4-endpoint flow 1:1 (quiz/submit + 3× annotate/submit + finalize-on-3rd). Single-page or tabs would require batching that the backend does not support. |
| D4 | Mid-attempt resilience via sessionStorage + beforeunload — POST `/start` ONLY on explicit click | Backend has no resume endpoint. Storage is best-effort hint; UI never auto-calls `/start`. Trust model documented (§8.4). |
| D5 | Training reuses existing 16b `ReferenceCard` (presentational, already extracted) | Visual parity with production. No re-design. Validation is training-side (D6) so 16b behavior is unchanged. |
| D6 | Per-step immediate feedback (score / pass / fail) before "Sonraki" button | Honest, momentum-preserving. Coaching ("hangi konsept kaçırıldı") is out of scope. |
| D7 | Summary screen — three variants: PASS detailed, FAIL ([Tekrar Dene]), DEGRADED (when restore is corrupt). No "N kaldı" counter (backend doesn't expose). 3rd-fail → locked-out screen via `/start 403`. | Backend response is truth. UI never invents the remaining-attempt number. |

---

## 5. Folder Structure

### 5.1 New files

```
frontend/src/
├── routes/
│   ├── Help.tsx                          # REPLACES STUB (16a)
│   └── Training.tsx                      # REPLACES STUB (16a)
│
├── components/
│   ├── help/
│   │   ├── HelpAccordion.tsx
│   │   ├── HelpSection.tsx
│   │   └── MarkdownView.tsx              # react-markdown wrapper with sanitize
│   │
│   └── training/
│       ├── TrainingProgress.tsx          # 5-pill stepper
│       ├── StartScreen.tsx               # confirm checkbox + Başla
│       ├── QuizStep.tsx
│       ├── AnnotateStep.tsx
│       ├── SummaryStep.tsx               # PASS / FAIL / DEGRADED variants
│       ├── LockedOutScreen.tsx
│       └── PendingStartBanner.tsx        # belt-and-braces (§8.5)
│
├── api/queries/
│   ├── help.ts                           # useHelpQuery
│   ├── training.ts                       # useTrainingStartMutation, useQuizSubmitMutation, useAnnotateSubmitMutation
│   └── me.ts                             # useSeenManualMutation (or extend auth.ts)
│
├── hooks/
│   └── useBeforeUnload.ts                # generic
│
├── stores/
│   └── trainingStore.ts                  # Zustand + persist(sessionStorage)
│
├── lib/
│   ├── refreshAuth.ts                    # await fetchQuery(authKeys.me) + authStore.setUser
│   ├── apiError.ts                       # isApiError, is409*, is403*
│   ├── trainingSchemas.ts                # Zod schemas for help.section + training.start payloads
│   └── trainingRecovery.ts               # submitWithRecovery wrapper (409-ack pattern)
│
└── test/
    └── handlers/                         # new MSW handlers split out for organization
        ├── help.ts
        └── training.ts
```

### 5.2 Modified files

```
frontend/src/
├── App.tsx                               # NO route-tree changes (gates already wired in 16a)
├── package.json                          # adds react-markdown, remark-gfm, rehype-sanitize
└── test/handlers.ts                      # imports new handler files
```

`ReferenceCard.tsx` is unchanged. 16b's `ReferencePanel.tsx` is unchanged. 16b validation rules are unchanged. Zero regression risk for 16b.

---

## 6. Routing & Gates

The 16a route tree already places `/help` and `/training` correctly:

```tsx
<Routes>
  <Route path="/login" element={<Login />} />
  <Route path="/register" element={<Register />} />

  <Route element={<RequireAuth />}>
    <Route path="/help" element={<Help />} />          {/* Outside RequireSeenManual — chicken/egg */}

    <Route element={<RequireSeenManual />}>
      <Route path="/training" element={<Training />} />

      <Route element={<RequirePassedTraining />}>
        <Route element={<AppShell />}>
          <Route element={<AnnotateLayout />}>
            <Route path="/" element={<Annotate />} />
            <Route path="/docs/:docId" element={<AnnotateDoc />} />
          </Route>
          <Route path="/me" element={<Profile />} />
        </Route>
      </Route>
    </Route>

    <Route path="/admin/*" element={<RequireAdmin><AdminLayout /></RequireAdmin>} />
  </Route>

  <Route path="*" element={<NotFound />} />
</Routes>
```

### 6.1 Already-passed defensive redirect

Inherited by 16c as a new requirement (Codex-2 FRAGILE-D):
- `Training.tsx` mount effect: `if (auth.user.has_passed_training) navigate('/', { replace: true })`
- `useTrainingStartMutation` onError: if `is409AlreadyPassed(err)` → `await refreshAuth(qc)` → `navigate('/', { replace: true })`

This protects users who:
- Manually type `/training` after completing it
- Have a stale tab open after passing in another tab

### 6.2 Locked-out

Reached when:
- Fresh `POST /api/training/start` returns `403 max_attempts_reached`

Mount effect in `Training.tsx`:
1. If restoring from sessionStorage with `step === 'locked-out'` → render `LockedOutScreen` directly
2. Else proceed to normal idle/restore flow

A locked-out user can still visit `/help` (gate ordering allows it) and click "Çıkış yap" from `LockedOutScreen`.

---

## 7. Help Viewer (`/help`)

### 7.1 Layout

Single column, `max-w-3xl mx-auto`, mounted within `RequireAuth` (no `AppShell` since AppShell would render the gated TopBar — out of scope here). Vertical accordion. Welcome (`01-welcome`) open by default.

```
┌─────────────────────────────────────────────┐
│ Yardım Kılavuzu                             │   ← h1 (focus on mount)
│                                             │
│ Lütfen başlamadan önce kılavuzu okuyup      │   ← banner ONLY in first_time=true
│ eğitime geç.                                │
├─────────────────────────────────────────────┤
│ ▼ Hoş geldin                                │
│   (markdown rendered body)                  │
├─────────────────────────────────────────────┤
│ ▶ Başlarken                                 │
├─────────────────────────────────────────────┤
│ … 9 sections total                          │
├─────────────────────────────────────────────┤
│                                             │
│   [Anladım, eğitime geç ▸]                  │   ← CTA ONLY in first_time=true
│                                             │
└─────────────────────────────────────────────┘
```

In normal mode (`?first_time` absent or user already has `has_seen_manual=1`), banner and CTA are hidden — page is browse-only reference.

### 7.2 Markdown rendering & security

`MarkdownView.tsx`:

```tsx
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'

const allowedTags = [
  'h1','h2','h3','h4','h5','h6',
  'p','br','hr',
  'ul','ol','li',
  'strong','em','code','pre','blockquote',
  'a','img',
  'table','thead','tbody','tr','td','th',
]

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: allowedTags,
  attributes: {
    ...defaultSchema.attributes,
    a: [...(defaultSchema.attributes?.a ?? []), ['target']],
  },
}

export function MarkdownView({ children }: { children: string }) {
  return (
    <div className="prose prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
```

**Forbidden**: `rehype-raw`. Spec calls this out for future PR reviewers.

Test: a fixture markdown body containing `<script>alert("xss")</script>` is loaded; assert that `screen.queryByText` does not find the alert text and that no `<script>` exists in the DOM.

### 7.3 Components

- **`Help.tsx`**: reads `useSearchParams()` for `first_time`, fetches `useHelpQuery()`, renders banner/CTA conditionally. On CTA click: `await useSeenManualMutation.mutateAsync()` → `await refreshAuth(qc)` → `navigate('/training', { replace: true })`. Error: `toast.error()`, button re-enabled.
- **`HelpAccordion.tsx`**: receives `sections: HelpSection[]`, renders Radix `Accordion type="multiple" defaultValue={[sections[0].id]}`. Each item wraps a `<HelpSection>`.
- **`HelpSection.tsx`**: receives `{ id, order, title, body }`; renders trigger (title) and content (`<MarkdownView>{body}</MarkdownView>`).

### 7.4 Hook

```ts
// api/queries/help.ts
export const helpKeys = {
  all: ['help'] as const,
  sections: () => [...helpKeys.all, 'sections'] as const,
}

export function useHelpQuery() {
  return useQuery({
    queryKey: helpKeys.sections(),
    queryFn: async () => {
      const raw = await unwrap(client.GET('/api/help'))
      return helpResponseSchema.parse(raw)  // Zod (see §11)
    },
    staleTime: Infinity,
  })
}
```

`staleTime: Infinity` because markdown rarely changes; manual refresh comes via Paket 16e admin actions (out of 16c scope).

### 7.5 Seen-manual mutation

```ts
// api/queries/me.ts
export function useSeenManualMutation() {
  return useMutation({
    mutationFn: () => unwrap(client.POST('/api/me/seen-manual')),
  })
}
```

`refreshAuth(qc)` is called AFTER successful mutation by the consumer (`Help.tsx`), not inside the mutation, because the consumer also needs to navigate.

---

## 8. Training Wizard (`/training`)

### 8.1 State machine

```
[idle]
  │
  │ user: click "Başla" (after confirm checkbox)
  ▼
[loading] ─── POST /start ─┬─ 200 ──▶ [quiz]
                           │            (store.hydrate(startResponse))
                           ├─ 409 already_passed ──▶ refreshAuth + navigate('/')
                           └─ 403 max_attempts_reached ──▶ [locked-out]

[quiz]
  │
  │ user: answer 5, click "Cevapları Gönder"
  ▼
[quiz-submitting] ─── POST /quiz/submit ─┬─ 200 ──▶ [quiz-result-shown]
                                          │            (store.recordQuizResult)
                                          └─ 409 ──▶ submitWithRecovery (§8.6)

[quiz-result-shown] ──── user: click "Sonraki: Doküman 1" ──▶ [doc, docIndex=0]

[doc, docIndex=i]
  │
  │ user: edit references, click "Submit & Sonraki"
  ▼
[doc-submitting] ─── POST /annotate/submit ─┬─ 200 ──▶ [doc-result-shown, docIndex=i]
                                             │            (store.recordDocResult)
                                             └─ 409 ──▶ submitWithRecovery (§8.6)

[doc-result-shown, docIndex<2] ──── user: click "Sonraki: Doküman j+1" ──▶ [doc, docIndex=i+1]

[doc-result-shown, docIndex=2] ──── user: click "Sonuçları Gör" ──▶
                                      await refreshAuth(qc)
                                      ──▶ [summary]  (PASS or FAIL variant from auth.user + store)
                                      (if refreshAuth fails → still go to [summary], degraded mode)

[summary, PASS] ──── user: click "Anotasyona Başla" ──▶ store.clear() + navigate('/')
[summary, FAIL] ──── user: click "Tekrar Dene" ──▶ store.clear() + POST /start (back to [loading])
                                                    (if 403 ──▶ [locked-out])
[summary, FAIL] ──── user: click "← Kılavuza dön" ──▶ navigate('/help')

[locked-out] ──── user: click "Çıkış yap" ──▶ POST /api/auth/logout + clear + navigate('/login')
[locked-out] ──── user: click "Yardımı incele" ──▶ navigate('/help')
```

`step` values stored in trainingStore are the **persistent** states: `idle | quiz | doc | summary | locked-out`. The transient sub-states (`loading`, `*-submitting`, `*-result-shown`) live in component-local state.

### 8.2 Store shape

```ts
// stores/trainingStore.ts
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type TrainingStep = 'idle' | 'quiz' | 'doc' | 'summary' | 'locked-out'

export type ReferenceDraft = ReferenceItem  // alias from generated types

export type TrainingState = {
  attemptId: number | null
  attemptNumber: number | null
  step: TrainingStep
  docIndex: 0 | 1 | 2
  questions: Question[]                      // 5
  goldDocs: GoldDoc[]                        // 3
  quizAnswers: Record<string, number>
  quizResult: { score: number; total: number } | null
  docRefs: Record<string, ReferenceDraft[]>      // by gold_id
  docResults: Record<string, AnnotateSubmitResponse>  // by gold_id
  resultShown: { kind: 'quiz' } | { kind: 'doc'; goldId: string } | null
  degraded: boolean                          // set if recovery couldn't resolve
}

export type TrainingActions = {
  hydrate: (start: StartResponse) => void
  setQuizAnswer: (questionId: string, choice: number) => void
  recordQuizResult: (r: QuizSubmitResponse) => void
  showResult: (kind: TrainingState['resultShown']) => void
  setDocRefs: (goldId: string, refs: ReferenceDraft[]) => void
  recordDocResult: (goldId: string, r: AnnotateSubmitResponse) => void
  advanceDoc: () => void                     // 0→1→2 (no summary transition; that's manual after refreshAuth)
  setStep: (step: TrainingStep) => void
  markDegraded: () => void
  clear: () => void
}

const initialState: TrainingState = {
  attemptId: null, attemptNumber: null,
  step: 'idle', docIndex: 0,
  questions: [], goldDocs: [],
  quizAnswers: {}, quizResult: null,
  docRefs: {}, docResults: {},
  resultShown: null, degraded: false,
}

export const useTrainingStore = create<TrainingState & TrainingActions>()(
  persist(
    (set, get) => ({
      ...initialState,
      hydrate: (s) => set({
        attemptId: s.attempt_id, attemptNumber: s.attempt_number,
        step: 'quiz', docIndex: 0,
        questions: s.questions, goldDocs: s.gold_docs,
        quizAnswers: {}, quizResult: null,
        docRefs: Object.fromEntries(s.gold_docs.map(d => [d.gold_id, []])),
        docResults: {}, resultShown: null, degraded: false,
      }),
      setQuizAnswer: (qid, c) => set((s) => ({ quizAnswers: { ...s.quizAnswers, [qid]: c } })),
      recordQuizResult: (r) => set({ quizResult: r, resultShown: { kind: 'quiz' } }),
      showResult: (kind) => set({ resultShown: kind }),
      setDocRefs: (gid, refs) => set((s) => ({ docRefs: { ...s.docRefs, [gid]: refs } })),
      recordDocResult: (gid, r) => set((s) => ({
        docResults: { ...s.docResults, [gid]: r },
        resultShown: { kind: 'doc', goldId: gid },
      })),
      advanceDoc: () => set((s) => {
        if (s.docIndex < 2) return { docIndex: (s.docIndex + 1) as 0 | 1 | 2, resultShown: null }
        return { resultShown: null }  // caller will transition to summary
      }),
      setStep: (step) => set({ step, resultShown: null }),
      markDegraded: () => set({ degraded: true }),
      clear: () => {
        sessionStorage.removeItem('training-attempt-v1')
        set({ ...initialState })
      },
    }),
    {
      name: 'training-attempt-v1',
      storage: createJSONStorage(() => sessionStorage),
      version: 1,
      partialize: (s) => ({
        attemptId: s.attemptId, attemptNumber: s.attemptNumber,
        step: s.step, docIndex: s.docIndex,
        questions: s.questions, goldDocs: s.goldDocs,
        quizAnswers: s.quizAnswers, quizResult: s.quizResult,
        docRefs: s.docRefs, docResults: s.docResults,
        resultShown: s.resultShown, degraded: s.degraded,
      }),
      migrate: (oldState, oldVersion) => {
        if (oldVersion < 1) return undefined as unknown as TrainingState  // drop any v0
        return oldState as TrainingState
      },
      onRehydrateStorage: () => (state, error) => {
        if (error || !state) return
        if (!validateRestoredShape(state)) {
          // shape invalid → wipe & reset
          sessionStorage.removeItem('training-attempt-v1')
          useTrainingStore.setState(initialState)
        }
      },
    }
  )
)

function validateRestoredShape(s: Partial<TrainingState>): boolean {
  if (s.attemptId !== null && typeof s.attemptId !== 'number') return false
  if (typeof s.step !== 'string') return false
  if (!['idle', 'quiz', 'doc', 'summary', 'locked-out'].includes(s.step)) return false
  if (![0, 1, 2].includes(s.docIndex as number)) return false
  if (s.step === 'quiz' || s.step === 'doc' || s.step === 'summary') {
    if (!Array.isArray(s.questions) || s.questions.length !== 5) return false
    if (!Array.isArray(s.goldDocs) || s.goldDocs.length !== 3) return false
    if (typeof s.attemptId !== 'number') return false
  }
  return true
}
```

### 8.3 Atomic start-write protection (Codex-2 BROKEN-C mitigation)

Race window: `POST /start` returns success → store mutation → sessionStorage write. If the browser crashes between response and write, an attempt is silently consumed.

**Mitigations**:

1. **Mutation in-flight disable**: `[Başla]` button has `disabled={mut.isPending}`. No double-click possible.
2. **Synchronous store commit**: Zustand `persist` middleware writes to sessionStorage synchronously inside the `setState` call. `store.hydrate(startResponse)` is called inside the `onSuccess` callback before any `setState` from component render returns. UI does not paint the new step until storage commit.
3. **Pending-start sentinel** (belt-and-braces):
   - Just before calling `POST /start`: `sessionStorage.setItem('training-start-pending', JSON.stringify({ ts: Date.now() }))`
   - On successful hydrate: `sessionStorage.removeItem('training-start-pending')`
   - On any mount of `Training.tsx`, if the sentinel is present AND `training-attempt-v1` is empty → render `<PendingStartBanner />`:

   ```
   ┌─────────────────────────────────────────────┐
   │ ⚠ Önceki başlatma yarıda kaldı              │
   │ Bir deneme harcanmış olabilir.              │
   │   [Yeni denemeyi başlat]  [Anladım, kapat]  │
   └─────────────────────────────────────────────┘
   ```

   "Anladım, kapat" → clear sentinel + show StartScreen. "Yeni denemeyi başlat" → clear sentinel + immediately call `/start`.

### 8.4 Trust model — what sessionStorage means

- Storage is a **best-effort hint** for resume. It is NEVER authoritative for whether the backend has received a submit.
- The backend is authoritative; its responses (200 with payload, or 409 already_submitted) are the only truth.
- On every submit:
  - 200 → record result, advance
  - 409 already_submitted → enter recovery flow (§8.6)
- On every "training pass" decision: AWAIT `refreshAuth(qc)` and read `user.has_passed_training`. Do not trust local state.
- On corrupt restore (`validateRestoredShape` fails): wipe storage, reset to initial state. User sees StartScreen.

### 8.5 beforeunload

`useBeforeUnload(enabled, message?)`:

```ts
export function useBeforeUnload(enabled: boolean, message?: string) {
  useEffect(() => {
    if (!enabled) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = message ?? ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [enabled, message])
}
```

Enabled when `step ∈ {quiz, doc}` AND no submit is in flight (avoid showing the prompt during navigation triggered by a successful submit).

**Known limitation** (Codex-2 FRAGILE-H, accepted): `beforeunload` is not honored by every mobile browser or on every navigation path. The StartScreen warning (§8.7) is the primary user education.

### 8.6 Recovery — submitWithRecovery

```ts
// lib/trainingRecovery.ts
export class AbortAdvance extends Error {
  constructor() { super('caller should not advance; recovery has redirected'); this.name = 'AbortAdvance' }
}

export type RecoveryKey = { kind: 'quiz' } | { kind: 'doc'; goldId: string }

export async function submitWithRecovery<R>(
  args: {
    submit: () => Promise<R>,
    key: RecoveryKey,
    qc: QueryClient,
  }
): Promise<R> {
  try {
    return await args.submit()
  } catch (err) {
    if (!isApiError(err)) throw err

    const store = useTrainingStore.getState()
    const code = err.code

    if (args.key.kind === 'quiz' && code === 'quiz_already_submitted') {
      const cached = store.quizResult
      if (cached) return cached as unknown as R
      // No prior result: backend says we did it but we don't have the score
      await refreshAuth(args.qc)
      store.markDegraded()
      store.setStep('summary')
      throw new AbortAdvance()
    }

    if (args.key.kind === 'doc' && code === 'gold_doc_already_submitted') {
      const cached = store.docResults[args.key.goldId]
      if (cached) return cached as unknown as R
      // No prior result: same DEGRADED path
      await refreshAuth(args.qc)
      store.markDegraded()
      store.setStep('summary')
      throw new AbortAdvance()
    }

    throw err
  }
}
```

Callers (QuizStep, AnnotateStep) catch `AbortAdvance` specifically — when it fires, they DO NOT call `store.advance*` or transition; the recovery path has already set `step='summary'`.

### 8.7 Per-step components

**`StartScreen.tsx`** (`step === 'idle'`):

```
┌─────────────────────────────────────────────┐
│ Eğitim                                      │
├─────────────────────────────────────────────┤
│ Aşağıdaki adımlardan oluşur:                │
│   1. 5 soruluk quiz (≥4 doğru)              │
│   2. 3 doküman üzerinde anotasyon (≥2 geçer)│
│                                             │
│ ⚠ DİKKAT: Başladığında 1 deneme harcanır.   │
│   Sayfayı yarıda kapatırsan o deneme        │
│   kaybolur ve hak harcanmış sayılır.        │
│   Maksimum 3 denemen var.                   │
│                                             │
│ ☐ Anladım, başlamaya hazırım                │   ← required checkbox
│                                             │
│   [Başla]   [← Kılavuza dön]                │   ← Başla disabled until checked
└─────────────────────────────────────────────┘
```

**`QuizStep.tsx`** (`step === 'quiz'` AND `resultShown !== {kind:'quiz'}`):

```
[●─○─○─○─○]  1/5: Quiz
─────────────────────────────────────────────
 ⓘ 5 soruyu cevapla, sonra "Cevapları Gönder"
   tuşuna bas. Skorunu hepsini birden öğrenirsin.
─────────────────────────────────────────────
 <fieldset>
   <legend>1. <question text></legend>
   ⚪ choice 0
   ⚪ choice 1
   ⚪ choice 2
   ⚪ choice 3
 </fieldset>

 …4 more fieldsets…

 [Cevapları Gönder]    ← disabled until 5 answered
```

After submit success → `resultShown = {kind:'quiz'}` → render result card replaces form:

```
[●─●─○─○─○]  Quiz tamamlandı
─────────────────────────────────────────────
<div role="status" aria-live="polite">
  ✓ Skor: 3 / 5
    (Geçmek için ≥4 gerekir)
</div>

 [Sonraki: Doküman 1 ▸]   ← focus moves here on render
```

Click → `store.setStep('doc')` (docIndex already 0) → `resultShown=null`.

**`AnnotateStep.tsx`** (`step === 'doc'` AND `resultShown` is not a doc result for the current docIndex):

```
[●─●─●─○─○]  3/5: Doküman 1
─────────────────────────────────────────────
<article>
  <h2 tabIndex={-1}>Doküman 1</h2>
  <p>{goldDocs[docIndex].content paragraphed}</p>
</article>
─────────────────────────────────────────────
<section aria-labelledby="refs-heading">
  <h3 id="refs-heading">Referanslar (kanun atfı yoksa boş bırakabilirsin)</h3>

  <ReferenceCard index=0 value=…  onChange onRemove disabled=submitting />
  <ReferenceCard index=1 …/>
  …

  [+ Yeni Referans]
</section>

[Submit & Sonraki ▸]    ← disabled while training-side validation fails
                          (see §10)
```

After submit success:

```
[●─●─●─●─○]  Doküman 1 tamamlandı
─────────────────────────────────────────────
<div role="status" aria-live="polite">
  ✓ Eşleşme: 2 / 2
    Durum: Geçti
</div>
                                              ← focus moves here
 [Sonraki: Doküman 2 ▸]    (or "Sonuçları Gör" when docIndex === 2)
```

For `docIndex === 2`, the click handler is special:

```ts
const onNext = async () => {
  try {
    await refreshAuth(qc)
  } catch {
    store.markDegraded()
  }
  store.setStep('summary')
}
```

Local state for refs: `useReducer` keyed inside `AnnotateStep` and synced via `store.setDocRefs(goldId, refs)` on every change (so resume restores them).

**`SummaryStep.tsx`** (`step === 'summary'`):

Three variants determined at render-time:

```ts
const auth = useAuthStore((s) => s.user)
const { quizResult, docResults, goldDocs, degraded } = useTrainingStore()

if (degraded) return <SummaryDegraded user={auth} />
if (auth?.has_passed_training) return <SummaryPass quiz={quizResult} docs={docResults} goldDocs={goldDocs} />
return <SummaryFail quiz={quizResult} docs={docResults} goldDocs={goldDocs} />
```

`SummaryPass`:

```
┌─────────────────────────────────────────────┐
│ 🎉 Tebrikler! Eğitimi geçtin                │
├─────────────────────────────────────────────┤
│ Quiz:    4/5   ✓ Geçti                      │
│ Doc 1:   2/2   ✓ Geçti                      │
│ Doc 2:   1/1   ✓ Geçti                      │
│ Doc 3:   0/2   ✗ Geçemedi                   │
│ Anot. geçen: 2 / 3 (gerekli: 2)             │
│                                             │
│ Overall: GEÇTI                              │
│                                             │
│   [Anotasyona Başla ▸]                      │
└─────────────────────────────────────────────┘
```

Click → `store.clear()` → `navigate('/', { replace: true })`.

`SummaryFail`:

```
┌─────────────────────────────────────────────┐
│ Eğitimi geçemedin                           │
├─────────────────────────────────────────────┤
│ Quiz:    2/5   ✗ Geçemedi (eşik 4)          │
│ Doc 1:   1/2   ✓ Geçti                      │
│ Doc 2:   0/1   ✗ Geçemedi                   │
│ Doc 3:   2/2   ✓ Geçti                      │
│ Anot. geçen: 2 / 3 (gerekli: 2)             │
│                                             │
│ Overall: GEÇEMEDİ                           │
│                                             │
│   [Tekrar Dene]   [← Kılavuza dön]          │
└─────────────────────────────────────────────┘
```

"Tekrar Dene" → `store.clear()` → trigger `useTrainingStartMutation`. On 403 → `setStep('locked-out')`. On 409 already_passed → defensive `refreshAuth` + `navigate('/')`.

`SummaryDegraded`:

```
┌─────────────────────────────────────────────┐
│ Sonuç                                       │
├─────────────────────────────────────────────┤
│ Bu attempt için detaylar yeniden            │
│ yüklenemedi.                                │
│                                             │
│ Genel durum: {auth.has_passed_training      │
│   ? 'Geçti' : 'Geçemedi'}                   │
│                                             │
│   {auth.has_passed_training                 │
│     ? <Button onClick=clear+nav('/')>        │
│         Anotasyona Başla ▸                  │
│       </Button>                              │
│     : <Button onClick=clear+POST /start>     │
│         Tekrar Dene                         │
│       </Button>}                             │
└─────────────────────────────────────────────┘
```

No fake breakdown. Auth is the single source of truth in degraded mode.

**`LockedOutScreen.tsx`** (`step === 'locked-out'`):

```
┌─────────────────────────────────────────────┐
│ Maksimum deneme sayısına ulaşıldı           │
├─────────────────────────────────────────────┤
│ Eğitimi geçemedin. Hesabının sıfırlanması   │
│ için bir yöneticiyle iletişime geç.         │
│                                             │
│ İletişim: team@example.com                  │
│                                             │
│   [Yardımı incele]   [Çıkış yap]            │
└─────────────────────────────────────────────┘
```

The email is a static placeholder. Runtime override is Paket 16e scope.

**`TrainingProgress.tsx`**:

```tsx
const labels = ['Quiz', 'Doc 1', 'Doc 2', 'Doc 3', 'Sonuç']
const activeIndex = step === 'quiz' ? 0
  : step === 'doc' ? 1 + docIndex
  : step === 'summary' ? 4
  : -1  // idle/locked-out: no pill highlighted

return (
  <ol role="list" className="flex items-center justify-between">
    {labels.map((label, i) => (
      <li key={label} role="listitem" aria-current={i === activeIndex ? 'step' : undefined}>
        <span className={cn('pill', i < activeIndex && 'done', i === activeIndex && 'active')}>
          {i < activeIndex ? '●' : i === activeIndex ? '◉' : '○'}
        </span>
        <span className="text-xs">{label}</span>
      </li>
    ))}
  </ol>
)
```

### 8.8 Hooks

```ts
// api/queries/training.ts
export const trainingKeys = { all: ['training'] as const }

export function useTrainingStartMutation() {
  return useMutation<StartResponse, ApiError, void>({
    mutationFn: async () => {
      sessionStorage.setItem('training-start-pending', JSON.stringify({ ts: Date.now() }))
      try {
        const raw = await unwrap(client.GET('/api/training/start'))
        const parsed = startResponseSchema.parse(raw)
        return parsed
      } finally {
        // Sentinel is removed on successful hydrate by caller, NOT here,
        // because we want it to persist if hydrate fails for any reason.
      }
    },
  })
}

export function useQuizSubmitMutation() {
  return useMutation<QuizSubmitResponse, ApiError, { attempt_id: number; answers: Record<string, number> }>({
    mutationFn: (body) => unwrap(client.POST('/api/training/quiz/submit', { body })),
  })
}

export function useAnnotateSubmitMutation() {
  return useMutation<
    AnnotateSubmitResponse, ApiError,
    { attempt_id: number; gold_id: string; references: ReferenceItem[] }
  >({
    mutationFn: (body) => unwrap(client.POST('/api/training/annotate/submit', { body })),
  })
}
```

Caller pattern (in `Training.tsx`):

```ts
const startMut = useTrainingStartMutation()

const onStart = async () => {
  try {
    const start = await startMut.mutateAsync()
    store.hydrate(start)  // synchronous; sessionStorage commits before paint
    sessionStorage.removeItem('training-start-pending')
  } catch (err) {
    if (is409AlreadyPassed(err)) {
      await refreshAuth(qc)
      navigate('/', { replace: true })
      return
    }
    if (is403LockedOut(err)) {
      store.setStep('locked-out')
      return
    }
    toast.error('Eğitim başlatılamadı, tekrar dene.')
  }
}
```

---

## 9. ReferenceCard Reuse

`ReferenceCard.tsx` (lines 1-103) is already presentational in 16b:

```ts
interface ReferenceCardProps {
  index: number
  value: ReferenceItem
  onChange: (next: ReferenceItem) => void
  onRemove: () => void
  disabled: boolean
}
```

`AnnotateStep.tsx` (training) imports it directly:

```tsx
import { ReferenceCard } from '@/components/annotation/ReferenceCard'
```

No extraction work. No modification. 16b regression risk: zero.

**Difference at the call site** (training vs 16b):
- 16b `ReferencePanel` wires `onChange` to a draft autosave reducer (`useReferencesState`) and `disabled` to the lock state.
- 16c `AnnotateStep` wires `onChange` to a local `useReducer` and `disabled` to `submitMut.isPending`. No autosave, no lock, no SSE.

The component cannot tell the difference.

---

## 10. Validation Strategy

**16b annotation validation is unchanged.** This spec explicitly preserves whatever client-side validation rules 16b ships. (Browser-native `required` on `source_text` per `ReferenceCard.tsx:97`. `kanun_no` is NOT client-side required in 16b.)

**Training-side validation is stricter and lives in `Training.tsx` only**, NOT in a shared helper:

```ts
// inside AnnotateStep.tsx
function isTrainingReferenceValid(r: ReferenceItem): boolean {
  if (!r.source_text || r.source_text.trim().length === 0) return false
  if (!r.kanun_no || r.kanun_no.trim().length === 0) return false
  return true
}

const allValid = refs.every(isTrainingReferenceValid)
// [Submit & Sonraki] disabled={!allValid || submitting}
```

**No shared `lib/validateReferences.ts` is created** — Codex-2 BROKEN-B prevents leaking strict rules into 16b.

Backend continues to enforce its own validation (returns 422 on malformed body). Training-side validation is a UX gate, not a security boundary.

---

## 11. Type Guards & Runtime Validation

`openapi-typescript` produces weak types for several endpoints (`/api/help` resolves to `unknown` per the generated `types.ts`). Defense:

### 11.1 Zod schemas (`lib/trainingSchemas.ts`)

```ts
import { z } from 'zod'

export const helpSectionSchema = z.object({
  id: z.string(),
  order: z.number().int(),
  title: z.string(),
  body: z.string(),
})

export const helpResponseSchema = z.object({
  sections: z.array(helpSectionSchema),
})

export const questionSchema = z.object({
  id: z.string(),
  text: z.string(),
  choices: z.array(z.string()).length(4),  // backend ships 4 choices
})

export const goldDocSchema = z.object({
  gold_id: z.string(),
  content: z.string(),
})

export const startResponseSchema = z.object({
  attempt_id: z.number().int(),
  attempt_number: z.number().int(),
  questions: z.array(questionSchema).length(5),
  gold_docs: z.array(goldDocSchema).length(3),
})

export const quizSubmitResponseSchema = z.object({
  score: z.number().int(),
  total: z.number().int(),
})

export const annotateSubmitResponseSchema = z.object({
  passed: z.boolean(),
  matched_count: z.number().int(),
  expected_count: z.number().int(),
  min_concept_count: z.number().int(),
})
```

Each `.parse()` call inside the mutation/query body converts `unknown` → typed at runtime. Failures throw `ZodError`, caught by react-query's error path, surfaced to user via toast.

### 11.2 Error narrowing (`lib/apiError.ts`)

```ts
export interface ApiError extends Error {
  status: number
  code?: string
  detail?: unknown
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof Error && typeof (err as ApiError).status === 'number'
}

export function is409(err: unknown, code?: string): err is ApiError {
  return isApiError(err) && err.status === 409 && (code === undefined || err.code === code)
}

export const is409AlreadySubmittedQuiz = (e: unknown) => is409(e, 'quiz_already_submitted')
export const is409AlreadySubmittedDoc = (e: unknown) => is409(e, 'gold_doc_already_submitted')
export const is409AlreadyPassed = (e: unknown) => is409(e, 'already_passed')
export const is403LockedOut = (e: unknown): e is ApiError =>
  isApiError(e) && e.status === 403 && e.code === 'max_attempts_reached'
```

`ApiError.code` is extracted by the existing `unwrap()` helper from 16a (which already parses `detail.error` into `code` on `ApiError`). If 16a's unwrap does not set `code`, this paket extends it — minimal change, included in the plan.

---

## 12. refreshAuth Helper

```ts
// lib/refreshAuth.ts
import type { QueryClient } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import { authKeys } from '@/api/queries/auth'
import { useAuthStore } from '@/stores/authStore'
import type { components } from '@/api/types'

type UserOut = components['schemas']['UserOut']

export async function refreshAuth(qc: QueryClient): Promise<UserOut> {
  const fresh = await qc.fetchQuery({
    queryKey: authKeys.me,
    queryFn: () => unwrap(client.GET('/api/auth/me')),
    staleTime: 0,
  })
  useAuthStore.getState().setUser(fresh as UserOut)
  return fresh as UserOut
}
```

`fetchQuery` populates the cache AND returns the fresh data. `staleTime: 0` forces a network hit. `authStore.setUser` is the synchronous bridge to Zustand gates (RequireSeenManual, RequirePassedTraining read from authStore).

Called from:
- `Help.tsx`: after `seenManual` mutation, before navigating to `/training`
- `Training.tsx`: after 3rd doc submit, before transitioning to summary
- `Training.tsx`: in `is409AlreadyPassed` error handler

---

## 13. Accessibility Contract

**Focus management on step transition**:
- Each step component renders an `<h2 ref={focusRef} tabIndex={-1}>` for the step title
- On `step` change (detected via `useEffect`), `focusRef.current?.focus()`
- Same for transitioning into `resultShown` cards within a step

**Progress bar a11y**:
- `<ol role="list">` of 5 `<li role="listitem">`
- Active step gets `aria-current="step"`
- Each pill has visible text ("Quiz", "Doc 1", etc.), not icon-only

**Quiz a11y**:
- Each question wrapped in `<fieldset>` with `<legend>` containing the question text
- Radio buttons grouped via shared `name` attribute on RadioGroup
- Submit button has `aria-describedby` pointing to a hidden hint when disabled ("Cevap eksik")

**Live regions**:
- Inline result cards (quiz score, doc result) wrapped in `<div role="status" aria-live="polite">`
- Submit-failure error cards (network error, unexpected backend) wrapped in `<div role="alert" aria-live="assertive">`

**Keyboard shortcuts**:
- Tab order: form fields → primary CTA → secondary CTA
- Enter on a radio: selects it (Radix default)
- Enter on focused submit button: submits (browser default)
- Escape on confirm checkbox or buttons: no special behavior in 16c (no modal dialogs)

---

## 14. Codex Adversarial Review — Findings & Mitigations

Two adversarial passes by Codex were conducted before spec finalization.

### Pass 1 (Sections 1-3)

| Severity | Finding | Mitigation |
|---|---|---|
| BROKEN | Session restore assumes resume; backend has none | Trust model (§8.4); 409 ack pattern (§8.6); refreshAuth as final truth |
| BROKEN | Abandoned attempts burn lockout silently | StartScreen warning + confirm checkbox (§8.7); pending-start sentinel (§8.3) |
| BROKEN | Step lock conflicts with idempotency on restore | 409 ack treats as success when local result is cached; DEGRADED otherwise |
| BROKEN | Pass-state navigation could bounce back | refreshAuth AWAITED before transition (§3, §8) |
| FRAGILE | "N kaldı" ambiguous | Removed; lockout via 403 only |
| FRAGILE | Per-question feedback expectation | UI copy banner clarifies "skor hep birden" |
| FRAGILE | Summary breakdown fragile under restore | SummaryDegraded variant (§8.7) |
| FRAGILE | seen-manual race with RequireSeenManual | refreshAuth AWAITED before navigate |
| FRAGILE | beforeunload not guaranteed on mobile | Documented; StartScreen warning is primary education |

### Pass 2 (full design)

| Severity | Finding | Mitigation |
|---|---|---|
| BROKEN | 409 ack without payload → fake breakdown | submitWithRecovery requires cached prior result; else DEGRADED (§8.6) |
| BROKEN | Strict validateReferences would change 16b behavior | No shared helper; training-side validation only (§10) |
| BROKEN | /start → store-write race on crash | In-flight disable + sync hydrate + pending-start sentinel (§8.3) |
| FRAGILE | /training has no already-passed redirect | Mount effect + 409 handler (§6.1) |
| FRAGILE | openapi-typescript types are weak (unknown) | Zod schemas validate at runtime (§11.1) |
| FRAGILE | react-markdown security underspecified | Explicit rehype-sanitize schema + ban on rehype-raw + XSS regression test (§7.2) |
| FRAGILE | Zustand persist versioning is undefined behavior | Explicit migrate + validateRestoredShape (§8.2) |
| FRAGILE | A11y at step transitions missing | Full a11y contract (§13) |

All findings are integrated. No open items.

---

## 15. Tests & Coverage

Coverage threshold: ≥80% statements / branches / functions / lines (16a/16b parity, enforced via `vite.config.ts`).

### 15.1 Unit / per-component

| File | Coverage focus |
|---|---|
| `MarkdownView.test.tsx` | Markdown elements render; `<script>` body stripped; banned `rehype-raw` test (lint or import check) |
| `HelpAccordion.test.tsx` | Default Welcome open; multi-open works; section order respects `order` |
| `HelpSection.test.tsx` | Title in trigger; body renders via MarkdownView |
| `Help.test.tsx` | first_time=true banner+CTA visible; normal mode hidden; CTA click → mut + refreshAuth + navigate('/training'); error toast |
| `StartScreen.test.tsx` | Checkbox required; disabled Başla; click triggers mutation; in-flight disabled state |
| `QuizStep.test.tsx` | 5 questions render; submit disabled until all answered; submit success → result card + Sonraki; error → retry |
| `AnnotateStep.test.tsx` | Doc content render; ReferenceCard list + Yeni Referans; training-strict validation; submit success → result; 3rd doc triggers refreshAuth |
| `SummaryStep.test.tsx` | PASS variant nav to /; FAIL Tekrar Dene triggers /start; DEGRADED uses auth.me as truth |
| `LockedOutScreen.test.tsx` | Logout flow; help link |
| `TrainingProgress.test.tsx` | Active pill has aria-current="step"; done/upcoming styling |
| `PendingStartBanner.test.tsx` | Renders when sentinel present + storage empty; Anladım clears; Yeni Denemeyi Başlat triggers start |
| `useBeforeUnload.test.ts` | Listener attached/detached on enabled flip |
| `trainingStore.test.ts` | hydrate / recordQuizResult / recordDocResult / advanceDoc / clear; persist roundtrip; validateRestoredShape (valid + invalid shapes) |
| `refreshAuth.test.ts` | fetchQuery called with staleTime:0; authStore.setUser invoked |
| `apiError.test.ts` | is409/is403 narrowing with various error shapes |
| `trainingSchemas.test.ts` | Zod schemas accept valid fixtures, reject malformed |
| `trainingRecovery.test.ts` | submitWithRecovery: 200 passthrough, 409 with cached → returns cached, 409 without cached → AbortAdvance + DEGRADED |

### 15.2 Integration (route-level)

| Path | Assertions |
|---|---|
| Happy path PASS | start → quiz → 3 docs → refreshAuth → SummaryPass → nav to / |
| FAIL retry | start → low quiz + fail docs → SummaryFail → Tekrar Dene → start (attempt_number=2) |
| Locked out | start → 403 → LockedOutScreen visible |
| Already passed redirect | `auth.has_passed_training=true` on mount → navigate('/') |
| F5 mid-quiz | sessionStorage seeded with step=quiz → restore → QuizStep visible |
| F5 mid-doc | sessionStorage seeded with step=doc, docIndex=1 → restore → AnnotateStep with doc 2 |
| 409 quiz idempotency | Pre-seeded quizResult + mock returns 409 → recovery uses cached, advances |
| 409 doc idempotency | Pre-seeded docResult + mock returns 409 → recovery uses cached, advances |
| Corrupt restore | sessionStorage with invalid shape → wiped, StartScreen rendered |
| 409 already_passed on /start | Mock returns 409 already_passed → refreshAuth + navigate('/') |
| Pending sentinel | Pre-seed `training-start-pending` + empty storage → banner rendered |
| XSS regression | Help section with `<script>alert(1)</script>` → no script in DOM |
| Help error path | Mock /api/help returns 500 → error UI rendered with retry |
| beforeunload | Mid-attempt: window.dispatchEvent(BeforeUnload) → preventDefault called |
| RequireSeenManual no longer redirects after CTA | full first-time flow: /login → /help?first_time → CTA → /training reachable |

### 15.3 MSW handlers (`test/handlers/`)

`help.ts`:
- `GET /api/help` → fixture sections (9 with realistic markdown content)
- Variants exposed via test setup overrides: 500 error, malformed shape (no `sections` key)

`training.ts`:
- `GET /api/training/start` → fixture (5 Q + 3 docs); variants: 409 already_passed, 403 max_attempts_reached, 500
- `POST /api/training/quiz/submit` → `{score: 3, total: 5}` default; variants: 200 with score=5, 409 quiz_already_submitted, 500
- `POST /api/training/annotate/submit` → `{passed: true, matched_count: 2, expected_count: 2, min_concept_count: 1}`; variants: passed=false, 409 gold_doc_already_submitted, 500

`/api/me/seen-manual` → `{ok: true}` (existing); error variant for Help.test.

### 15.4 Manual E2E smoke

Performed after CI green, before tagging:

1. Create fresh user: `INSERT INTO users (...) VALUES (... has_seen_manual=0, has_passed_training=0, ...)` via SQL or invite code (`SETUP-INVITE`) flow.
2. Login → expect `/help?first_time=true` redirect.
3. Accordion open/close interactions; verify Welcome open default.
4. Click "Anladım, eğitime geç" → expect `/training` and DB shows `has_seen_manual=1`.
5. StartScreen: confirm checkbox, click Başla.
6. Quiz: answer 5 questions, submit, see score card.
7. Annotate 3 docs (try a mix of pass/fail to surface different result cards).
8. Summary screen reflects outcome.
9. On PASS: "Anotasyona Başla" → / loads (Annotate layout from 16b).
10. On FAIL (use a separate fresh user): "Tekrar Dene" → new attempt. Verify `attempt_number` increments in DB.
11. Force 3rd failed attempt → LockedOutScreen visible. POST /start in DB tools returns 403.
12. F5 mid-quiz → return to same quiz step with answers preserved.
13. F5 mid-doc 2 → return to doc 2 with refs preserved.
14. Mobile Chrome simulation: verify accordion and wizard are usable; note that beforeunload may not appear (documented limitation).
15. /docs/:docId (16b) still works — no regression.

---

## 16. Acceptance Criteria

- [ ] All new unit + integration tests pass; 16a + 16b existing tests pass (no regression).
- [ ] Coverage thresholds (≥80% on all 4 metrics) met across the frontend codebase.
- [ ] `npm run typecheck` clean.
- [ ] `npm run lint` clean.
- [ ] `npm run gen:types:check` clean (no type drift from backend OpenAPI).
- [ ] Manual E2E smoke (§15.4) all 15 steps verified.
- [ ] First-time user flow: gates flip correctly in DB; user reaches `/` after pass.
- [ ] F5 mid-attempt: state restores correctly.
- [ ] 409 idempotency: pre-submitted state advances without fake breakdown.
- [ ] Locked-out: 403 from `/start` lands on LockedOutScreen, not generic error.
- [ ] XSS regression: scripted markdown body is stripped (assert via test).
- [ ] No `rehype-raw` import anywhere (verify via grep in plan's final task).
- [ ] No `lib/validateReferences.ts` exists (validation stays training-side).
- [ ] 16b regression check: `frontend/src/components/annotation/ReferenceCard.tsx` is byte-identical pre/post; `ReferencePanel.tsx` is byte-identical pre/post.
- [ ] A11y: keyboard-only walkthrough of full training wizard succeeds (Tab order, focus management, live region announcements verified via screen reader if available).

---

## 17. Files Changed Summary

**Added (24)**:
- 2 routes (Help.tsx, Training.tsx — replace STUBs)
- 3 help components + 7 training components + 1 banner
- 1 hook (useBeforeUnload)
- 1 store (trainingStore)
- 4 lib helpers (refreshAuth, apiError, trainingSchemas, trainingRecovery)
- 3 query files (help, training, me)
- 2 MSW handler files

**Modified (3)**:
- `package.json` — 3 new deps
- `test/handlers.ts` — import new files
- `lib/apiError.ts` may extend the existing `unwrap()` helper from 16a to set `code` on ApiError (small, additive)

**Untouched** (regression-safe):
- 16a `App.tsx` route tree
- 16a auth, gates, AppShell, ErrorBoundary, LoadingScreen
- 16b ReferenceCard, ReferencePanel, AnnotateDoc, AnnotateLayout, all hooks (useFeed, useDoc, useAnnotation, useDraft, useLock, useReferencesState, useSSE)
- Backend (zero changes)

---

## 18. Risks & Open Questions

**Accepted limitations** (documented, not addressed in 16c):
- Mobile `beforeunload` is not guaranteed.
- Backend has no resume endpoint → corrupt sessionStorage means user must start fresh.
- Static admin email in LockedOutScreen — runtime override deferred to 16e.
- Quiz feedback is per-quiz, not per-question. Coaching deferred to a future package.

**Risks under mitigation**:
- React/Tailwind build size growth from react-markdown + remark-gfm — measure on bundle stats after T1; if >50KB gzipped delta, evaluate alternatives.
- ZodError surfacing — must produce a usable toast message, not raw error text.

**No open questions remain**. All gray areas resolved through user Q&A or Codex review.

---

**Approval gate**: After this spec is reviewed and approved by the user, the writing-plans skill produces the implementation plan (`docs/superpowers/plans/2026-05-11-package-16c-onboarding.md`) for subagent-driven-development execution.
