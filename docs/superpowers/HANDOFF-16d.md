# HANDOFF — Paket 16d Gamification UI

**Tarih**: 2026-05-11
**Repo**: `/Users/barandincoguz/Desktop/deneme` on `main`
**Son commit**: `9b3911c spec(paket-16d): gamification UI design`

## TL;DR — İlk 30 Saniye

1. Sen Türkiye Gelir İdaresi Başkanlığı özelge (tax ruling) anotasyon platformunun frontend'ini geliştiriyorsun. Bursiyer crowdsourced annotation; tax practitioner search index.
2. 15 backend paketi + 16a/16b/16c frontend paketleri shipped. **16d spec yazıldı, plan yazılmadı.** Sıradaki adım: writing-plans skill → subagent-driven-development execute.
3. **Spec**: `docs/superpowers/specs/2026-05-11-paket-16d-gamification-ui-design.md` (1162 satır, 18 bölüm, 3 Codex pass'i entegre).
4. **Kullanıcı pre-approved autonomous execution**. Onay duraklatması istemiyor (`"onayladım, plan yaz ve execute et"` desenli).
5. İlk eylem: Spec'i oku → writing-plans skill'i çağır → 16d plan'ini yaz → SDD ile execute et.

---

## 1. Proje Bağlamı

- **Domain**: Crowdsourced annotation of Turkish Tax Administration (Gelir İdaresi Başkanlığı) tax rulings ("özelge"). Bursiyer (scholarship student) annotators extract law references from ruling documents to build a search index for tax practitioners.
- **Scale**: 18K target docs, 2-30 concurrent users.
- **Backend stack**: Python 3.13 (Docker uses 3.11 — Codex flagged), FastAPI, SQLite (WAL+FK+busy timeout), Pydantic v2.
- **Frontend stack**: React 18, Vite 5, TypeScript strict, TanStack Query 5, Zustand 4 (persist + sessionStorage), Tailwind, shadcn/ui (Radix), Vitest + MSW v2, Zod (runtime validation), sonner (toasts), react-markdown + remark-gfm + rehype-sanitize (XSS-safe; **NEVER add rehype-raw**).
- **Auth**: cookie-session (`credentials: 'include'`). No CSRF currently (Codex flagged for Dalga 2).

---

## 2. Shipped State — Tags + Tests

| Tag | Date | Tests |
|---|---|---|
| `paket-1-foundation` through `paket-15-docker` | Backend complete | 741 backend pass (Dalga 1 hardening sonrası) |
| `paket-16a-frontend-foundation` | foundation, gates, AppShell, MSW | 53 fe tests |
| `paket-16b-annotate-workflow` | 3-col annotate, lock, draft, SSE, references | 126 fe tests |
| `paket-16c-onboarding` | help viewer, training wizard, all Codex fixes | 244 fe tests at tag |
| (Dalga 1 hardening, on top of 16c) | validation, lock ownership, admin guards | **258 fe / 741 be** at HEAD |

### Recent commits (top 10)

```
9b3911c spec(paket-16d): gamification UI design — TopBar + Profile + SSE personals
e078904 fix(ui): TR-friendly reference field labels
0815700 chore(backend): drop unused sqlite3+bootstrap_admin from B4 test
37b9a4b fix(backend): admin validation hardening (B3+B4)
b9ce03f fix(backend): lock ownership enforcement + atomic acquire (B1+B2)
a3f8391 fix(paket-16b+c): shared reference validation, 16b parity
8e812c0 fix(paket-16c): training validation accepts kanun_ad-only refs
c9ef7c5 chore(paket-16c): tag paket-16c-onboarding
6f74617 feat(paket-16c): Training route + integration
d5f4543 feat(paket-16c): LockedOut + PendingStartBanner
```

---

## 3. Established Workflow Patterns (CRITICAL — User Preferences)

1. **Direct-to-main, NO branches/worktrees**. User explicitly chose this from 16a onward.
2. **Brainstorming → spec → plan → execute** cycle per package. Use `superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:subagent-driven-development` skills.
3. **Section-by-section design presentation** during brainstorming. Wait for user "mantıklı" approval per section. Don't dump 6 sections at once.
4. **Codex consultation generously** — adversarial review after major design sections is the standard pattern. Use `codex:codex-rescue` subagent. Medium effort default. After each Codex pass, integrate findings before moving on.
5. **Multiple Codex passes per spec**: 16a had 11 rounds, 16b had 1 (with 18 findings), 16c had 2 passes (15 findings total), 16d had 3 passes (19 findings). Don't skimp.
6. **User pre-approves autonomous execution** with phrases like "onayladım, plan yaz ve execute et", "ne varsa execute et", "duraklamadan devam et". Do NOT pause for confirmation between tasks once plan is approved.
7. **Per-task subagent dispatch + 2-stage review**: implementer subagent → spec compliance reviewer → code quality reviewer. Fresh subagent per task. Don't make subagents read plan file — provide full task text inline.
8. **Model selection**: haiku for mechanical (label rename, single file create with full spec); sonnet for integration (multi-file refactor, route wiring); opus for architecture/design.
9. **Test coverage ≥80% per metric** (statements/branches/functions/lines). 16a-c maintained 85-88%.
10. **Commit message style**: conventional commits (feat/fix/chore/spec/plan/refactor). Multi-line body explaining the WHY. Co-Authored-By footer (Claude Opus 4.7).
11. **Spec → docs/superpowers/specs/YYYY-MM-DD-name.md**. Plan → docs/superpowers/plans/YYYY-MM-DD-name.md.
12. **ASCII previews in AskUserQuestion** for layout decisions. The `preview` field is a powerful UX clarifier — use it for visual choices.
13. **TR/EN code-switching**: user mostly Turkish but switches to English mid-sentence. Match their register.
14. **"Tertemiz giriş" requests** mean: kill stale dev servers, clear caches (`node_modules/.vite`, `vite.config.js` artifacts, `backend/static`, `__pycache__`), restart fresh. Document this in 16b history.

---

## 4. Active Dev Servers

Verify and restart if needed at session start:

```bash
# Check if running
lsof -ti :8000 :5173 || echo "ports clean"

# If not running, start them
DATA_DIR=./deneme-dev/data DISABLE_SPA_MOUNT=1 .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload   # background
cd frontend && npm run dev   # background
```

**DB state**: `deneme-dev/data/db/annotations.db`
- Test users with `flags=1` (has_seen_manual + has_passed_training both 1): `admin`, `tester`, `barandincoguz@gmail.com`, `testbot`, `e2e16c`
- Invite code: `SETUP-INVITE`
- 4 docs + 4 annotations seeded

---

## 5. Current Package: 16d Gamification UI

### What 16d does
- TopBar widget in AppShell: logo + XP/streak/today/online + profile dropdown (avatar + bell counter + Profilim/Yardım/Çıkış)
- Profile page (/me) replaces 16a STUB: single scroll, ProfileHeader + 4 StatCards + BadgesGrid (Kazanılmış / Hepsi tabs) + NotificationsList
- useSSE extended (16b's pattern) for: badge_unlocked (celebration toast 15s, NO action button), speed_warning + char_limit_warning (gentle toast 8s), user_online/user_offline
- Bell counter with last-10 dropdown + "Tümünü okundu yap"

### Backend touches (3 endpoints + 2 SSE + 1 dict field — all justified, Codex-validated)
1. `GET /api/users/online` — auth required, returns `[{id, username, avatar_color}]` from `broker.online_user_ids()`
2. `GET /api/badges/catalog` — auth required, returns 7 entries with optional `criterion` field (imperative, for locked badges)
3. `POST /api/me/notifications/read-all` — atomic UPDATE, returns `{marked_count}`
4. SSE broker emits `user_online` (on subscribe, via `publish_to_others` to skip self-echo) and `user_offline` (on unsubscribe AND on QueueFull drop path)
5. **BROKER HARDENING (CRITICAL — Codex BROKEN finding)**: `q.put_nowait()` QueueFull path must call `unsubscribe()` and emit `user_offline` before exiting. Currently the dead queue stays in `_subscribers` dict — ghost online users.
6. `BADGE_DEFS` dict gains optional `criterion: str` field per badge.

### Spec status
- **Written**: `docs/superpowers/specs/2026-05-11-paket-16d-gamification-ui-design.md`
- **Self-reviewed**: clean (no TBD/TODO/FIXME), 1162 lines, 18 sections, 3 Codex passes integrated (11 BROKEN + 8 FRAGILE fixed)
- **User approval**: NOT YET CONFIRMED in current conversation when session ended. User asked for handoff to new conversation BEFORE final approval. **In new session, ask user to confirm spec approval before running writing-plans skill.**

### Locked design decisions (from Q&A — DO NOT re-litigate)
| # | Decision |
|---|---|
| D1 | TopBar = full bar (logo + stats + online + profile) |
| D2 | Online users = backend endpoint + 30s polling + SSE merge |
| D3 | Warnings = gentle toast (8s); Badge = celebration toast (15s, INFORMATIONAL ONLY, no action button — Codex BROKEN-B fix) |
| D4 | Profile /me = single scroll, no tabs |
| D5 | Locked badges = grayscale + 🔒 + `criterion` text |
| D6 | Mark-all-read = backend endpoint |
| D7 | refetchInterval:30_000 on useUnreadNotifications + useOnlineUsers (staleTime ≠ polling — Codex BROKEN-D, BROKEN-E) |

---

## 6. After 16d Roadmap

- **16e Admin Panel UI** — /admin/* routes. Users CRUD, AuditLog (with trace_id), Locks force-release, Training overrides, Settings. Backend ready (Paket 11). Codex Dalga 1 B1-B4 fixes can be verified through UI here.
- **16f Docker multi-stage** — Python 3.13 reconcile + frontend build copy + SPA serve. Fixes Codex B6.
- **17a Domain norm** — Tebliğ/Sirküler/BKK as first-class annotation types; Türkçe atıf normalizer ("Geçici 67", "5/1-a", "Mükerrer 80").
- **17b SSE hardening** — Last-Event-ID replay, backpressure, proper id: per event.
- **17c source_text offset/range** — link annotation to document offsets, not free text.
- **17d Notification DELETE** — let users clean stale read items.
- **17e Quality workflow** — majority/second-reviewer for annotations.

---

## 7. Things to NEVER Do (Regressions)

1. **NEVER add `rehype-raw`** to frontend deps. Bypasses XSS sanitize. Spec §7.2 of 16c explicit ban.
2. **NEVER modify `frontend/src/components/annotation/ReferenceCard.tsx` or `ReferencePanel.tsx`** without explicit user instruction. 16b regression risk; the 16d spec assumes byte-identical.
3. **NEVER use `--no-verify` on git commits** or skip hooks unless user explicitly requests.
4. **NEVER skip Codex adversarial loop** on major design sections. The user expects it.
5. **NEVER add new client-side validation rules to 16b annotation save flow** without checking the shared `lib/validateReferences.ts` first (added in Dalga 1 — `isValidReference()` + `areAllReferencesValid()`).
6. **NEVER touch `vite.config.js`/`.d.ts` if they appear** — they're stale composite TypeScript emit artifacts. The build script is `tsc --noEmit && vite build` precisely to prevent this. If artifacts reappear, delete them + investigate.
7. **NEVER add `branches` to the workflow.** Direct-to-main is the user's chosen pattern.

---

## 8. Files the Next Session Should Read First

Priority order (read in this order if you need full context):

1. `docs/superpowers/specs/2026-05-11-paket-16d-gamification-ui-design.md` — the spec (just-written)
2. `frontend/src/hooks/useSSE.ts` — 16b SSE pattern; 16d will refactor into orchestrator
3. `frontend/src/components/shell/AppShell.tsx` — currently placeholder; 16d adds TopBar
4. `frontend/src/routes/Profile.tsx` — STUB; 16d replaces
5. `backend/shared/sse.py` — broker (16d hardens QueueFull path)
6. `backend/gamification/models.py` + `backend/gamification/badges.py` — ProfileResponse + BADGE_DEFS
7. `backend/notifications/routes.py` — notification endpoints (16d adds /read-all)
8. `frontend/src/test/msw-handlers.ts` — handler patterns (16d adds factories)
9. `docs/superpowers/specs/2026-05-11-paket-16c-onboarding-design.md` — read §7 for MarkdownView pattern reuse + §11 for Zod schema pattern
10. `docs/superpowers/plans/2026-05-11-package-16c-onboarding.md` — read for plan structure precedent

---

## 9. Codex Consultation Pattern

### When to consult
- After each major design section (architecture, state machine, per-step components)
- Before writing spec (sanity check on full design)
- After plan is written (optional)
- When stuck or low confidence

### How to consult
- Use `codex:codex-rescue` subagent (Agent tool with `subagent_type: codex:codex-rescue`)
- Medium effort by default; high effort for full system review
- Provide RICH context: backend contract, frontend constraints, design decisions, prior Codex findings already integrated (so it doesn't repeat itself), explicit questions

### Prompt template
```
[Adversarial check or full review]. Medium effort.

## CONTEXT
- Project: …
- Stack: …
- Working directory: /Users/barandincoguz/Desktop/deneme

## BACKEND CONTRACT (locked)
[exact endpoint shapes, payloads]

## DESIGN DECISIONS (locked, do not re-litigate)
[bulleted list]

## PRIOR CODEX FINDINGS ALREADY INTEGRATED
[bulleted list of fixes already applied]

## QUESTIONS
[numbered list of specific concerns]

Format: short bullets. BROKEN first, then FRAGILE. Max N items.
```

---

## 10. Codex Deep Review (post-16c) — Outstanding Items

The Codex full-system review on 2026-05-11 (after 16c tag) flagged these. Dalga 1 fixed 4 of them; remaining items per dalga:

### Dalga 1 (DONE — commits b9ce03f, 37b9a4b, 0815700)
- ✅ B1 Lock ownership on save/complete
- ✅ B2 Atomic lock acquire (`BEGIN IMMEDIATE`)
- ✅ B3 Admin quiz/gold validation (Pydantic validators)
- ✅ B4 enable_user existence check

### Dalga 2 (in progress — 16d is part of it)
- 🔄 **16d Gamification UI** — current
- ⏳ 16e Admin Panel UI
- ⏳ 16f Docker multi-stage + Python 3.13 (B6)
- ⏳ Export version history (B7)
- ⏳ CSRF protection
- ⏳ X-Forwarded-For trust boundary

### Dalga 3 (Paket 17 series)
- ⏳ Norm modeling (Tebliğ/Sirküler/BKK)
- ⏳ Türkçe atıf normalizer
- ⏳ source_text offset/range
- ⏳ Majority/second-reviewer workflow
- ⏳ SSE replay (Last-Event-ID)
- ⏳ Notification DELETE
- ⏳ Pre-training notification visibility

---

## 11. Test Database State

`deneme-dev/data/db/annotations.db`:
- Users (flags=1): admin, tester, barandincoguz@gmail.com, testbot, e2e16c
- Invite code: `SETUP-INVITE`
- 4 docs + 4 annotations seeded
- Some users have earned badges + history (verify with `sqlite3 deneme-dev/data/db/annotations.db "SELECT user_id, COUNT(*) FROM badges_earned GROUP BY user_id"`)

For 16d testing, the most useful user is one with:
- Some XP (>100)
- Some streak (≥3 days)
- Some earned badges (≥2)
- Some unread notifications

If no such user exists, create one via DB seeding or by running E2E flow manually.

---

## 12. Immediate Next Action

```
1. Read docs/superpowers/specs/2026-05-11-paket-16d-gamification-ui-design.md fully.
2. Ask user: "Spec onaylandı mı? Writing-plans'a geçeyim mi?"
3. If approved: invoke superpowers:writing-plans skill with the spec.
4. After plan is written + committed: invoke superpowers:subagent-driven-development.
5. Per-task: dispatch implementer → spec-reviewer → code-quality-reviewer subagent (haiku/sonnet by complexity).
6. After all tasks: full suite + coverage check + tag paket-16d-gamification-ui.
```

Pre-approved: user said "writing plansa geçmeden önce" — meaning approval is implicit after handoff transition. **Confirm once on first message of new session**, then proceed autonomously.

---

## 13. Communication Style Notes

- **Turkish primarily**, but you can match the user's register (TR↔EN code-switch is fine)
- **Concise updates**: 1-2 sentences per progress, not paragraphs
- **No "Should I continue?" prompts** during approved execution
- **State results and decisions directly** — don't narrate deliberation
- **Show what's running**: when starting a subagent or background task, briefly say what it's doing
- **Trust but verify**: after each subagent dispatch, verify with `git log -1` or `npm run test:run` before claiming success

---

## 14. Glossary (Domain)

- **Özelge**: Tax ruling document issued by Turkish Tax Administration
- **Bursiyer**: Scholarship student who annotates as part of their program
- **Mükellef**: Taxpayer
- **Kanun**: Law (e.g., VUK = Vergi Usul Kanunu, KDV = Katma Değer Vergisi)
- **Madde / Fıkra / Bent**: Article / Paragraph / Clause — Turkish legal structure
- **Geçici / Mükerrer madde**: Provisional / Repeated article numbering (e.g., "Geçici 67", "Mükerrer 80")
- **Tebliğ / Sirküler / BKK**: Communiqué / Circular / Council of Ministers Decision — other tax instrument types (NOT yet first-class in our model — Codex flagged)
- **Anotasyon**: Annotation — 6-field reference (kanun_no, kanun_ad, madde, fikra, bent, source_text)
- **Kilit (lock)**: Per-document lock, 30s heartbeat, 5min auto-expiry

---

**End of handoff. New session: read this file first, then the 16d spec, then ask user for go-ahead.**
