# Paket 16e — Admin Panel UI Design

**Status:** DRAFT (awaiting Codex adversarial review)
**Author:** Claude Code (Opus 4.7) + Codex consultation
**Date:** 2026-05-12
**Predecessors:** 16a (foundation), 16b (annotate), 16c (onboarding+manual+training), 16c.1 (training UX), 16c.1.1 (skip replay fix), 16d (gamification UI). Backend admin endpoints landed in Paket 11.

## 1. Goal

Replace the `AdminLayout` stub at `/admin/*` with a usable admin panel oriented for **rare crisis intervention** (incident investigation + lock release first-class). Secondary: user management, platform configuration, training content overrides.

## 2. Why this paket exists now

- Backend admin API was finished in Paket 11 but only `/admin/*` stub UI exists
- Codex Dalga 1 B1–B4 fixes need UI to verify
- Operations team currently has no way to investigate incidents by `trace_id` despite the backend writing it
- `RequireAdmin` gate already wraps `/admin/*` from 16d; ProfileDropdown already links here

## 3. Locked Decisions (D-series)

| ID | Decision | Rationale |
|---|---|---|
| **D1** | **Nested React Router 6 sub-routes** (`/admin/users`, `/admin/audit`, `/admin/events`, `/admin/locks`, `/admin/settings`, `/admin/training`), NOT shadcn `Tabs` | Deep-link, back/forward, share-by-URL for incident write-ups. Matches existing routing pattern (Outlet). |
| **D2** | **Left sidebar nav on desktop**, compact selector on mobile (`md:hidden`) | Admin work is cross-section; sidebar keeps tool map visible. |
| **D3** | **Operational domain grouping** in sidebar — Operations (Audit, System Events, Locks), People (Users), Platform (Settings), Training Content (Gold docs, Quiz). | Matches mental model: "Audit" and "Events" are different consumers despite both being logs. |
| **D4** | **No TanStack Table.** Build a narrow local `AdminTable` + `AdminListCard` primitive in `frontend/src/components/admin/`. | Endpoints expose simple offset pagination; adding a table engine before UX needs it bloats surface. |
| **D5** | **Backend addition: `?trace_id=...` query filter on `GET /api/admin/audit-log`** + matching `?trace_id` on `GET /api/admin/system-events` if backend exposes the column. UI gets a `trace_id` search box. | Crisis-intervention priority demands cross-row correlation. Codex flagged "false confidence" risk of displaying without filtering. |
| **D6** | **Training overrides: structured forms only**, with diff-before-save. No raw JSON escape hatch. | Gold-doc/quiz overrides drive pass/fail for every annotator; a blind JSON paste can corrupt onboarding silently. Power-user speed traded for safety. |
| **D7** | **Locks: doc_id input + confirmation modal**, no active-locks listing. Backend has no `GET active locks` and we are not adding one in this paket. | Smaller surface; user explicitly chose this. |
| **D8** | **Audit filter set**: date presets (24h / 7d / 30d / custom) + `action_type` select + `admin_id` select + `trace_id` search box. All optional, AND-composed. URL-synced (`?action=...&trace_id=...`). | URL-syncing makes investigations shareable. |
| **D9** | **Single paket scope** — Audit + Events + Locks + Users + Settings + Training overrides all in 16e. ~12–14 TDD tasks. | User choice. Atomic delivery; no 16e/16e.1 split. |
| **D10** | **Existing `RequireAdmin` gate is sufficient** — no per-action role re-check on frontend. Backend always re-validates admin role on mutations. | Trust backend authoritative; avoid double-gate UX bugs. |

## 4. Information Architecture

```
/admin                          → redirects to /admin/audit (default landing for crisis priority)
├── /admin/audit                → Admin actions investigation (default)
├── /admin/events               → User activity stream
├── /admin/locks                → Force-release tool
├── /admin/users                → User management table
├── /admin/settings             → Runtime config editor
└── /admin/training
    ├── /admin/training/gold-docs
    └── /admin/training/quiz
```

**Sidebar (desktop, `lg:flex`):**

```
┌──────────────┐
│ ⚠ Operations │
│   Audit      │
│   Events     │
│   Locks      │
├──────────────┤
│ 👤 People    │
│   Users      │
├──────────────┤
│ ⚙ Platform   │
│   Settings   │
├──────────────┤
│ 📚 Training  │
│   Gold Docs  │
│   Quiz       │
└──────────────┘
```

**Mobile (`md:hidden`):** A `Select` at the top of `AdminLayout` content area, options grouped via Radix `<SelectGroup>` matching the sidebar groups.

## 5. Backend additions in scope

Two backend endpoint extensions land **in this paket** (not separate package):

### 5.1 `GET /api/admin/audit-log?trace_id=...`

Add optional `trace_id` query param. Filter on `admin_audit_log.trace_id` exact match. Combine with existing filters via AND. If `trace_id` matches no rows, return empty list (not 404).

### 5.2 `GET /api/admin/system-events?trace_id=...`

Same pattern if `system_events` table has a `trace_id` column. Verify migration history during T1 — if column absent, scope this to audit-log only and flag for follow-up paket.

### 5.3 Tests

Per-endpoint pytest:
- `trace_id` filter returns matching rows only
- `trace_id` filter combined with `action_type` filter (AND)
- `trace_id` not present → empty list, 200
- Non-admin caller → 403 (existing behavior, regression check)

## 6. Per-section design

### 6.1 Audit (`/admin/audit`) — first-class crisis tool

**Layout:**
```
┌─────────────────────────────────────────────────┐
│ Audit Log                                       │
│                                                 │
│ ┌─────────────────────────────────────────────┐│
│ │ Date: [Last 7d ▾]  Action: [all ▾]          ││
│ │ Admin: [all ▾]  Trace: [______]  [Filter]   ││
│ └─────────────────────────────────────────────┘│
│                                                 │
│ ┌─────────────────────────────────────────────┐│
│ │ Timestamp │ Admin │ Action │ Target │ Trace ││
│ │ ────────  │ ──── │ ────── │ ─────  │ ───── ││
│ │ ...rows                                      ││
│ └─────────────────────────────────────────────┘│
│                                                 │
│ [< Önceki]  Sayfa 3 / 17  [Sonraki >]           │
└─────────────────────────────────────────────────┘
```

**Behavior:**
- Filters URL-synced via `useSearchParams`; clearing filter clears URL param
- `trace_id` cell is clickable → copies to clipboard via `navigator.clipboard.writeText` + sonner toast "Trace ID kopyalandı"
- Each row's `trace_id` is also a "🔍 İlgili kayıtlar" link that filters to that trace
- Pagination is offset-based (matches backend); show "X / Y" page count not infinite scroll
- Empty state: "Bu filtrelerle eşleşen kayıt yok" + "Filtreleri temizle" button
- Loading state: skeleton 5 rows
- Error state: inline card "Audit log alınamadı" + retry button

**Components new:**
- `frontend/src/routes/admin/AuditPage.tsx`
- `frontend/src/components/admin/AdminTable.tsx` (generic; reused by Events, Users)
- `frontend/src/components/admin/DateRangePicker.tsx` (presets + custom)
- `frontend/src/api/queries/admin.ts` (auditLog, systemEvents queries)

**Schemas (`frontend/src/lib/adminSchemas.ts`):**
- `auditLogRowSchema`: id, ts, admin_username, action_type, target_kind, target_id, metadata (record), trace_id
- `auditLogResponseSchema`: rows[], total, limit, offset

### 6.2 System Events (`/admin/events`)

Same shape as Audit but split because:
- Different table (`system_events` vs `admin_audit_log`)
- Different retention (events high-volume, short retention; audit long retention)
- Different consumers (event_type vs action_type)

**Filters:** date presets + `event_type` select + optional `trace_id` (if column present). NO admin_id (events are user-driven).

**Schemas:** `systemEventRowSchema` parallel to audit.

### 6.3 Locks (`/admin/locks`)

**Layout:**
```
┌──────────────────────────────────────┐
│ Document Lock Force-Release          │
│                                      │
│ ⚠ Bu işlem geri alınamaz. Lock'u    │
│   tutan kullanıcı kaydı kaybedebilir.│
│                                      │
│ Document ID: [_______________]       │
│ [ Kilidi Aç ]                        │
└──────────────────────────────────────┘
```

**Behavior:**
- Submit triggers Radix Dialog with typed "RELEASE" confirmation (reuse pattern from `SkipConfirmDialog`)
- Success: sonner toast "Lock açıldı" + clear input
- 404 (no lock on doc): toast.warning "Bu dokümanın aktif lock'u yok"
- Mutation invalidates lock queries elsewhere

**Components new:**
- `frontend/src/routes/admin/LocksPage.tsx`
- Reuses `SkipConfirmDialog` typed-gate pattern via new shared `TypedConfirmDialog` extracted from `SkipConfirmDialog`

**Refactor:** Extract `TypedConfirmDialog` from current `SkipConfirmDialog` so both `SkipConfirmDialog` and lock-release reuse it. Done as part of T2 (Admin foundation).

### 6.4 Users (`/admin/users`)

**Layout:** AdminTable with columns: username, email, role, status, training, last_seen, actions.

**Row actions** (DropdownMenu per row):
- Promote to Admin (only on role=user)
- Demote to User (only on role=admin, gated: cannot demote last admin → backend returns 409, frontend shows toast)
- Disable (only on is_active=true)
- Enable (only on is_active=false)
- Reset Training (always available; opens TypedConfirmDialog with "RESET")

**Top toolbar:**
- Search input (filters table client-side by username/email substring)
- Filter chips: Role (all/admin/user), Status (all/active/disabled), Training (all/passed/in-progress/not-started)
- "Davet Linki Üret" button → `POST /api/users/admin/invite/rotate`, opens Dialog showing new invite code + copy button

**Confirmations:**
- Promote: simple confirm dialog "X kullanıcısını admin yap?"
- Demote: TypedConfirmDialog with "DEMOTE"
- Disable: TypedConfirmDialog with "DISABLE"
- Reset training: TypedConfirmDialog with "RESET"
- Enable: simple confirm (less risky)

**Backend error handling:**
- 409 last-admin demote: toast "Son adminin demote edilemez"
- 404 user not found: toast "Kullanıcı bulunamadı" (race condition between table render + action)
- Other 4xx/5xx: generic toast + console.error for tracing

### 6.5 Settings (`/admin/settings`)

**Layout:**
```
┌─────────────────────────────────┐
│ Runtime Settings                │
│ ┌──────────────────────────────┐│
│ │ training.quiz_pass_threshold ││
│ │ Açıklama: ...                ││
│ │ [4____] (mevcut: 4)          ││
│ │ [Kaydet]                     ││
│ └──────────────────────────────┘│
│ ┌──────────────────────────────┐│
│ │ gamification.xp_doc_save     ││
│ │ ...                          ││
│ └──────────────────────────────┘│
│ ...                              │
└─────────────────────────────────┘
```

**Behavior:**
- Each setting card has: key, description (from backend metadata if present, else just key), current server value, editable input
- Input type from `typeof value`: number → number input, boolean → Switch, string → text input, JSON → disabled (greyed out + "Bu ayar tipi UI'dan düzenlenemez")
- Dirty-state per card: edit button → save/revert action pair; revert restores server value
- Zod schema: `settingValueSchema = z.union([z.number(), z.boolean(), z.string()])`; reject `unknown` at boundary
- Save mutation invalidates settings query

**Grouping:** group cards by prefix (`training.*`, `gamification.*`, `retention.*`) under `<h2>` headers.

### 6.6 Training overrides

#### 6.6.1 Gold Docs (`/admin/training/gold-docs`)

**Layout:** Two-pane: list on left, editor on right.

**List pane:**
- Each gold doc: gold_id, source badge ("Kod tabanı" or "Override" or "Custom"), `is_deleted` badge if tombstoned
- New gold doc button: "+ Yeni Gold Doc" → empty editor with custom gold_id input

**Editor pane (structured form):**
```
┌─────────────────────────────────────────┐
│ Gold ID: gold_kvk1 (read-only)          │
│                                          │
│ İçerik (markdown):                      │
│ [───────── textarea ──────────]         │
│                                          │
│ Beklenen Kavramlar:                     │
│ [─ Concept 1 row ─ + remove]            │
│ [─ Concept 2 row ─ + remove]            │
│ [+ Kavram Ekle]                         │
│                                          │
│ Min Concept Count: [1__]                │
│                                          │
│ [Sil (Tombstone)] [Kaydet] [Vazgeç]    │
└─────────────────────────────────────────┘
```

**Concept row (structured):** kanun_no, kanun_ad, madde, fikra, bent fields (all optional). No raw JSON.

**Save flow:** "Kaydet" → diff modal shows:
- Old expected_concepts (server value)
- New expected_concepts (form)
- Highlighted JSON-like diff (additions green, removals red, modifications yellow)
- "Bu değişiklik tüm gelecek bursiyerlerin training pass/fail sonuçlarını etkileyecek. Devam edilsin mi?"
- TypedConfirmDialog with "OVERRIDE"

**Delete flow:** "Sil (Tombstone)" → TypedConfirmDialog with "DELETE". Soft delete (is_deleted=1), not hard delete.

**Components new:**
- `frontend/src/routes/admin/training/GoldDocsPage.tsx`
- `frontend/src/components/admin/training/GoldDocEditor.tsx`
- `frontend/src/components/admin/training/ConceptRowEditor.tsx`
- `frontend/src/components/admin/DiffPreviewDialog.tsx`

#### 6.6.2 Quiz (`/admin/training/quiz`)

**Layout:** same two-pane.

**Editor:**
- text (textarea)
- choices: 4 string inputs labeled A/B/C/D
- correct_choice_idx: Radio group (0/1/2/3)

**Save flow:** diff modal showing old text/choices/correct_idx vs. new + TypedConfirmDialog with "OVERRIDE"

**Delete:** same tombstone pattern with "DELETE"

## 7. Component Inventory (new files)

### Routes (`frontend/src/routes/admin/`)
- `AuditPage.tsx`
- `EventsPage.tsx`
- `LocksPage.tsx`
- `UsersPage.tsx`
- `SettingsPage.tsx`
- `training/GoldDocsPage.tsx`
- `training/QuizPage.tsx`

### Reusable admin components (`frontend/src/components/admin/`)
- `AdminSidebar.tsx`
- `AdminMobileNav.tsx`
- `AdminTable.tsx`
- `DateRangePicker.tsx`
- `DiffPreviewDialog.tsx`
- `TypedConfirmDialog.tsx` (extracted from existing SkipConfirmDialog)
- `training/GoldDocEditor.tsx`
- `training/QuizEditor.tsx`
- `training/ConceptRowEditor.tsx`
- `users/RoleActions.tsx`
- `users/TrainingActions.tsx`

### API + schemas
- `frontend/src/api/queries/admin.ts` (audit, events, settings, users, locks, training overrides — all admin queries here)
- `frontend/src/lib/adminSchemas.ts` (all Zod schemas)

### Backend additions
- `backend/admin/routes.py`: add `trace_id` query param to audit-log and system-events
- `tests/test_admin_routes.py`: new test cases for trace_id filter

## 8. State management

- TanStack Query for all server state
- URL state for filters (`useSearchParams`) — Audit, Events
- Local component state for editor forms (no Zustand needed; admin editors are self-contained)
- React Hook Form for Settings / Gold Doc / Quiz editors with Zod resolver

## 9. Test plan

### Backend
- `tests/test_admin_routes.py`: trace_id filter (audit + events), invalid trace_id, combined with action_type, non-admin 403 regression

### Frontend per page
For each route page:
1. Renders empty state
2. Renders loading state (skeleton)
3. Renders error state with retry
4. Renders data list with all columns
5. Filter interaction updates URL and refetches
6. Pagination next/prev works

For mutations:
1. Confirmation dialog opens
2. TypedConfirmDialog blocks submit until typed correctly
3. Success → toast + invalidation
4. Backend 4xx → error toast with backend message
5. Backend 5xx → generic toast

For diff dialog:
1. Renders old vs new highlighted
2. Confirms via typed gate
3. Cancel resets

### MSW handlers
- `frontend/src/test/msw-handlers.ts`: add handlers for all admin endpoints (factories for paginated responses with `total`, `limit`, `offset`)

## 10. Accessibility checks

- Sidebar nav uses `<nav aria-label="Admin">` with `<ul>` of links
- AdminTable: `<table role="table">` with `<th scope="col">`
- DropdownMenu (Radix) keyboard nav already correct
- All inputs labeled (`<label htmlFor>`)
- Skip link on AdminLayout for keyboard users (reuse 16c.1 Training skip link pattern)
- TypedConfirmDialog: focus traps work (Radix); typed input has `aria-label`

## 11. Hard constraints (regression protection)

1. NEVER add `rehype-raw` (XSS bypass)
2. NEVER modify `ReferenceCard.tsx` / `ReferencePanel.tsx`
3. Direct-to-main, no branches
4. TDD per task: failing test → impl → green → atomic commit
5. NEVER skip pre-commit hooks (`--no-verify`)
6. Settings page: never persist `unknown` typed values; Zod-validate at boundary
7. Training override save: NEVER write a save mutation without diff confirmation
8. Lock force-release: NEVER allow submit without typed "RELEASE"

## 12. Task decomposition (proposed, ~13 tasks)

| # | Task | Type | Blocks |
|---|------|------|--------|
| 1 | Backend: add `trace_id` filter to `/api/admin/audit-log` + `/api/admin/system-events` (if column present) + tests | BE | 5, 6 |
| 2 | Frontend: `AdminLayout` shell — sidebar nav, mobile selector, redirect /admin → /admin/audit, route scaffolding (all routes stub) + tests | FE foundation | all FE |
| 3 | Frontend: `AdminTable` + `DateRangePicker` + `TypedConfirmDialog` primitives extracted/built + tests | FE foundation | 5–13 |
| 4 | Frontend: `api/queries/admin.ts` + `lib/adminSchemas.ts` + MSW handler factories | FE foundation | 5–13 |
| 5 | Frontend: `AuditPage` — table + filters + pagination + trace_id search + URL sync + tests | FE | — |
| 6 | Frontend: `EventsPage` — same shape as Audit (split from Audit) + tests | FE | — |
| 7 | Frontend: `LocksPage` — input + TypedConfirmDialog + force-release mutation + tests | FE | — |
| 8 | Frontend: `UsersPage` — table + row actions + invite rotate + tests | FE | — |
| 9 | Frontend: `SettingsPage` — list + typed editor + revert + Zod validation + tests | FE | — |
| 10 | Frontend: `DiffPreviewDialog` reusable for both overrides + tests | FE foundation | 11, 12 |
| 11 | Frontend: `GoldDocsPage` + `GoldDocEditor` + `ConceptRowEditor` + diff confirm + tests | FE | — |
| 12 | Frontend: `QuizPage` + `QuizEditor` + diff confirm + tests | FE | — |
| 13 | Polish: lint, typecheck, build, full test suite, manual smoke pass, commit `paket-16e-admin-panel-ui` tag | Verify | — |

**Parallelizable after T2–T4:** 5↔6, 7↔8↔9. T10 must land before 11 and 12.

## 13. Out of scope

- Active locks LIST endpoint (D7)
- Raw JSON override editor (D6)
- Settings revert-to-historical-value (no history endpoint exists)
- Per-action role re-check on frontend (D10)
- Notification DELETE (17d roadmap)
- Quality workflow (17e roadmap)
- Pagination on Users table — initial scope assumes <500 users (verify with backend; if more, add server-side filter in T8)

## 14. Open Codex review questions

1. Are there sequencing risks in landing backend D5 (trace_id filter) before frontend D5 (UI search)? Should the FE search be feature-flagged on T1 commit, or is T5 wave-safe?
2. Is the `TypedConfirmDialog` extraction safe given that `SkipConfirmDialog` (`paket-16c.1`) is already in production-equivalent state? Risk of test-snapshot churn?
3. Should `DiffPreviewDialog` use `react-diff-viewer-continued` (new dep) or hand-roll JSON diff for the override use case? Bundle size vs. clarity.
4. Last-admin demote: is backend 409 the actual response shape, or does it 422 / 400? Need to verify before writing the toast string.
5. `system_events.trace_id` column existence — confirm via migration history during T1.

## 15. Decision log (this spec)

- 2026-05-12 12:00: Codex tradeoff analysis received and reviewed
- 2026-05-12 12:00: User locked priority=crisis, trace_id=backend+UI, override=structured-only, locks=manual-only
- 2026-05-12 12:00: User locked scope=single-paket, audit-filters=full-set
- 2026-05-12 12:00: Defaults from Codex auto-locked (D1, D2, D3, D4)
