# Çok-Kullanıcılı Annotation Platformu — Tasarım Dökümanı

**Tarih:** 2026-05-05
**Durum:** Taslak — kullanıcı incelemesi bekliyor
**Önceki spec:** `2026-05-05-soru-anotasyon-araci-design.md` (tek-kullanıcılı yerel araç — bu spec onun yerine geçer / üstüne çıkar)

## Amaç

Bursiyer ekibinin Türkçe vergi/idari özelgelerinden 3 soru çıkararak yapılandırılmış veri üreten, çok-kullanıcılı, web tabanlı, oyunlaştırılmış bir anotasyon platformu. Mevcut tek-kullanıcılı yerel araç bu platforma evrilir.

## Problem & Bağlam

- 18.000+ özelge dokümanı için manuel soru çıkarma anotasyonu gerekiyor
- Birden fazla bursiyer eşzamanlı çalışacak (2-5 başlangıç, talebe göre 10-30'a çıkabilir)
- Anotasyonlar arasında tutarsızlık riski → chain review modeli ile inter-rater quality
- Veri kaybı sıfır olmalı (çift-katmanlı backup)
- Bursiyer motivasyonu için gamification ama "yarış değil kalite" kültürü
- Bursiyer giriş kalitesini garanti için training gate (eğitim testi)
- Sistem deploy-agnostic olmalı: Docker → HF Spaces, self-host, başka PaaS

## Kapsam Dışı

- Çok-tenant SaaS (tek kuruluş, tek instance)
- Tek dokümanın gerçek-zamanlı eş-düzenlenmesi (Google Docs tarzı)
- LLM tabanlı otomatik soru çıkarma (manuel etiketleme aracı)
- Mobile uygulamalar (sadece responsive web)
- E-mail bildirimleri v1'de yok (sadece in-app)
- Çoklu dil (sadece Türkçe arayüz, Türkçe içerik)
- 100+ eşzamanlı kullanıcı (gelirse PostgreSQL'e geçiş, şema aynı kalır)

## Tech Stack & Architecture

```
┌─────────────────────────────────────────────────────┐
│  Docker container (deployment-agnostic)              │
│  ┌───────────────────────────────────────┐          │
│  │  FastAPI + Uvicorn                     │          │
│  │  ├─ HTTP REST API                      │          │
│  │  ├─ Server-Sent Events (SSE)           │          │
│  │  └─ Static file serving (frontend)     │          │
│  ├───────────────────────────────────────┤          │
│  │  SQLite (WAL mode) — primary DB        │          │
│  │  Background workers:                   │          │
│  │  ├─ Backup loop (10-15 min)            │          │
│  │  ├─ Lock expiry sweep (1 min)          │          │
│  │  ├─ Streak roll-over (00:00 UTC+3)     │          │
│  │  └─ Retention archival (daily)         │          │
│  └───────────────┬───────────────────────┘          │
│                  │                                   │
│  Volume: /data/ (Docker named volume)                │
│  ├─ db/annotations.db                                │
│  ├─ documents/  (kullanıcı yükler)                   │
│  └─ backup/     (10-15dk snapshot rotation)          │
└────────────────┬─────────────────────────────────────┘
                 │ git push (her 10-15dk)
                 ▼
        ┌────────────────────────┐
        │  GitHub private repo   │
        │  anotasyon-backup/     │
        │  └─ backup/*.json      │
        └────────────────────────┘
```

**Frontend:** **React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui** (build edilen SPA, FastAPI'nin static mount'undan servis edilir). Detayları aşağıdaki "Frontend Architecture" bölümünde.
**Auth:** Session cookie (HttpOnly, SameSite=Lax) + bcrypt password hash
**Live updates:** SSE (Server-Sent Events) — tek-yön, basit, ihtiyaca yeter

## Major Decisions (özet tablo)

| Konu | Karar | Rationale |
|---|---|---|
| Ölçek | 2-30 kullanıcı | Bursiyer ekibi, gerekirse 100'e ölçeklenir |
| DB | SQLite + WAL | 30 kullanıcıya rahat, taşınabilir, şema PostgreSQL'e bire bir uyumlu |
| Live updates | SSE | Tek yön yeterli, WS karmaşıklığına gerek yok |
| Review modeli | Chain (Option 3) | Yaratıcılığı bozmaz, attribution net, diff doğal |
| Doc completion | Soft `is_completed` tag | Kilit yok, sürekli evrim, kullanıcı isterse işaretler |
| Shuffle | 3-sekmeli (Review default, Yeni shuffled, Doğruladıklarım) | Bursiyere kontrol, istatistiksel doğruluk |
| Lock | Heartbeat, 5dk idle release, queue YOK | "Başka doc seç" yeterli, queue overkill |
| Auth | Tek davet kodu (rotate edilebilir) | Bursiyer ekibi için en pratik |
| Admin | Multi-admin, manuel DB bootstrap, son-admin guardrail | Güvenli, basit |
| Training | 5 quiz + 3 gold-doc, 3 deneme, lifetime pass | Otomatik puanlama, manuel müdahale yok |
| Gold puanlama | Concept-keyword matching | Embedding/LLM gereksiz |
| Behavioral | Tüm eşikler `site_settings`'de admin-configurable | Hard-code yok |
| Tekrar göstergesi | Sadece seans aktivite sayaçları | "Gözetlendiği hissi" minimal |
| Metadata | 6 alan (doc_id, created_at, word_count, ozelge_no, topic, density, difficulty) | Statik, annotation-bağımsız |
| Gamification | Minimum + 20 doc/gün hedef + 7 rozet, leaderboard YOK | Yarış değil kalite |
| Backup | Her 10-15dk: lokal + GitHub private repo | Çift-katman, deployment-agnostic |
| Restore | Manuel CLI (`python -m backend.cli restore-from-github`) | Production'da güvenli |
| First-time UX | Login → kılavuz görme zorunlu (`has_seen_manual=False` ise redirect) | Bursiyer hazırlığı |
| Frontend stack | React 18 + Vite + TypeScript + Tailwind + shadcn/ui | Bursiyer ekosistemi tanıdık, type safety, hazır component'ler, virtual scroll, SSE hook'ları |

---

## Frontend Architecture

### Tech Stack

| Kütüphane | Sürüm | Amaç |
|---|---|---|
| React | 18 | UI framework |
| Vite | 5 | Build tool, HMR, dev server |
| TypeScript | 5 | Type safety |
| Tailwind CSS | 3 | Utility-first CSS |
| shadcn/ui | latest | Radix tabanlı copy-paste component primitives |
| React Router | 6 | Client-side routing |
| TanStack Query | 5 | Server state, cache, request deduplication |
| Zustand | 4 | Hafif client state (auth, UI) |
| react-hook-form + zod | 7+3 | Form validation (login, register, training quiz) |
| @tanstack/react-virtual | 3 | 18K dokümanlık liste virtual scroll |
| sonner | latest | Toast notifications (shadcn ile entegre) |
| openapi-typescript | latest | FastAPI OpenAPI'den TS tip üretimi |
| date-fns | latest | TR locale tarih formatlama |
| lucide-react | latest | Icon set (shadcn uyumlu) |

**Seçim mantığı:** Zustand orta yol (Redux overkill, Context yetmez); TanStack Query SSE ile uyumlu cache invalidation; shadcn/ui copy-paste ile özelleştirilebilir; react-virtual 18K liste için battle-tested; tek form lib (react-hook-form + zod) tüm formlar için.

### Folder Structure

```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.js
├── components.json              # shadcn/ui config
├── index.html
└── src/
    ├── main.tsx                 # React + Router entry
    ├── App.tsx                  # Route tree, providers (QueryClient, Auth, Toast)
    │
    ├── routes/
    │   ├── Login.tsx
    │   ├── Register.tsx
    │   ├── Help.tsx             # /help (manual gate destination)
    │   ├── Training.tsx         # /training quiz + 3 gold doc
    │   ├── Annotate.tsx         # / ana ekran (3 sekme)
    │   ├── Profile.tsx          # /me XP, streak, rozetler
    │   └── admin/
    │       ├── AdminLayout.tsx
    │       ├── Users.tsx
    │       ├── AuditLog.tsx
    │       ├── Settings.tsx
    │       └── Locks.tsx
    │
    ├── components/
    │   ├── ui/                  # shadcn primitives (button, dialog, sheet, ...)
    │   ├── annotation/
    │   │   ├── DocList.tsx              # virtual scroll sol kolon
    │   │   ├── DocViewer.tsx            # orta okuma alanı
    │   │   ├── QuestionPanel.tsx        # sağ 3 textarea + Sakla/Atla
    │   │   ├── AttributionLabel.tsx     # "Ahmet · 2 saat önce"
    │   │   └── LockBadge.tsx            # 🔒 + tooltip
    │   ├── topbar/
    │   │   ├── TopBar.tsx
    │   │   ├── XpBadge.tsx
    │   │   ├── StreakCounter.tsx
    │   │   ├── DailyProgress.tsx
    │   │   └── OnlineUsers.tsx          # avatar listesi
    │   ├── modals/
    │   │   ├── LockConflictModal.tsx
    │   │   ├── BadgeUnlockedToast.tsx
    │   │   └── SpeedWarningToast.tsx
    │   └── ManualGate.tsx               # has_seen_manual=false redirector
    │
    ├── hooks/
    │   ├── useAuth.ts                   # session, current user
    │   ├── useSSE.ts                    # event stream subscription
    │   ├── useDoc.ts                    # document fetch + cache invalidation
    │   ├── useDraft.ts                  # debounced auto-save (2sn)
    │   ├── useLock.ts                   # heartbeat + release lifecycle
    │   ├── useShortcuts.ts              # Ctrl+Enter, Ctrl+K, vs.
    │   └── useGamification.ts           # XP, streak, rozetler
    │
    ├── api/
    │   ├── client.ts                    # fetch wrapper, error handling
    │   ├── types.ts                     # openapi-typescript çıktısı (otomatik)
    │   └── endpoints/
    │       ├── auth.ts
    │       ├── docs.ts
    │       ├── annotations.ts
    │       ├── locks.ts
    │       ├── training.ts
    │       └── admin.ts
    │
    ├── stores/                          # Zustand
    │   ├── authStore.ts
    │   └── uiStore.ts                   # tab seçimi, modal state
    │
    ├── lib/
    │   ├── utils.ts                     # shadcn cn() helper
    │   ├── formatters.ts                # tarih, sayı (TR locale)
    │   └── shortcuts.ts                 # klavye kısayolu kayıt sistemi
    │
    └── styles/
        └── globals.css                  # Tailwind directives + shadcn vars
```

### Routing & Gates

```tsx
// App.tsx
<Routes>
  <Route path="/login" element={<Login />} />
  <Route path="/register" element={<Register />} />
  <Route element={<RequireAuth />}>
    <Route element={<RequireSeenManual />}>
      <Route element={<RequirePassedTraining />}>
        <Route path="/" element={<Annotate />} />
        <Route path="/me" element={<Profile />} />
      </Route>
      <Route path="/training" element={<Training />} />
    </Route>
    <Route path="/help" element={<Help />} />
    <Route path="/admin/*" element={<RequireAdmin><AdminLayout/></RequireAdmin>} />
  </Route>
</Routes>
```

Wrapper'lar:
- `RequireAuth`: session yoksa `/login`'e
- `RequireSeenManual`: `has_seen_manual=false` ise `/help?first_time=true`
- `RequirePassedTraining`: `has_passed_training=false` ise `/training`
- `RequireAdmin`: admin değilse 404

### SSE Integration Pattern

```ts
// hooks/useSSE.ts
function useSSE() {
  const queryClient = useQueryClient()
  useEffect(() => {
    const es = new EventSource('/api/events')
    es.addEventListener('lock_acquired', () => {
      queryClient.invalidateQueries({ queryKey: ['locks'] })
    })
    es.addEventListener('badge_unlocked', (e) => {
      const data = JSON.parse(e.data)
      toast.success(`Yeni rozet: ${data.name}`)
      queryClient.invalidateQueries({ queryKey: ['profile'] })
    })
    es.addEventListener('speed_warning', (e) => {
      toast.warning(JSON.parse(e.data).message)
    })
    es.addEventListener('presence', (e) => {
      queryClient.setQueryData(['presence'], JSON.parse(e.data))
    })
    return () => es.close()
  }, [])
}
```

### Auto-Save Pattern

```ts
// hooks/useDraft.ts
function useDraft(docId: string, questions: [string, string, string]) {
  const debounced = useDebouncedValue(questions, 2000)
  useEffect(() => {
    if (!docId) return
    putDraft(docId, debounced)
  }, [debounced, docId])
}
```

### Lock Heartbeat Pattern

```ts
// hooks/useLock.ts
function useLock(docId: string, isFocused: boolean) {
  // mount → POST /api/locks/{docId}/acquire
  // every 30s while isFocused → POST /api/locks/{docId}/heartbeat
  // unmount or save/skip → POST /api/locks/{docId}/release
  // 409 ise modal aç (LockConflictModal)
}
```

### Type Generation (Backend → Frontend)

`/api/openapi.json`'dan otomatik tip:
```json
"scripts": {
  "gen:types": "openapi-typescript http://localhost:8000/openapi.json -o src/api/types.ts"
}
```

Backend Pydantic modelleri değişince `npm run gen:types` ile frontend tipleri senkronize. CI'da bir adım olarak da koşturulabilir.

### Vite Config (Dev Proxy)

```ts
// vite.config.ts
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
  },
})
```

- **Dev:** Vite 5173 + FastAPI 8000, proxy ile tek origin gibi davranır
- **Prod:** `npm run build` → `backend/static/`, FastAPI tek port'tan SPA + API serve eder

---

## Şema (18 tablo, 4 domain)

### A. Core — "data of record" (8 tablo)

```sql
-- 1. users
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    email           TEXT UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
    is_active       INTEGER NOT NULL DEFAULT 1,
    has_passed_training  INTEGER NOT NULL DEFAULT 0,
    has_seen_manual INTEGER NOT NULL DEFAULT 0,
    avatar_color    TEXT,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_users_active ON users(is_active);
CREATE INDEX idx_users_role ON users(role);

-- 2. invite_codes
CREATE TABLE invite_codes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_by_admin_id INTEGER REFERENCES users(id),
    rotated_at      TIMESTAMP,
    created_at      TIMESTAMP NOT NULL
);
CREATE UNIQUE INDEX idx_invite_active ON invite_codes(is_active) WHERE is_active=1;

-- 3. site_settings (key-value JSON)
CREATE TABLE site_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMP NOT NULL,
    updated_by_user_id INTEGER REFERENCES users(id)
);

-- 4. documents_meta
CREATE TABLE documents_meta (
    document_id     TEXT PRIMARY KEY,
    file_path       TEXT NOT NULL,
    word_count      INTEGER NOT NULL,
    sentence_count  INTEGER NOT NULL,
    text_density    REAL NOT NULL,
    estimated_difficulty TEXT NOT NULL CHECK(estimated_difficulty IN ('Kolay','Orta','Zor')),
    ozelge_no       TEXT,
    topic_category  TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_docs_difficulty ON documents_meta(estimated_difficulty);
CREATE INDEX idx_docs_topic ON documents_meta(topic_category);
CREATE INDEX idx_docs_ozelge ON documents_meta(ozelge_no);

-- 5. annotations (CURRENT)
CREATE TABLE annotations (
    document_id     TEXT PRIMARY KEY REFERENCES documents_meta(document_id),
    question_1      TEXT,
    question_2      TEXT,
    question_3      TEXT,
    is_completed    INTEGER NOT NULL DEFAULT 0,
    last_editor_user_id INTEGER REFERENCES users(id),
    completed_by_user_id INTEGER REFERENCES users(id),
    edit_count      INTEGER NOT NULL DEFAULT 0,
    unique_users_count INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_ann_completed ON annotations(is_completed);
CREATE INDEX idx_ann_editor ON annotations(last_editor_user_id);

-- 6. annotation_versions (HISTORY, append-only)
CREATE TABLE annotation_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     TEXT NOT NULL REFERENCES documents_meta(document_id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    question_1      TEXT,
    question_2      TEXT,
    question_3      TEXT,
    diff_from_previous TEXT,                       -- JSON
    is_diff_zero    INTEGER NOT NULL DEFAULT 0,
    action          TEXT NOT NULL,                 -- 'create','edit','complete_mark','uncomplete'
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_ver_doc_time ON annotation_versions(document_id, created_at DESC);
CREATE INDEX idx_ver_user_time ON annotation_versions(user_id, created_at DESC);
CREATE INDEX idx_ver_diff_zero ON annotation_versions(is_diff_zero);

-- 7. drafts (per-user)
CREATE TABLE drafts (
    document_id     TEXT NOT NULL REFERENCES documents_meta(document_id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    question_1      TEXT,
    question_2      TEXT,
    question_3      TEXT,
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (document_id, user_id)
);

-- 8. document_locks (active only)
CREATE TABLE document_locks (
    document_id     TEXT PRIMARY KEY REFERENCES documents_meta(document_id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    acquired_at     TIMESTAMP NOT NULL,
    last_heartbeat  TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_lock_user ON document_locks(user_id);
CREATE INDEX idx_lock_expires ON document_locks(expires_at);
```

### B. Event Logs — append-only, time-series (5 tablo)

```sql
-- 9. user_sessions
CREATE TABLE user_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    session_token   TEXT NOT NULL,
    ip_hash         TEXT,
    user_agent      TEXT,
    started_at      TIMESTAMP NOT NULL,
    ended_at        TIMESTAMP,
    last_activity_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_session_user_active ON user_sessions(user_id, ended_at);
CREATE INDEX idx_session_token ON user_sessions(session_token);

-- 10. activity_events (high-freq)
CREATE TABLE activity_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    session_id      INTEGER REFERENCES user_sessions(id),
    event_type      TEXT NOT NULL,
    document_id     TEXT,
    duration_ms     INTEGER,
    extra_json      TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_act_user_time ON activity_events(user_id, created_at DESC);
CREATE INDEX idx_act_doc_time ON activity_events(document_id, created_at DESC);
CREATE INDEX idx_act_type_time ON activity_events(event_type, created_at DESC);

-- 11. behavioral_events (triggers)
CREATE TABLE behavioral_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    detector        TEXT NOT NULL,
    threshold_value REAL,
    actual_value    REAL,
    context_json    TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_beh_user_time ON behavioral_events(user_id, created_at DESC);
CREATE INDEX idx_beh_detector ON behavioral_events(detector);

-- 12. admin_audit_log (immutable)
CREATE TABLE admin_audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id   INTEGER NOT NULL REFERENCES users(id),
    action_type     TEXT NOT NULL,
    target_kind     TEXT,
    target_id       TEXT,
    metadata_json   TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_audit_admin_time ON admin_audit_log(admin_user_id, created_at DESC);
CREATE INDEX idx_audit_action ON admin_audit_log(action_type);

-- 13. system_events
CREATE TABLE system_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK(severity IN ('info','warn','error')),
    message         TEXT,
    extra_json      TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_sys_severity_time ON system_events(severity, created_at DESC);
CREATE INDEX idx_sys_type ON system_events(event_type);
```

### C. Auxiliary — gamification & training (5 tablo)

```sql
-- 14. gamification_state (denormalized for speed)
CREATE TABLE gamification_state (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id),
    total_xp        INTEGER NOT NULL DEFAULT 0,
    current_streak_days INTEGER NOT NULL DEFAULT 0,
    longest_streak_days INTEGER NOT NULL DEFAULT 0,
    last_active_date TEXT,
    today_save_count INTEGER NOT NULL DEFAULT 0,
    today_complete_count INTEGER NOT NULL DEFAULT 0,
    today_review_count INTEGER NOT NULL DEFAULT 0,
    today_skip_count INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP NOT NULL
);

-- 15. gamification_ledger (XP audit trail)
CREATE TABLE gamification_ledger (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    delta_xp        INTEGER NOT NULL,
    reason          TEXT NOT NULL,
    related_doc_id  TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_ledger_user_time ON gamification_ledger(user_id, created_at DESC);

-- 16. badges_earned
CREATE TABLE badges_earned (
    user_id         INTEGER NOT NULL REFERENCES users(id),
    badge_id        TEXT NOT NULL,
    earned_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (user_id, badge_id)
);

-- 17. training_attempts
CREATE TABLE training_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    attempt_number  INTEGER NOT NULL,
    quiz_score      INTEGER NOT NULL,
    quiz_total      INTEGER NOT NULL,
    annotation_pass_count INTEGER NOT NULL,
    annotation_total INTEGER NOT NULL,
    annotation_details_json TEXT,
    passed          INTEGER NOT NULL,
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP NOT NULL
);
CREATE INDEX idx_train_user ON training_attempts(user_id);

-- 18. notifications (persistent for offline users)
CREATE TABLE notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    kind            TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT,
    data_json       TEXT,
    is_read         INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_notif_user_unread ON notifications(user_id, is_read);
```

---

## Modüler Backend Yapısı

```
backend/
├── main.py                 # FastAPI app, lifespan, route mount
├── config.py
├── shared/                 # cross-cutting
│   ├── db.py
│   ├── auth.py
│   ├── sse.py
│   ├── audit.py
│   └── settings.py
├── users/                  # users, invite_codes
├── documents/              # documents_meta + raw doc reading + metadata extraction
├── annotations/            # annotations, annotation_versions, drafts + diff
├── locks/                  # document_locks + heartbeat sweep
├── shuffle/                # 3-tab feed logic (Review/Yeni/Doğruladıklarım)
├── gamification/           # state, ledger, badges, rules
├── training/               # gating + quiz_data (statik)
├── behavioral/             # detectors (speed, char_limit)
├── notifications/          # in-app
├── admin/                  # admin panel routes + cli
├── backup/                 # SQLite → JSON → GitHub
└── docs_help/              # markdown kullanım kılavuzu
```

Modül kuralları:
- Her modül kendi tablolarına sahip; başka modülün tablolarına direkt erişmez
- Cross-domain işlem `service.py` üzerinden
- Her event `shared/audit.py`'den yazılır
- FK'ler `SET NULL` (modüler bağımsızlık)

---

## API Yüzey Alanı (özet)

```
POST   /api/auth/register          (davet kodu + ad/soyad/şifre)
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/me

GET    /api/feed?tab=review|new|verified  (3 sekmeli shuffle)
GET    /api/documents/{id}                (içerik + metadata + annotation + draft)
POST   /api/annotations                   (Sakla — versioning + diff hesabı)
POST   /api/annotations/{id}/skip
POST   /api/annotations/{id}/complete     (toggle is_completed)
PUT    /api/drafts/{id}                   (autosave, debounced 2sn)

POST   /api/locks/{id}/acquire
POST   /api/locks/{id}/heartbeat
POST   /api/locks/{id}/release

GET    /api/me/profile                    (XP, streak, today_counters, badges)
GET    /api/me/notifications              (unread)
POST   /api/me/notifications/{id}/read
POST   /api/me/seen-manual                (gating'i geç)

GET    /api/training/start
POST   /api/training/quiz/submit
POST   /api/training/annotate/submit

GET    /api/events                        (SSE)

GET    /api/help                          (markdown content)

POST   /api/admin/users/{id}/promote
POST   /api/admin/users/{id}/demote
POST   /api/admin/users/{id}/disable
POST   /api/admin/invite/rotate
GET    /api/admin/audit-log
GET    /api/admin/system-events
POST   /api/admin/locks/{id}/force-release
GET    /api/admin/settings
PUT    /api/admin/settings/{key}
GET    /api/admin/training/{user_id}/reset

GET    /api/export?format=csv|jsonl

# Static (Vite build çıktısı, backend/static/'den serve)
GET    /                                  → SPA index.html (React Router devralır)
GET    /login,/register,/help,/training,/me,/admin/...  → SPA index.html (client-side routing)
GET    /assets/*                          → Vite-bundled JS/CSS/images
```

`backend/main.py` (Paket 16'da eklenir, en sonda — `/api/*` route'ları öncelikli):
```python
from fastapi.staticfiles import StaticFiles
if config.STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="spa")
```
- `config.STATIC_DIR = backend/static` (Vite `outDir`)
- `html=True` SPA fallback için (her path → index.html, React Router devralır)

---

## Major Flow'lar

### 1. Bursiyer Onboarding

```
[Davet kodu paylaşılır]
  ↓
Register: kullanıcı adı + e-mail (opsiyonel) + şifre + davet kodu
  ↓
İlk login → has_seen_manual=False → /help?first_time=true (zorunlu redirect)
  ↓
Kılavuzu okur, "Anladım, devam et" → POST /api/me/seen-manual
  ↓
has_passed_training=False → /training (zorunlu redirect)
  ↓
Bölüm 1: 5 quiz (eşik 4/5) → Bölüm 2: 3 gold-doc annotation (eşik 2/3, concept-keyword check) → her doc'tan sonra "doğruyu göster"
  ↓
Pass → has_passed_training=True (kalıcı), training_attempts.passed=1
Fail → 3 deneme hakkı, hepsi tükenirse admin'e bildirim
  ↓
Ana arayüze yönlenir → Review sekmesi default açık, soft öneri toast'u
```

### 2. Anotasyon Akışı (Chain Review)

```
Sol kolonda 3 sekme: [🔄 Review] [🆕 Yeni] [✓ Doğruladıklarım]
  ↓
Bursiyer Review'da `doc_42` tıklar
  ↓
POST /api/locks/doc_42/acquire
  - Kilit yoksa → 200 OK (kullanıcının kilidi yazılır)
  - Kilit varsa başkasında → 409 + "Mehmet çalışıyor (3dk önce)" → modal → "Başka doc seç"
  ↓
GET /api/documents/doc_42 → içerik + (varsa) önceki kullanıcının annotation'ı + (varsa) bu kullanıcının draft'ı
  ↓
Sağ panelde 3 textarea: önceki kullanıcının cevabı doludur, "by Ahmet · 2 saat önce" attribution gösterilir
  ↓
Bursiyer üstünde çalışır:
  - Her tuş vuruşundan 2sn sonra debounce → PUT /api/drafts/doc_42
  - Her 30sn → POST /api/locks/doc_42/heartbeat
  - 5dk hareketsizse → kilit auto-release (sweep job)
  ↓
Sakla butonuna basar (veya Ctrl+Enter):
  - 3 soru tam dolu mu? boşsa hata
  - POST /api/annotations
    - Yeni annotation_versions satırı (diff_from_previous hesaplanır, is_diff_zero set edilir)
    - annotations CURRENT row update (last_editor, edit_count++, unique_users güncellenir)
    - drafts satırı silinir
    - lock release (POST /api/locks/doc_42/release)
    - activity_events kaydı
    - gamification: +1 XP (+5 ise complete_mark), today_save_count++
    - SSE: lock_released, badge_unlocked (varsa)
  ↓
Frontend bir sonraki dokümana otomatik geçer (aktif sekmeden, shuffle ile)
```

### 3. Lock Lifecycle

```
acquire (5dk expires_at) → heartbeat (her 30sn → expires_at += 5dk) → release (manuel veya save/skip)
                                                     ↑
                                       Eğer heartbeat 5dk gelmezse:
                                       Background sweep (her 1dk):
                                       DELETE FROM document_locks WHERE expires_at < NOW
                                       SSE: lock_released yayını
```

### 4. Backup Cycle

```
Background loop (her N dakika, default 600=10dk):
  ↓
Tüm tabloları SQL → JSON dump
  ↓
write /data/backup/latest.json
write /data/backup/{YYYYMMDD-HHMM}.json
rotate: son 144 (= 24 saat × 10dk) snapshot tut
  ↓
git add /data/backup/ && git commit -m "auto-backup {timestamp}"
git push origin main (PAT ile)
  ↓
system_events: success/fail kaydı
```

### 5. Restore (manuel CLI)

```
$ python -m backend.cli restore-from-github
  ↓
1. Mevcut DB'yi /data/db/corrupt-{timestamp}.db.bak olarak yedekle
2. git clone {backup-repo} /tmp/restore
3. Latest snapshot'ı seç (veya kullanıcı tarihten seçer)
4. JSON'dan tabloları yeniden oluştur (TRUNCATE + INSERT)
5. Validation: row count'ları logla
6. Confirm prompt
7. Yeni DB hazır
```

---

## Behavioral Detectors (configurable)

Tüm parametreler `site_settings` tablosunda. Defaults (admin değiştirebilir):

```json
{
  "speed_warning.window_seconds": 300,
  "speed_warning.max_saves_in_window": 5,
  "speed_warning.min_seconds_per_doc": 30,
  "speed_warning.min_words_for_min_seconds": 100,
  "char_limit.warn_threshold": 300,
  "char_limit.alert_threshold": 600,
  "lock.expires_seconds": 300,
  "lock.heartbeat_interval_seconds": 30,
  "backup.interval_seconds": 600,
  "training.quiz_pass_threshold": 4,
  "training.annotation_pass_threshold": 2,
  "training.max_attempts": 3,
  "gamification.daily_target_docs": 20,
  "gamification.xp_save": 1,
  "gamification.xp_complete": 5,
  "gamification.xp_review": 2,
  "gamification.good_reviewer.min_reviews": 20,
  "gamification.good_reviewer.min_kept": 15
}
```

---

## SSE Event Türleri

| Event | Scope | Payload |
|---|---|---|
| `presence` | Broadcast | `{online_users: [{id, username, avatar_color}]}` |
| `lock_acquired` | Broadcast | `{document_id, by_username, started_at}` |
| `lock_released` | Broadcast | `{document_id}` |
| `speed_warning` | Personal | `{message, recent_action_count, window_seconds}` |
| `badge_unlocked` | Personal | `{badge_id, name, description}` |
| `streak_at_risk` | Personal | `{current_streak, hours_left}` |
| `notification` | Personal | `{notification_id, title, body}` |

---

## Gamification Detayı

**XP Kuralları:**
- Sakla: +1
- Atla: 0
- Tamamlandı işaretle: +5
- Review (mevcut annotation'ı düzenleyip kaydet): +2
- Training pass: +50 (one-time)
- Sonraki kullanıcı seninkini değiştirmemiş (diff=0 öncekinin üstüne): +3 (gecikmeli, post-hoc)

**Streak:**
- Her gün en az 1 save → streak += 1
- Bir gün atla → streak = 0
- Hesaplama günlük midnight job ile (UTC+3)

**Rozetler:**

| ID | İsim | Kriter |
|---|---|---|
| `first_annotation` | İlk Annotation | İlk save |
| `annotations_10` | 10 Annotation | 10 save |
| `annotations_100` | 100 Annotation | 100 save |
| `annotations_1000` | 1000 Annotation | 1000 save |
| `first_completion` | İlk Tamamlama | İlk `is_completed` toggle |
| `marathoner` | Maratoncu | 7 günlük streak |
| `good_reviewer` | Good Reviewer | ≥20 review yapmış VE bunların ≥15'inde sonraki kullanıcı diff=0 (yani senin yazdığın korunmuş) |

Rozetler her save sonrası `gamification.service.check_badges(user)` ile kontrol edilir.

---

## Documentation / Help (`/help`)

Markdown bazlı, dokuz bölüm:
1. Hoş geldin — proje neden var
2. Hızlı başlangıç — login → kılavuz → training → annotation
3. Anotasyon nasıl yapılır — 3 few-shot iyi-kötü örnek
4. Chain review nedir — A → B → diff → completed
5. Klavye kısayolları
6. Önemli kurallar — kalite > hız, char limit, etik
7. Skor & rozetler — nasıl XP, hangi rozetler
8. SSS — 5-7 sık sorulan
9. Teşekkür — bursiyerlere

İlk-kullanıcı redirect: `has_seen_manual=False` → `/help?first_time=true` zorunlu.

---

## Deployment

### Docker (Multi-Stage Build)

`Dockerfile` iki aşamalı: önce frontend Vite build, sonra backend imajına kopya.

```dockerfile
# ====== Stage 1: Frontend build ======
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build  # outputs to ../backend/static via vite.config outDir

# ====== Stage 2: Backend ======
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=frontend-build /app/backend/static/ ./backend/static/
RUN pip install --no-cache-dir -e .
VOLUME ["/data"]
ENV DATA_DIR=/data
EXPOSE 8000
CMD ["sh", "-c", "python -m backend.cli migrate && uvicorn backend.main:app --host 0.0.0.0 --port 8000"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" || exit 1
```

Dev (lokal): `frontend/` ve `backend/` ayrı çalışır (Vite 5173 + uvicorn 8000, Vite proxy ile birleşir). Prod: tek konteyner.

`docker-compose.yml`:
- Service: `app`
- Named volume: `anotasyon_data:/data`
- Port: `8000:8000`
- ENV: `BACKUP_REPO_URL`, `GITHUB_PAT`, `SESSION_SECRET`, `BOOTSTRAP_ADMIN_USERNAME`

### HF Spaces (opsiyon, persistent disk değilse)

- Persistent disk gerekli (yoksa veri ephemeral, yine de GitHub recovery var)
- Secrets: `GITHUB_PAT`, `SESSION_SECRET`
- Dockerfile direkt kullanılır

### Self-host

- Docker Compose ile herhangi bir Linux sunucuda
- Reverse proxy: nginx/caddy (HTTPS için)

---

## Resolved Decisions (önceki Open Questions)

1. **Davet kodu:** Aktifken birden fazla bursiyer aynı kodla kayıt olur. Admin "rotate" → eski kod `is_active=0`, yeni kod `is_active=1`. Eski kullanıcılar etkilenmez.
2. **Admin demote:** Demote edilenin role'ü `'user'` olur, ama tüm annotation'ları, audit log girişleri, attribution **olduğu gibi korunur**. Demote edilmiş eski admin kullanıcı olarak çalışmaya devam eder.
3. **Avatar color:** Register sırasında `username` SHA hash'inden 12-renkli paletten otomatik seçim. Kullanıcı değiştiremez. Sadece admin manuel değiştirebilir (çakışma vs.).
4. **GitHub PAT:** **Fine-grained PAT** kullanılır — sadece `anotasyon-backup` repo'suna `Contents: write` izni. Klasik PAT'tan daha az yetkili (least privilege). HF Spaces secrets / Docker env'de tutulur.
5. **Training gold docs (HİBRİT):**
   - **Kod tabanında baseline** — `backend/training/gold_docs.py` initial seed listesi (her zaman var, version control'lü)
   - **DB'de override** — yeni 19. tablo `training_gold_doc_overrides`
   - **Resolution:** runtime'da DB row varsa onu kullan, yoksa code baseline'dan oku
   - Admin UI: code entry'yi düzenle → DB override yaratır; sil → DB'de `is_deleted=true`; ekle → custom DB row; "Reset to code" → DB row sil
   - Avantaj: kod baseline güncellenebilir + admin esnekliği bozmaz
6. **Migration:** **Yok.** Temiz başlangıç. Eski tek-kullanıcılı `data/annotations.db` zaten temizlendi. Yeni sistem sıfırdan kurulacak. (Migration script'i v2'de gerekirse eklenebilir.)

### Yeni 19. Tablo (Q5 hibrit modeli için)

```sql
-- 19. training_gold_doc_overrides
CREATE TABLE training_gold_doc_overrides (
    gold_id         TEXT PRIMARY KEY,         -- code baseline'daki ID veya custom yeni ID
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    content         TEXT,                     -- null ise code'dakini kullan
    expected_concepts TEXT,                   -- JSON array, null ise code'dakini kullan
    min_concept_count INTEGER,                -- null ise code'dakini kullan
    source          TEXT NOT NULL CHECK(source IN ('override','custom')),
    created_by_admin_id INTEGER REFERENCES users(id),
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
```

**Resolution mantığı (`backend/training/service.py`):**
```python
def get_active_gold_docs() -> list[GoldDoc]:
    code_baseline = load_code_gold_docs()  # backend/training/gold_docs.py
    overrides = db.fetch_all_overrides()   # dict[gold_id, override_row]

    out = []
    seen_ids = set()
    for code in code_baseline:
        ov = overrides.get(code.id)
        if ov and ov.is_deleted:
            continue  # admin sildi
        if ov:
            out.append(GoldDoc(
                id=code.id,
                content=ov.content or code.content,
                concepts=ov.expected_concepts or code.expected_concepts,
                min_count=ov.min_concept_count or code.min_concept_count,
            ))
            seen_ids.add(code.id)
        else:
            out.append(code)
            seen_ids.add(code.id)
    # Custom (DB-only) entries
    for ov in overrides.values():
        if ov.source == 'custom' and not ov.is_deleted and ov.gold_id not in seen_ids:
            out.append(GoldDoc(id=ov.gold_id, content=ov.content,
                               concepts=ov.expected_concepts,
                               min_count=ov.min_concept_count))
    return out
```

---

## Implementation Packages (sıralı)

Spec onaylanınca writing-plans skill'i ile detaylı plan üretilecek. Sıra:

| # | Paket | Bağımlılık |
|---|---|---|
| 1 | **Foundation refactor** — modüler folder yapısı, shared/ helpers, schema migration v0→v1 | mevcut araç |
| 2 | **Auth + Users + Invite Code + Multi-Admin** | 1 |
| 3 | **First-time Manual Gating + /help content** | 2 |
| 4 | **Documents Metadata + Ingestion Pipeline** | 1 |
| 5 | **Annotations Chain (versions, diff, drafts) + Locks (heartbeat)** | 2, 4 |
| 6 | **3-Tab Shuffle Feed** | 5 |
| 7 | **SSE + Live Updates (presence, lock events)** | 5 |
| 8 | **Behavioral Detectors + Site Settings** | 5 |
| 9 | **Gamification (XP, streak, badges, daily target) + Notifications** | 5 |
| 10 | **Training Gate (quiz + gold-doc annotation)** | 4, 5 |
| 11 | **Admin Panel (users, audit, settings, locks, training reset)** | 2, 5 |
| 12 | **Backup (lokal + GitHub) + Restore CLI** | 1 |
| 13 | **Retention & Archival** | 12 |
| 14 | **Export (CSV/JSONL)** | 5 |
| 15 | **Dockerization + Healthcheck** | hepsi |
| 16 | **Frontend SPA Build** — React 18 + Vite + TS + Tailwind + shadcn/ui ile tüm UI: Login/Register, Help (manual gate), Training quiz + 3 gold-doc annotation, ana Annotate ekranı (3-sekmeli sol liste virtual-scroll, orta DocViewer, sağ QuestionPanel auto-save), TopBar (XP/streak/günlük progress/online avatarlar), modaller (LockConflict, BadgeUnlocked, SpeedWarning toast'ları), Notifications, Profile, Admin panel (Users, AuditLog, Settings, Locks). `useSSE`/`useDraft`/`useLock`/`useShortcuts` hook'ları. `openapi-typescript` ile backend tip senkronizasyonu. Vite multi-stage Docker build. | 5-9, 11 |
| 17 | **End-to-End Test (multi-user simulation, lock contention, backup/restore drill)** | hepsi |

Paket başına bir implementation plan dokümanı yazılır, subagent-driven development ile yürütülür.
