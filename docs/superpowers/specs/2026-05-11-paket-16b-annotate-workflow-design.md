# Paket 16b — Frontend Annotate Workflow Design

**Status:** Approved (brainstorming complete, Codex adversarial review applied)
**Builds on:** Paket 16a (tag `paket-16a-frontend-foundation`, commit `0f4abc0`)
**Backend prerequisites:** Paket 4 (documents), 5 (annotations chain), 6 (shuffle feed), 7 (SSE), locks subsystem — all already in place.

---

## 1. Problem & Goal

16a delivered a foundation (auth, routing, gates, test infra, API client). It exposed STUB routes for the actual annotation work. 16b builds the **core annotation experience**: a 3-column workspace where annotators browse a per-user-per-day shuffled feed, read tax-court decisions, manage structured legal references (kanun_no/madde/source_text), auto-save drafts, and commit annotations with optimistic concurrency via the existing lock subsystem.

The goal is a **high-throughput, single-paket** annotate workflow: from "user logs in" to "user has saved 30 docs in 30 minutes" without leaving the screen. Lock contention is real (30 concurrent users) so eager lock acquisition + SSE-driven badge updates keep the team coordinated.

This paket is the user-facing payoff of all the backend work done in paketler 4-7.

---

## 2. Scope (locked)

**IN scope (16b):**

- **AnnotateLayout** — 3-column resizable shell, owns DocList + tab strip + Outlet
- **DocList** — virtual scroll (react-virtual), 3 tabs (new/review/verified), verbose 4-line cards, infinite-load pagination
- **DocViewer** — full document text display (read-only)
- **ReferencePanel** — inline card list of references, "+ Yeni Referans" appends, footer with "Atla" (skip) and "Sakla" (save) buttons
- **ReferenceCard** — 6-field inline form per reference: kanun_no, kanun_ad, madde, fıkra, bent, source_text
- **LockConflictModal** — shown when POST /acquire returns 409
- **Eager lock acquisition** with heartbeat (30s) and best-effort release on navigation/unmount
- **Draft auto-save** debounced 2s, full-body replacement, silent restore on doc load
- **SSE subscription** for `lock_acquired` and `lock_released` events only (badge updates + current-doc lock theft handling)
- **Save → auto-advance** to next doc in current tab (`replace: true` history)
- **URL-driven routing** — `/` (empty editor) and `/docs/:docId` (full editor)
- **LockBadge + AttributionLabel** — small reusable presentation components
- **~14-18 atomic commits**, ~22 new source files, ~20 test files

**OUT of scope (deferred to 16c-f + later paketler):**

- Annotation chain history viewer (the "kim ne zaman ne değiştirdi" timeline) → 16d/16e
- `annotation_saved` / `annotation_completed` SSE events → 16d (used by gamification UI for "Ahmet 30 saniye önce kaydetti" toasts)
- `speed_warning` / `char_limit_warning` toast notifications → 16d
- Gamification top bar (XP, streak, daily progress, online avatars) → 16d
- Onboarding pages (Help markdown viewer, Training quiz) → 16c
- Admin panel (Users, AuditLog, Settings, Locks, Force-release UI) → 16e
- Docker multi-stage reconcile → 16f
- Annotation skip flow detail (the backend POST /skip already releases lock; UI is just a button call) → IN scope but minimal
- Annotation `is_completed` toggle (Tamamlandı checkmark) → minimal IN scope (single checkbox in ReferencePanel footer, optional v1)
- Bulk operations, filtering by date/vergi_turu, search → later
- Keyboard shortcuts (Ctrl+Enter to save, etc.) → minimal IN scope (Ctrl+Enter save)
- Reference field autocomplete (kanun_no → kanun_ad lookup) → later
- Pagination beyond infinite scroll (page jumping, sorting toggles) → later

---

## 3. Locked Decisions

### From user brainstorming session

| # | Decision | Value |
|---|---|---|
| 1 | Scope | Single paket — full annotate workflow |
| 2 | Lock UX | **Eager** — POST /acquire on `/docs/:docId` route mount |
| 3 | Reference panel layout | **Inline card list** — each ref a card with 6 fields visible, "+ Yeni Referans" appends |
| 4 | SSE scope | **Lock events only** (`lock_acquired`, `lock_released`); other events deferred |
| 5 | Draft load precedence | **Silent restore** — draft > annotation > empty list |
| 6 | DocList row | **Verbose 4-line card** — sayi+tarih+vergi+status / konu / editor history / lock badge |
| 7 | Post-save flow | **Auto-advance** — POST annotation → DELETE draft → release lock → navigate next in feed, `replace: true` |
| 8 | Routing | **URL-driven** — `/docs/:docId`, auto-advance uses `replace: true` (no history pollution) |

### Codex adversarial review fixes (18 findings applied)

Applied to the data flow in §6:

**Broken-tier (6):**
- Saving while debounced PUT /drafts in flight could resurrect deleted drafts → guard with `isSavingRef` + AbortController; abort in-flight draft PUT before annotation save (B1)
- Heartbeat interval could survive route unmount if acquire resolves after cleanup → check `cancelledRef` after acquire returns, store interval handle in ref, guarantee clear (B2)
- `pickNextInFeed` could navigate to `undefined` → returns explicit union `{type:'next', id} | {type:'done'} | {type:'empty'}` (B3)
- Linear save chain leaves lock held if draft delete fails → wrap release in `finally`; treat draft delete as recoverable cleanup debt (B4)
- EventSource cleanup not explicit → return cleanup from useEffect, `es.close()` (B5)
- Heartbeat 404 (lock lost mid-edit) not handled → on 404, stop interval, set `status='lost'`, show "Kilit kaybedildi" UI, navigate('/') (B6)

**Fragile-tier (12):**
- SSE race during acquire (could kick self out) → track `acquiring` flag, ignore current-doc events until acquire resolves (F1)
- No SSE reconnect/error strategy → `onerror` invalidates feed; default browser reconnect trusted (F2)
- `pickNextInFeed` ignores pagination → if at end of loaded page, fetch next page before declaring done (F3)
- Save invalidations race feed snapshot → await refetch before picking next (F4)
- Release failure has weak UX → retry once, then non-blocking warning toast (F5)
- Draft error states undocumented → useDraft tracks `idle|saving|saved|error`, surfaced in UI footer (F6)
- Overlapping PUT /drafts could overwrite newer → AbortController abort superseded request, serialize with revision counter (F7)
- Same-user 409 in second tab → check `detail.by_user_id === currentUser.id`, show "Başka sekmede açık" UX instead of "X kullanıcı düzenliyor" (F8)
- Missing AbortController on cancellable requests → all client.* calls use `{ signal }` (F9)
- `keepalive` release is best-effort → design assumes 90s TTL is correctness floor; release-on-unload is opportunistic (F10)
- Unstable effect deps could duplicate lock loops → useLock deps are `[docId]` only; callbacks ref-stored (F11)
- Late draft GET overwrites local edits → useDraft initializes form once, gated by `hydrated` flag (F12)

---

## 4. Folder Structure

### New directory layout (16b additions)

```
frontend/src/
├── routes/
│   ├── Annotate.tsx                # MODIFY: 16a STUB → "EmptyEditor" placeholder
│   ├── AnnotateLayout.tsx          # NEW: 3-column shell + tab strip + Outlet
│   └── AnnotateDoc.tsx             # NEW: /docs/:docId editor
├── components/
│   ├── annotation/                 # NEW directory
│   │   ├── DocList.tsx
│   │   ├── DocListItem.tsx
│   │   ├── DocViewer.tsx
│   │   ├── ReferencePanel.tsx
│   │   ├── ReferenceCard.tsx
│   │   ├── AttributionLabel.tsx
│   │   ├── LockBadge.tsx
│   │   └── TabStrip.tsx            # 3 tab pills (new/review/verified)
│   ├── modals/                     # NEW directory
│   │   └── LockConflictModal.tsx
│   ├── shell/
│   │   ├── ResizableColumns.tsx    # NEW: 3-pane splitter (custom, ~120 lines)
│   │   └── AppShell.tsx            # KEEP: 16a version is fine; AnnotateLayout owns tab strip
│   └── ui/                         # NEW shadcn additions: tabs, dialog, tooltip, badge, scroll-area, textarea, separator
├── hooks/
│   ├── useFeed.ts                  # tab-based useInfiniteQuery + status filters
│   ├── useDoc.ts                   # GET /documents/{id}
│   ├── useAnnotation.ts            # GET /docs/{id}/annotation
│   ├── useDraft.ts                 # load + debounced PUT + DELETE + AbortController guard
│   ├── useLock.ts                  # acquire + heartbeat + release + 404 handler
│   ├── useReferencesState.ts       # local refs CRUD via useReducer
│   ├── useSSE.ts                   # EventSource + invalidation + lock theft handler
│   └── useNextDocId.ts             # composes feed pages + pickNextInFeed
├── api/queries/
│   ├── feed.ts                     # useFeed, feedKeys
│   ├── documents.ts                # useDoc, docKeys
│   ├── annotations.ts              # useAnnotation, useSaveAnnotation, useSkip, useToggleComplete
│   ├── drafts.ts                   # useDraftQuery, usePutDraft, useDeleteDraft
│   └── locks.ts                    # useAcquireLock, useHeartbeat, useReleaseLock
├── lib/
│   ├── formatters.ts               # relative date "2 saat önce" (date-fns + tr locale)
│   └── nextDocId.ts                # pure helper with explicit union return type
├── stores/
│   └── annotateStore.ts            # current tab (persisted to sessionStorage)
└── test/
    └── msw-handlers/
        └── annotate.ts             # NEW: handlers for feed/doc/annotation/draft/lock endpoints
```

**Numerical estimate:** 22 new source files + 20 test files + 1 modify (Annotate.tsx) + 1 modify (App.tsx route tree) + 1 modify (msw-handlers.ts) ≈ **~45 files touched**.

### shadcn additions (T2 of plan)

```bash
npx shadcn@latest add tabs dialog tooltip badge scroll-area textarea separator
```

---

## 5. Route Tree (16a → 16b)

```tsx
// 16a (current, simplified)
<Route element={<AppShell />}>
  <Route path="/" element={<Annotate />} />    // STUB
  <Route path="/me" element={<Profile />} />
</Route>

// 16b
<Route element={<AppShell />}>
  <Route element={<AnnotateLayout />}>         // 3-col shell + DocList
    <Route path="/" element={<EmptyEditor />}/>
    <Route path="/docs/:docId" element={<AnnotateDoc />}/>
  </Route>
  <Route path="/me" element={<Profile />} />
</Route>
```

**Why `AnnotateLayout` as a layout route:**
- Sol kolon (DocList) her doc seçiminde unmount olmaz → virtual scroll state korunur, scroll pozisyonu kaybolmaz
- Tab seçimi `AnnotateLayout`'a aittir; URL'e yansır mı? → **HAYIR.** Tab seçimi `annotateStore` (sessionStorage persist). Yeni sekme/refresh açıldığında sessionStorage'dan restore. Bu, kullanıcının çalışma sekmesini korur ama URL'i temiz tutar.
- SSE subscription da `AnnotateLayout`'da → DocList her zaman canlı.
- `AnnotateDoc` mount/unmount → lock lifecycle. Doc geçişi `<Outlet />` swap, çok hızlı.

---

## 6. Data Flow (Codex-fix-applied)

### 6.1 `useLock` — final, post-adversarial

```ts
// hooks/useLock.ts
const HEARTBEAT_MS = 30_000        // 3x safety margin vs 90s server TTL
const HEARTBEAT_RETRY_LIMIT = 2    // attempts before declaring 'lost'

export type LockStatus = 'idle' | 'acquiring' | 'held' | 'conflict' | 'lost' | 'released'

export interface LockSnapshot {
  status: LockStatus
  info: LockInfo | null
  conflict: LockConflictDetail | null
  /** Last known username holding the lock when status==='conflict' or 'lost'. */
  conflictUsername: string | null
  /** True for the same-user-cross-tab case (B+F8 fix). */
  conflictIsSameUser: boolean
}

export function useLock(docId: string) {
  const [snapshot, setSnapshot] = useState<LockSnapshot>({
    status: 'idle', info: null, conflict: null,
    conflictUsername: null, conflictIsSameUser: false,
  })
  const cancelledRef = useRef(false)
  const heartbeatTimerRef = useRef<number | null>(null)
  const heartbeatFailuresRef = useRef(0)
  const acquireAbortRef = useRef<AbortController | null>(null)
  const myUserId = useAuthStore((s) => s.user?.id ?? null)

  // Acquire + start heartbeat
  useEffect(() => {
    cancelledRef.current = false
    heartbeatFailuresRef.current = 0
    const acquireCtrl = new AbortController()
    acquireAbortRef.current = acquireCtrl
    setSnapshot((s) => ({ ...s, status: 'acquiring' }))

    ;(async () => {
      try {
        const result = await client.POST('/api/locks/{document_id}/acquire', {
          params: { path: { document_id: docId } },
          signal: acquireCtrl.signal,
        })
        if (cancelledRef.current) return  // B2 fix: discard if unmounted

        if (result.error !== undefined) {
          if (result.response.status === 409) {
            const detail = (result.error as { detail?: LockConflictDetail }).detail
            const same = detail?.by_user_id === myUserId
            setSnapshot({
              status: 'conflict',
              info: null,
              conflict: detail ?? null,
              conflictUsername: detail?.by_username ?? null,
              conflictIsSameUser: same,                       // F8 fix
            })
            return
          }
          throw new ApiError(
            result.response.status,
            String(result.response.status),
            'Kilit alınamadı',
            result.error,
          )
        }

        setSnapshot({
          status: 'held',
          info: result.data!,
          conflict: null,
          conflictUsername: null,
          conflictIsSameUser: false,
        })

        // Heartbeat loop (B2: only starts if not cancelled)
        if (!cancelledRef.current) {
          heartbeatTimerRef.current = window.setInterval(async () => {
            if (cancelledRef.current) return
            try {
              const hb = await client.POST('/api/locks/{document_id}/heartbeat', {
                params: { path: { document_id: docId } },
              })
              if (hb.error !== undefined) {
                if (hb.response.status === 404) {
                  // B6 fix: we lost the lock (admin force-release or sweep)
                  heartbeatFailuresRef.current = HEARTBEAT_RETRY_LIMIT
                } else {
                  heartbeatFailuresRef.current += 1
                }
              } else {
                heartbeatFailuresRef.current = 0
              }
            } catch {
              heartbeatFailuresRef.current += 1
            }
            if (heartbeatFailuresRef.current >= HEARTBEAT_RETRY_LIMIT) {
              if (heartbeatTimerRef.current) {
                clearInterval(heartbeatTimerRef.current)
                heartbeatTimerRef.current = null
              }
              setSnapshot((s) => ({ ...s, status: 'lost' }))
            }
          }, HEARTBEAT_MS)
        }
      } catch (e) {
        if (cancelledRef.current) return
        if ((e as { name?: string })?.name === 'AbortError') return
        setSnapshot((s) => ({ ...s, status: 'idle' }))
      }
    })()

    return () => {
      cancelledRef.current = true
      acquireAbortRef.current?.abort()
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current)
        heartbeatTimerRef.current = null
      }
      // F10: keepalive release is best-effort; correctness backstop is 90s TTL
      try {
        fetch(`/api/locks/${encodeURIComponent(docId)}/release`, {
          method: 'POST',
          credentials: 'include',
          keepalive: true,
        }).catch(() => {})
      } catch { /* no-op */ }
    }
  }, [docId, myUserId])   // F11: stable primitive deps only

  // Explicit release (used by save)
  const release = useCallback(async () => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current)
      heartbeatTimerRef.current = null
    }
    try {
      await client.POST('/api/locks/{document_id}/release', {
        params: { path: { document_id: docId } },
      })
    } catch {
      // F5: best-effort; surface non-blocking warning via caller's toast
      throw new Error('release_failed')
    }
    setSnapshot({
      status: 'released',
      info: null,
      conflict: null,
      conflictUsername: null,
      conflictIsSameUser: false,
    })
  }, [docId])

  return { ...snapshot, release }
}
```

### 6.2 `useDraft` — final, post-adversarial

```ts
// hooks/useDraft.ts
const DRAFT_DEBOUNCE_MS = 2_000

export type DraftSaveStatus = 'idle' | 'saving' | 'saved' | 'error'  // F6

export function useDraft(docId: string) {
  const qc = useQueryClient()
  const [saveStatus, setSaveStatus] = useState<DraftSaveStatus>('idle')
  const inFlightAbortRef = useRef<AbortController | null>(null)
  const isSavingAnnotationRef = useRef(false)         // B1: blocks PUT during commit
  const revRef = useRef(0)                            // F7: monotonic revision

  // Load existing draft once. 404 → null. F12: only initial fetch hydrates;
  // useReferencesState gates its initial-load on this query's resolved state.
  const draftQuery = useQuery({
    queryKey: ['drafts', docId],
    queryFn: async ({ signal }) => {
      const r = await client.GET('/api/drafts/{document_id}', {
        params: { path: { document_id: docId } },
        signal,
      })
      if (r.response.status === 404) return null
      return unwrap(r) as { references: ReferenceItem[] }
    },
    retry: false,
    staleTime: Infinity,
  })

  // Internal PUT — used by debounced wrapper + by lockBeforeSave()
  const putRaw = async (refs: ReferenceItem[], myRev: number) => {
    // F7: cancel any older in-flight PUT
    inFlightAbortRef.current?.abort()
    const ctrl = new AbortController()
    inFlightAbortRef.current = ctrl

    setSaveStatus('saving')
    try {
      const r = await client.PUT('/api/drafts/{document_id}', {
        params: { path: { document_id: docId } },
        body: { references: refs },
        signal: ctrl.signal,
      })
      if (myRev !== revRef.current) {
        // Newer write started; abandon stale response
        return
      }
      if (r.error !== undefined) {
        setSaveStatus('error')
        return
      }
      setSaveStatus('saved')
    } catch (e) {
      if ((e as { name?: string })?.name === 'AbortError') return
      setSaveStatus('error')
    }
  }

  const debouncedSave = useMemo(
    () =>
      debounce((refs: ReferenceItem[]) => {
        if (isSavingAnnotationRef.current) return   // B1: gate during commit
        const myRev = ++revRef.current
        void putRaw(refs, myRev)
      }, DRAFT_DEBOUNCE_MS),
    [docId],  // stable across renders
  )

  // B1: called by handleSave before POST /annotations to block any further writes
  const blockSavesUntilFurtherNotice = useCallback(() => {
    isSavingAnnotationRef.current = true
    debouncedSave.cancel()
    inFlightAbortRef.current?.abort()
  }, [debouncedSave])

  const unblockSaves = useCallback(() => {
    isSavingAnnotationRef.current = false
  }, [])

  const deleteMutation = useMutation({
    mutationFn: async () => {
      const r = await client.DELETE('/api/drafts/{document_id}', {
        params: { path: { document_id: docId } },
      })
      // 404 OK
      if (r.error !== undefined && r.response.status !== 404) {
        throw new ApiError(
          r.response.status, String(r.response.status), 'Draft silinemedi', r.error,
        )
      }
      qc.setQueryData(['drafts', docId], null)
    },
  })

  return {
    draftQuery,
    debouncedSave,
    deleteMutation,
    saveStatus,
    blockSavesUntilFurtherNotice,
    unblockSaves,
  }
}
```

### 6.3 `handleSave` — final, post-adversarial

```ts
// inside AnnotateDoc.tsx
const handleSave = async () => {
  // B1: block all draft writes for the duration of this save
  draft.blockSavesUntilFurtherNotice()

  let saveOK = false
  try {
    // 1. Commit annotation
    await saveAnnotationMutation.mutateAsync({
      document_id: docId,
      references: refs.list,
    })
    saveOK = true
  } catch (err) {
    // ApiError shown inline by mutation.error; user stays on doc, lock still held
    draft.unblockSaves()                                  // allow re-edits
    return
  }

  // 2. Best-effort cleanup wrapped in try blocks (B4 fix)
  let lockReleaseFailed = false
  let draftDeleteFailed = false
  try {
    await draft.deleteMutation.mutateAsync()
  } catch {
    draftDeleteFailed = true
  }
  try {
    await lock.release()
  } catch {
    lockReleaseFailed = true
  }

  // 3. Refetch feed BEFORE picking next (F4 fix)
  await qc.invalidateQueries({ queryKey: ['feed'] })
  await qc.refetchQueries({ queryKey: ['feed', currentTab] })

  // 4. Pick next from refreshed feed (B3 + F3 fix via pickNextInFeed contract)
  const next = await pickNextInFeedAcrossPages({
    qc,
    currentTab,
    currentDocId: docId,
  })

  // 5. Non-blocking warnings for cleanup failures (F5)
  if (lockReleaseFailed) {
    toast.warning('Kilit serbest bırakılamadı; 90 saniye içinde otomatik temizlenir.')
  }
  if (draftDeleteFailed) {
    toast.warning('Taslak silinemedi; bir sonraki düzenlemede üzerine yazılacak.')
  }

  // 6. Navigate
  if (next.type === 'next') {
    navigate(`/docs/${next.id}`, { replace: true })
  } else if (next.type === 'done') {
    toast.success('Bu sekmedeki tüm dokümanlar bitti.')
    navigate('/', { replace: true })
  } else {
    navigate('/', { replace: true })
  }
}
```

### 6.4 `useSSE` — final, post-adversarial

```ts
// hooks/useSSE.ts
export function useSSE(opts: {
  /** Set by AnnotateDoc to suppress kick-out during own acquire (F1). */
  acquiringDocId: string | null
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const meId = useAuthStore((s) => s.user?.id ?? null)
  const acquiringDocIdRef = useRef(opts.acquiringDocId)
  acquiringDocIdRef.current = opts.acquiringDocId

  useEffect(() => {
    let cancelled = false
    let es: EventSource | null = null

    const open = () => {
      es = new EventSource('/api/events')

      es.addEventListener('lock_acquired', (e) => {
        if (cancelled) return
        const data = JSON.parse((e as MessageEvent).data) as {
          document_id: string; by_user_id: number; by_username: string
        }
        qc.invalidateQueries({ queryKey: ['feed'] })

        // F1 fix: don't kick out self while our own acquire is in flight
        if (data.document_id === acquiringDocIdRef.current) return
        if (data.by_user_id === meId) return  // own acquire echo

        const currentDocId = getCurrentDocIdFromUrl()
        if (data.document_id === currentDocId) {
          toast.error(`Bu doküman ${data.by_username} tarafından alındı.`)
          navigate('/', { replace: true })
        }
      })

      es.addEventListener('lock_released', () => {
        if (cancelled) return
        qc.invalidateQueries({ queryKey: ['feed'] })
      })

      es.onerror = () => {
        if (cancelled) return
        // F2: trust browser auto-reconnect; refetch feed on reconnect.
        // EventSource readyState 0 = CONNECTING (auto-reconnect in progress)
        if (es && es.readyState === EventSource.CONNECTING) {
          qc.invalidateQueries({ queryKey: ['feed'] })
        }
      }
    }

    open()

    return () => {
      cancelled = true
      es?.close()        // B5 fix
    }
  }, [qc, navigate, meId])   // F11: stable deps
}

function getCurrentDocIdFromUrl(): string | null {
  const m = window.location.pathname.match(/^\/docs\/([^/?#]+)/)
  return m?.[1] ?? null
}
```

### 6.5 `useReferencesState` (local CRUD via useReducer)

```ts
// hooks/useReferencesState.ts
type Action =
  | { type: 'init'; refs: ReferenceItem[] }
  | { type: 'add' }
  | { type: 'update'; index: number; ref: ReferenceItem }
  | { type: 'remove'; index: number }

const empty = (): ReferenceItem => ({
  kanun_no: null, kanun_ad: null, madde: null, fikra: null, bent: null,
  source_text: '',
})

function reducer(state: ReferenceItem[], action: Action): ReferenceItem[] {
  switch (action.type) {
    case 'init': return action.refs
    case 'add': return [...state, empty()]
    case 'update': {
      const next = state.slice()
      next[action.index] = action.ref
      return next
    }
    case 'remove': return state.filter((_, i) => i !== action.index)
  }
}

export function useReferencesState(opts: {
  draftQueryStatus: 'pending' | 'success' | 'error'
  draftData: { references: ReferenceItem[] } | null
  annotationData: { references: ReferenceItem[] } | null
  onChange: (refs: ReferenceItem[]) => void   // wired to debouncedSave
}) {
  const [refs, dispatch] = useReducer(reducer, [])
  const hydratedRef = useRef(false)              // F12: hydrate once

  useEffect(() => {
    if (hydratedRef.current) return
    if (opts.draftQueryStatus !== 'success') return  // wait for draft load
    const initial =
      opts.draftData?.references ??
      opts.annotationData?.references ??
      []
    dispatch({ type: 'init', refs: initial })
    hydratedRef.current = true
  }, [opts.draftQueryStatus, opts.draftData, opts.annotationData])

  // Propagate every change to debounced save
  useEffect(() => {
    if (!hydratedRef.current) return
    opts.onChange(refs)
  }, [refs, opts])

  return {
    list: refs,
    add: () => dispatch({ type: 'add' }),
    update: (index: number, ref: ReferenceItem) => dispatch({ type: 'update', index, ref }),
    remove: (index: number) => dispatch({ type: 'remove', index }),
    hydrated: hydratedRef.current,
  }
}
```

### 6.6 `useFeed` (paginated)

```ts
// hooks/useFeed.ts (api/queries/feed.ts wires it through)
const PAGE_SIZE = 50

export function useFeed(tab: 'new' | 'review' | 'verified') {
  return useInfiniteQuery({
    queryKey: ['feed', tab],
    queryFn: async ({ pageParam = 0, signal }) =>
      unwrap(await client.GET('/api/feed', {
        params: { query: { tab, limit: PAGE_SIZE, offset: pageParam } },
        signal,
      })),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.flatMap((p) => p.items).length
      return loaded < lastPage.total ? loaded : undefined
    },
    staleTime: 30_000,
  })
}
```

### 6.7 `pickNextInFeedAcrossPages` (B3 + F3 fix)

```ts
// lib/nextDocId.ts
export type NextDocResult =
  | { type: 'next'; id: string }
  | { type: 'done' }      // current tab has no more docs
  | { type: 'empty' }     // feed has zero items

export async function pickNextInFeedAcrossPages(opts: {
  qc: QueryClient
  currentTab: 'new' | 'review' | 'verified'
  currentDocId: string | null
}): Promise<NextDocResult> {
  // Read latest cached infinite-query state
  const state = opts.qc.getQueryState(['feed', opts.currentTab]) as
    | { data?: { pages: { items: FeedItem[]; total: number }[] } }
    | undefined

  if (!state?.data) return { type: 'empty' }

  const allItems = state.data.pages.flatMap((p) => p.items)
  if (allItems.length === 0) return { type: 'empty' }
  const total = state.data.pages[0]?.total ?? allItems.length

  // Find next after current. If not found, return first item (current was in another tab).
  let idx = -1
  if (opts.currentDocId) {
    idx = allItems.findIndex((d) => d.document_id === opts.currentDocId)
  }
  const candidate = idx === -1 ? allItems[0] : allItems[idx + 1]
  if (candidate) return { type: 'next', id: candidate.document_id }

  // At end of loaded items; if more pages exist, fetch the next one
  if (allItems.length < total) {
    // useInfiniteQuery exposes fetchNextPage via the hook; here we trigger
    // a refetch — caller will await invalidateQueries before calling us.
    // After invalidation the loaded list may grow; recurse once.
    await opts.qc.refetchQueries({ queryKey: ['feed', opts.currentTab] })
    const after = opts.qc.getQueryState(['feed', opts.currentTab]) as
      | { data?: { pages: { items: FeedItem[]; total: number }[] } }
      | undefined
    const grown = after?.data?.pages.flatMap((p) => p.items) ?? []
    if (grown.length > allItems.length) {
      return pickNextInFeedAcrossPages({
        qc: opts.qc,
        currentTab: opts.currentTab,
        currentDocId: opts.currentDocId,
      })  // one recursion is safe; grown.length > allItems.length monotonically
    }
  }

  return { type: 'done' }
}
```

---

## 7. Component Contracts

| Component | Props | Responsibility |
|---|---|---|
| `AnnotateLayout` | — | 3-col splitter, tab strip (via TabStrip), mounts DocList (left) + `<Outlet />` (mid+right). Owns `useSSE`. |
| `EmptyEditor` | — | Placeholder: "Listeden bir doküman seçin". Shown at `/`. |
| `AnnotateDoc` | — (reads docId from URL) | Owns `useLock`, `useDoc`, `useAnnotation`, `useDraft`, `useReferencesState`, save handler. Renders DocViewer + ReferencePanel + LockConflictModal. |
| `DocList` | `tab: Tab`, `onSelectDoc: (id: string) => void`, `selectedId: string \| null` | Renders react-virtual'lı liste. Infinite-load trigger at last 10 items. |
| `DocListItem` | `item: FeedItem`, `isSelected: boolean`, `onClick: () => void` | 4-line verbose kart. |
| `TabStrip` | `tab: Tab`, `onChange: (tab: Tab) => void` | shadcn Tabs primitive wrapper. Persists to annotateStore. |
| `DocViewer` | `docId: string` | useDoc(docId) + render pdf_text + metadata header (sayi, tarih, vergi_turu). |
| `ReferencePanel` | `lockHeld: boolean`, `refs: ReferenceItem[]`, `onAdd/onUpdate/onRemove`, `onSave/onSkip`, `isSaving: boolean`, `error: ApiError \| null`, `draftSaveStatus: DraftSaveStatus` | Render ReferenceCard listesi + "+ Yeni Referans" + footer (Atla/Sakla). Footer status: "Taslak kaydedildi" / "Kaydediliyor…" / "Taslak hatası". |
| `ReferenceCard` | `index: number`, `ref: ReferenceItem`, `onChange/onRemove`, `disabled: boolean` | 6-field form. source_text required (textarea, en az 1 char). Diğer 5 alan opsiyonel. Disabled when lock not held. |
| `AttributionLabel` | `username: string \| null`, `date: string \| null` | "{username} · {relative date}" e.g. "Ahmet · 2 saat önce" |
| `LockBadge` | `username: string`, `acquiredAt: string` | 🔒 ikonu + username + tooltip (acquired_at) |
| `LockConflictModal` | `open: boolean`, `conflictUsername: string \| null`, `isSameUser: boolean`, `onClose: () => void` | shadcn Dialog. Title değişken: `isSameUser` → "Başka sekmede açık", else "{username} kullanıyor". Action: "Listeye dön" → navigate('/'). |
| `ResizableColumns` | `left/middle/right: ReactNode`, `defaultSizes?: [number,number,number]`, `minSizes?: [number,number,number]` | 3-pane splitter. localStorage persist (key: `annotate.col.sizes`). |

---

## 8. Hook Contracts

| Hook | Inputs | Outputs |
|---|---|---|
| `useFeed(tab)` | tab | infinite query result (pages, fetchNextPage, hasNextPage) |
| `useDoc(docId)` | docId | `{ data, isPending, error }` for DocumentDetail |
| `useAnnotation(docId)` | docId | `{ data, isPending, error }` for AnnotationWithChain (or null if 404) |
| `useDraft(docId)` | docId | `{ draftQuery, debouncedSave, deleteMutation, saveStatus, blockSavesUntilFurtherNotice, unblockSaves }` |
| `useLock(docId)` | docId | `{ status, info, conflict, conflictUsername, conflictIsSameUser, release }` |
| `useReferencesState({...})` | draft + annotation data | `{ list, add, update, remove, hydrated }` |
| `useSSE({ acquiringDocId })` | acquiringDocId | none — side effects only (cache invalidation + lock theft) |

---

## 9. Backend Touches

**None.** All backend APIs already exist (paketler 4-7). 16b is pure frontend.

A side note: the existing FastAPI `Reference` Pydantic model uses `Optional` fields for everything except `source_text`. Frontend zod schema must mirror this (5 optional + 1 required).

---

## 10. Integration Contract Checklist (16b complete kriteri)

| # | Check | Type |
|---|---|---|
| 1 | `frontend/npm run typecheck && lint && format:check && test:coverage && build` exit 0 | CI |
| 2 | Coverage ≥80% (statements/branches/lines/functions) on all 16b-owned files | CI |
| 3 | `frontend/npm run test:run` ~ 53 (from 16a) + ~30 (from 16b) = ~83 tests green | CI |
| 4 | Backend `pytest -x -q` green (no regression) | CI |
| 5 | Manual smoke: build + serve via FastAPI + login → `/` shows DocList → click doc → `/docs/:id` editor renders with lock acquired | manual |
| 6 | Manual smoke: edit refs → wait 2s → DevTools network shows PUT /drafts | manual |
| 7 | Manual smoke: refresh page → draft restored silently | manual |
| 8 | Manual smoke: "Sakla" → next doc auto-loads in same tab | manual |
| 9 | Manual smoke: open 2 tabs → first holds lock → second shows LockConflictModal with "Başka sekmede açık" wording | manual |
| 10 | Manual smoke: admin force-release another user's doc → that user sees "Kilit kaybedildi" + navigate to `/` (the `status: 'lost'` path) | manual |

---

## 11. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Heartbeat interval survives unmount due to async acquire race | Low | High | B2 fix: cancelledRef check after acquire; interval handle in ref; cleanup guaranteed |
| Draft write resurrects after save | Medium | High | B1 fix: isSavingRef gate + AbortController + debounce cancel before commit |
| `pickNextInFeed` navigates to undefined | High (without B3 fix) | High | B3+F3 fix: explicit union type + pagination fallback |
| Linear save chain leaves lock held on draft delete failure | Medium | Medium | B4 fix: cleanup steps in independent try blocks; non-blocking warnings; 90s TTL backstop |
| SSE kicks own user out during acquire race | Low | Medium | F1 fix: track acquiringDocId, ignore current-doc events during acquire |
| Cross-tab same-user 409 shows wrong wording | Medium | Low | F8 fix: detect by_user_id === me; "Başka sekmede açık" branch |
| react-virtual + infinite-load corner cases (jank, missed page boundaries) | Low | Medium | Battle-tested library; test with mock 200-item feed |
| `window.location.pathname` parsing for SSE current-doc could miss when route is mid-transition | Low | Low | Document-id parsing is forgiving; falls back to no-op if no match |
| EventSource auth expiry (401 reconnect loop) | Low | Low | onSessionExpired wired in 16a clears session; EventSource will close on next 401 |
| Date formatter for "2 saat önce" requires date-fns Turkish locale registered | Low | Low | formatter.ts initializes locale at module load |
| Coverage threshold on shadcn components (new tabs/dialog/tooltip/badge/etc) | Low | Low | Already exempted via lint ignores; coverage exclude pattern already covers `src/components/ui/**` |
| Large doc bodies (5000+ words) jank DocViewer scroll | Low | Medium | Render pdf_text as plain text in a scrollable container; no markdown parsing in 16b |
| `is_completed` UI state out of sync with backend | Low | Low | useAnnotation invalidated on save; 16b uses a single checkbox; full chain UI in 16d/e |

---

## 12. Implementation Estimate

| Element | New files | Notes |
|---|---|---|
| Routes | 3 | AnnotateLayout (NEW), AnnotateDoc (NEW), Annotate (MODIFY → EmptyEditor) |
| Components | 11 | annotation/*: 8 + modals/LockConflictModal + shell/ResizableColumns + components/ui/TabStrip wrapper |
| Hooks | 8 | useFeed, useDoc, useAnnotation, useDraft, useLock, useReferencesState, useSSE, useNextDocId |
| API queries | 5 | feed, documents, annotations, drafts, locks |
| Lib | 2 | formatters, nextDocId |
| Stores | 1 | annotateStore (current tab) |
| Test infra | 1 | msw-handlers/annotate.ts (additional handlers) |
| Tests | ~20 | Hook tests (8) + component tests (~10) + integration test (AnnotateDoc.test.tsx, full flow) |
| App.tsx route tree | MODIFY | Add nested routes |
| msw-handlers.ts | MODIFY | Re-export annotate handlers |

**Total**: ~22 new source files + ~20 test files + ~3 modify ≈ **~45 files**.

**Commit estimate**: **14-18 atomic commits** (TDD per layer, smoke gates).
**Time estimate**: **4-6 dev-days** (single developer, focused).

### Test coverage targets

| Surface | Target |
|---|---|
| useLock, useDraft, useSSE, useFeed | 90%+ (state machine) |
| useReferencesState, useNextDocId | 95%+ (pure-ish reducer + helper) |
| AnnotateDoc integration | 85%+ (full lifecycle test) |
| DocList, ReferencePanel, ReferenceCard | 80%+ (interaction-driven) |
| LockConflictModal | 80%+ |
| Smoke / other components | 80%+ |

Coverage gate stays at **≥80% across all metrics** (vitest enforced).

---

## 13. Out of Spec / Deferred

**Subsequent paketler:**
- **16c** Onboarding — Help markdown viewer, Training quiz + gold-doc, activate `RequireSeenManual` + `RequirePassedTraining` flows.
- **16d** Gamification UI — TopBar (XP, streak, daily progress, online avatars), Profile, notifications panel, SSE personal events (badge_unlocked, speed_warning, char_limit_warning), annotation_saved/completed events for attribution.
- **16e** Admin panel — `/admin/*` routes + admin queries (Users CRUD, AuditLog with trace_id filter, SystemEvents, Settings, Locks force-release UI, Training admin, Backup/Retention/Export viewers).
- **16f** Docker reconcile — Paket 15 single-stage → multi-stage with node:22-slim frontend-build, T6 smoke extended with SPA serve check.

**Later (Paket 17+):**
- CI: GitHub Actions (typecheck → lint → test → build + drift detection)
- E2E: Playwright (multi-user, lock contention, backup/restore drill)
- Observability: JSON logs, /api/metrics, Sentry frontend
- Performance: bundle analyzer, lazy route loading
- Full a11y audit (axe-core, screen reader)
- Cross-tab session sync (BroadcastChannel)
- Runtime env (currently build-time)
- PWA / offline support
- Dark mode (next-themes integration)
- i18n framework
- Reference field autocomplete (kanun_no → kanun_ad lookup table)
- Annotation chain history viewer
- Bulk operations / filtering / search
