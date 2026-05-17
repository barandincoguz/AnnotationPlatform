# POLISH_BACKLOG.md

Generated 2026-05-17 by 5 parallel reviewers. Source files:
`/tmp/polish-security.md`, `/tmp/polish-frontend.md`, `/tmp/polish-backend.md`,
`/tmp/polish-perf-a11y.md`, `/tmp/polish-quality.md`.

Total findings: **Critical 5 · High 28 · Medium 54 · Low 22 · Info 8 = 117**.

This file groups them into actionable batches. Items marked **APPLY** are
in-scope for the polish-phase auto-fix sprint. Items marked **DEFER** are
real findings but exceed polish scope (require new architecture, broad
contract changes, or carry too much risk for unattended application).

---

## Batch 1 — Security Critical / High

| ID | Sev | Area | Description | Verdict |
|----|-----|------|-------------|---------|
| S1 | Critical | backup | `dump_all_tables_to_json` writes `users.password_hash` + `user_sessions.session_token` into snapshots pushed to GitHub | **APPLY** — column whitelist on dump |
| S2 | Critical | csrf | No CSRF/Origin defense — admin POSTs forgeable across origins | **APPLY** — Origin/Referer middleware (~30 lines) |
| S3 | Critical | secrets | `.env.production` ships `admin/admin123456789` + no SESSION_SECRET | **APPLY** — replace with template; add tombstone gate on bootstrap-admin seed |
| S4 | Critical | trust | `X-Forwarded-For` honored unconditionally | **APPLY** — opt-in `TRUST_FORWARDED_FOR=1` env |
| S5 | High | rate-limit | No throttle on `/api/auth/login` / `/register` | **APPLY** — in-memory sliding window |
| S6 | High | backup | Restore brings old creds back live; no forced rotation | **APPLY** — `expire_all_sessions` post-restore |
| S7 | High | session | Session token stored cleartext at rest | **DEFER** — sha256-at-rest is correct but touches every auth call site; S1 nullifies the practical leak |
| S8 | High | csrf | Admin POST empty-body routes | Covered by **S2** |
| S9 | High | cors | Latent CORS+credentials risk | **APPLY** — guard comment only |

## Batch 2 — Frontend Critical / High

| ID | Sev | Area | Description | Verdict |
|----|-----|------|-------------|---------|
| F1 | Critical | useLock | Cleanup beacon uses `window.location.origin`, ignores `VITE_API_BASE_URL` | **APPLY** |
| F2 | High | useDraft | `debouncedSave.cancel` never called on docId change → stale PUT | **APPLY** |
| F3 | High | nextDocId | `pickNextInFeedAcrossPages` recursion has no depth ceiling | **APPLY** |
| F4 | High | AnnotateDoc | Early-return-before-hooks fragile convention | **APPLY** — add lock comment |
| F5 | High | clipboard | Copy fires `toast.success` even on rejection | **APPLY** |
| F6 | High | sort | `'sayi'` dead key — store accepts, menu doesn't render | **APPLY** — remove from type + bump persist version |
| F7 | High | i18n | `team@example.com` placeholder in LockedOutScreen | **APPLY** — remove fake addr |

## Batch 3 — Backend High

| ID | Sev | Area | Description | Verdict |
|----|-----|------|-------------|---------|
| B1 | High | concurrency | `save_annotation` read outside BEGIN — lost-update race | **APPLY** — read inside `BEGIN IMMEDIATE` |
| B2 | High | concurrency | `register()` non-transactional + IntegrityError → 500 | **APPLY** — wrap + catch |
| B3 | High | validation | RotateInvite / Login / SaveAnnotation accept empty/unbounded strings | **APPLY** — `Field(min/max_length)` |
| B4 | High | validation | `PUT /api/drafts/{id}` accepts arbitrary `list[dict]` | **APPLY** — cap length + item size |
| B5 | High | export | CSV cells aren't formula-injection-guarded | **APPLY** — prefix `'` on `= + - @ \t \r` |
| B6 | High | api | Admin audit/events return raw JSON strings | **APPLY** — `json.loads()` on response |

## Batch 4 — Performance / A11y High

| ID | Sev | Area | Description | Verdict |
|----|-----|------|-------------|---------|
| P1 | High | perf | `DocListItem` no `React.memo` + inline onClick → full window re-renders | **APPLY** — memo + stable callback |
| P2 | High | perf | DocList useEffect deps include whole `feed` object | **APPLY** — narrow deps |
| P3 | High | perf | Backend `COUNT(*)` re-runs every page fetch on 17.9k-row anti-join | **APPLY** — return total only on page 0 |
| P4 | High | a11y | Sonner Toaster has no `aria-live` | **APPLY** — set role/aria via props |
| P5 | High | a11y | `AppShell` missing skip-link (admin has one) | **APPLY** |
| P6 | High | perf | Topbar windowFocus thunders 3 requests + 30s polls | **APPLY** — drop windowFocus on profile, bump intervals |

## Batch 5 — Quality / DX High

| ID | Sev | Area | Description | Verdict |
|----|-----|------|-------------|---------|
| Q1 | High | docs | Lock TTL: README + 3 toast strings say 90s, backend default is 300s | **APPLY** — update strings to "5 dakika" |
| Q2 | High | dx | README claims 782 backend / 455 frontend tests, actual 809 / 501 | **APPLY** — replace counts with run commands |
| Q3 | High | quality | `FeedTab` declared twice (store + queries) | **APPLY** — single source |
| Q4 | High | quality | `emptyRef`/kanun-presence regex duplicated 2x | **APPLY** — extract helpers |
| Q5 | High | dx | `gen:types:check` not gated by CI | **DEFER** — new `.github/workflows/` directory exceeds polish scope; record as backlog |

## Safe Mediums (selected)

| ID | Sev | Area | Description | Verdict |
|----|-----|------|-------------|---------|
| M1 | Med | api | `GET /api/documents` no pagination | **APPLY** — add `limit/offset` caps |
| M2 | Med | api | `LastAdminCannotBeRemoved` returns 400 not 409 | **APPLY** |
| M3 | Med | api | Training reset 404 uses bare-string detail | **APPLY** |
| M4 | Med | quality | `mark_all_read` calls `db.commit()` on autocommit | **APPLY** — drop call |
| M5 | Med | quality | SSE route accesses `broker._subscribers` | **APPLY** — use public method |
| M6 | Med | typo | `Döküman` (×2) + `GEÇTI` (×1) | **APPLY** — `Doküman` / `GEÇTİ` |
| M7 | Med | typo | `i̇çerik` combining-dot in GoldDocEditor + tests | **APPLY** — `İçerik` |
| M8 | Med | a11y | DocListItem button has no accessible name | **APPLY** — `aria-label` |
| M9 | Med | a11y | Loading text without `role=status` | **APPLY** — wrap |
| M10 | Med | quality | Stray `print()` in backend production paths | **APPLY** — switch to `logging` |
| M11 | Med | api | `_check_active_invite` runs before uniqueness — leaks invite validity | **APPLY** — reorder |
| M12 | Med | quality | `useSSE` invalidates via bare `['feed']` instead of `feedKeys.all` | **APPLY** |
| M13 | Med | perf | `normalizeOzelgeText` recomputes every render in DocViewer | **APPLY** — `useMemo` |
| M14 | Med | perf | Login page inline style object recreated per keystroke | **APPLY** — hoist |
| M15 | Med | dx | `.env.example` missing `VITE_PROXY_TARGET` | **APPLY** — add commented line |
| M16 | Med | a11y | TypedConfirmDialog doesn't submit on Enter | **APPLY** — wrap in `<form>` |
| M17 | Med | a11y | SortMenu trigger conveys direction via color only | **APPLY** — `aria-label` with text |
| M18 | Med | api | `mark_read` SELECT-then-UPDATE — extra round-trip | **APPLY** |

## Selected Low / Trivial

| ID | Sev | Description | Verdict |
|----|-----|-------------|---------|
| L1 | Low | Empty `annotations.db` tracked despite gitignore | **APPLY** — `git rm --cached` |
| L2 | Low | DocListItem renders raw YYYYMMDD; DocViewer uses formatYmd | **APPLY** — unify |
| L3 | Low | `auth.spec.ts` meta-test asserts constant equals its literal | **APPLY** — delete dead test |

## Out of Polish Scope (DEFER list)

- S7 session-token-hash-at-rest (broad refactor)
- Q5 add `.github/workflows/` CI (new infrastructure)
- Bundle reorg under `lib/schemas/` (mechanical, ~30 imports moved)
- Session-cookie `__Host-` prefix (would break staging deploys)
- Password complexity rules (UX scope creep)
- Common-password dictionary load (new dependency)
- SPA path-traversal symlink edge case (no current user-upload surface)
- PAT in `.git/config` → git credential helper (touches credential plumbing)
- Vitest coverage thresholds — keep but document; ratcheting up would surface real gaps requiring new tests
- DocList full virtualization sweep — already virtualized; only memo gap is in scope
- Custom-id keys on reference cards (requires `useReferencesState` reducer audit)
- Restructure `lib/` into `lib/schemas/`, `lib/text/` — mechanical, not polish

---

## Application Order (commit boundaries)

1. **commit 1** — Batch 1 security (5 items) — already started with `97be06d`
2. **commit 2** — Batch 3 backend transactions + validators (B1–B6)
3. **commit 3** — Batch 2 frontend critical/high (F1–F7)
4. **commit 4** — Batch 4 perf + a11y high (P1–P6)
5. **commit 5** — Batch 5 docs/quality high (Q1–Q4)
6. **commit 6** — Safe mediums (M1–M18)
7. **commit 7** — Trivial lows + dead code (L1–L3)

Each commit runs lint + typecheck + relevant tests before landing.
