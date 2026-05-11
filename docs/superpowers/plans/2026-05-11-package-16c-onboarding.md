# Paket 16c — Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 16a `/help` and `/training` STUBs with production content; activate the `RequireSeenManual` and `RequirePassedTraining` gates wired in 16a so that new users complete onboarding (manual reading → 5-step training wizard → annotate).

**Architecture:** React 18 + Vite + TS strict, building on 16a foundation (auth, gates, shell, MSW test infra) and 16b annotation components (`ReferenceCard` reused as-is). Help viewer = shadcn Accordion + react-markdown with rehype-sanitize. Training = 5-step wizard (Quiz → 3×Doc → Summary) with Zustand store persisted to sessionStorage. Recovery patterns (`submitWithRecovery` for 409 idempotency), atomic start-write protection (pending-start sentinel), refresh-auth helper for race-free gate transitions. All Codex-1 + Codex-2 findings (7 BROKEN + 8 FRAGILE) integrated.

**Tech Stack:** TanStack Query 5, Zustand 4 (with persist + sessionStorage), Zod (runtime schema validation), react-markdown 9 + remark-gfm 4 + rehype-sanitize 6, Vitest + MSW v2.

**Spec:** `docs/superpowers/specs/2026-05-11-paket-16c-onboarding-design.md` (commit c5aee88).

---

## File Map

### New files (24)

```
frontend/src/
├── routes/
│   ├── Help.tsx                          # replaces 16a STUB
│   └── Training.tsx                      # replaces 16a STUB
├── components/
│   ├── help/
│   │   ├── HelpAccordion.tsx
│   │   ├── HelpSection.tsx
│   │   └── MarkdownView.tsx
│   └── training/
│       ├── TrainingProgress.tsx
│       ├── StartScreen.tsx
│       ├── QuizStep.tsx
│       ├── AnnotateStep.tsx
│       ├── SummaryStep.tsx
│       ├── LockedOutScreen.tsx
│       └── PendingStartBanner.tsx
├── api/queries/
│   ├── help.ts
│   ├── training.ts
│   └── me.ts
├── hooks/
│   └── useBeforeUnload.ts
├── stores/
│   └── trainingStore.ts
├── lib/
│   ├── refreshAuth.ts
│   ├── apiError.ts
│   ├── trainingSchemas.ts
│   └── trainingRecovery.ts
```

### Modified files (2)

```
frontend/
├── package.json                          # +3 deps: react-markdown, remark-gfm, rehype-sanitize
└── src/test/msw-handlers.ts              # +help, +training handlers
```

### Untouched (regression-safe)

- All 16a/16b files
- `ReferenceCard.tsx`, `ReferencePanel.tsx`, `Annotate*`, hooks (useFeed, useDoc, useDraft, useLock, useSSE, useReferencesState)
- Backend (zero changes)
- `App.tsx` route tree (gates wire already correct)

---

## Task Order

| # | Task | Depends on | Atomic commit |
|---|---|---|---|
| T1 | Add deps + verify build | — | `chore(paket-16c): add react-markdown/remark-gfm/rehype-sanitize` |
| T2 | `lib/apiError.ts` (type guards) | T1 | `feat(paket-16c): apiError type guards` |
| T3 | `lib/refreshAuth.ts` | T2 | `feat(paket-16c): refreshAuth helper` |
| T4 | `hooks/useBeforeUnload.ts` | T1 | `feat(paket-16c): useBeforeUnload hook` |
| T5 | `lib/trainingSchemas.ts` (Zod) | T1 | `feat(paket-16c): zod runtime schemas` |
| T6 | `lib/trainingRecovery.ts` (submitWithRecovery + AbortAdvance) | T2 | `feat(paket-16c): submit recovery helper` |
| T7 | `api/queries/help.ts` + MSW help handler | T5 | `feat(paket-16c): useHelpQuery` |
| T8 | `components/help/MarkdownView.tsx` + XSS test | T1 | `feat(paket-16c): MarkdownView with sanitize` |
| T9 | `components/help/HelpAccordion.tsx` + `HelpSection.tsx` | T8 | `feat(paket-16c): HelpAccordion + HelpSection` |
| T10 | `routes/Help.tsx` + `api/queries/me.ts` (useSeenManualMutation) | T3, T7, T9 | `feat(paket-16c): Help route + seen-manual flow` |
| T11 | `stores/trainingStore.ts` | T1 | `feat(paket-16c): trainingStore (zustand + persist)` |
| T12 | `api/queries/training.ts` (3 mutations + sentinel) + MSW training handlers | T2, T5 | `feat(paket-16c): training mutations + handlers` |
| T13 | `components/training/TrainingProgress.tsx` | T1 | `feat(paket-16c): TrainingProgress stepper` |
| T14 | `components/training/StartScreen.tsx` | T12 | `feat(paket-16c): StartScreen + confirm gate` |
| T15 | `components/training/QuizStep.tsx` | T11, T12, T6 | `feat(paket-16c): QuizStep` |
| T16 | `components/training/AnnotateStep.tsx` | T11, T12, T6, T3 | `feat(paket-16c): AnnotateStep` |
| T17 | `components/training/SummaryStep.tsx` (3 variants) | T11 | `feat(paket-16c): SummaryStep (pass/fail/degraded)` |
| T18 | `components/training/LockedOutScreen.tsx` + `PendingStartBanner.tsx` | T11 | `feat(paket-16c): LockedOut + PendingStartBanner` |
| T19 | `routes/Training.tsx` + integration tests | T11-T18 | `feat(paket-16c): Training route + integration` |
| T20 | Manual E2E + acceptance + tag | T1-T19 | `chore(paket-16c): tag paket-16c-onboarding` |

---

## Task 1: Add deps + verify build

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install runtime dependencies**

Run:
```bash
cd frontend && npm install react-markdown@^9.0.0 remark-gfm@^4.0.0 rehype-sanitize@^6.0.0
```

- [ ] **Step 2: Verify lockfile and `package.json` updated**

Run: `grep -E "react-markdown|remark-gfm|rehype-sanitize" frontend/package.json`
Expected output (order may vary):
```
"react-markdown": "^9.0.0",
"rehype-sanitize": "^6.0.0",
"remark-gfm": "^4.0.0",
```

- [ ] **Step 3: Verify build still green**

Run: `cd frontend && npm run typecheck && npm run lint && npm run test:run`
Expected: all pass; 126 existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "$(cat <<'EOF'
chore(paket-16c): add react-markdown/remark-gfm/rehype-sanitize

Runtime deps for /help markdown viewer. Forbidden: rehype-raw (bypasses
sanitize). Spec §7.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: lib/apiError.ts (type guards)

**Files:**
- Create: `frontend/src/lib/apiError.ts`
- Test: `frontend/src/lib/apiError.test.ts`

- [ ] **Step 1: Write failing test**

Create `frontend/src/lib/apiError.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { ApiError } from '@/api/client'
import {
  isApiError,
  is409,
  is409AlreadySubmittedQuiz,
  is409AlreadySubmittedDoc,
  is409AlreadyPassed,
  is403LockedOut,
} from './apiError'

describe('apiError type guards', () => {
  it('isApiError true for ApiError instance', () => {
    expect(isApiError(new ApiError(409, 'foo', 'bar'))).toBe(true)
  })

  it('isApiError false for plain Error', () => {
    expect(isApiError(new Error('x'))).toBe(false)
  })

  it('isApiError false for non-error', () => {
    expect(isApiError({ status: 409 })).toBe(false)
    expect(isApiError(null)).toBe(false)
    expect(isApiError('foo')).toBe(false)
  })

  it('is409 matches status without code constraint', () => {
    expect(is409(new ApiError(409, 'any_code', 'm'))).toBe(true)
    expect(is409(new ApiError(403, 'any_code', 'm'))).toBe(false)
  })

  it('is409 with code matches both', () => {
    expect(is409(new ApiError(409, 'foo', 'm'), 'foo')).toBe(true)
    expect(is409(new ApiError(409, 'bar', 'm'), 'foo')).toBe(false)
  })

  it('is409AlreadySubmittedQuiz', () => {
    expect(is409AlreadySubmittedQuiz(new ApiError(409, 'quiz_already_submitted', 'm'))).toBe(true)
    expect(is409AlreadySubmittedQuiz(new ApiError(409, 'gold_doc_already_submitted', 'm'))).toBe(false)
  })

  it('is409AlreadySubmittedDoc', () => {
    expect(is409AlreadySubmittedDoc(new ApiError(409, 'gold_doc_already_submitted', 'm'))).toBe(true)
    expect(is409AlreadySubmittedDoc(new ApiError(409, 'quiz_already_submitted', 'm'))).toBe(false)
  })

  it('is409AlreadyPassed', () => {
    expect(is409AlreadyPassed(new ApiError(409, 'already_passed', 'm'))).toBe(true)
    expect(is409AlreadyPassed(new ApiError(409, 'other', 'm'))).toBe(false)
  })

  it('is403LockedOut', () => {
    expect(is403LockedOut(new ApiError(403, 'max_attempts_reached', 'm'))).toBe(true)
    expect(is403LockedOut(new ApiError(403, 'other', 'm'))).toBe(false)
    expect(is403LockedOut(new ApiError(409, 'max_attempts_reached', 'm'))).toBe(false)
  })
})
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd frontend && npx vitest run src/lib/apiError.test.ts`
Expected: FAIL with "Cannot find module './apiError'"

- [ ] **Step 3: Write `apiError.ts`**

Create `frontend/src/lib/apiError.ts`:

```ts
import { ApiError } from '@/api/client'

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError
}

export function is409(err: unknown, code?: string): err is ApiError {
  return isApiError(err) && err.status === 409 && (code === undefined || err.code === code)
}

export function is409AlreadySubmittedQuiz(err: unknown): err is ApiError {
  return is409(err, 'quiz_already_submitted')
}

export function is409AlreadySubmittedDoc(err: unknown): err is ApiError {
  return is409(err, 'gold_doc_already_submitted')
}

export function is409AlreadyPassed(err: unknown): err is ApiError {
  return is409(err, 'already_passed')
}

export function is403LockedOut(err: unknown): err is ApiError {
  return isApiError(err) && err.status === 403 && err.code === 'max_attempts_reached'
}
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd frontend && npx vitest run src/lib/apiError.test.ts`
Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/apiError.ts frontend/src/lib/apiError.test.ts
git commit -m "$(cat <<'EOF'
feat(paket-16c): apiError type guards

Centralized narrowing for 409/403 codes used across training mutations
and recovery. Builds on 16a ApiError class which already carries code.
Spec §11.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: lib/refreshAuth.ts

**Files:**
- Create: `frontend/src/lib/refreshAuth.ts`
- Test: `frontend/src/lib/refreshAuth.test.ts`

- [ ] **Step 1: Write failing test**

Create `frontend/src/lib/refreshAuth.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { QueryClient } from '@tanstack/react-query'
import { server } from '@/test/msw-server'
import { makeUser } from '@/test/msw-handlers'
import { useAuthStore } from '@/stores/authStore'
import { authKeys } from '@/api/queries/auth'
import { refreshAuth } from './refreshAuth'

const API = 'http://localhost'

describe('refreshAuth', () => {
  let qc: QueryClient
  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    useAuthStore.setState({ status: 'authed', user: null, error: null })
  })

  it('fetches /api/auth/me with staleTime 0 and updates authStore', async () => {
    const user = makeUser({ has_seen_manual: true, has_passed_training: true })
    server.use(http.get(`${API}/api/auth/me`, () => HttpResponse.json(user)))

    const fresh = await refreshAuth(qc)

    expect(fresh.has_passed_training).toBe(true)
    expect(useAuthStore.getState().user?.has_passed_training).toBe(true)
    expect(qc.getQueryData(authKeys.me)).toEqual(user)
  })

  it('throws on network error and does not mutate authStore', async () => {
    server.use(http.get(`${API}/api/auth/me`, () => HttpResponse.error()))

    await expect(refreshAuth(qc)).rejects.toBeDefined()
    expect(useAuthStore.getState().user).toBeNull()
  })
})
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd frontend && npx vitest run src/lib/refreshAuth.test.ts`
Expected: FAIL with "Cannot find module './refreshAuth'"

- [ ] **Step 3: Write `refreshAuth.ts`**

Create `frontend/src/lib/refreshAuth.ts`:

```ts
import type { QueryClient } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import { authKeys } from '@/api/queries/auth'
import { useAuthStore } from '@/stores/authStore'
import type { components } from '@/api/types'

type UserOut = components['schemas']['UserOut']

/**
 * Forces a fresh /api/auth/me fetch (bypassing TanStack staleness) and
 * mirrors the result into the Zustand authStore so gates re-evaluate
 * synchronously. Used after mutations that flip server-side flags
 * (has_seen_manual, has_passed_training) before navigation.
 *
 * Spec §12.
 */
export async function refreshAuth(qc: QueryClient): Promise<UserOut> {
  const fresh = await qc.fetchQuery({
    queryKey: authKeys.me,
    queryFn: () => unwrap(await client.GET('/api/auth/me')),
    staleTime: 0,
  })
  useAuthStore.getState().setUser(fresh as UserOut)
  return fresh as UserOut
}
```

Note: the `async`/`await` inside `queryFn` requires inlining; an alternative is `async () => unwrap(await client.GET('/api/auth/me'))`. The version above must compile cleanly — if TypeScript complains about the `await` placement, use the alternative form below:

```ts
queryFn: async () => unwrap(await client.GET('/api/auth/me')),
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd frontend && npx vitest run src/lib/refreshAuth.test.ts`
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/refreshAuth.ts frontend/src/lib/refreshAuth.test.ts
git commit -m "$(cat <<'EOF'
feat(paket-16c): refreshAuth helper

fetchQuery(authKeys.me, staleTime:0) + authStore.setUser. Closes the
race between server-side flag flips (seen-manual, passed-training) and
gate redirects (RequireSeenManual, RequirePassedTraining). Spec §12.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: hooks/useBeforeUnload.ts

**Files:**
- Create: `frontend/src/hooks/useBeforeUnload.ts`
- Test: `frontend/src/hooks/useBeforeUnload.test.ts`

- [ ] **Step 1: Write failing test**

Create `frontend/src/hooks/useBeforeUnload.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useBeforeUnload } from './useBeforeUnload'

describe('useBeforeUnload', () => {
  it('attaches listener when enabled=true', () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    renderHook(() => useBeforeUnload(true))
    expect(addSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function))
  })

  it('does not attach listener when enabled=false', () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    renderHook(() => useBeforeUnload(false))
    const calls = addSpy.mock.calls.filter((c) => c[0] === 'beforeunload')
    expect(calls).toHaveLength(0)
  })

  it('detaches listener on unmount', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    const { unmount } = renderHook(() => useBeforeUnload(true))
    unmount()
    expect(removeSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function))
  })

  it('handler calls preventDefault and sets returnValue', () => {
    let captured: ((e: BeforeUnloadEvent) => void) | null = null
    vi.spyOn(window, 'addEventListener').mockImplementation((evt, fn) => {
      if (evt === 'beforeunload') captured = fn as (e: BeforeUnloadEvent) => void
    })
    renderHook(() => useBeforeUnload(true, 'Devam ediyorsun'))
    expect(captured).not.toBeNull()
    const evt = { preventDefault: vi.fn(), returnValue: '' } as unknown as BeforeUnloadEvent
    captured!(evt)
    expect(evt.preventDefault).toHaveBeenCalled()
    expect(evt.returnValue).toBe('Devam ediyorsun')
  })
})
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd frontend && npx vitest run src/hooks/useBeforeUnload.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement hook**

Create `frontend/src/hooks/useBeforeUnload.ts`:

```ts
import { useEffect } from 'react'

/**
 * Show the browser's "leave page?" prompt when `enabled` is true.
 *
 * Known limitation: not honored on every mobile browser. Spec §8.5
 * documents that StartScreen warning is the primary user education
 * for "abandoned attempts burn lockout slots".
 */
export function useBeforeUnload(enabled: boolean, message?: string): void {
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

- [ ] **Step 4: Run test, verify pass**

Run: `cd frontend && npx vitest run src/hooks/useBeforeUnload.test.ts`
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useBeforeUnload.ts frontend/src/hooks/useBeforeUnload.test.ts
git commit -m "$(cat <<'EOF'
feat(paket-16c): useBeforeUnload hook

Guards mid-attempt browser close. Used by Training.tsx when step ∈
{quiz, doc} and no submit is in-flight. Spec §8.5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: lib/trainingSchemas.ts (Zod)

**Files:**
- Create: `frontend/src/lib/trainingSchemas.ts`
- Test: `frontend/src/lib/trainingSchemas.test.ts`

- [ ] **Step 1: Write failing test**

Create `frontend/src/lib/trainingSchemas.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import {
  helpResponseSchema,
  startResponseSchema,
  quizSubmitResponseSchema,
  annotateSubmitResponseSchema,
} from './trainingSchemas'

describe('Zod schemas', () => {
  describe('helpResponseSchema', () => {
    it('accepts valid sections', () => {
      const valid = {
        sections: [
          { id: '01-welcome', order: 1, title: 'Hoş geldin', body: '# Hoş geldin\n…' },
        ],
      }
      expect(() => helpResponseSchema.parse(valid)).not.toThrow()
    })

    it('rejects missing sections', () => {
      expect(() => helpResponseSchema.parse({})).toThrow()
    })

    it('rejects malformed section', () => {
      expect(() =>
        helpResponseSchema.parse({ sections: [{ id: 1, order: '1', title: '', body: '' }] }),
      ).toThrow()
    })
  })

  describe('startResponseSchema', () => {
    const valid = {
      attempt_id: 42,
      attempt_number: 1,
      questions: Array.from({ length: 5 }, (_, i) => ({
        id: `q${i + 1}`,
        text: `Soru ${i + 1}`,
        choices: ['a', 'b', 'c', 'd'],
      })),
      gold_docs: [
        { gold_id: 'sample_kvk_5', content: '…' },
        { gold_id: 'sample_kdv_29', content: '…' },
        { gold_id: 'sample_gvk_67', content: '…' },
      ],
    }

    it('accepts well-formed payload', () => {
      expect(() => startResponseSchema.parse(valid)).not.toThrow()
    })

    it('rejects wrong question count', () => {
      const bad = { ...valid, questions: valid.questions.slice(0, 3) }
      expect(() => startResponseSchema.parse(bad)).toThrow()
    })

    it('rejects wrong gold_doc count', () => {
      const bad = { ...valid, gold_docs: valid.gold_docs.slice(0, 2) }
      expect(() => startResponseSchema.parse(bad)).toThrow()
    })

    it('rejects choices length != 4', () => {
      const bad = {
        ...valid,
        questions: [
          { ...valid.questions[0], choices: ['a', 'b'] },
          ...valid.questions.slice(1),
        ],
      }
      expect(() => startResponseSchema.parse(bad)).toThrow()
    })
  })

  describe('quizSubmitResponseSchema', () => {
    it('accepts {score, total}', () => {
      expect(() => quizSubmitResponseSchema.parse({ score: 3, total: 5 })).not.toThrow()
    })
    it('rejects floats', () => {
      expect(() => quizSubmitResponseSchema.parse({ score: 3.5, total: 5 })).toThrow()
    })
  })

  describe('annotateSubmitResponseSchema', () => {
    it('accepts full shape', () => {
      expect(() =>
        annotateSubmitResponseSchema.parse({
          passed: true,
          matched_count: 2,
          expected_count: 2,
          min_concept_count: 1,
        }),
      ).not.toThrow()
    })
    it('rejects missing passed', () => {
      expect(() =>
        annotateSubmitResponseSchema.parse({
          matched_count: 2,
          expected_count: 2,
          min_concept_count: 1,
        }),
      ).toThrow()
    })
  })
})
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd frontend && npx vitest run src/lib/trainingSchemas.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement schemas**

Create `frontend/src/lib/trainingSchemas.ts`:

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
  choices: z.array(z.string()).length(4),
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

export type HelpSection = z.infer<typeof helpSectionSchema>
export type HelpResponse = z.infer<typeof helpResponseSchema>
export type Question = z.infer<typeof questionSchema>
export type GoldDoc = z.infer<typeof goldDocSchema>
export type StartResponse = z.infer<typeof startResponseSchema>
export type QuizSubmitResponse = z.infer<typeof quizSubmitResponseSchema>
export type AnnotateSubmitResponse = z.infer<typeof annotateSubmitResponseSchema>
```

- [ ] **Step 4: Run test, verify pass**

Run: `cd frontend && npx vitest run src/lib/trainingSchemas.test.ts`
Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/trainingSchemas.ts frontend/src/lib/trainingSchemas.test.ts
git commit -m "$(cat <<'EOF'
feat(paket-16c): zod runtime schemas

openapi-typescript produces unknown for /help; error shapes are not
modeled. Zod schemas parse at runtime so storage/restore/MSW paths
catch malformed payloads early. Spec §11.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: lib/trainingRecovery.ts (submitWithRecovery + AbortAdvance)

**Files:**
- Create: `frontend/src/lib/trainingRecovery.ts`
- Test: `frontend/src/lib/trainingRecovery.test.ts`

- [ ] **Step 1: Write failing test**

Create `frontend/src/lib/trainingRecovery.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/client'
import { useTrainingStore } from '@/stores/trainingStore'
import { submitWithRecovery, AbortAdvance } from './trainingRecovery'

const makeQc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } })

describe('submitWithRecovery', () => {
  beforeEach(() => {
    useTrainingStore.getState().clear()
  })

  it('passes through 200 result unchanged', async () => {
    const qc = makeQc()
    const result = await submitWithRecovery({
      submit: async () => ({ score: 3, total: 5 }),
      key: { kind: 'quiz' },
      qc,
    })
    expect(result).toEqual({ score: 3, total: 5 })
  })

  it('on 409 quiz with cached prior result, returns the cache', async () => {
    const qc = makeQc()
    useTrainingStore.setState({ quizResult: { score: 4, total: 5 } })
    const result = await submitWithRecovery({
      submit: async () => {
        throw new ApiError(409, 'quiz_already_submitted', 'dup')
      },
      key: { kind: 'quiz' },
      qc,
    })
    expect(result).toEqual({ score: 4, total: 5 })
  })

  it('on 409 quiz WITHOUT cached prior, throws AbortAdvance + DEGRADED', async () => {
    const qc = makeQc()
    const fetchSpy = vi.spyOn(qc, 'fetchQuery').mockResolvedValue({
      id: 1,
      username: 'tester',
      role: 'user',
      avatar_color: '#000',
      has_seen_manual: true,
      has_passed_training: true,
    } as never)

    await expect(
      submitWithRecovery({
        submit: async () => {
          throw new ApiError(409, 'quiz_already_submitted', 'dup')
        },
        key: { kind: 'quiz' },
        qc,
      }),
    ).rejects.toBeInstanceOf(AbortAdvance)

    expect(fetchSpy).toHaveBeenCalled()
    expect(useTrainingStore.getState().degraded).toBe(true)
    expect(useTrainingStore.getState().step).toBe('summary')
  })

  it('on 409 doc with cached prior result, returns the cache', async () => {
    const qc = makeQc()
    const docResult = {
      passed: true,
      matched_count: 2,
      expected_count: 2,
      min_concept_count: 1,
    }
    useTrainingStore.setState({ docResults: { gold_x: docResult } })
    const result = await submitWithRecovery({
      submit: async () => {
        throw new ApiError(409, 'gold_doc_already_submitted', 'dup')
      },
      key: { kind: 'doc', goldId: 'gold_x' },
      qc,
    })
    expect(result).toEqual(docResult)
  })

  it('on non-409 error, rethrows', async () => {
    const qc = makeQc()
    await expect(
      submitWithRecovery({
        submit: async () => {
          throw new ApiError(500, 'boom', 'server')
        },
        key: { kind: 'quiz' },
        qc,
      }),
    ).rejects.toMatchObject({ status: 500 })
  })
})
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd frontend && npx vitest run src/lib/trainingRecovery.test.ts`
Expected: FAIL (modules missing — trainingRecovery and trainingStore not yet created).

This task creates `trainingRecovery.ts` only. The test depends on `trainingStore.ts` (Task 11). To unblock TDD here, define a **minimal placeholder** store now and replace it in Task 11. Add this temporary import inside the test:

```ts
// in test file, ensure import resolves:
import '@/stores/trainingStore'
```

The placeholder is in Step 3 below.

- [ ] **Step 3: Create placeholder trainingStore (replaced by full store in T11) + trainingRecovery.ts**

Create `frontend/src/stores/trainingStore.ts` (PLACEHOLDER — replaced in T11):

```ts
import { create } from 'zustand'

interface PlaceholderState {
  quizResult: { score: number; total: number } | null
  docResults: Record<string, { passed: boolean; matched_count: number; expected_count: number; min_concept_count: number }>
  degraded: boolean
  step: string
  clear: () => void
}

export const useTrainingStore = create<PlaceholderState>((set) => ({
  quizResult: null,
  docResults: {},
  degraded: false,
  step: 'idle',
  clear: () => set({ quizResult: null, docResults: {}, degraded: false, step: 'idle' }),
}))
```

Create `frontend/src/lib/trainingRecovery.ts`:

```ts
import type { QueryClient } from '@tanstack/react-query'
import { useTrainingStore } from '@/stores/trainingStore'
import { isApiError, is409AlreadySubmittedQuiz, is409AlreadySubmittedDoc } from './apiError'
import { refreshAuth } from './refreshAuth'

/**
 * Recovery signal: the caller MUST NOT call store.advance* after this is
 * thrown. The recovery path has already transitioned to the summary step.
 */
export class AbortAdvance extends Error {
  constructor() {
    super('caller should not advance; recovery has redirected')
    this.name = 'AbortAdvance'
  }
}

export type RecoveryKey = { kind: 'quiz' } | { kind: 'doc'; goldId: string }

interface SubmitWithRecoveryArgs<R> {
  submit: () => Promise<R>
  key: RecoveryKey
  qc: QueryClient
}

/**
 * Wraps a submit mutation with idempotency-aware recovery.
 *
 * - 200 → return result, caller advances
 * - 409 already_submitted + cached prior result in store → return cached, caller advances
 * - 409 already_submitted + no cached prior → DEGRADED: refreshAuth + step='summary' + throw AbortAdvance
 * - other errors → rethrow
 *
 * Spec §8.6.
 */
export async function submitWithRecovery<R>(args: SubmitWithRecoveryArgs<R>): Promise<R> {
  try {
    return await args.submit()
  } catch (err) {
    if (!isApiError(err)) throw err

    const store = useTrainingStore.getState() as {
      quizResult: { score: number; total: number } | null
      docResults: Record<string, R>
      degraded: boolean
      step: string
    } & { markDegraded?: () => void; setStep?: (s: string) => void }

    if (args.key.kind === 'quiz' && is409AlreadySubmittedQuiz(err)) {
      const cached = store.quizResult
      if (cached) return cached as unknown as R
      await refreshAuth(args.qc)
      useTrainingStore.setState({ degraded: true, step: 'summary' })
      throw new AbortAdvance()
    }

    if (args.key.kind === 'doc' && is409AlreadySubmittedDoc(err)) {
      const cached = store.docResults[args.key.goldId]
      if (cached) return cached
      await refreshAuth(args.qc)
      useTrainingStore.setState({ degraded: true, step: 'summary' })
      throw new AbortAdvance()
    }

    throw err
  }
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/lib/trainingRecovery.test.ts`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/trainingRecovery.ts frontend/src/lib/trainingRecovery.test.ts frontend/src/stores/trainingStore.ts
git commit -m "$(cat <<'EOF'
feat(paket-16c): submit recovery helper

submitWithRecovery wraps quiz/annotate mutations to honor backend
idempotency (409 already_submitted). Cached prior result advances UI;
no cache → DEGRADED + AbortAdvance signal. Placeholder trainingStore
unblocks tests; full store lands in T11. Spec §8.6.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: api/queries/help.ts + MSW help handler

**Files:**
- Create: `frontend/src/api/queries/help.ts`
- Create: `frontend/src/api/queries/help.test.ts`
- Modify: `frontend/src/test/msw-handlers.ts` (add help handler + helper)

- [ ] **Step 1: Add MSW help handler**

Edit `frontend/src/test/msw-handlers.ts` — find the `const API = 'http://localhost'` line and add ABOVE the `ANNOTATE_DEFAULTS` array (or directly after it, but before the final `handlers` export):

```ts
// Add to msw-handlers.ts:
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
```

Then append `HELP_DEFAULT_HANDLER` to the exported `handlers` array (insert just before `...ANNOTATE_DEFAULTS`):

```ts
export const handlers = [
  // ... existing entries ...
  HELP_DEFAULT_HANDLER,
  ...ANNOTATE_DEFAULTS,
]
```

- [ ] **Step 2: Write failing test**

Create `frontend/src/api/queries/help.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { server } from '@/test/msw-server'
import { useHelpQuery } from './help'

const API = 'http://localhost'

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useHelpQuery', () => {
  it('returns parsed sections on success', async () => {
    const { result } = renderHook(() => useHelpQuery(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.sections.length).toBeGreaterThan(0)
    expect(result.current.data?.sections[0]).toMatchObject({
      id: expect.any(String),
      order: expect.any(Number),
      title: expect.any(String),
      body: expect.any(String),
    })
  })

  it('errors on malformed payload (zod parse fails)', async () => {
    server.use(http.get(`${API}/api/help`, () => HttpResponse.json({ wrong: 'shape' })))
    const { result } = renderHook(() => useHelpQuery(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })

  it('errors on 500', async () => {
    server.use(http.get(`${API}/api/help`, () => HttpResponse.error()))
    const { result } = renderHook(() => useHelpQuery(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
```

- [ ] **Step 3: Run test, verify fail**

Run: `cd frontend && npx vitest run src/api/queries/help.test.ts`
Expected: FAIL "Cannot find module './help'".

- [ ] **Step 4: Implement useHelpQuery**

Create `frontend/src/api/queries/help.ts`:

```ts
import { useQuery } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import { helpResponseSchema, type HelpResponse } from '@/lib/trainingSchemas'

export const helpKeys = {
  all: ['help'] as const,
  sections: () => [...helpKeys.all, 'sections'] as const,
}

export function useHelpQuery() {
  return useQuery<HelpResponse>({
    queryKey: helpKeys.sections(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/help'))
      return helpResponseSchema.parse(raw)
    },
    staleTime: Infinity,
  })
}
```

- [ ] **Step 5: Run test, verify pass**

Run: `cd frontend && npx vitest run src/api/queries/help.test.ts`
Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/queries/help.ts frontend/src/api/queries/help.test.ts frontend/src/test/msw-handlers.ts
git commit -m "$(cat <<'EOF'
feat(paket-16c): useHelpQuery + MSW handler

GET /api/help with Zod parse at the query boundary. staleTime: Infinity
because markdown rarely changes. MSW default handler + makeHelpResponse
factory for test overrides. Spec §7.4, §11.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: components/help/MarkdownView.tsx + XSS regression test

**Files:**
- Create: `frontend/src/components/help/MarkdownView.tsx`
- Create: `frontend/src/components/help/MarkdownView.test.tsx`

- [ ] **Step 1: Write failing test (XSS + element coverage)**

Create `frontend/src/components/help/MarkdownView.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MarkdownView } from './MarkdownView'

describe('MarkdownView', () => {
  it('renders h1', () => {
    render(<MarkdownView>{`# Hoş geldin`}</MarkdownView>)
    expect(screen.getByRole('heading', { level: 1, name: /hoş geldin/i })).toBeInTheDocument()
  })

  it('renders h2 and paragraphs', () => {
    render(<MarkdownView>{`## Başlık\n\nBir paragraf.`}</MarkdownView>)
    expect(screen.getByRole('heading', { level: 2, name: /başlık/i })).toBeInTheDocument()
    expect(screen.getByText(/bir paragraf\./i)).toBeInTheDocument()
  })

  it('renders unordered list', () => {
    render(<MarkdownView>{`- item 1\n- item 2`}</MarkdownView>)
    const items = screen.getAllByRole('listitem')
    expect(items.length).toBeGreaterThanOrEqual(2)
  })

  it('renders inline code', () => {
    const { container } = render(<MarkdownView>{`Use \`npm test\` to run.`}</MarkdownView>)
    expect(container.querySelector('code')).not.toBeNull()
  })

  it('renders GFM table', () => {
    const md = '| a | b |\n| - | - |\n| 1 | 2 |'
    const { container } = render(<MarkdownView>{md}</MarkdownView>)
    expect(container.querySelector('table')).not.toBeNull()
  })

  it('XSS: strips <script> tags from body', () => {
    const dangerous = `# Title\n\n<script>window.__xss__ = true</script>\n\nBody.`
    const { container } = render(<MarkdownView>{dangerous}</MarkdownView>)
    expect(container.querySelector('script')).toBeNull()
    // also verify the script content text is not rendered
    expect(screen.queryByText(/window\.__xss__/)).toBeNull()
  })

  it('XSS: strips on* handlers from elements', () => {
    const dangerous = `<img src="x" onerror="window.__xss__=true">`
    const { container } = render(<MarkdownView>{dangerous}</MarkdownView>)
    const img = container.querySelector('img')
    if (img) {
      expect(img.getAttribute('onerror')).toBeNull()
    }
  })
})
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd frontend && npx vitest run src/components/help/MarkdownView.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement MarkdownView**

Create `frontend/src/components/help/MarkdownView.tsx`:

```tsx
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'

// CRITICAL: do NOT add rehype-raw. It bypasses sanitization. Spec §7.2.
const allowedTags = [
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'p', 'br', 'hr',
  'ul', 'ol', 'li',
  'strong', 'em', 'code', 'pre', 'blockquote',
  'a', 'img',
  'table', 'thead', 'tbody', 'tr', 'td', 'th',
]

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: allowedTags,
  attributes: {
    ...defaultSchema.attributes,
    a: [...(defaultSchema.attributes?.a ?? []), ['target']],
  },
}

interface MarkdownViewProps {
  children: string
}

export function MarkdownView({ children }: MarkdownViewProps) {
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

- [ ] **Step 4: Run test, verify pass**

Run: `cd frontend && npx vitest run src/components/help/MarkdownView.test.tsx`
Expected: 7 tests pass.

- [ ] **Step 5: Verify rehype-raw is NOT imported anywhere**

Run: `grep -rn "rehype-raw\|rehypeRaw" frontend/src/ || echo "CLEAN"`
Expected: `CLEAN`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/help/MarkdownView.tsx frontend/src/components/help/MarkdownView.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16c): MarkdownView with sanitize

react-markdown + remark-gfm + rehype-sanitize. Strict allowed-tags
whitelist. rehype-raw explicitly banned (spec §7.2). XSS regression
tests verify <script> bodies and onerror handlers are stripped.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: components/help/HelpSection.tsx + HelpAccordion.tsx

**Files:**
- Create: `frontend/src/components/help/HelpSection.tsx`
- Create: `frontend/src/components/help/HelpAccordion.tsx`
- Create: `frontend/src/components/help/HelpAccordion.test.tsx`
- Verify: shadcn `Accordion` primitive exists (`frontend/src/components/ui/accordion.tsx`)

- [ ] **Step 1: Verify or install shadcn Accordion primitive**

Run: `ls frontend/src/components/ui/accordion.tsx 2>/dev/null || echo "MISSING"`

If `MISSING`, install:
```bash
cd frontend && npx shadcn@latest add accordion
```

(If shadcn CLI not installed: `npm install --no-save @radix-ui/react-accordion` and create the wrapper file manually per shadcn template.)

Then commit the primitive immediately (atomic):
```bash
git add frontend/src/components/ui/accordion.tsx frontend/package.json frontend/package-lock.json
git commit -m "chore(paket-16c): add shadcn Accordion primitive"
```

- [ ] **Step 2: Write failing test**

Create `frontend/src/components/help/HelpAccordion.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HelpAccordion } from './HelpAccordion'

const sections = [
  { id: '01-welcome', order: 1, title: 'Hoş geldin', body: '# Hoş geldin\n\nMerhaba.' },
  { id: '02-getting-started', order: 2, title: 'Başlarken', body: '# Başlarken\n\nİlk adım.' },
  { id: '03-annotation-guide', order: 3, title: 'Anotasyon', body: '# Anotasyon\n\nReferans ekle.' },
]

describe('HelpAccordion', () => {
  it('renders all section titles as triggers', () => {
    render(<HelpAccordion sections={sections} />)
    expect(screen.getByRole('button', { name: /hoş geldin/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /başlarken/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /anotasyon/i })).toBeInTheDocument()
  })

  it('has first section expanded by default', () => {
    render(<HelpAccordion sections={sections} />)
    expect(screen.getByText(/merhaba/i)).toBeInTheDocument()
  })

  it('expands additional sections without collapsing the first', async () => {
    const user = userEvent.setup()
    render(<HelpAccordion sections={sections} />)
    expect(screen.queryByText(/i̇lk adım/i)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /başlarken/i }))
    expect(screen.getByText(/i̇lk adım/i)).toBeInTheDocument()
    // First section's body still visible
    expect(screen.getByText(/merhaba/i)).toBeInTheDocument()
  })

  it('renders empty when sections is empty', () => {
    const { container } = render(<HelpAccordion sections={[]} />)
    expect(container.querySelector('[data-state]')).toBeNull()
  })

  it('respects ordering by `order` field', () => {
    const unsorted = [
      { ...sections[2], order: 2 },
      { ...sections[0], order: 1 },
      { ...sections[1], order: 3 },
    ]
    render(<HelpAccordion sections={unsorted} />)
    const triggers = screen.getAllByRole('button')
    expect(triggers[0]).toHaveTextContent(/hoş geldin/i)
    expect(triggers[1]).toHaveTextContent(/anotasyon/i)
    expect(triggers[2]).toHaveTextContent(/başlarken/i)
  })
})
```

- [ ] **Step 3: Run test, verify fail**

Run: `cd frontend && npx vitest run src/components/help/HelpAccordion.test.tsx`
Expected: FAIL.

- [ ] **Step 4: Implement HelpSection**

Create `frontend/src/components/help/HelpSection.tsx`:

```tsx
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion'
import { MarkdownView } from './MarkdownView'
import type { HelpSection as HelpSectionData } from '@/lib/trainingSchemas'

interface HelpSectionProps {
  section: HelpSectionData
}

export function HelpSection({ section }: HelpSectionProps) {
  return (
    <AccordionItem value={section.id}>
      <AccordionTrigger>{section.title}</AccordionTrigger>
      <AccordionContent>
        <MarkdownView>{section.body}</MarkdownView>
      </AccordionContent>
    </AccordionItem>
  )
}
```

- [ ] **Step 5: Implement HelpAccordion**

Create `frontend/src/components/help/HelpAccordion.tsx`:

```tsx
import { Accordion } from '@/components/ui/accordion'
import { HelpSection } from './HelpSection'
import type { HelpSection as HelpSectionData } from '@/lib/trainingSchemas'

interface HelpAccordionProps {
  sections: HelpSectionData[]
}

export function HelpAccordion({ sections }: HelpAccordionProps) {
  if (sections.length === 0) return null
  const sorted = [...sections].sort((a, b) => a.order - b.order)
  const defaultValue = [sorted[0].id]
  return (
    <Accordion type="multiple" defaultValue={defaultValue} className="w-full">
      {sorted.map((s) => (
        <HelpSection key={s.id} section={s} />
      ))}
    </Accordion>
  )
}
```

- [ ] **Step 6: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/components/help/HelpAccordion.test.tsx`
Expected: 5 tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/help/HelpSection.tsx frontend/src/components/help/HelpAccordion.tsx frontend/src/components/help/HelpAccordion.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16c): HelpAccordion + HelpSection

Radix Accordion (multi-open), first section default-open, sorts by
order field, body rendered via MarkdownView. Spec §7.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: routes/Help.tsx + api/queries/me.ts (useSeenManualMutation)

**Files:**
- Modify: `frontend/src/routes/Help.tsx` (replace 16a STUB)
- Create: `frontend/src/api/queries/me.ts`
- Create: `frontend/src/api/queries/me.test.ts`
- Create: `frontend/src/routes/Help.test.tsx`

- [ ] **Step 1: Write failing tests for useSeenManualMutation**

Create `frontend/src/api/queries/me.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { server } from '@/test/msw-server'
import { useSeenManualMutation } from './me'

const API = 'http://localhost'

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useSeenManualMutation', () => {
  it('POSTs /api/me/seen-manual and resolves on success', async () => {
    let called = false
    server.use(
      http.post(`${API}/api/me/seen-manual`, () => {
        called = true
        return HttpResponse.json({ ok: true })
      }),
    )
    const { result } = renderHook(() => useSeenManualMutation(), { wrapper: wrapper() })
    await result.current.mutateAsync()
    await waitFor(() => expect(called).toBe(true))
  })

  it('rejects on 500', async () => {
    server.use(
      http.post(`${API}/api/me/seen-manual`, () =>
        HttpResponse.json({ detail: { error: 'boom', message: 'x' } }, { status: 500 }),
      ),
    )
    const { result } = renderHook(() => useSeenManualMutation(), { wrapper: wrapper() })
    await expect(result.current.mutateAsync()).rejects.toBeDefined()
  })
})
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd frontend && npx vitest run src/api/queries/me.test.ts`
Expected: FAIL "Cannot find module './me'".

- [ ] **Step 3: Implement useSeenManualMutation**

Create `frontend/src/api/queries/me.ts`:

```ts
import { useMutation } from '@tanstack/react-query'
import { client, unwrapVoid } from '@/api/client'

export function useSeenManualMutation() {
  return useMutation({
    mutationFn: async () => unwrapVoid(await client.POST('/api/me/seen-manual')),
  })
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/api/queries/me.test.ts`
Expected: 2 tests pass.

- [ ] **Step 5: Write failing test for Help.tsx**

Create `frontend/src/routes/Help.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server, mockAuthedUser } from '@/test/msw-handlers'
import { renderWithProviders } from '@/test/render'
import { Help } from './Help'
import { useAuthStore } from '@/stores/authStore'

const API = 'http://localhost'

describe('Help route', () => {
  it('renders accordion in normal mode without CTA', async () => {
    server.use(mockAuthedUser({ has_seen_manual: true, has_passed_training: false }))
    renderWithProviders(<Help />, { initialEntries: ['/help'] })
    await waitFor(() => expect(screen.getByRole('button', { name: /hoş geldin/i })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /eğitime geç/i })).not.toBeInTheDocument()
  })

  it('renders banner + CTA in first_time mode', async () => {
    server.use(mockAuthedUser({ has_seen_manual: false, has_passed_training: false }))
    renderWithProviders(<Help />, { initialEntries: ['/help?first_time=true'] })
    await waitFor(() => expect(screen.getByRole('button', { name: /eğitime geç/i })).toBeInTheDocument())
    expect(screen.getByText(/lütfen başlamadan önce/i)).toBeInTheDocument()
  })

  it('CTA click POSTs seen-manual, refreshes auth, and navigates to /training', async () => {
    const user = userEvent.setup()
    let seenManualCalled = false
    server.use(
      mockAuthedUser({ has_seen_manual: false }),
      http.post(`${API}/api/me/seen-manual`, () => {
        seenManualCalled = true
        return HttpResponse.json({ ok: true })
      }),
    )
    // After mutation, /me returns updated user
    useAuthStore.setState({
      status: 'authed',
      user: { id: 1, username: 't', role: 'user', avatar_color: '#000', has_seen_manual: false, has_passed_training: false } as never,
      error: null,
    })

    renderWithProviders(<Help />, { initialEntries: ['/help?first_time=true'] })
    await waitFor(() => expect(screen.getByRole('button', { name: /eğitime geç/i })).toBeInTheDocument())

    server.use(mockAuthedUser({ has_seen_manual: true }))
    await user.click(screen.getByRole('button', { name: /eğitime geç/i }))

    await waitFor(() => expect(seenManualCalled).toBe(true))
    await waitFor(() => expect(screen.getByTestId('route-training')).toBeInTheDocument())
  })

  it('CTA error shows toast and re-enables button', async () => {
    const user = userEvent.setup()
    server.use(
      mockAuthedUser({ has_seen_manual: false }),
      http.post(`${API}/api/me/seen-manual`, () =>
        HttpResponse.json({ detail: { error: 'boom', message: 'sunucu hatası' } }, { status: 500 }),
      ),
    )
    renderWithProviders(<Help />, { initialEntries: ['/help?first_time=true'] })
    await waitFor(() => expect(screen.getByRole('button', { name: /eğitime geç/i })).toBeInTheDocument())
    const cta = screen.getByRole('button', { name: /eğitime geç/i })
    await user.click(cta)
    // Button should be back to enabled after error
    await waitFor(() => expect(cta).not.toBeDisabled())
  })

  it('error path for help fetch renders error message', async () => {
    server.use(
      mockAuthedUser({ has_seen_manual: true }),
      http.get(`${API}/api/help`, () => HttpResponse.error()),
    )
    renderWithProviders(<Help />, { initialEntries: ['/help'] })
    await waitFor(() =>
      expect(screen.getByText(/yardım yüklenemedi|tekrar dene/i)).toBeInTheDocument(),
    )
  })
})
```

- [ ] **Step 6: Run test, verify fail**

Run: `cd frontend && npx vitest run src/routes/Help.test.tsx`
Expected: FAIL.

- [ ] **Step 7: Implement Help.tsx (replace STUB)**

Overwrite `frontend/src/routes/Help.tsx`:

```tsx
import { useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { HelpAccordion } from '@/components/help/HelpAccordion'
import { Button } from '@/components/ui/button'
import { useHelpQuery } from '@/api/queries/help'
import { useSeenManualMutation } from '@/api/queries/me'
import { refreshAuth } from '@/lib/refreshAuth'

export function Help() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const firstTime = searchParams.get('first_time') === 'true'
  const helpQuery = useHelpQuery()
  const seenManualMut = useSeenManualMutation()
  const h1Ref = useRef<HTMLHeadingElement | null>(null)

  useEffect(() => {
    h1Ref.current?.focus()
  }, [])

  const onCtaClick = async () => {
    try {
      await seenManualMut.mutateAsync()
      await refreshAuth(qc)
      navigate('/training', { replace: true })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Bir hata oluştu, tekrar dene.'
      toast.error(message)
    }
  }

  if (helpQuery.isLoading) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <p className="text-sm text-muted-foreground">Yükleniyor...</p>
      </div>
    )
  }

  if (helpQuery.isError) {
    return (
      <div className="mx-auto max-w-3xl p-6" role="alert">
        <h1 className="text-xl font-semibold">Yardım yüklenemedi</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {helpQuery.error instanceof Error ? helpQuery.error.message : 'Bilinmeyen hata.'}
        </p>
        <Button onClick={() => helpQuery.refetch()} className="mt-4">
          Tekrar Dene
        </Button>
      </div>
    )
  }

  const sections = helpQuery.data?.sections ?? []

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 ref={h1Ref} tabIndex={-1} className="text-2xl font-semibold focus:outline-none">
        Yardım Kılavuzu
      </h1>
      {firstTime && (
        <p className="mt-2 text-sm text-muted-foreground">
          Lütfen başlamadan önce kılavuzu okuyup eğitime geç.
        </p>
      )}
      <div className="mt-6">
        <HelpAccordion sections={sections} />
      </div>
      {firstTime && (
        <div className="mt-8 flex justify-center">
          <Button
            size="lg"
            onClick={onCtaClick}
            disabled={seenManualMut.isPending}
          >
            {seenManualMut.isPending ? 'Kaydediliyor...' : 'Anladım, eğitime geç →'}
          </Button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 8: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/routes/Help.test.tsx`
Expected: 5 tests pass.

- [ ] **Step 9: Full suite gate**

Run: `cd frontend && npm run test:run`
Expected: 126 (16a/16b) + new T1-T10 tests all pass.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/routes/Help.tsx frontend/src/api/queries/me.ts frontend/src/api/queries/me.test.ts frontend/src/routes/Help.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16c): Help route + seen-manual flow

Replaces 16a STUB. first_time=true mode shows banner + CTA; click runs
seenManual mutation → await refreshAuth → navigate('/training'). Normal
mode is browse-only. Spec §7.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: stores/trainingStore.ts (full implementation)

**Files:**
- Modify: `frontend/src/stores/trainingStore.ts` (REPLACE placeholder from T6)
- Create: `frontend/src/stores/trainingStore.test.ts`

- [ ] **Step 1: Write failing test**

Create `frontend/src/stores/trainingStore.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { useTrainingStore } from './trainingStore'
import type { StartResponse } from '@/lib/trainingSchemas'

const makeStart = (): StartResponse => ({
  attempt_id: 42,
  attempt_number: 1,
  questions: Array.from({ length: 5 }, (_, i) => ({
    id: `q${i + 1}`,
    text: `Soru ${i + 1}`,
    choices: ['a', 'b', 'c', 'd'],
  })),
  gold_docs: [
    { gold_id: 'gold_a', content: 'A' },
    { gold_id: 'gold_b', content: 'B' },
    { gold_id: 'gold_c', content: 'C' },
  ],
})

describe('trainingStore', () => {
  beforeEach(() => {
    sessionStorage.clear()
    useTrainingStore.getState().clear()
  })

  it('initial state is idle', () => {
    const s = useTrainingStore.getState()
    expect(s.step).toBe('idle')
    expect(s.attemptId).toBeNull()
    expect(s.docIndex).toBe(0)
    expect(s.degraded).toBe(false)
  })

  it('hydrate transitions to quiz', () => {
    useTrainingStore.getState().hydrate(makeStart())
    const s = useTrainingStore.getState()
    expect(s.step).toBe('quiz')
    expect(s.attemptId).toBe(42)
    expect(s.questions).toHaveLength(5)
    expect(s.goldDocs).toHaveLength(3)
    expect(s.docRefs).toEqual({ gold_a: [], gold_b: [], gold_c: [] })
  })

  it('setQuizAnswer accumulates answers', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().setQuizAnswer('q1', 2)
    useTrainingStore.getState().setQuizAnswer('q2', 0)
    expect(useTrainingStore.getState().quizAnswers).toEqual({ q1: 2, q2: 0 })
  })

  it('recordQuizResult sets resultShown to quiz', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().recordQuizResult({ score: 4, total: 5 })
    const s = useTrainingStore.getState()
    expect(s.quizResult).toEqual({ score: 4, total: 5 })
    expect(s.resultShown).toEqual({ kind: 'quiz' })
  })

  it('setDocRefs persists refs by gold_id', () => {
    useTrainingStore.getState().hydrate(makeStart())
    const refs = [{ kanun_no: '5520', kanun_ad: null, madde: '5', fikra: '1', bent: 'a', source_text: 'x' }]
    useTrainingStore.getState().setDocRefs('gold_a', refs)
    expect(useTrainingStore.getState().docRefs.gold_a).toEqual(refs)
  })

  it('recordDocResult sets resultShown to doc', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().recordDocResult('gold_a', {
      passed: true, matched_count: 2, expected_count: 2, min_concept_count: 1,
    })
    const s = useTrainingStore.getState()
    expect(s.docResults.gold_a.passed).toBe(true)
    expect(s.resultShown).toEqual({ kind: 'doc', goldId: 'gold_a' })
  })

  it('advanceDoc 0→1', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().advanceDoc()
    expect(useTrainingStore.getState().docIndex).toBe(1)
    expect(useTrainingStore.getState().resultShown).toBeNull()
  })

  it('clear wipes storage and resets to initial', () => {
    useTrainingStore.getState().hydrate(makeStart())
    expect(useTrainingStore.getState().step).toBe('quiz')
    useTrainingStore.getState().clear()
    expect(useTrainingStore.getState().step).toBe('idle')
    expect(sessionStorage.getItem('training-attempt-v1')).toBeNull()
  })

  it('persist roundtrip — write preserves state', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().setQuizAnswer('q1', 2)
    const raw = sessionStorage.getItem('training-attempt-v1')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!)
    expect(parsed.state.step).toBe('quiz')
    expect(parsed.state.quizAnswers.q1).toBe(2)
  })

  it('markDegraded sets flag', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().markDegraded()
    expect(useTrainingStore.getState().degraded).toBe(true)
  })

  it('setStep changes step and clears resultShown', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.setState({ resultShown: { kind: 'quiz' } })
    useTrainingStore.getState().setStep('doc')
    expect(useTrainingStore.getState().step).toBe('doc')
    expect(useTrainingStore.getState().resultShown).toBeNull()
  })
})
```

- [ ] **Step 2: Run tests, verify fail (placeholder lacks methods)**

Run: `cd frontend && npx vitest run src/stores/trainingStore.test.ts`
Expected: FAIL.

- [ ] **Step 3: Replace placeholder with full store**

Overwrite `frontend/src/stores/trainingStore.ts`:

```ts
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type {
  StartResponse,
  Question,
  GoldDoc,
  QuizSubmitResponse,
  AnnotateSubmitResponse,
} from '@/lib/trainingSchemas'
import type { components } from '@/api/types'

type ReferenceDraft = components['schemas']['ReferenceItem']

export type TrainingStep = 'idle' | 'quiz' | 'doc' | 'summary' | 'locked-out'

export interface TrainingState {
  attemptId: number | null
  attemptNumber: number | null
  step: TrainingStep
  docIndex: 0 | 1 | 2
  questions: Question[]
  goldDocs: GoldDoc[]
  quizAnswers: Record<string, number>
  quizResult: QuizSubmitResponse | null
  docRefs: Record<string, ReferenceDraft[]>
  docResults: Record<string, AnnotateSubmitResponse>
  resultShown: { kind: 'quiz' } | { kind: 'doc'; goldId: string } | null
  degraded: boolean
}

export interface TrainingActions {
  hydrate: (start: StartResponse) => void
  setQuizAnswer: (questionId: string, choice: number) => void
  recordQuizResult: (r: QuizSubmitResponse) => void
  setDocRefs: (goldId: string, refs: ReferenceDraft[]) => void
  recordDocResult: (goldId: string, r: AnnotateSubmitResponse) => void
  advanceDoc: () => void
  setStep: (step: TrainingStep) => void
  markDegraded: () => void
  clear: () => void
}

const initialState: TrainingState = {
  attemptId: null,
  attemptNumber: null,
  step: 'idle',
  docIndex: 0,
  questions: [],
  goldDocs: [],
  quizAnswers: {},
  quizResult: null,
  docRefs: {},
  docResults: {},
  resultShown: null,
  degraded: false,
}

const STORAGE_KEY = 'training-attempt-v1'

export function validateRestoredShape(s: Partial<TrainingState>): boolean {
  if (s.attemptId !== null && s.attemptId !== undefined && typeof s.attemptId !== 'number') return false
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

export const useTrainingStore = create<TrainingState & TrainingActions>()(
  persist(
    (set) => ({
      ...initialState,
      hydrate: (s) =>
        set({
          attemptId: s.attempt_id,
          attemptNumber: s.attempt_number,
          step: 'quiz',
          docIndex: 0,
          questions: s.questions,
          goldDocs: s.gold_docs,
          quizAnswers: {},
          quizResult: null,
          docRefs: Object.fromEntries(s.gold_docs.map((d) => [d.gold_id, []])),
          docResults: {},
          resultShown: null,
          degraded: false,
        }),
      setQuizAnswer: (questionId, choice) =>
        set((prev) => ({ quizAnswers: { ...prev.quizAnswers, [questionId]: choice } })),
      recordQuizResult: (r) => set({ quizResult: r, resultShown: { kind: 'quiz' } }),
      setDocRefs: (goldId, refs) =>
        set((prev) => ({ docRefs: { ...prev.docRefs, [goldId]: refs } })),
      recordDocResult: (goldId, r) =>
        set((prev) => ({
          docResults: { ...prev.docResults, [goldId]: r },
          resultShown: { kind: 'doc', goldId },
        })),
      advanceDoc: () =>
        set((prev) => {
          if (prev.docIndex < 2) {
            return { docIndex: (prev.docIndex + 1) as 0 | 1 | 2, resultShown: null }
          }
          return { resultShown: null }
        }),
      setStep: (step) => set({ step, resultShown: null }),
      markDegraded: () => set({ degraded: true }),
      clear: () => {
        sessionStorage.removeItem(STORAGE_KEY)
        set({ ...initialState })
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => sessionStorage),
      version: 1,
      partialize: (s) => ({
        attemptId: s.attemptId,
        attemptNumber: s.attemptNumber,
        step: s.step,
        docIndex: s.docIndex,
        questions: s.questions,
        goldDocs: s.goldDocs,
        quizAnswers: s.quizAnswers,
        quizResult: s.quizResult,
        docRefs: s.docRefs,
        docResults: s.docResults,
        resultShown: s.resultShown,
        degraded: s.degraded,
      }),
      migrate: (oldState, oldVersion) => {
        if (oldVersion < 1) return undefined as unknown as TrainingState & TrainingActions
        return oldState as TrainingState & TrainingActions
      },
      onRehydrateStorage: () => (state, error) => {
        if (error || !state) return
        if (!validateRestoredShape(state)) {
          sessionStorage.removeItem(STORAGE_KEY)
          useTrainingStore.setState({ ...initialState })
        }
      },
    },
  ),
)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/stores/trainingStore.test.ts src/lib/trainingRecovery.test.ts`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/trainingStore.ts frontend/src/stores/trainingStore.test.ts
git commit -m "feat(paket-16c): trainingStore (zustand + persist)

Full state machine. Persisted to sessionStorage with version + migrate +
onRehydrateStorage validation. Drops corrupt restores. Replaces T6
placeholder. Spec §8.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: api/queries/training.ts + MSW training handlers

**Files:**
- Create: `frontend/src/api/queries/training.ts`
- Create: `frontend/src/api/queries/training.test.ts`
- Modify: `frontend/src/test/msw-handlers.ts`

- [ ] **Step 1: Add training factories + handlers to msw-handlers.ts**

Append to `frontend/src/test/msw-handlers.ts` BEFORE the `handlers` export:

```ts
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
  http.get(`${API}/api/training/start`, () => HttpResponse.json(makeStartResponse())),
  http.post(`${API}/api/training/quiz/submit`, () => HttpResponse.json({ score: 4, total: 5 })),
  http.post(`${API}/api/training/annotate/submit`, () =>
    HttpResponse.json({ passed: true, matched_count: 2, expected_count: 2, min_concept_count: 1 }),
  ),
  http.post(`${API}/api/me/seen-manual`, () => HttpResponse.json({ ok: true })),
]

export function mockTrainingStartLockedOut() {
  return http.get(`${API}/api/training/start`, () =>
    HttpResponse.json({ detail: { error: 'max_attempts_reached', message: 'too many' } }, { status: 403 }),
  )
}

export function mockTrainingStartAlreadyPassed() {
  return http.get(`${API}/api/training/start`, () =>
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
    HttpResponse.json({ passed: false, matched_count: 0, expected_count: 2, min_concept_count: 1 }),
  )
}
```

Add `...TRAINING_DEFAULT_HANDLERS` to the `handlers` array.

- [ ] **Step 2: Write failing test**

Create `frontend/src/api/queries/training.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { server, mockTrainingStartLockedOut, mockTrainingStartAlreadyPassed, mockQuizSubmitAlreadySubmitted } from '@/test/msw-handlers'
import { useTrainingStartMutation, useQuizSubmitMutation, useAnnotateSubmitMutation } from './training'

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useTrainingStartMutation', () => {
  it('returns parsed StartResponse', async () => {
    const { result } = renderHook(() => useTrainingStartMutation(), { wrapper: wrapper() })
    const data = await result.current.mutateAsync()
    expect(data.questions).toHaveLength(5)
    expect(data.gold_docs).toHaveLength(3)
  })

  it('writes pending-start sentinel before request', async () => {
    sessionStorage.removeItem('training-start-pending')
    const { result } = renderHook(() => useTrainingStartMutation(), { wrapper: wrapper() })
    const promise = result.current.mutateAsync()
    expect(sessionStorage.getItem('training-start-pending')).not.toBeNull()
    await promise
  })

  it('throws on 403 locked out', async () => {
    server.use(mockTrainingStartLockedOut())
    const { result } = renderHook(() => useTrainingStartMutation(), { wrapper: wrapper() })
    await expect(result.current.mutateAsync()).rejects.toMatchObject({ status: 403, code: 'max_attempts_reached' })
  })

  it('throws on 409 already_passed', async () => {
    server.use(mockTrainingStartAlreadyPassed())
    const { result } = renderHook(() => useTrainingStartMutation(), { wrapper: wrapper() })
    await expect(result.current.mutateAsync()).rejects.toMatchObject({ status: 409, code: 'already_passed' })
  })
})

describe('useQuizSubmitMutation', () => {
  it('returns parsed result', async () => {
    const { result } = renderHook(() => useQuizSubmitMutation(), { wrapper: wrapper() })
    const data = await result.current.mutateAsync({ attempt_id: 1, answers: { q01: 0 } })
    expect(data).toEqual({ score: 4, total: 5 })
  })

  it('throws on 409', async () => {
    server.use(mockQuizSubmitAlreadySubmitted())
    const { result } = renderHook(() => useQuizSubmitMutation(), { wrapper: wrapper() })
    await expect(result.current.mutateAsync({ attempt_id: 1, answers: {} })).rejects.toMatchObject({
      status: 409, code: 'quiz_already_submitted',
    })
  })
})

describe('useAnnotateSubmitMutation', () => {
  it('returns parsed result', async () => {
    const { result } = renderHook(() => useAnnotateSubmitMutation(), { wrapper: wrapper() })
    const data = await result.current.mutateAsync({ attempt_id: 1, gold_id: 'gold_a', references: [] })
    expect(data).toMatchObject({ passed: true, matched_count: 2 })
  })
})
```

- [ ] **Step 3: Implement training mutations**

Create `frontend/src/api/queries/training.ts`:

```ts
import { useMutation } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import {
  startResponseSchema,
  quizSubmitResponseSchema,
  annotateSubmitResponseSchema,
  type StartResponse,
  type QuizSubmitResponse,
  type AnnotateSubmitResponse,
} from '@/lib/trainingSchemas'
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

export const trainingKeys = { all: ['training'] as const }
export const PENDING_START_SENTINEL_KEY = 'training-start-pending'

export function useTrainingStartMutation() {
  return useMutation<StartResponse, Error, void>({
    mutationFn: async () => {
      sessionStorage.setItem(PENDING_START_SENTINEL_KEY, JSON.stringify({ ts: Date.now() }))
      const raw = await unwrap(await client.GET('/api/training/start'))
      return startResponseSchema.parse(raw)
    },
  })
}

export function useQuizSubmitMutation() {
  return useMutation<QuizSubmitResponse, Error, { attempt_id: number; answers: Record<string, number> }>({
    mutationFn: async (body) => {
      const raw = await unwrap(await client.POST('/api/training/quiz/submit', { body }))
      return quizSubmitResponseSchema.parse(raw)
    },
  })
}

export function useAnnotateSubmitMutation() {
  return useMutation<AnnotateSubmitResponse, Error, { attempt_id: number; gold_id: string; references: ReferenceItem[] }>({
    mutationFn: async (body) => {
      const raw = await unwrap(await client.POST('/api/training/annotate/submit', { body }))
      return annotateSubmitResponseSchema.parse(raw)
    },
  })
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/api/queries/training.test.ts`
Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/queries/training.ts frontend/src/api/queries/training.test.ts frontend/src/test/msw-handlers.ts
git commit -m "feat(paket-16c): training mutations + handlers

3 mutations (start, quiz/submit, annotate/submit) + Zod parse at
boundary. Sentinel written before /start (Codex-2 BROKEN-C). MSW
factories for happy + 403/409 variants. Spec §8.3, §8.8.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: components/training/TrainingProgress.tsx

**Files:**
- Create: `frontend/src/components/training/TrainingProgress.tsx`
- Create: `frontend/src/components/training/TrainingProgress.test.tsx`

- [ ] **Step 1: Write failing test**

Create `frontend/src/components/training/TrainingProgress.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TrainingProgress } from './TrainingProgress'

describe('TrainingProgress', () => {
  it('renders 5 labeled pills', () => {
    render(<TrainingProgress step="quiz" docIndex={0} />)
    expect(screen.getByText(/quiz/i)).toBeInTheDocument()
    expect(screen.getByText(/doc 1/i)).toBeInTheDocument()
    expect(screen.getByText(/doc 2/i)).toBeInTheDocument()
    expect(screen.getByText(/doc 3/i)).toBeInTheDocument()
    expect(screen.getByText(/sonuç/i)).toBeInTheDocument()
  })

  it('quiz step → aria-current on Quiz pill', () => {
    const { container } = render(<TrainingProgress step="quiz" docIndex={0} />)
    expect(container.querySelector('[aria-current="step"]')?.textContent).toMatch(/quiz/i)
  })

  it('doc step docIndex=1 → aria-current on Doc 2', () => {
    const { container } = render(<TrainingProgress step="doc" docIndex={1} />)
    expect(container.querySelector('[aria-current="step"]')?.textContent).toMatch(/doc 2/i)
  })

  it('summary step → aria-current on Sonuç', () => {
    const { container } = render(<TrainingProgress step="summary" docIndex={0} />)
    expect(container.querySelector('[aria-current="step"]')?.textContent).toMatch(/sonuç/i)
  })

  it('idle step → no aria-current', () => {
    const { container } = render(<TrainingProgress step="idle" docIndex={0} />)
    expect(container.querySelector('[aria-current="step"]')).toBeNull()
  })
})
```

- [ ] **Step 2: Implement TrainingProgress**

Create `frontend/src/components/training/TrainingProgress.tsx`:

```tsx
import { cn } from '@/lib/utils'
import type { TrainingStep } from '@/stores/trainingStore'

interface TrainingProgressProps {
  step: TrainingStep
  docIndex: 0 | 1 | 2
}

const LABELS = ['Quiz', 'Doc 1', 'Doc 2', 'Doc 3', 'Sonuç']

export function TrainingProgress({ step, docIndex }: TrainingProgressProps) {
  const activeIndex =
    step === 'quiz' ? 0
    : step === 'doc' ? 1 + docIndex
    : step === 'summary' ? 4
    : -1

  return (
    <ol role="list" className="mb-6 flex items-center justify-between gap-2">
      {LABELS.map((label, i) => {
        const done = i < activeIndex
        const active = i === activeIndex
        return (
          <li
            key={label}
            role="listitem"
            aria-current={active ? 'step' : undefined}
            className="flex flex-1 flex-col items-center gap-1"
          >
            <span
              className={cn(
                'flex h-6 w-6 items-center justify-center rounded-full border text-xs',
                done && 'border-primary bg-primary text-primary-foreground',
                active && 'border-primary bg-background font-semibold text-primary',
                !done && !active && 'border-muted-foreground text-muted-foreground',
              )}
            >
              {done ? '●' : active ? '◉' : '○'}
            </span>
            <span className={cn('text-xs', active && 'font-medium')}>{label}</span>
          </li>
        )
      })}
    </ol>
  )
}
```

- [ ] **Step 3: Run + commit**

```bash
cd frontend && npx vitest run src/components/training/TrainingProgress.test.tsx
# expect 5 pass
git add frontend/src/components/training/TrainingProgress.tsx frontend/src/components/training/TrainingProgress.test.tsx
git commit -m "feat(paket-16c): TrainingProgress stepper

5-pill ordered list. aria-current=step on active. Visible labels.
Spec §8.7, §13.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: components/training/StartScreen.tsx

**Files:**
- Create: `frontend/src/components/training/StartScreen.tsx`
- Create: `frontend/src/components/training/StartScreen.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/training/StartScreen.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StartScreen } from './StartScreen'

describe('StartScreen', () => {
  it('renders warning copy', () => {
    render(<StartScreen onStart={vi.fn()} onBackToHelp={vi.fn()} isPending={false} />)
    expect(screen.getByText(/1 deneme harcanır/i)).toBeInTheDocument()
  })

  it('Başla disabled until checkbox checked', async () => {
    const user = userEvent.setup()
    render(<StartScreen onStart={vi.fn()} onBackToHelp={vi.fn()} isPending={false} />)
    expect(screen.getByRole('button', { name: /^başla$/i })).toBeDisabled()
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: /^başla$/i })).not.toBeDisabled()
  })

  it('Başla click triggers onStart', async () => {
    const user = userEvent.setup()
    const onStart = vi.fn()
    render(<StartScreen onStart={onStart} onBackToHelp={vi.fn()} isPending={false} />)
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: /^başla$/i }))
    expect(onStart).toHaveBeenCalledOnce()
  })

  it('Başla disabled while pending', async () => {
    const user = userEvent.setup()
    render(<StartScreen onStart={vi.fn()} onBackToHelp={vi.fn()} isPending={true} />)
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: /başla|başlatılıyor/i })).toBeDisabled()
  })

  it('Kılavuza dön invokes onBackToHelp', async () => {
    const user = userEvent.setup()
    const onBack = vi.fn()
    render(<StartScreen onStart={vi.fn()} onBackToHelp={onBack} isPending={false} />)
    await user.click(screen.getByRole('button', { name: /kılavuza dön/i }))
    expect(onBack).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Implement StartScreen**

```tsx
// frontend/src/components/training/StartScreen.tsx
import { useState } from 'react'
import { Button } from '@/components/ui/button'

interface StartScreenProps {
  onStart: () => void
  onBackToHelp: () => void
  isPending: boolean
}

export function StartScreen({ onStart, onBackToHelp, isPending }: StartScreenProps) {
  const [confirmed, setConfirmed] = useState(false)
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-2 text-sm">
        <p>Aşağıdaki adımlardan oluşur:</p>
        <ol className="ml-5 list-decimal space-y-1">
          <li>5 soruluk quiz (≥4 doğru)</li>
          <li>3 doküman üzerinde anotasyon (≥2 geçer)</li>
        </ol>
      </div>
      <div className="rounded-md border border-amber-500/50 bg-amber-50 p-4 text-sm dark:bg-amber-950/20">
        <p className="font-medium">⚠ DİKKAT</p>
        <p className="mt-1">
          Başladığında <strong>1 deneme harcanır</strong>. Sayfayı yarıda kapatırsan o
          deneme kaybolur ve hak harcanmış sayılır. Maksimum 3 denemen var.
        </p>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
          className="h-4 w-4"
        />
        Anladım, başlamaya hazırım
      </label>
      <div className="flex gap-2">
        <Button onClick={onStart} disabled={!confirmed || isPending} size="lg">
          {isPending ? 'Başlatılıyor...' : 'Başla'}
        </Button>
        <Button onClick={onBackToHelp} variant="ghost">← Kılavuza dön</Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Run + commit**

```bash
cd frontend && npx vitest run src/components/training/StartScreen.test.tsx
git add frontend/src/components/training/StartScreen.tsx frontend/src/components/training/StartScreen.test.tsx
git commit -m "feat(paket-16c): StartScreen + confirm gate

Mandatory checkbox + warning copy. Spec §8.7, Codex BROKEN-2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: components/training/QuizStep.tsx

**Files:**
- Create: `frontend/src/components/training/QuizStep.tsx`
- Create: `frontend/src/components/training/QuizStep.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/training/QuizStep.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useTrainingStore } from '@/stores/trainingStore'
import { QuizStep } from './QuizStep'

const questions = [
  { id: 'q01', text: 'Soru 1', choices: ['a', 'b', 'c', 'd'] },
  { id: 'q02', text: 'Soru 2', choices: ['a', 'b', 'c', 'd'] },
  { id: 'q03', text: 'Soru 3', choices: ['a', 'b', 'c', 'd'] },
  { id: 'q04', text: 'Soru 4', choices: ['a', 'b', 'c', 'd'] },
  { id: 'q05', text: 'Soru 5', choices: ['a', 'b', 'c', 'd'] },
]

describe('QuizStep', () => {
  beforeEach(() => {
    useTrainingStore.getState().clear()
    useTrainingStore.setState({ questions, attemptId: 100, step: 'quiz' })
  })

  it('renders 5 fieldsets, 20 radios', () => {
    render(<QuizStep onSubmit={vi.fn()} isSubmitting={false} />)
    expect(screen.getAllByRole('group')).toHaveLength(5)
    expect(screen.getAllByRole('radio')).toHaveLength(20)
  })

  it('shows info banner', () => {
    render(<QuizStep onSubmit={vi.fn()} isSubmitting={false} />)
    expect(screen.getByText(/skorunu hepsini birden öğreneceksin/i)).toBeInTheDocument()
  })

  it('submit disabled until 5 answered', async () => {
    const user = userEvent.setup()
    render(<QuizStep onSubmit={vi.fn()} isSubmitting={false} />)
    const btn = screen.getByRole('button', { name: /cevapları gönder/i })
    expect(btn).toBeDisabled()
    for (let i = 0; i < 5; i++) {
      await user.click(screen.getAllByRole('radio')[i * 4])
    }
    expect(btn).not.toBeDisabled()
  })

  it('submit invokes onSubmit with answers', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<QuizStep onSubmit={onSubmit} isSubmitting={false} />)
    for (let i = 0; i < 5; i++) {
      await user.click(screen.getAllByRole('radio')[i * 4 + (i % 4)])
    }
    await user.click(screen.getByRole('button', { name: /cevapları gönder/i }))
    expect(onSubmit).toHaveBeenCalledWith({ q01: 0, q02: 1, q03: 2, q04: 3, q05: 0 })
  })

  it('shows result card with role=status when resultShown=quiz', () => {
    useTrainingStore.setState({ quizResult: { score: 3, total: 5 }, resultShown: { kind: 'quiz' } })
    render(<QuizStep onSubmit={vi.fn()} isSubmitting={false} />)
    expect(screen.getByText(/3 \/ 5/)).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('Sonraki advances to doc step', async () => {
    const user = userEvent.setup()
    useTrainingStore.setState({ quizResult: { score: 4, total: 5 }, resultShown: { kind: 'quiz' } })
    render(<QuizStep onSubmit={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /sonraki: doküman 1/i }))
    expect(useTrainingStore.getState().step).toBe('doc')
  })
})
```

- [ ] **Step 2: Implement QuizStep**

```tsx
// frontend/src/components/training/QuizStep.tsx
import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { useTrainingStore } from '@/stores/trainingStore'

interface QuizStepProps {
  onSubmit: (answers: Record<string, number>) => void
  isSubmitting: boolean
}

export function QuizStep({ onSubmit, isSubmitting }: QuizStepProps) {
  const questions = useTrainingStore((s) => s.questions)
  const quizAnswers = useTrainingStore((s) => s.quizAnswers)
  const setQuizAnswer = useTrainingStore((s) => s.setQuizAnswer)
  const resultShown = useTrainingStore((s) => s.resultShown)
  const quizResult = useTrainingStore((s) => s.quizResult)
  const setStep = useTrainingStore((s) => s.setStep)

  const headingRef = useRef<HTMLHeadingElement | null>(null)
  useEffect(() => {
    headingRef.current?.focus()
  }, [resultShown])

  const allAnswered = questions.every((q) => quizAnswers[q.id] !== undefined)

  if (resultShown?.kind === 'quiz' && quizResult) {
    return (
      <section aria-labelledby="quiz-result-heading">
        <h2 ref={headingRef} tabIndex={-1} id="quiz-result-heading" className="text-xl font-semibold focus:outline-none">
          Quiz tamamlandı
        </h2>
        <div role="status" aria-live="polite" className="mt-4 rounded-md border bg-card p-4 text-sm">
          ✓ Skor: <strong>{quizResult.score} / {quizResult.total}</strong>
          <p className="mt-1 text-xs text-muted-foreground">(Geçmek için ≥4 gerekir)</p>
        </div>
        <div className="mt-6">
          <Button onClick={() => setStep('doc')}>Sonraki: Doküman 1 ▸</Button>
        </div>
      </section>
    )
  }

  return (
    <section aria-labelledby="quiz-heading">
      <h2 ref={headingRef} tabIndex={-1} id="quiz-heading" className="text-xl font-semibold focus:outline-none">
        Quiz
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        ⓘ 5 soruyu cevapla, sonra "Cevapları Gönder" tuşuna bas. Skorunu hepsini birden öğreneceksin.
      </p>
      <div className="mt-6 space-y-6">
        {questions.map((q, idx) => (
          <fieldset key={q.id} className="rounded-md border p-4">
            <legend className="px-2 text-sm font-medium">{idx + 1}. {q.text}</legend>
            <div className="mt-2 space-y-2">
              {q.choices.map((choice, ci) => (
                <label key={ci} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name={q.id}
                    value={ci}
                    checked={quizAnswers[q.id] === ci}
                    onChange={() => setQuizAnswer(q.id, ci)}
                    disabled={isSubmitting}
                    className="h-4 w-4"
                  />
                  {choice}
                </label>
              ))}
            </div>
          </fieldset>
        ))}
      </div>
      <div className="mt-6">
        <Button onClick={() => onSubmit(quizAnswers)} disabled={!allAnswered || isSubmitting}>
          {isSubmitting ? 'Gönderiliyor...' : 'Cevapları Gönder'}
        </Button>
      </div>
    </section>
  )
}
```

- [ ] **Step 3: Run + commit**

```bash
cd frontend && npx vitest run src/components/training/QuizStep.test.tsx
git add frontend/src/components/training/QuizStep.tsx frontend/src/components/training/QuizStep.test.tsx
git commit -m "feat(paket-16c): QuizStep

5 fieldsets, 4 radios each, all-required gate. Inline result via
role=status + aria-live. Spec §8.7, §13.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: components/training/AnnotateStep.tsx

**Files:**
- Create: `frontend/src/components/training/AnnotateStep.tsx`
- Create: `frontend/src/components/training/AnnotateStep.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/training/AnnotateStep.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useTrainingStore } from '@/stores/trainingStore'
import { AnnotateStep } from './AnnotateStep'

const goldDocs = [
  { gold_id: 'gold_a', content: 'Doc A içeriği — KVK 5/1-a uyarınca...' },
  { gold_id: 'gold_b', content: 'Doc B içeriği — KDV 29...' },
  { gold_id: 'gold_c', content: 'Doc C içeriği — GVK Geçici 67...' },
]

describe('AnnotateStep', () => {
  beforeEach(() => {
    useTrainingStore.getState().clear()
    useTrainingStore.setState({
      goldDocs, attemptId: 100, step: 'doc', docIndex: 0,
      docRefs: { gold_a: [], gold_b: [], gold_c: [] },
    })
  })

  it('renders current doc content', () => {
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByText(/doc a içeriği/i)).toBeInTheDocument()
  })

  it('renders + Yeni Referans button', () => {
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByRole('button', { name: /yeni referans/i })).toBeInTheDocument()
  })

  it('adding a reference renders fields', async () => {
    const user = userEvent.setup()
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /yeni referans/i }))
    expect(screen.getByLabelText(/^kanun_no$/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^source_text$/i)).toBeInTheDocument()
  })

  it('Submit disabled if reference is missing kanun_no', async () => {
    const user = userEvent.setup()
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /yeni referans/i }))
    await user.type(screen.getByLabelText(/^source_text$/i), 'metin')
    expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled()
  })

  it('Submit enabled with zero references (legal case)', () => {
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByRole('button', { name: /submit/i })).not.toBeDisabled()
  })

  it('Submit invokes onSubmit with gold_id + refs', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<AnnotateStep onSubmit={onSubmit} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /submit/i }))
    expect(onSubmit).toHaveBeenCalledWith('gold_a', [])
  })

  it('shows result card via role=status when resultShown=doc for current', () => {
    useTrainingStore.setState({
      docResults: { gold_a: { passed: true, matched_count: 2, expected_count: 2, min_concept_count: 1 } },
      resultShown: { kind: 'doc', goldId: 'gold_a' },
    })
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByText(/2 \/ 2/)).toBeInTheDocument()
    expect(screen.getByText(/geçti/i)).toBeInTheDocument()
  })

  it('Sonraki advances when docIndex<2', async () => {
    const user = userEvent.setup()
    const onAdvance = vi.fn()
    useTrainingStore.setState({
      docResults: { gold_a: { passed: true, matched_count: 1, expected_count: 1, min_concept_count: 1 } },
      resultShown: { kind: 'doc', goldId: 'gold_a' },
    })
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={onAdvance} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /sonraki: doküman 2/i }))
    expect(onAdvance).toHaveBeenCalledOnce()
  })

  it('docIndex=2 → "Sonuçları Gör" button', () => {
    useTrainingStore.setState({
      docIndex: 2,
      docResults: { gold_c: { passed: true, matched_count: 1, expected_count: 1, min_concept_count: 1 } },
      resultShown: { kind: 'doc', goldId: 'gold_c' },
    })
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByRole('button', { name: /sonuçları gör/i })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Implement AnnotateStep**

```tsx
// frontend/src/components/training/AnnotateStep.tsx
import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { ReferenceCard } from '@/components/annotation/ReferenceCard'
import { useTrainingStore } from '@/stores/trainingStore'
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

function emptyRef(): ReferenceItem {
  return { kanun_no: null, kanun_ad: null, madde: null, fikra: null, bent: null, source_text: '' }
}

function isTrainingReferenceValid(r: ReferenceItem): boolean {
  if (!r.source_text || r.source_text.trim().length === 0) return false
  if (!r.kanun_no || r.kanun_no.trim().length === 0) return false
  return true
}

interface AnnotateStepProps {
  onSubmit: (goldId: string, references: ReferenceItem[]) => void
  onAdvance: () => void
  isSubmitting: boolean
}

export function AnnotateStep({ onSubmit, onAdvance, isSubmitting }: AnnotateStepProps) {
  const docIndex = useTrainingStore((s) => s.docIndex)
  const goldDocs = useTrainingStore((s) => s.goldDocs)
  const docRefs = useTrainingStore((s) => s.docRefs)
  const docResults = useTrainingStore((s) => s.docResults)
  const resultShown = useTrainingStore((s) => s.resultShown)
  const setDocRefs = useTrainingStore((s) => s.setDocRefs)
  const headingRef = useRef<HTMLHeadingElement | null>(null)

  useEffect(() => {
    headingRef.current?.focus()
  }, [resultShown, docIndex])

  const currentDoc = goldDocs[docIndex]
  if (!currentDoc) {
    return <p className="text-sm text-muted-foreground">Doküman bulunamadı.</p>
  }
  const refs = docRefs[currentDoc.gold_id] ?? []
  const allValid = refs.every(isTrainingReferenceValid)

  const updateRef = (idx: number, next: ReferenceItem) => {
    const updated = [...refs]; updated[idx] = next
    setDocRefs(currentDoc.gold_id, updated)
  }
  const removeRef = (idx: number) => setDocRefs(currentDoc.gold_id, refs.filter((_, i) => i !== idx))
  const addRef = () => setDocRefs(currentDoc.gold_id, [...refs, emptyRef()])

  if (resultShown?.kind === 'doc' && resultShown.goldId === currentDoc.gold_id) {
    const result = docResults[currentDoc.gold_id]
    if (!result) return null
    const isLast = docIndex === 2
    return (
      <section aria-labelledby="doc-result-heading">
        <h2 ref={headingRef} tabIndex={-1} id="doc-result-heading" className="text-xl font-semibold focus:outline-none">
          Doküman {docIndex + 1} tamamlandı
        </h2>
        <div role="status" aria-live="polite" className="mt-4 rounded-md border bg-card p-4 text-sm">
          <p>Eşleşme: <strong>{result.matched_count} / {result.expected_count}</strong></p>
          <p className="mt-1">Durum: <strong>{result.passed ? 'Geçti' : 'Geçemedi'}</strong></p>
        </div>
        <div className="mt-6">
          <Button onClick={onAdvance}>
            {isLast ? 'Sonuçları Gör ▸' : `Sonraki: Doküman ${docIndex + 2} ▸`}
          </Button>
        </div>
      </section>
    )
  }

  return (
    <section aria-labelledby="doc-heading">
      <h2 ref={headingRef} tabIndex={-1} id="doc-heading" className="text-xl font-semibold focus:outline-none">
        Doküman {docIndex + 1}
      </h2>
      <article className="mt-4 rounded-md border bg-card p-4">
        {currentDoc.content.split(/\n\s*\n/).map((para, i) => (
          <p key={i} className="mb-2 text-sm leading-relaxed last:mb-0">{para}</p>
        ))}
      </article>
      <section aria-labelledby="refs-heading" className="mt-6 space-y-3">
        <h3 id="refs-heading" className="text-sm font-medium">
          Referanslar <span className="text-muted-foreground">(kanun atfı yoksa boş bırakabilirsin)</span>
        </h3>
        {refs.map((r, i) => (
          <ReferenceCard
            key={i}
            index={i}
            value={r}
            onChange={(next) => updateRef(i, next)}
            onRemove={() => removeRef(i)}
            disabled={isSubmitting}
          />
        ))}
        <Button onClick={addRef} variant="outline" size="sm" disabled={isSubmitting}>
          + Yeni Referans
        </Button>
      </section>
      <div className="mt-6">
        <Button onClick={() => onSubmit(currentDoc.gold_id, refs)} disabled={isSubmitting || !allValid}>
          {isSubmitting ? 'Gönderiliyor...' : 'Submit & Sonraki ▸'}
        </Button>
      </div>
    </section>
  )
}
```

- [ ] **Step 3: Verify 16b ReferenceCard untouched**

Run: `git diff --stat HEAD -- frontend/src/components/annotation/ReferenceCard.tsx frontend/src/components/annotation/ReferencePanel.tsx`
Expected: no output.

- [ ] **Step 4: Run + commit**

```bash
cd frontend && npx vitest run src/components/training/AnnotateStep.test.tsx
git add frontend/src/components/training/AnnotateStep.tsx frontend/src/components/training/AnnotateStep.test.tsx
git commit -m "feat(paket-16c): AnnotateStep

Reuses 16b ReferenceCard untouched. Training-strict validation local.
3rd doc → Sonuçları Gör. Spec §8.7, §9, §10.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: components/training/SummaryStep.tsx (PASS/FAIL/DEGRADED)

**Files:**
- Create: `frontend/src/components/training/SummaryStep.tsx`
- Create: `frontend/src/components/training/SummaryStep.test.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/training/SummaryStep.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useTrainingStore } from '@/stores/trainingStore'
import { useAuthStore } from '@/stores/authStore'
import { SummaryStep } from './SummaryStep'
import { makeUser } from '@/test/msw-handlers'

const goldDocs = [
  { gold_id: 'gold_a', content: 'A' },
  { gold_id: 'gold_b', content: 'B' },
  { gold_id: 'gold_c', content: 'C' },
]

describe('SummaryStep', () => {
  beforeEach(() => {
    useTrainingStore.getState().clear()
    useTrainingStore.setState({
      attemptId: 100, step: 'summary', goldDocs,
      quizResult: { score: 4, total: 5 },
      docResults: {
        gold_a: { passed: true, matched_count: 2, expected_count: 2, min_concept_count: 1 },
        gold_b: { passed: true, matched_count: 1, expected_count: 1, min_concept_count: 1 },
        gold_c: { passed: false, matched_count: 0, expected_count: 2, min_concept_count: 1 },
      },
    })
  })

  it('PASS variant when has_passed_training=true', () => {
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: true }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    expect(screen.getByText(/tebrikler/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /anotasyona başla/i })).toBeInTheDocument()
  })

  it('FAIL variant when has_passed_training=false', () => {
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: false }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    expect(screen.getByText(/geçemedin/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /tekrar dene/i })).toBeInTheDocument()
  })

  it('DEGRADED hides breakdown', () => {
    useTrainingStore.setState({ degraded: true })
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: true }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    expect(screen.getByText(/detaylar yeniden yüklenemedi/i)).toBeInTheDocument()
    expect(screen.queryByText(/quiz: 4/i)).not.toBeInTheDocument()
  })

  it('DEGRADED + passed → Anotasyona Başla', () => {
    useTrainingStore.setState({ degraded: true })
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: true }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    expect(screen.getByRole('button', { name: /anotasyona başla/i })).toBeInTheDocument()
  })

  it('DEGRADED + not passed → Tekrar Dene', () => {
    useTrainingStore.setState({ degraded: true })
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: false }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    expect(screen.getByRole('button', { name: /tekrar dene/i })).toBeInTheDocument()
  })

  it('Anotasyona Başla → onAnnotate', async () => {
    const user = userEvent.setup()
    const onAnnotate = vi.fn()
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: true }), error: null })
    render(<SummaryStep onAnnotate={onAnnotate} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /anotasyona başla/i }))
    expect(onAnnotate).toHaveBeenCalledOnce()
  })

  it('Tekrar Dene → onRetry', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: false }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={onRetry} onBackToHelp={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /tekrar dene/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Implement SummaryStep**

```tsx
// frontend/src/components/training/SummaryStep.tsx
import { Button } from '@/components/ui/button'
import { useTrainingStore } from '@/stores/trainingStore'
import { useAuthStore } from '@/stores/authStore'

interface SummaryStepProps {
  onAnnotate: () => void
  onRetry: () => void
  onBackToHelp: () => void
}

export function SummaryStep({ onAnnotate, onRetry, onBackToHelp }: SummaryStepProps) {
  const degraded = useTrainingStore((s) => s.degraded)
  const quizResult = useTrainingStore((s) => s.quizResult)
  const docResults = useTrainingStore((s) => s.docResults)
  const goldDocs = useTrainingStore((s) => s.goldDocs)
  const user = useAuthStore((s) => s.user)
  const passed = !!user?.has_passed_training

  if (degraded) {
    return (
      <section aria-labelledby="summary-degraded-heading" className="space-y-4">
        <h2 id="summary-degraded-heading" className="text-xl font-semibold">Sonuç</h2>
        <p className="text-sm">Bu attempt için detaylar yeniden yüklenemedi.</p>
        <p className="text-sm">Genel durum: <strong>{passed ? 'Geçti' : 'Geçemedi'}</strong></p>
        <div className="flex gap-2">
          {passed
            ? <Button onClick={onAnnotate}>Anotasyona Başla ▸</Button>
            : <Button onClick={onRetry}>Tekrar Dene</Button>}
        </div>
      </section>
    )
  }

  const passedDocs = goldDocs.filter((g) => docResults[g.gold_id]?.passed).length

  if (passed) {
    return (
      <section aria-labelledby="summary-pass-heading" className="space-y-4">
        <h2 id="summary-pass-heading" className="text-xl font-semibold">🎉 Tebrikler! Eğitimi geçtin</h2>
        <div className="space-y-1 rounded-md border bg-card p-4 text-sm">
          {quizResult && (
            <p>Quiz: <strong>{quizResult.score}/{quizResult.total}</strong> {quizResult.score >= 4 ? '✓ Geçti' : '✗ Geçemedi'}</p>
          )}
          {goldDocs.map((g, i) => {
            const r = docResults[g.gold_id]
            return <p key={g.gold_id}>Doc {i + 1}: <strong>{r ? `${r.matched_count}/${r.expected_count}` : '—'}</strong> {r?.passed ? '✓ Geçti' : '✗ Geçemedi'}</p>
          })}
          <p>Anot. geçen: {passedDocs} / 3 (gerekli: 2)</p>
          <p className="mt-2 font-semibold">Overall: GEÇTI</p>
        </div>
        <Button onClick={onAnnotate} size="lg">Anotasyona Başla ▸</Button>
      </section>
    )
  }

  return (
    <section aria-labelledby="summary-fail-heading" className="space-y-4">
      <h2 id="summary-fail-heading" className="text-xl font-semibold">Eğitimi geçemedin</h2>
      <div className="space-y-1 rounded-md border bg-card p-4 text-sm">
        {quizResult && (
          <p>Quiz: <strong>{quizResult.score}/{quizResult.total}</strong> {quizResult.score >= 4 ? '✓ Geçti' : '✗ Geçemedi (eşik 4)'}</p>
        )}
        {goldDocs.map((g, i) => {
          const r = docResults[g.gold_id]
          return <p key={g.gold_id}>Doc {i + 1}: <strong>{r ? `${r.matched_count}/${r.expected_count}` : '—'}</strong> {r?.passed ? '✓ Geçti' : '✗ Geçemedi'}</p>
        })}
        <p>Anot. geçen: {passedDocs} / 3 (gerekli: 2)</p>
        <p className="mt-2 font-semibold">Overall: GEÇEMEDİ</p>
      </div>
      <div className="flex gap-2">
        <Button onClick={onRetry}>Tekrar Dene</Button>
        <Button onClick={onBackToHelp} variant="ghost">← Kılavuza dön</Button>
      </div>
    </section>
  )
}
```

- [ ] **Step 3: Run + commit**

```bash
cd frontend && npx vitest run src/components/training/SummaryStep.test.tsx
git add frontend/src/components/training/SummaryStep.tsx frontend/src/components/training/SummaryStep.test.tsx
git commit -m "feat(paket-16c): SummaryStep (pass/fail/degraded)

Auth.user.has_passed_training is single truth source. DEGRADED hides
breakdown when restore was corrupt. Spec §8.7, Codex-2 BROKEN-A.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 18: LockedOutScreen + PendingStartBanner

**Files:**
- Create: `frontend/src/components/training/LockedOutScreen.tsx` + test
- Create: `frontend/src/components/training/PendingStartBanner.tsx` + test

- [ ] **Step 1: Tests**

```tsx
// frontend/src/components/training/LockedOutScreen.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LockedOutScreen } from './LockedOutScreen'

describe('LockedOutScreen', () => {
  it('renders explainer + admin email', () => {
    render(<LockedOutScreen onLogout={vi.fn()} onGoToHelp={vi.fn()} />)
    expect(screen.getByText(/maksimum deneme sayısına ulaşıldı/i)).toBeInTheDocument()
    expect(screen.getByText(/team@example\.com/i)).toBeInTheDocument()
  })

  it('Çıkış yap → onLogout', async () => {
    const user = userEvent.setup()
    const onLogout = vi.fn()
    render(<LockedOutScreen onLogout={onLogout} onGoToHelp={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /çıkış yap/i }))
    expect(onLogout).toHaveBeenCalledOnce()
  })

  it('Yardımı incele → onGoToHelp', async () => {
    const user = userEvent.setup()
    const onGoToHelp = vi.fn()
    render(<LockedOutScreen onLogout={vi.fn()} onGoToHelp={onGoToHelp} />)
    await user.click(screen.getByRole('button', { name: /yardımı incele/i }))
    expect(onGoToHelp).toHaveBeenCalledOnce()
  })
})
```

```tsx
// frontend/src/components/training/PendingStartBanner.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PendingStartBanner } from './PendingStartBanner'

describe('PendingStartBanner', () => {
  it('renders warning copy', () => {
    render(<PendingStartBanner onDismiss={vi.fn()} onStartNew={vi.fn()} />)
    expect(screen.getByText(/önceki başlatma yarıda kaldı/i)).toBeInTheDocument()
  })

  it('Anladım, kapat → onDismiss', async () => {
    const user = userEvent.setup()
    const onDismiss = vi.fn()
    render(<PendingStartBanner onDismiss={onDismiss} onStartNew={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /anladım, kapat/i }))
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('Yeni denemeyi başlat → onStartNew', async () => {
    const user = userEvent.setup()
    const onStartNew = vi.fn()
    render(<PendingStartBanner onDismiss={vi.fn()} onStartNew={onStartNew} />)
    await user.click(screen.getByRole('button', { name: /yeni denemeyi başlat/i }))
    expect(onStartNew).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Implementations**

```tsx
// frontend/src/components/training/LockedOutScreen.tsx
import { Button } from '@/components/ui/button'

interface LockedOutScreenProps {
  onLogout: () => void
  onGoToHelp: () => void
}

export function LockedOutScreen({ onLogout, onGoToHelp }: LockedOutScreenProps) {
  return (
    <section role="alert" aria-labelledby="locked-out-heading" className="mx-auto max-w-2xl space-y-4 rounded-md border border-destructive bg-destructive/5 p-6">
      <h2 id="locked-out-heading" className="text-xl font-semibold">Maksimum deneme sayısına ulaşıldı</h2>
      <p className="text-sm">Eğitimi geçemedin. Hesabının sıfırlanması için bir yöneticiyle iletişime geç.</p>
      <p className="text-sm">İletişim: <a href="mailto:team@example.com" className="underline">team@example.com</a></p>
      <div className="flex gap-2">
        <Button onClick={onGoToHelp} variant="outline">Yardımı incele</Button>
        <Button onClick={onLogout} variant="ghost">Çıkış yap</Button>
      </div>
    </section>
  )
}
```

```tsx
// frontend/src/components/training/PendingStartBanner.tsx
import { Button } from '@/components/ui/button'

interface PendingStartBannerProps {
  onDismiss: () => void
  onStartNew: () => void
}

export function PendingStartBanner({ onDismiss, onStartNew }: PendingStartBannerProps) {
  return (
    <div role="alert" className="mx-auto max-w-2xl space-y-3 rounded-md border border-amber-500 bg-amber-50 p-4 dark:bg-amber-950/20">
      <p className="font-medium">⚠ Önceki başlatma yarıda kaldı</p>
      <p className="text-sm">Bir deneme harcanmış olabilir.</p>
      <div className="flex gap-2">
        <Button onClick={onStartNew} size="sm">Yeni denemeyi başlat</Button>
        <Button onClick={onDismiss} variant="ghost" size="sm">Anladım, kapat</Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Run + commit**

```bash
cd frontend && npx vitest run src/components/training/LockedOutScreen.test.tsx src/components/training/PendingStartBanner.test.tsx
git add frontend/src/components/training/LockedOutScreen.tsx frontend/src/components/training/LockedOutScreen.test.tsx frontend/src/components/training/PendingStartBanner.tsx frontend/src/components/training/PendingStartBanner.test.tsx
git commit -m "feat(paket-16c): LockedOut + PendingStartBanner

LockedOutScreen for 3-fail dest with static admin email. PendingStartBanner
for crash between /start + persist. Spec §8.3, §8.7.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 19: routes/Training.tsx + integration tests

**Files:**
- Modify: `frontend/src/routes/Training.tsx` (replace 16a STUB)
- Create: `frontend/src/routes/Training.test.tsx`

- [ ] **Step 1: Implement Training.tsx (replace STUB)**

Overwrite `frontend/src/routes/Training.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/authStore'
import { useTrainingStore } from '@/stores/trainingStore'
import { useBeforeUnload } from '@/hooks/useBeforeUnload'
import {
  useTrainingStartMutation, useQuizSubmitMutation, useAnnotateSubmitMutation,
  PENDING_START_SENTINEL_KEY,
} from '@/api/queries/training'
import { useLogoutMutation } from '@/api/queries/auth'
import { refreshAuth } from '@/lib/refreshAuth'
import { submitWithRecovery, AbortAdvance } from '@/lib/trainingRecovery'
import { is403LockedOut, is409AlreadyPassed } from '@/lib/apiError'
import { TrainingProgress } from '@/components/training/TrainingProgress'
import { StartScreen } from '@/components/training/StartScreen'
import { QuizStep } from '@/components/training/QuizStep'
import { AnnotateStep } from '@/components/training/AnnotateStep'
import { SummaryStep } from '@/components/training/SummaryStep'
import { LockedOutScreen } from '@/components/training/LockedOutScreen'
import { PendingStartBanner } from '@/components/training/PendingStartBanner'
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

export function Training() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const step = useTrainingStore((s) => s.step)
  const docIndex = useTrainingStore((s) => s.docIndex)
  const attemptId = useTrainingStore((s) => s.attemptId)
  const hydrate = useTrainingStore((s) => s.hydrate)
  const recordQuizResult = useTrainingStore((s) => s.recordQuizResult)
  const recordDocResult = useTrainingStore((s) => s.recordDocResult)
  const advanceDoc = useTrainingStore((s) => s.advanceDoc)
  const setStep = useTrainingStore((s) => s.setStep)
  const clear = useTrainingStore((s) => s.clear)

  const startMut = useTrainingStartMutation()
  const quizMut = useQuizSubmitMutation()
  const annMut = useAnnotateSubmitMutation()
  const logoutMut = useLogoutMutation()

  const [pendingSentinelVisible, setPendingSentinelVisible] = useState(false)

  useEffect(() => {
    if (user?.has_passed_training && step !== 'summary' && step !== 'locked-out') {
      navigate('/', { replace: true })
    }
  }, [user, step, navigate])

  useEffect(() => {
    if (step === 'idle' && sessionStorage.getItem(PENDING_START_SENTINEL_KEY)) {
      setPendingSentinelVisible(true)
    }
  }, [step])

  useBeforeUnload(
    (step === 'quiz' || step === 'doc') && !quizMut.isPending && !annMut.isPending,
    'Eğitime devam ediyorsun, sayfayı kapatma.',
  )

  const handleStart = async () => {
    try {
      const startResp = await startMut.mutateAsync()
      hydrate(startResp)
      sessionStorage.removeItem(PENDING_START_SENTINEL_KEY)
      setPendingSentinelVisible(false)
    } catch (err) {
      if (is409AlreadyPassed(err)) {
        await refreshAuth(qc)
        navigate('/', { replace: true })
        return
      }
      if (is403LockedOut(err)) {
        setStep('locked-out')
        return
      }
      toast.error('Eğitim başlatılamadı, tekrar dene.')
    }
  }

  const handleQuizSubmit = async (answers: Record<string, number>) => {
    if (attemptId === null) return
    try {
      const result = await submitWithRecovery({
        submit: () => quizMut.mutateAsync({ attempt_id: attemptId, answers }),
        key: { kind: 'quiz' },
        qc,
      })
      recordQuizResult(result)
    } catch (err) {
      if (err instanceof AbortAdvance) return
      toast.error('Cevap gönderilemedi, tekrar dene.')
    }
  }

  const handleDocSubmit = async (goldId: string, references: ReferenceItem[]) => {
    if (attemptId === null) return
    try {
      const result = await submitWithRecovery({
        submit: () => annMut.mutateAsync({ attempt_id: attemptId, gold_id: goldId, references }),
        key: { kind: 'doc', goldId },
        qc,
      })
      recordDocResult(goldId, result)
    } catch (err) {
      if (err instanceof AbortAdvance) return
      toast.error('Anotasyon gönderilemedi, tekrar dene.')
    }
  }

  const handleDocAdvance = async () => {
    if (docIndex < 2) {
      advanceDoc()
      return
    }
    try {
      await refreshAuth(qc)
    } catch {
      useTrainingStore.setState({ degraded: true })
    }
    setStep('summary')
  }

  const handleRetry = async () => {
    clear()
    await handleStart()
  }

  const handleLogout = () => {
    clear()
    logoutMut.mutate()
  }

  const handleGoHelp = () => navigate('/help', { replace: false })
  const handleAnnotate = () => { clear(); navigate('/', { replace: true }) }
  const handleDismissPending = () => {
    sessionStorage.removeItem(PENDING_START_SENTINEL_KEY)
    setPendingSentinelVisible(false)
  }

  return (
    <div className="mx-auto max-w-3xl p-6">
      <h1 className="mb-4 text-2xl font-semibold">Eğitim</h1>
      {pendingSentinelVisible && step === 'idle' && (
        <div className="mb-6">
          <PendingStartBanner onDismiss={handleDismissPending} onStartNew={handleStart} />
        </div>
      )}
      {step !== 'idle' && step !== 'locked-out' && (
        <TrainingProgress step={step} docIndex={docIndex} />
      )}
      {step === 'idle' && (
        <StartScreen onStart={handleStart} onBackToHelp={handleGoHelp} isPending={startMut.isPending} />
      )}
      {step === 'quiz' && <QuizStep onSubmit={handleQuizSubmit} isSubmitting={quizMut.isPending} />}
      {step === 'doc' && (
        <AnnotateStep onSubmit={handleDocSubmit} onAdvance={handleDocAdvance} isSubmitting={annMut.isPending} />
      )}
      {step === 'summary' && (
        <SummaryStep onAnnotate={handleAnnotate} onRetry={handleRetry} onBackToHelp={handleGoHelp} />
      )}
      {step === 'locked-out' && (
        <LockedOutScreen onLogout={handleLogout} onGoToHelp={handleGoHelp} />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Integration tests**

Create `frontend/src/routes/Training.test.tsx`. **The implementer should write 8 integration scenarios per spec §15.2, each as a separate `it()` block within a top-level `describe('Training route')`:**

1. **Happy path PASS** — full wizard with `/auth/me` returning `has_passed_training=true` after 3rd doc → SummaryPass → click "Anotasyona Başla" → screen.findByTestId('route-root')
2. **Fail path** — `mockAnnotateSubmitFail` → SummaryFail with "Tekrar Dene" button visible
3. **Locked out** — `mockTrainingStartLockedOut` → click "Başla" → LockedOutScreen
4. **Already-passed redirect on mount** — auth `has_passed_training=true` → immediate `screen.findByTestId('route-root')`
5. **409 already_passed on /start** — `mockTrainingStartAlreadyPassed` → after refreshAuth (mock returns updated user) → route-root
6. **F5 resume mid-quiz** — sessionStorage pre-seeded `step:'quiz', quizAnswers:{q01:1}` → mount → second radio of first question is checked
7. **409 quiz idempotency** — sessionStorage pre-seeded with `quizResult:{score:5,total:5}` + `mockQuizSubmitAlreadySubmitted` → submit quiz → recovery returns cached → result card shows 5/5
8. **Corrupt restore** — sessionStorage seeded with invalid shape (`step:'invalid-step'`) → mount → StartScreen visible (validation wiped storage)
9. **Pending sentinel** — `sessionStorage.setItem('training-start-pending', ...)` + empty store → mount → PendingStartBanner visible

For each scenario, the test must:
- Reset `sessionStorage` and `useTrainingStore` in `beforeEach`
- Set `useAuthStore` with appropriate user
- Apply MSW overrides via `server.use(...)` before render
- Use `renderWithProviders(<Training />, { initialEntries: ['/training'] })`
- Drive via `userEvent` (await each click) and assert via `screen.findBy*` / `waitFor`

Full reference implementation: see `Training.test.tsx` in the 16b precedent (`frontend/src/routes/AnnotateDoc.test.tsx`) for the renderWithProviders pattern. Adapt the structure here using the factories from `msw-handlers.ts` added in T7 and T12.

- [ ] **Step 3: Run integration tests, verify pass**

Run: `cd frontend && npx vitest run src/routes/Training.test.tsx`
Expected: all 8-9 scenarios pass.

- [ ] **Step 4: Full suite gate + coverage**

Run:
```bash
cd frontend && npm run test:run && npm run test:coverage
```
Expected: all pass; coverage ≥80% on all 4 metrics.

If coverage falls below threshold on any metric, add targeted tests for uncovered branches before proceeding. Common gaps: error toast paths, edge cases in `validateRestoredShape`, degraded summary keyboard flow.

- [ ] **Step 5: Typecheck + lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/Training.tsx frontend/src/routes/Training.test.tsx
git commit -m "feat(paket-16c): Training route + integration

Wires all step components + recovery + refreshAuth + beforeunload.
8 integration scenarios. Spec §6, §8.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 20: Manual E2E + acceptance + tag

- [ ] **Step 1: Full automated suite green**

```bash
cd frontend && npm run typecheck && npm run lint && npm run test:coverage
```
Expected: all green, coverage ≥80%.

- [ ] **Step 2: Verify no forbidden imports + zero 16b regression**

```bash
grep -rn "rehype-raw\|rehypeRaw" frontend/src/ frontend/package.json || echo "CLEAN"
find frontend/src/lib -name "validateReferences*" || echo "CLEAN"
git diff paket-16b-annotate-workflow -- frontend/src/components/annotation/ReferenceCard.tsx frontend/src/components/annotation/ReferencePanel.tsx
```
Expected: `CLEAN`, `CLEAN`, no diff.

- [ ] **Step 3: Start backend + frontend**

```bash
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
# Backend (in own terminal): cd to repo root and run uvicorn
DATA_DIR=./deneme-dev/data DISABLE_SPA_MOUNT=1 .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload &
# Frontend
cd frontend && npm run dev &
```

Wait for both ready signals.

- [ ] **Step 4: Manual E2E (spec §15.4 — all 15 steps)**

Create a fresh user with `has_seen_manual=0, has_passed_training=0`. Walk all 15 steps from spec §15.4. Document PASS/FAIL per step. If any FAIL: fix in a follow-up commit before tagging.

- [ ] **Step 5: SPA dev assets regression check (from 16b fix)**

```bash
curl -s http://127.0.0.1:5173/docs/test | grep -o 'src="/[^"]*"' | head -3
```
Expected: includes `/@vite/client` and `/src/main.tsx`, NOT prebuilt hashed assets.

- [ ] **Step 6: Tag**

```bash
git tag paket-16c-onboarding
git log --oneline -1
```

- [ ] **Step 7: Final commit**

```bash
git commit --allow-empty -m "chore(paket-16c): tag paket-16c-onboarding

20 tasks. Manual E2E all PASS. Coverage ≥80%. ReferenceCard/Panel 16b
byte-identical. rehype-raw absent. No shared validateReferences.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

### Spec coverage

| Spec § | Task(s) |
|---|---|
| §1 Goal & Scope | T10, T19 |
| §2 Tech Stack Additions | T1 |
| §3 Backend Contract | locked (no FE work) |
| §4 D1-D7 decisions | T9 (D1), T10 (D2), T19 (D3,D4), T16 (D5), T15+T16 (D6), T17 (D7) |
| §5 Folder Structure | all tasks |
| §6 Routing & Gates | T19 |
| §7 Help Viewer | T7-T10 |
| §7.2 Markdown security + ban rehype-raw | T8, T20 (verification) |
| §8.1 State machine | T11+T19 |
| §8.2 Store + validateRestoredShape | T11 |
| §8.3 Atomic start-write + sentinel | T12, T18, T19 |
| §8.4 Trust model + 409 ack | T6, T11 |
| §8.5 beforeunload | T4, T19 |
| §8.6 submitWithRecovery + AbortAdvance | T6 |
| §8.7 Per-step components | T13-T18 |
| §8.8 Hooks | T7, T9 (me), T12 |
| §9 ReferenceCard reuse (untouched) | T16 + T20 verification |
| §10 Training-only validation | T16 |
| §11 Type guards + Zod | T2, T5 |
| §12 refreshAuth | T3 |
| §13 A11y | T13, T15, T16, T17 |
| §14 Codex findings (all 15) | distributed; mapped per finding in respective task |
| §15 Tests | every task has TDD pair; T19 integration |
| §16 Acceptance criteria | T20 |

### Placeholder scan

Manual sweep of generated plan against the No-Placeholders rules: no TBD / TODO / FIXME / "fill in details" / "Add appropriate error handling" patterns found. Each step has either explicit code, an explicit command, or an explicit scenario list with reference precedent.

### Type consistency

- `TrainingStep` exported from T11 → consumed in T13.
- `StartResponse`, `QuizSubmitResponse`, `AnnotateSubmitResponse`, `HelpResponse`, `Question`, `GoldDoc` types inferred from Zod schemas in T5 → consumed in T7, T11, T12.
- `ReferenceItem` from generated openapi types → consumed in T11, T16.
- `submitWithRecovery`, `AbortAdvance`, `RecoveryKey` from T6 → consumed in T19.
- `PENDING_START_SENTINEL_KEY` exported from T12 → consumed in T19.
- `refreshAuth(qc)` from T3 → consumed in T10, T19.
- API endpoint paths consistent (`/api/help`, `/api/me/seen-manual`, `/api/training/start`, `/api/training/quiz/submit`, `/api/training/annotate/submit`).
- Snake_case (`gold_id`, `attempt_id`) preserved at API boundary; camelCase (`goldId`, `attemptId`) used in store/component layer.

### Notes for subagent dispatch

- Dispatch each task to a fresh subagent with: this plan section + spec link (`docs/superpowers/specs/2026-05-11-paket-16c-onboarding-design.md` at commit `c5aee88`) + 16a tag (`paket-16a-frontend-foundation`) + 16b tag (`paket-16b-annotate-workflow`).
- Foundation tasks T2-T6, T8-T9, T13-T18 are mechanical — fast model.
- T11 (store), T12 (mutations + handlers), T19 (route + integration) are integration points — standard model or higher.
- After every task, run spec-compliance review then code-quality review per skill `superpowers:subagent-driven-development` workflow.

---
