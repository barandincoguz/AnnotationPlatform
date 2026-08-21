# Feedback System Design

**Date:** 2026-07-07  
**Status:** Approved  
**Approach:** C — iki sayfa (kullanıcı formu + admin listesi)

## Amaç

Kullanıcılara şikayet ve öneri göndermeleri için yeni bir sekme eklemek.  
Adminlerin bu gönderimleri görüntüleyebilmesi için admin panelinde liste sayfası oluşturmak.

## Veritabanı

Yeni tablo: `user_feedback`

| Kolon | Tip | Kısıt |
|-------|-----|-------|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | — |
| `user_id` | INTEGER NOT NULL | FK → users(id) ON DELETE CASCADE |
| `type` | TEXT NOT NULL | CHECK IN ('complaint', 'suggestion') |
| `message` | TEXT NOT NULL | — |
| `created_at` | TIMESTAMP NOT NULL | DEFAULT CURRENT_TIMESTAMP |

İndeksler:
- `idx_fb_user_time` → (user_id, created_at DESC)
- `idx_fb_type` → (type)

## Backend

### Migration: v0016_user_feedback.py

- SCHEMA_SQL = tablo + indext
- `up(conn)` fonksiyonu (mevcut migration pattern)

### Modül: backend/feedback/

```
backend/feedback/
├── __init__.py     → router export
├── models.py       → Pydantic şemalar
├── service.py      → DB iş mantığı
└── routes.py       → FastAPI endpoint'leri
```

### Endpoints

| Method | Path | Auth | Açıklama |
|--------|------|------|----------|
| POST | /api/feedback | authenticate | Kullanıcı gönderim yapar |
| GET | /api/admin/feedback | require_admin | Admin listesi (tip filtresi destekler) |

### models.py şemalar

```python
class FeedbackType(str):
    complaint = "complaint"
    suggestion = "suggestion"

class FeedbackCreateRequest(BaseModel):
    type: FeedbackType
    message: str

class FeedbackRow(BaseModel):
    id: int
    user_id: int
    username: str
    type: FeedbackType
    message: str
    created_at: str
```

### service.py işlevler

- `submit_feedback(conn, user_id, type, message)` → inserts + audits
- `list_feedback(conn, type_filter=None)` → returns list of rows with username

## Frontend

### Yeni dosyalar

```
frontend/src/routes/Feedback.tsx                    # Kullanıcı formu sayfası
frontend/src/routes/admin/FeedbackPage.tsx           # Admin listesi
frontend/src/api/queries/feedback.ts                 # API query
frontend/src/lib/feedbackSchemas.ts                  # Zod validation
frontend/src/components/admin/FeedbackTypeBadge.tsx  # Tip badge
frontend/src/routes/admin/AdminLayout.test.tsx       # test ekle
```

### Kullanıcı Sayfası: /feedback

- TabStrip veya form layout ile "Şikayet" / "Öneri" seçimi
- Textarea alanı (message)
- Gönder butonu
- Başarılı gönderim → toast + form temizlenir
- Validation: type seçili + message en az 1 karakter

### Admin Sayfası: /admin/feedback

- AdminTable component kullanır
- Kolonlar: ID, Kullanıcı, Tip, Mesaj, Tarih
- Filtre: tip seçici (Tümü / Şikayet / Öneri)
- Mesaj sütunu truncation + expand (overflow önleme)

### Navigasyon

**TopBar.tsx:** "İstatistikler" link'inin yanına yeni "Şikayet/Öneri" link
- İkon: MessageSquare veya Send
- Mobil: ikon sadece, masaüstü: ikon + metin

**adminNav.ts:** "Operations" grubuna "Feedback" ekle

### App.tsx route ekle

```tsx
<Route path="/feedback" element={<Feedback />} />
<Route path="feedback" element={<FeedbackPage />} />  {/* admin alt route */}
```

## Test Plan (özet)

- **Backend:** POST /api/feedback 200/401/422, GET /api/admin/feedback 200/403, service unit tests
- **Frontend:** Feedback form validation testleri, FeedbackPage render testleri, msw handlers
- **E2E:** Kullanıcı form gönderim + admin listesi görüntüleme (isteğe bağlı)

## Değişen Dosyalar (özet)

| Dosya | Değişiklik |
|-------|-----------|
| `backend/main.py` | feedback router register |
| `backend/migrations/runner.py` | migration keşif (otomatik) |
| `frontend/src/App.tsx` | yeni route'lar ekle |
| `frontend/src/components/topbar/TopBar.tsx` | yeni nav link |
| `frontend/src/components/admin/adminNav.ts` | yeni menü öğesi |

## Kapsam Dışı

- Yanıt/tepki mekanizması (admin kullanıcıya cevap veremez)
- Email bildirimleri
- Anonim geri bildirim (sadece giriş yapmış kullanıcılar)
- File attachment
