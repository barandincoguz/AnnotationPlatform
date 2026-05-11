# Paket 16d — Gamification UI (Design)

**Status**: Draft — design phase
**Date**: 2026-05-11
**Builds on**: Paket 16a (tag `paket-16a-frontend-foundation`), 16b (tag `paket-16b-annotate-workflow`), 16c (tag `paket-16c-onboarding`)
**Backend dependencies (already shipped)**: Paket 7 (SSE), Paket 8 (behavioral detectors), Paket 9 (gamification XP/streak/badges + notifications)
**Backend touches in 16d**: 3 new endpoints + 2 SSE broker hardening changes + 1 dict field

---

## 1. Goal & Scope

Surface the gamification + presence + notification data that Paket 7-9 produces. The annotation workflow (16b) is functional but lonely — no XP feedback, no streak, no peer visibility, no badge celebration, no notifications. 16d makes the platform feel alive.

### In scope

1. **TopBar** in `AppShell` (currently a placeholder header). Compact h-12 widget with XP / streak / today progress / online users / profile dropdown (avatar + bell counter + Profilim/Yardım/Çıkış).
2. **Profile page** `/me` (currently a 16a STUB). Single scrollable page with ProfileHeader + 4 StatCards + BadgesGrid (Kazanılmış / Hepsi tabs) + NotificationsList (read + unread history).
3. **SSE personal event handling** — extend 16b's `useSSE` to handle `badge_unlocked`, `speed_warning`, `char_limit_warning`, `user_online`, `user_offline` events. 16b lock + feed handlers preserved (regression-safe).
4. **Bell counter** in TopBar — unread notification count + dropdown listing last 10 + "Tümünü okundu yap" action + link to /me notifications section.

### Out of scope

- Notification DELETE endpoint — deferred to Paket 17 (read history is immutable for this release).
- Pre-training user notification surface — AppShell is post-training; pre-training users see notifications only after passing. Architectural carry-over from 16c; addressed in a future package.
- Backend SSE replay / Last-Event-ID — Paket 17b backend hardening. 16d accepts SSE drop possibility with optimistic UI + 30s polling reconcile.
- Client-side speed / char-limit guards (fallback for dropped SSE warnings) — Paket 16d.1 follow-up.
- XP delta animation on number change — Paket 16d.1 polish.
- Mobile responsive deep polish — alongside future theme pass.
- Admin announcement send UI — Paket 16e admin panel.

---

## 2. Tech Stack Additions

No new runtime dependencies. Reuses existing 16a-c stack:
- `@tanstack/react-query` for server state with `refetchInterval` for polling
- `zustand` not needed for 16d (TanStack Query covers all server state)
- `sonner` for toast notifications (already shipped)
- `zod` for runtime payload validation
- `@radix-ui/react-dropdown-menu` (already in shadcn) for ProfileDropdown
- `@radix-ui/react-tabs` (already shipped in 16c) for BadgesGrid
- `@radix-ui/react-tooltip` (already shipped 16b) for badge tooltips and online avatars

---

## 3. Backend Contract

### 3.1 Existing endpoints (locked, no changes)

```
GET /api/me/profile
  Auth: require_passed_training is NOT enforced (works for pre-training too — zeroed state)
  Response 200: {
    user: { id, username, role, avatar_color },
    xp: { total: int },
    streak: { current: int, longest: int, last_active_date: str|null },
    today: { save: int, complete: int, review: int, skip: int, daily_target: int },
    badges: [{ id, name, description, earned_at }, ...],
  }

GET /api/me/notifications?unread_only={bool}&limit={int}
  Auth: get_current_user
  Response 200: {
    items: [{ id: int, kind: str, title: str, body: str|null,
              created_at: str, read_at: str|null }, ...]
  }

POST /api/me/notifications/{notification_id}/read
  Auth: get_current_user
  Response 200: {ok: true}
  404 NotificationNotFound

GET /api/events (SSE)
  Auth: cookie (browser EventSource sends credentials by default)
  Event types emitted:
    - lock_acquired, lock_released (broadcast)
    - annotation_saved (broadcast)
    - badge_unlocked (publish_to user only)
    - speed_warning (publish_to user only)
    - char_limit_warning (publish_to user only)
```

### 3.2 NEW endpoints (3)

```
GET /api/users/online
  Auth: get_current_user
  Source: broker.online_user_ids() — in-memory set of user_ids with active SSE subscription
  Response 200: [
    { id: int, username: str, avatar_color: str },
    ...
  ]
  Ordered by user_id ascending. Empty array when no one is connected.

GET /api/badges/catalog
  Auth: get_current_user
  Source: BADGE_DEFS Python dict (static)
  Response 200: [
    { id: str, name: str, description: str, criterion: str|null },
    ...
  ]
  `description` is past-tense achievement narrative ("10 kayıt biriktirdin").
  `criterion` is OPTIONAL imperative locked-state hint ("10 kayıt yap").
  When `criterion` is null, frontend BadgeCard hides the description on locked variants.

POST /api/me/notifications/read-all
  Auth: get_current_user
  Side effect: UPDATE notifications SET read_at = NOW WHERE user_id = ? AND read_at IS NULL
  Response 200: { marked_count: int }
  Atomic — single UPDATE. Idempotent: repeated call returns marked_count=0.
```

### 3.3 NEW SSE events (2)

```
event: user_online
data: { id: int, username: str, avatar_color: str }
  Emitted: broadcast on broker.subscribe() (excluding the user themselves via publish_to_others to avoid self-echo)
  When: after a new EventSource connection, AFTER the subscribe() registers the queue

event: user_offline
data: { id: int }
  Emitted: broadcast on broker.unsubscribe() AND on the QueueFull drop path
  When: graceful disconnect OR slow-consumer queue full
```

### 3.4 Broker hardening (CRITICAL)

The existing broker has a `q.put_nowait` pattern that silently drops the queue on `QueueFull`. Currently `online_user_ids()` retains the dead user forever. 16d MUST fix this:

```python
# backend/shared/sse.py — publish_to method
async def publish_to(self, user_ids, event_type, data):
    event = SSEEvent(event_type=event_type, data=data)
    for uid in user_ids:
        for q in list(self._subscribers.get(uid, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # CURRENT: silent drop, queue stays in self._subscribers
                # NEW (16d): remove the dead queue + emit user_offline
                self.unsubscribe(uid, q)
                # Lazy-import to avoid cycle; this fires AFTER unsubscribe so
                # online_user_ids() no longer includes the user if this was
                # their last subscription
                if uid not in self._subscribers:
                    asyncio.create_task(
                        self.publish_broadcast('user_offline', {'id': uid})
                    )
```

### 3.5 BADGE_DEFS extension

`backend/gamification/badges.py` — add optional `criterion` field per badge:

```python
BADGE_DEFS: dict[str, dict[str, str]] = {
    "first_annotation": {
        "name": "İlk Annotation",
        "description": "İlk kayıt başarıyla yapıldı.",
        "criterion": "İlk anotasyon kaydını yap.",
    },
    "annotations_10": {
        "name": "10 Annotation",
        "description": "10 kayıt biriktirdin.",
        "criterion": "10 anotasyon kaydı biriktir.",
    },
    # ... 7 toplam — her birine imperative criterion eklenecek
}
```

The catalog endpoint serializes all keys (including criterion when present).

---

## 4. Locked Design Decisions

Each decision below was confirmed in user Q&A during the brainstorming phase.

| # | Decision | Rationale |
|---|---|---|
| D1 | TopBar = full bar (logo + XP/streak/today + online + profile dropdown) | User chose full visibility over minimal or hybrid. FAQ already promises "üst barda online bursiyerler ve onların açtıkları dokümanlar görünür" — implementing the promise. |
| D2 | Online users source = backend endpoint + 30s polling + SSE merge | Tab-scoped sessionStorage / SSE-only approaches were rejected. Polling is the truth source; SSE optimizes responsiveness; both reconcile every 30s. |
| D3 | Warnings = gentle toast (8s); Badge unlock = celebration toast (15s, informational only) + bell counter | Modal-based celebration rejected (interrupts flow). Bell counter persists missed events; toast is ephemeral. Toast has NO action button — clicking through would unmount AnnotateDoc and lose draft (Codex BROKEN-B). |
| D4 | Profile /me = single scrollable page (no tabs) | Tabbed Profile rejected as extra cognitive load for a small team. Stats + Badges + Notifications fit comfortably in vertical scroll. |
| D5 | Locked badges = grayscale + 🔒 + `criterion` text | Past-tense description reused for locked was confusing (Codex BROKEN-A). Imperative criterion clarifies "how to unlock". |
| D6 | Mark-all-read = backend endpoint (POST /read-all) | Frontend batching N individual POSTs is unsafe (race, half-success). One atomic SQL UPDATE on backend. Idempotent. |
| D7 | `useUnreadNotifications` + `useOnlineUsers` both have `refetchInterval: 30_000` | `staleTime` alone is not polling — only freshness. SSE drops would leave indefinite stale state (Codex BROKEN-D, BROKEN-E). |

---

## 5. Folder Structure

### 5.1 New files

```
frontend/src/
├── routes/
│   └── Profile.tsx                       # REPLACES STUB (16a)
│
├── components/
│   ├── topbar/
│   │   ├── TopBar.tsx
│   │   ├── XPBadge.tsx
│   │   ├── StreakCounter.tsx
│   │   ├── DailyProgress.tsx
│   │   ├── OnlineUsers.tsx
│   │   └── ProfileDropdown.tsx
│   │
│   ├── badges/
│   │   ├── BadgesGrid.tsx
│   │   └── BadgeCard.tsx
│   │
│   ├── notifications/
│   │   ├── NotificationsList.tsx
│   │   └── NotificationItem.tsx
│   │
│   └── profile/
│       ├── ProfileHeader.tsx
│       └── StatCards.tsx
│
├── api/queries/
│   ├── profile.ts                        # useProfile
│   ├── notifications.ts                  # useUnreadNotifications, useNotificationsHistory,
│   │                                     #   useMarkReadMutation, useMarkAllReadMutation
│   ├── badges.ts                         # useBadgesCatalog, useLockedBadges selector
│   └── users.ts                          # useOnlineUsers
│
├── hooks/
│   ├── useSSE.ts                         # MODIFIED — orchestrator only (was 16b inline)
│   └── sse/
│       ├── lockHandlers.ts               # EXTRACTED from 16b useSSE
│       ├── feedHandlers.ts               # EXTRACTED from 16b useSSE
│       ├── notificationHandlers.ts       # NEW — badge/warnings
│       └── presenceHandlers.ts           # NEW — user_online/user_offline
│
├── lib/
│   ├── profileSchemas.ts                 # Zod schemas for profile + notifications + badges + online
│   ├── sseSchemas.ts                     # Zod schemas for SSE event payloads
│   ├── notificationKinds.ts              # icon mapping registry
│   └── formatRelativeTr.ts               # MOVED from 16b (existing) — re-export only
```

### 5.2 Modified files

```
frontend/src/
├── components/shell/AppShell.tsx         # add TopBar; was placeholder header
├── hooks/useSSE.ts                       # orchestrator pattern; handlers extracted
└── test/msw-handlers.ts                  # add profile / notifications / catalog / online handlers + factories
```

### 5.3 Backend modified files

```
backend/
├── users/routes.py                       # +GET /api/users/online
├── gamification/badges.py                # +criterion field in BADGE_DEFS
├── gamification/routes.py                # +GET /api/badges/catalog (or new file)
├── notifications/routes.py               # +POST /read-all
├── notifications/service.py              # +mark_all_read function
└── shared/sse.py                         # broker user_online/user_offline + QueueFull cleanup
```

---

## 6. Routing & Gates

The 16a route tree already places `/me` correctly behind `RequirePassedTraining` + `AppShell`:

```tsx
<Route element={<RequirePassedTraining />}>
  <Route element={<AppShell />}>       {/* TopBar mounts here */}
    <Route element={<AnnotateLayout />}>
      <Route path="/" element={<Annotate />} />
      <Route path="/docs/:docId" element={<AnnotateDoc />} />
    </Route>
    <Route path="/me" element={<Profile />} />
  </Route>
</Route>
```

No changes needed. The TopBar inherits AppShell visibility — visible on all gated routes.

`/me` page itself does not gate further; it shows what `useProfile` returns. Pre-training users never reach AppShell, so /me unreachable for them (accepted limitation).

---

## 7. TopBar (`components/topbar/`)

### 7.1 Layout

```tsx
<header className="h-12 border-b bg-background px-4 grid grid-cols-[1fr_auto_1fr] items-center gap-4">
  {/* Left: logo + project name */}
  <div className="flex items-center gap-2">
    <Logo />
    <span className="font-semibold">Anotasyon Platformu</span>
  </div>

  {/* Center: gamification stats */}
  <div className="flex items-center gap-4">
    <XPBadge total={profile.data?.xp.total ?? 0} />
    <StreakCounter current={profile.data?.streak.current ?? 0} longest={profile.data?.streak.longest ?? 0} />
    <DailyProgress today={profile.data?.today.save ?? 0} target={profile.data?.today.daily_target ?? 0} />
  </div>

  {/* Right: presence + profile (width budget) */}
  <div className="ml-auto flex items-center gap-3">
    <div className="max-w-[200px] overflow-hidden">
      <OnlineUsers users={online.data ?? []} maxVisible={5} />
    </div>
    <div className="flex-none">
      <ProfileDropdown
        user={authStore.user}
        unreadCount={unread.data?.items.length ?? 0}
      />
    </div>
  </div>
</header>
```

**Width budget (Codex FRAGILE-C)**:
- Left column `1fr` flexible
- Center column `auto` content-sized
- Right column `1fr` capped via `max-w-[200px]` on OnlineUsers + `flex-none` on ProfileDropdown
- Below `md:` (`<768px`), OnlineUsers hides; only the overflow count "+N online" shows as a clickable chip that opens a popover

### 7.2 Per-component contract

**XPBadge.tsx**:
- Props: `total: number`
- Render: `<span aria-label="Toplam XP"><Sparkle /> {tr_locale_format(total)}</span>`
- Number formatting: `1240` → `1.240` (Turkish locale thousand separator)
- No animation in MVP — opt-in for 16d.1 follow-up

**StreakCounter.tsx**:
- Props: `current: number, longest: number`
- Color tier: 0 → "—" gri; 1-3 gri; 4-6 turuncu; 7+ kırmızı
- Tooltip (shadcn Tooltip): on hover shows "En uzun: N gün" — ONLY if `longest > current`
- aria-label: `${current} gün streak`

**DailyProgress.tsx**:
- Props: `today: number, target: number`
- If `target === 0`: widget hidden entirely
- Else: progress bar (Tailwind `bg-primary` width `${min(today/target, 1) * 100}%`) + label `{today}/{target}`
- If `today >= target`: "Bugün ✓" badge + green tint
- aria-role: `progressbar` with `aria-valuenow`/`aria-valuemax`

**OnlineUsers.tsx**:
- Props: `users: OnlineUser[], maxVisible: number`
- Render: up to `maxVisible` avatars (Tailwind colored circles with first-letter initials) + "+N" chip if `users.length > maxVisible`
- Tooltip on each avatar: `{username}`
- "+N" chip click: shadcn Popover lists all online users with avatar + name
- Empty array: hidden (no "0 online" label)
- aria-label: `${users.length} kullanıcı çevrimiçi`

**ProfileDropdown.tsx**:
- Props: `user: User, unreadCount: number`
- Trigger: avatar (colored circle, initials) + `unreadCount > 0` ? red dot with count (capped "9+") : no dot
- Dropdown (shadcn DropdownMenu) sections:
  ```
  ┌─ {user.username} • {role label}    ─┐
  ├─ 🔔 Bildirimler (N okunmamış)        │
  │    └─ submenu: last 10 + "Tümünü okundu yap" + "Tümünü Gör" → /me │
  ├─ Profilim                            │
  ├─ Yardım                              │
  ├─ Çıkış                               │
  └────────────────────────────────────────┘
  ```
- Bell submenu items render `NotificationItem` (truncated title, kind icon, relative time)
- Click on notification: `useMarkReadMutation.mutate(id)`; no navigation (user can navigate to /me from "Tümünü Gör")
- "Tümünü okundu yap": `useMarkAllReadMutation.mutate()`
- "Tümünü Gör": `navigate('/me#notifications')` (anchor scroll)

### 7.3 Loading / error tolerance per widget

| Query | Loading state | Error state |
|---|---|---|
| useProfile | Skeleton XPBadge/StreakCounter/DailyProgress (gray placeholders) | All 3 stats show "—" (no widget hidden, no toast) |
| useOnlineUsers | OnlineUsers hidden during loading | OnlineUsers hidden entirely on error (best-effort widget) |
| useUnreadNotifications | Bell counter hidden (no count badge) | Bell counter shows 0 (no error UI in topbar) |

TopBar must never crash. Each widget guards against undefined data with `??` fallbacks.

---

## 8. Profile Page (`/me`)

### 8.1 Layout

Single scrollable page, max-w-4xl, vertical flow:

```
┌───────────────────────────────────────────────────────┐
│ [Avatar] @testbot                                     │ ← ProfileHeader
│ Bursiyer • Hesap oluşturuldu: 2026-05-01              │
├───────────────────────────────────────────────────────┤
│ ┌─────────┬─────────┬─────────┬─────────┐             │
│ │ ✨ 1240 │ 🔥 3    │ 3/10 ▰  │ 🏆 5    │             │ ← StatCards
│ │ XP      │ Streak  │ Bugün   │ Rozet   │             │
│ │         │ (en u.12)│ ▰▰▰░░░░│         │             │
│ └─────────┴─────────┴─────────┴─────────┘             │
├───────────────────────────────────────────────────────┤
│ Rozetler                  [Kazanılmış (5)] [Hepsi (7)]│ ← BadgesGrid (tabs)
│ ┌─────┬─────┬─────┬─────┐                             │
│ │ 🏆  │ ✨  │ 💪  │ ...  │                             │
│ │İlk  │ 10  │ 100 │      │                             │
│ │Annt │ Annt│ Annt│      │                             │
│ │ 2sa │ 1g  │ ... │      │                             │
│ └─────┴─────┴─────┴─────┘                             │
├───────────────────────────────────────────────────────┤
│ Bildirimler               [Tümünü okundu yap]         │ ← NotificationsList
│ • 🏆 Yeni rozet: "İlk Annotation"  2 saat önce  [✓]   │
│   İlk kayıt başarıyla yapıldı.                        │
│ • ✓ Eğitim geçildi                 1 gün önce         │
│   ...                                                  │
└───────────────────────────────────────────────────────┘
```

### 8.2 Components

**ProfileHeader.tsx**:
- Props: `user: User, createdAt: string`
- Avatar (large), `@{username}`, role badge, "Hesap oluşturuldu: {tr_date}"

**StatCards.tsx**:
- Props: `profile: ProfileResponse`
- 4-card grid: `grid grid-cols-2 md:grid-cols-4 gap-4`
- Cards:
  1. XP — `✨ {xp.total formatted} / Toplam XP`
  2. Streak — `🔥 {current} gün / Streak / En uzun: {longest} gün`
  3. Bugün — if `daily_target === 0`: `{today.save} / Bugün / Günlük hedef kapalı`; else: progress bar + `{today.save}/{daily_target}`
  4. Rozet — `🏆 {badges.length} / Toplam Rozet`

**BadgesGrid.tsx**:
- Props: `earned: BadgeOut[], catalog: BadgeCatalogItem[]`
- shadcn Tabs:
  - **Default tab determined at mount** (Codex FRAGILE-E):
    ```ts
    const defaultTab = useMemo(
      () => earned.length === 0 ? 'hepsi' : 'kazanilmis',
      []   // intentionally empty — compute once
    )
    ```
- Tab "Kazanılmış": grid of `<BadgeCard variant="earned" />`
- Tab "Hepsi": grid of all 7 — earned use `variant="earned"`, rest use `variant="locked"`
- Empty state in Kazanılmış tab: "Henüz rozet yok. Hepsi sekmesinde mevcut rozetleri gör."
- Catalog fetch error: BadgesGrid renders only Kazanılmış tab + inline warning "Tüm rozet kataloğu yüklenemedi" + retry button

**BadgeCard.tsx**:
- Props: `badge: { id, name, description, criterion?, earned_at? }, variant: 'earned' | 'locked'`
- Layout (Codex FRAGILE-C, FRAGILE-D fixes):
  ```tsx
  <Card className={cn(variant === 'locked' && 'grayscale opacity-60')}>
    <CardContent>
      <div className="flex items-center gap-2">
        <span className="text-2xl" aria-hidden>{badgeIcon(badge.id)}</span>
        <h3 className="font-medium">{badge.name}</h3>
        {variant === 'locked' && <Lock className="ml-auto h-4 w-4" />}
      </div>
      <Tooltip>
        <TooltipTrigger asChild>
          <p className="line-clamp-2 text-sm text-muted-foreground">
            {variant === 'earned' ? badge.description : (badge.criterion ?? '')}
          </p>
        </TooltipTrigger>
        <TooltipContent>
          {variant === 'earned' ? badge.description : (badge.criterion ?? badge.description)}
        </TooltipContent>
      </Tooltip>
      {variant === 'earned' && (
        <span className="text-xs text-muted-foreground">{formatRelativeTr(badge.earned_at)}</span>
      )}
    </CardContent>
  </Card>
  ```
- `badgeIcon(id)`: small map for 7 badges — first_annotation → 🏆, annotations_10 → ✨, etc. Fallback 🎖️.

**NotificationsList.tsx**:
- Props: `items: Notification[]`
- Render last 50 (backend limit). Vertical list, `<NotificationItem>` per entry.
- "Tümünü okundu yap" button: only shown if `items.some(i => !i.read_at)`. Click → `useMarkAllReadMutation.mutate()`.
- Empty: "Henüz bildirim yok."
- Loading: skeleton 3 rows
- Error: error block + retry; rest of /me renders normally (graceful degradation)

**NotificationItem.tsx**:
- Props: `item: Notification`
- Layout:
  ```tsx
  <div className={cn(
    'flex items-start gap-3 border-b py-3',
    item.read_at === null && 'border-l-4 border-l-primary pl-3 font-medium'
  )}>
    <span className="text-xl">{iconForKind(item.kind)}</span>
    <div className="flex-1 min-w-0">
      <h4 className="truncate" title={item.title}>{item.title}</h4>
      {item.body && <p className="text-sm text-muted-foreground line-clamp-2">{item.body}</p>}
      <time className="text-xs text-muted-foreground">{formatRelativeTr(item.created_at)}</time>
    </div>
    {item.read_at === null && (
      <Button variant="ghost" size="sm" onClick={() => markRead.mutate(item.id)}>
        <Check className="h-4 w-4" />
      </Button>
    )}
  </div>
  ```

---

## 9. SSE Handler Extension

### 9.1 Module structure

The 16b `useSSE.ts` becomes an orchestrator. All handler logic moves to `hooks/sse/` modules.

```
hooks/
├── useSSE.ts                # orchestrator — wires EventSource + cleanup
└── sse/
    ├── lockHandlers.ts      # EXTRACTED from 16b — lock_acquired, lock_released
    ├── feedHandlers.ts      # EXTRACTED from 16b — annotation_saved → feed invalidate
    ├── notificationHandlers.ts  # NEW — badge_unlocked, speed_warning, char_limit_warning
    └── presenceHandlers.ts  # NEW — user_online, user_offline
```

### 9.2 useSSE.ts (orchestrator)

```tsx
export function useSSE(opts: UseSSEOpts) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const meId = useAuthStore((s) => s.user?.id ?? null)
  const acquiringRef = useRef<string | null>(opts.acquiringDocId)
  acquiringRef.current = opts.acquiringDocId

  useEffect(() => {
    let cancelled = false
    const es = new EventSource('/api/events')

    registerLockHandlers(es, { qc, navigate, meId, acquiringRef })
    registerFeedHandlers(es, { qc })
    registerNotificationHandlers(es, { qc, navigate })
    registerPresenceHandlers(es, { qc })

    es.onerror = () => {
      if (cancelled) return
      if (es.readyState === EventSource.CONNECTING) {
        void qc.invalidateQueries({ queryKey: feedKeys.all })
        void qc.invalidateQueries({ queryKey: usersKeys.online })
      }
    }

    return () => { cancelled = true; es.close() }
  }, [qc, navigate, meId])
}
```

### 9.3 notificationHandlers.ts

```tsx
import type { QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { badgeUnlockedSchema, speedWarningSchema, charLimitWarningSchema } from '@/lib/sseSchemas'
import { profileKeys } from '@/api/queries/profile'
import { notificationsKeys } from '@/api/queries/notifications'

interface Opts { qc: QueryClient }

export function registerNotificationHandlers(es: EventSource, opts: Opts) {
  es.addEventListener('badge_unlocked', (e) => {
    const data = parseEventData(e, badgeUnlockedSchema)
    if (!data) return
    // Codex BROKEN-B: toast is INFORMATIONAL ONLY (no action button)
    toast.success(`🎉 Yeni rozet: ${data.badge_name}`, {
      duration: 15_000,
      description: data.badge_description,
    })
    void opts.qc.invalidateQueries({ queryKey: profileKeys.me() })
    void opts.qc.invalidateQueries({ queryKey: notificationsKeys.all })
  })

  es.addEventListener('speed_warning', (e) => {
    const data = parseEventData(e, speedWarningSchema)
    if (!data) return
    toast.warning('Bir nefes al', {
      duration: 8_000,
      description: `Son ${data.window_minutes} dakikada ${data.save_count} kayıt attın. Kalite hızdan önemli.`,
    })
  })

  es.addEventListener('char_limit_warning', (e) => {
    const data = parseEventData(e, charLimitWarningSchema)
    if (!data) return
    toast.warning('Metin uzunluğu dikkat', {
      duration: 8_000,
      description: `${data.ref_index + 1}. referansın metin alıntısı ${data.detail}.`,
    })
  })
}
```

### 9.4 presenceHandlers.ts

```tsx
import type { QueryClient } from '@tanstack/react-query'
import { usersKeys } from '@/api/queries/users'

interface Opts { qc: QueryClient }

export function registerPresenceHandlers(es: EventSource, opts: Opts) {
  const invalidate = () => void opts.qc.invalidateQueries({ queryKey: usersKeys.online() })
  es.addEventListener('user_online', invalidate)
  es.addEventListener('user_offline', invalidate)
}
```

### 9.5 sseSchemas.ts

```ts
import { z } from 'zod'

export const badgeUnlockedSchema = z.object({
  badge_id: z.string(),
  badge_name: z.string(),
  badge_description: z.string(),
})

export const speedWarningSchema = z.object({
  window_minutes: z.number().int(),
  save_count: z.number().int(),
})

export const charLimitWarningSchema = z.object({
  ref_index: z.number().int(),
  detail: z.string(),
})

export const userOnlinePayloadSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  avatar_color: z.string(),
})

export const userOfflinePayloadSchema = z.object({
  id: z.number().int(),
})

export function parseEventData<T>(e: MessageEvent, schema: z.ZodType<T>): T | null {
  try {
    const raw = JSON.parse(e.data as string)
    const result = schema.safeParse(raw)
    if (!result.success) {
      console.warn('[SSE] payload parse failed', e.type, result.error.issues)
      return null
    }
    return result.data
  } catch {
    return null
  }
}
```

---

## 10. Hooks & Queries

### 10.1 profile.ts

```ts
export const profileKeys = {
  all: ['profile'] as const,
  me: () => [...profileKeys.all, 'me'] as const,
}

export function useProfile() {
  return useQuery<ProfileResponse>({
    queryKey: profileKeys.me(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/me/profile'))
      return profileResponseSchema.parse(raw)
    },
    staleTime: 5_000,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  })
}
```

### 10.2 notifications.ts

```ts
export const notificationsKeys = {
  all: ['notifications'] as const,
  unread: () => [...notificationsKeys.all, 'unread'] as const,
  history: () => [...notificationsKeys.all, 'history'] as const,
}

export function useUnreadNotifications() {
  return useQuery({
    queryKey: notificationsKeys.unread(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/me/notifications', {
        params: { query: { unread_only: true, limit: 50 } },
      }))
      return notificationsListSchema.parse(raw)
    },
    staleTime: 5_000,
    refetchInterval: 30_000,  // Codex BROKEN-E
  })
}

export function useNotificationsHistory() {
  return useQuery({
    queryKey: notificationsKeys.history(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/me/notifications', {
        params: { query: { unread_only: false, limit: 50 } },
      }))
      return notificationsListSchema.parse(raw)
    },
    staleTime: 5_000,
    refetchOnWindowFocus: true,
  })
}

export function useMarkReadMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      unwrapVoid(client.POST('/api/me/notifications/{notification_id}/read', {
        params: { path: { notification_id: id } },
      })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: notificationsKeys.all })
    },
  })
}

export function useMarkAllReadMutation() {
  const qc = useQueryClient()
  return useMutation<{ marked_count: number }>({
    mutationFn: async () => {
      const raw = await unwrap(client.POST('/api/me/notifications/read-all'))
      return markAllReadResponseSchema.parse(raw)
    },
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: notificationsKeys.all })
      toast.success(`${data.marked_count} bildirim okundu işaretlendi.`)
    },
  })
}
```

### 10.3 badges.ts

```ts
export const badgesKeys = {
  all: ['badges'] as const,
  catalog: () => [...badgesKeys.all, 'catalog'] as const,
}

export function useBadgesCatalog() {
  return useQuery({
    queryKey: badgesKeys.catalog(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/badges/catalog'))
      return badgesCatalogSchema.parse(raw)
    },
    staleTime: Infinity,
  })
}

// Selector helper — joins catalog with earned (Codex BROKEN-C)
export function useLockedBadges() {
  const catalog = useBadgesCatalog()
  const profile = useProfile()
  return useMemo(() => {
    if (!catalog.data || !profile.data) return []
    const earnedIds = new Set(profile.data.badges.map((b) => b.id))
    return catalog.data.filter((b) => !earnedIds.has(b.id))
  }, [catalog.data, profile.data])
}
```

### 10.4 users.ts

```ts
export const usersKeys = {
  all: ['users'] as const,
  online: () => [...usersKeys.all, 'online'] as const,
}

export function useOnlineUsers() {
  return useQuery({
    queryKey: usersKeys.online(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/users/online'))
      return onlineUsersSchema.parse(raw)
    },
    staleTime: 30_000,
    refetchInterval: 30_000,  // Codex BROKEN-D
  })
}
```

---

## 11. Type Guards & Runtime Validation

All backend responses pass through Zod schemas at the query/mutation boundary. Failures are isolated per hook (Codex FRAGILE-F):

- useProfile parse fail → `Profile` page shows full retry; TopBar widgets show "—"
- useBadgesCatalog parse fail → BadgesGrid renders Kazanılmış only + warning
- useOnlineUsers parse fail → TopBar OnlineUsers hidden
- useUnreadNotifications parse fail → Bell counter 0
- useNotificationsHistory parse fail → Notifications section error block on /me

### 11.1 profileSchemas.ts

```ts
import { z } from 'zod'

export const userSectionSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  role: z.string(),
  avatar_color: z.string(),
})

export const xpSectionSchema = z.object({ total: z.number().int() })

export const streakSectionSchema = z.object({
  current: z.number().int(),
  longest: z.number().int(),
  last_active_date: z.string().nullable(),
})

export const todaySectionSchema = z.object({
  save: z.number().int(),
  complete: z.number().int(),
  review: z.number().int(),
  skip: z.number().int(),
  daily_target: z.number().int(),
})

export const badgeOutSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  earned_at: z.string(),
})

export const profileResponseSchema = z.object({
  user: userSectionSchema,
  xp: xpSectionSchema,
  streak: streakSectionSchema,
  today: todaySectionSchema,
  badges: z.array(badgeOutSchema),
})

export const notificationSchema = z.object({
  id: z.number().int(),
  kind: z.string(),
  title: z.string(),
  body: z.string().nullable(),
  created_at: z.string(),
  read_at: z.string().nullable(),
})

export const notificationsListSchema = z.object({
  items: z.array(notificationSchema),
})

export const markAllReadResponseSchema = z.object({
  marked_count: z.number().int(),
})

export const badgesCatalogItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  criterion: z.string().nullable().optional(),
})

export const badgesCatalogSchema = z.array(badgesCatalogItemSchema)

export const onlineUserSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  avatar_color: z.string(),
})

export const onlineUsersSchema = z.array(onlineUserSchema)

// Inferred types
export type ProfileResponse = z.infer<typeof profileResponseSchema>
export type Notification = z.infer<typeof notificationSchema>
export type BadgeCatalogItem = z.infer<typeof badgesCatalogItemSchema>
export type OnlineUser = z.infer<typeof onlineUserSchema>
```

### 11.2 notificationKinds.ts

```ts
export const NOTIFICATION_KIND_ICONS: Record<string, string> = {
  badge_unlocked: '🏆',
  training_passed: '🎓',
  training_reset: '🔄',
  admin_announcement: '📢',
  lock_lost: '🔓',
}

export function iconForKind(kind: string): string {
  return NOTIFICATION_KIND_ICONS[kind] ?? '🔔'
}
```

---

## 12. Accessibility Contract

- TopBar `<header role="banner">` (default for `<header>`)
- XPBadge `aria-label="Toplam XP"`
- StreakCounter `aria-label={`${current} gün streak`}`
- DailyProgress `<div role="progressbar" aria-valuenow={today} aria-valuemax={target} aria-valuemin={0}>`
- OnlineUsers `aria-label={`${count} kullanıcı çevrimiçi`}`
- ProfileDropdown trigger has `aria-label="Profil menüsü"`; unread count announced via `<span class="sr-only">{unreadCount} okunmamış bildirim</span>`
- BadgesGrid tabs use Radix Tabs (a11y built-in)
- BadgeCard locked variant has `aria-disabled="true"` and a `<Lock>` icon with `aria-label="Kilitli"`
- Toast notifications via sonner — default ARIA live region is `polite`; badge_unlocked celebration uses `aria-live="polite"` (not assertive — informational)
- NotificationItem mark-as-read button has `aria-label={`${item.title} bildirimini okundu işaretle`}`

---

## 13. Codex Adversarial Review — Findings & Mitigations

Three adversarial passes by Codex during brainstorming.

### Pass 1 (Architecture, Sections 1-3)

| Severity | Finding | Mitigation |
|---|---|---|
| BROKEN | Mark-all-read endpoint missing | NEW endpoint `POST /read-all` |
| BROKEN | Profile history limited to unread_only=true | Separate `useNotificationsHistory()` with `unread_only=false` |
| BROKEN | Locked badges need catalog join | `useBadgesCatalog()` + `useLockedBadges()` selector |
| BROKEN | Online users stale on dropped SSE | `refetchInterval: 30_000` on useOnlineUsers |
| BROKEN | Unread count stale on dropped SSE | `refetchInterval: 30_000` on useUnreadNotifications |
| FRAGILE | Badge unlock SSE drop → no celebration | Profile mount refetches; cached diff surfaces new badges |
| FRAGILE | Warning SSE drop → no user feedback | Accepted limitation; deferred client-side guards to 16d.1 |
| FRAGILE | lock/annotation cache SSE-only | 16b pattern preserved (save-invalidate, route-focus refetch) |

### Pass 2 (Profile design)

| Severity | Finding | Mitigation |
|---|---|---|
| BROKEN | Locked badge past-tense copy mismatch | NEW `criterion` field in BADGE_DEFS + catalog |
| BROKEN | daily_target=0 edge case | StatCards: raw count + "Günlük hedef kapalı" subtitle |
| BROKEN | Badge card mobile overflow | line-clamp-2 + Tooltip; 2-col mobile, 4-col desktop |
| FRAGILE | Notification kind drift | `notificationKinds.ts` map + unknown-kind test |
| FRAGILE | Mark-all-read race during refetch | Mutation success toast for deterministic feedback |
| FRAGILE | No notification DELETE | Documented; deferred to Paket 17 |
| FRAGILE | Pre-training notification visibility | Documented architectural gap; deferred to Paket 17 |

### Pass 3 (Final full-design review)

| Severity | Finding | Mitigation |
|---|---|---|
| BROKEN | Ghost online users on QueueFull drop | Broker hardening: drop path calls unsubscribe + emits user_offline |
| BROKEN | Badge toast action destroys annotate work | Toast has NO action button — informational only |
| FRAGILE | TopBar right column width budget | max-w-[200px] + flex-none + viewport-conditional hide |
| FRAGILE | Bell dropdown title overflow | `truncate` + native `title` attr tooltip |
| FRAGILE | Fresh-user empty Kazanılmış tab | Default tab = "Hepsi" if earned.length === 0 |
| FRAGILE | Zod schema failure boundary | Explicit per-hook isolated error states |

All findings integrated. No open items.

---

## 14. Tests & Coverage

Coverage threshold: ≥80% statements / branches / functions / lines (16a/b/c parity).

### 14.1 Unit (per-component)

| File | Tests |
|---|---|
| `XPBadge.test.tsx` | total=0, TR locale formatting, aria-label |
| `StreakCounter.test.tsx` | current=0 "—", color tiers (1-3/4-6/7+), tooltip on `longest > current` |
| `DailyProgress.test.tsx` | daily_target=0 hidden, progress bar width, "Bugün ✓" badge |
| `OnlineUsers.test.tsx` | empty hidden, max 5 + "+N", popover, viewport <md hides full list |
| `ProfileDropdown.test.tsx` | unreadCount badge ("9+" cap), dropdown open, bell submenu render |
| `TopBar.test.tsx` | 3-col grid, loading skeletons, error tolerance per widget |
| `BadgeCard.test.tsx` | earned variant, locked variant + criterion (or hidden if null), line-clamp + tooltip |
| `BadgesGrid.test.tsx` | tab switching, default-tab logic (`earned.length === 0` → "Hepsi"), catalog error degrades |
| `NotificationItem.test.tsx` | unread border + bold, read muted, mark-read click, per-kind icon |
| `NotificationsList.test.tsx` | empty state, mark-all button visibility, history mixed |
| `ProfileHeader.test.tsx` | avatar + username + role + created_at |
| `StatCards.test.tsx` | 4 stats render; daily_target=0 → raw count + "Günlük hedef kapalı" |

### 14.2 Hook tests

| File | Tests |
|---|---|
| `profile.test.ts` | success, 401, Zod parse failure |
| `notifications.test.ts` | useUnreadNotifications + refetchInterval, useNotificationsHistory, mutations |
| `badges.test.ts` | useBadgesCatalog Infinity stale, useLockedBadges selector |
| `users.test.ts` | useOnlineUsers + refetchInterval, SSE invalidate triggers refetch |
| `sse/notificationHandlers.test.ts` | badge_unlocked toast + invalidate, warnings, payload parse fail |
| `sse/presenceHandlers.test.ts` | user_online/user_offline → invalidate users.online |
| `sse/lockHandlers.test.ts` | 16b extract — behavior unchanged |
| `sse/feedHandlers.test.ts` | 16b extract — behavior unchanged |
| `useSSE.test.ts` | orchestrator wiring, cleanup, reconnect path |
| `lib/notificationKinds.test.ts` | known kinds, unknown → 🔔 fallback |
| `lib/sseSchemas.test.ts` | valid/invalid payloads per schema |

### 14.3 Integration

| Scenario | Setup | Assert |
|---|---|---|
| TopBar end-to-end | Default MSW handlers | All widgets render |
| Profile mount + cache | Pre-cache profile, navigate to /me | Renders immediately, refetches in bg |
| Bell dropdown flow | Pre-seeded notifications | Click → mark-read → count drops |
| Mark-all-read with toast | Pre-seed 5 unread | Toast "5 bildirim..."; count goes 5→0 |
| Badge celebration | SSE dispatch badge_unlocked | Toast rendered + profile invalidated |
| Online users SSE merge | Dispatch user_online | useOnlineUsers refetches |
| Locked badges grayscale | Mock profile.badges=2, catalog=7 | 5 cards show locked + 🔒 + criterion |
| Catalog fetch error degrades | Mock /badges/catalog 500 | BadgesGrid shows Kazanılmış only + warning |
| daily_target=0 in TopBar | Mock daily_target=0 | DailyProgress hidden |
| daily_target=0 in StatCards | Same | Bugün card: count + "Günlük hedef kapalı" |
| Fresh user default tab | Mock badges=[] | BadgesGrid defaults to "Hepsi" tab |
| Width budget at small viewport | Mock viewport <md | OnlineUsers full list hidden, overflow chip visible |

### 14.4 Backend tests

For each new endpoint:
- `GET /api/users/online` — empty list, populated list, auth required (401 if no session)
- `GET /api/badges/catalog` — 7 entries shape, criterion field optional in catalog, auth required
- `POST /api/me/notifications/read-all` — marks all unread, returns count, idempotent (repeat returns 0), auth required
- SSE user_online emitted on subscribe (via test client connect, NOT publish to self via publish_to_others)
- SSE user_offline emitted on unsubscribe (graceful disconnect AND QueueFull drop path)
- Broker QueueFull cleanup — after dropping a queue, online_user_ids() no longer includes the user

### 14.5 MSW handler factories

`test/msw-handlers.ts` additions:

```ts
export function makeProfile(overrides: Partial<ProfileResponse> = {}): ProfileResponse { ... }
export function makeNotification(overrides: Partial<Notification> = {}): Notification { ... }
export function makeBadgeCatalogItem(overrides: Partial<BadgeCatalogItem> = {}): BadgeCatalogItem { ... }

// Override helpers
export function mockProfileWithDailyTargetZero() { ... }
export function mockProfileWithLongStreak() { ... }
export function mockBadgesCatalogError() { ... }
export function mockOnlineUsersEmpty() { ... }
export function mockUnreadCount(n: number) { ... }
```

---

## 15. Acceptance Criteria

- [ ] All new unit + hook + integration tests pass
- [ ] 16a/16b/16c existing tests pass (zero regression)
- [ ] Coverage ≥80% all 4 metrics
- [ ] `npm run typecheck` clean
- [ ] `npm run lint` clean
- [ ] `npm run gen:types:check` clean (backend OpenAPI sync after new endpoints land)
- [ ] **Backend additions verified**:
  - GET `/api/users/online` returns shape; auth required
  - GET `/api/badges/catalog` returns 7 entries with optional criterion
  - POST `/api/me/notifications/read-all` returns `{marked_count}`; idempotent
  - SSE emits `user_online` on subscribe (excluding self), `user_offline` on unsubscribe AND on QueueFull drop
  - Broker QueueFull path cleanly removes the dead queue
- [ ] **Backend tests**: all new endpoints + broker hardening covered
- [ ] Manual E2E smoke (next section)
- [ ] No regression to 16b SSE lock handling
- [ ] No regression to 16b annotation save flow
- [ ] TopBar visible on all post-training routes; hidden on login/register/help/training
- [ ] Profile /me reachable, all sections render with default seed user (testbot)

---

## 16. Manual E2E Smoke

After CI green, before tagging:

1. Fresh user (flags=1 already from 16c) → login → TopBar visible with XP 0, Streak 0, Bugün 0/10, no online avatars yet
2. Click `/me` from ProfileDropdown → Profile page renders: identity, 4 stat cards (Bugün progress bar, XP 0, Streak —, Rozet 0), BadgesGrid defaults to "Hepsi" (no earned yet), Notifications empty
3. Make an annotation save → bell counter bumps if `first_annotation` badge fires; toast pops "🎉 Yeni rozet: İlk Annotation"
4. Navigate back to TopBar → XP increases, Bugün progress moves
5. Open ProfileDropdown bell → see the new notification (unread, bold)
6. Click notification → marks as read; counter decrements
7. "Tümünü Gör" → /me Notifications section → see all (read + unread)
8. /me BadgesGrid → "Kazanılmış (1)" tab now active by default; "Hepsi (7)" shows 1 colored + 6 grayscale with 🔒
9. Open `/docs/:docId` in a second browser tab → first tab's OnlineUsers shows +1 user
10. Close second tab → after up to 30s, first tab's OnlineUsers drops by 1 (polling reconcile OR SSE user_offline)
11. Force QueueFull (load test backend with many publishes per second) → verify broker drops the dead queue and emits user_offline
12. Force SSE disconnect → reconnect → useProfile + useOnlineUsers refetch on reconnect
13. Verify `/help` and `/training` do NOT show TopBar (correct gating)
14. Verify TopBar layout at viewport <768px: OnlineUsers full list hidden, overflow chip + ProfileDropdown still visible
15. Trigger speed_warning manually (admin SQL inject 5 saves in last 5min) → toast pops on 6th save

---

## 17. Files Changed Summary

**Backend modified (5 files)**:
- `backend/users/routes.py` — +GET /api/users/online
- `backend/gamification/badges.py` — +criterion field per badge
- `backend/gamification/routes.py` — +GET /api/badges/catalog (new file if needed)
- `backend/notifications/routes.py` — +POST /api/me/notifications/read-all
- `backend/notifications/service.py` — +mark_all_read function
- `backend/shared/sse.py` — broker.subscribe emits user_online (via publish_to_others), unsubscribe emits user_offline, QueueFull drop path calls unsubscribe + emits user_offline

**Frontend new (~22 files)**:
- 6 TopBar components
- 2 BadgesGrid components
- 2 Notifications components
- 2 Profile components
- 4 query files (profile, notifications, badges, users)
- 4 SSE handler modules (extracted lock+feed, new notif+presence)
- 3 lib helpers (profileSchemas, sseSchemas, notificationKinds)
- 1 route replacement (Profile.tsx)

**Frontend modified (3)**:
- `components/shell/AppShell.tsx` — add TopBar
- `hooks/useSSE.ts` — orchestrator refactor
- `test/msw-handlers.ts` — factories + handlers

**Untouched (regression-safe)**:
- All 16a/16b/16c source files except useSSE refactor
- ReferenceCard, ReferencePanel (16b)
- Help, Training routes (16c)

---

## 18. Risks & Open Questions

**Accepted limitations**:
- SSE drops on QueueFull mitigated by broker cleanup + 30s polling reconcile, but not eliminated
- Mobile beforeunload not honored (carryover from 16c)
- DELETE notification → Paket 17
- Pre-training notification visibility → Paket 17 (architectural)
- Client-side speed/char_limit guards → Paket 16d.1 follow-up
- Backend SSE replay / Last-Event-ID → Paket 17b backend hardening
- XP delta animation, mobile responsive deep polish → 16d.1 / theme pass

**Risks under mitigation**:
- TopBar adds h-12 above existing AnnotateLayout 3-col grid — verify @tanstack/react-virtual still works with adjusted viewport height (16b DocList uses container-relative measurements; should not regress, but smoke test in Step 14)
- AppShell h-12 + AnnotateLayout flex-1 must equal exactly 100vh — adjust min-h-screen calculations
- Broker `asyncio.create_task` inside QueueFull cleanup must run within the asyncio loop context — verify in backend test

**No open questions**. All gray areas resolved through user Q&A and three Codex reviews.

---

**Approval gate**: After this spec is reviewed and approved by the user, the writing-plans skill produces the implementation plan (`docs/superpowers/plans/2026-05-11-package-16d-gamification-ui.md`) for subagent-driven-development execution.
