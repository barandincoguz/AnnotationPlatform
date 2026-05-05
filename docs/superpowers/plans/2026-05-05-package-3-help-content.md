# Paket 3 — First-Time Manual + /help Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bursiyerlerin sisteme ilk girdiklerinde gördüğü kullanım kılavuzunu kur — `backend/docs_help/` paketi altında 9 bölümlük markdown içerik + `/api/help` endpoint'i. Frontend Paket 16'da bu içeriği render eder.

**Architecture:** Markdown dosyaları `backend/docs_help/content/NN-slug.md` (NN = sıra numarası). `GET /api/help` endpoint'i tüm bölümleri JSON listesi olarak döner: `[{id, order, title, body}, ...]`. Title dosyanın ilk `# H1` başlığından parse edilir. Frontend (Paket 16) react-markdown ile render eder. Auth gerekli (ama `has_seen_manual` gerekmiyor — kılavuz GERÇEKTE manualin kendisi).

**Tech Stack:** FastAPI, sadece stdlib (Path.glob), pytest, mevcut Paket 2 auth deps (`get_current_user`).

---

## Mimari Kararlar

- **Format:** Raw markdown — frontend renderlar (esneklik, copy-paste sample içerik için ideal)
- **Section ID:** Filename stem (örn. `02-getting-started`)
- **Sıralama:** Filename'in ilk 2 karakteri (`01-`, `02-`, ...) ile alphabetik sort
- **Title:** İlk `# H1` satırı, yoksa stem fallback
- **Auth:** `get_current_user` (login lazım), `has_seen_manual` zorunlu DEĞİL
- **Path traversal koruması:** Section ID frontend'den gelmiyor (frontend listeyi alıp tüm bölümleri renderlar)
- **Encoding:** UTF-8, Türkçe karakter desteği

## Dosya Yapısı

```
backend/docs_help/
├── __init__.py                  # boş
├── routes.py                    # /api/help endpoint'i
├── service.py                   # list_help_sections() helper
└── content/
    ├── 01-welcome.md
    ├── 02-getting-started.md
    ├── 03-annotation-guide.md
    ├── 04-chain-review.md
    ├── 05-keyboard-shortcuts.md
    ├── 06-rules.md
    ├── 07-gamification.md
    ├── 08-faq.md
    └── 09-thanks.md

tests/
└── test_help.py
```

---

## Task 1: Markdown Content (9 bölüm)

**Files:**
- Create: `backend/docs_help/__init__.py` (empty), `backend/docs_help/content/*.md` (9 files)

- [ ] **Step 1: Create package structure**

```bash
mkdir -p backend/docs_help/content
touch backend/docs_help/__init__.py
```

- [ ] **Step 2: Write `backend/docs_help/content/01-welcome.md`**

```markdown
# Hoş geldin

Bu platforma katıldığın için teşekkürler. Burada Türkiye Gelir İdaresi Başkanlığı tarafından yayınlanmış vergi özelgelerini okuyup içlerinde geçen 3 soruyu çıkarıyorsun.

## Neden bu iş önemli?

Çıkardığın soru-doküman eşleşmeleri, mükelleflerin "bana benzer bir durum için ne demişler?" sorusuna hızlı yanıt verecek bir arama sistemi için temel veri seti olacak. Yani senin yaptığın işin direkt bir karşılığı var: ileride bir muhasebeci, bir müşavir veya bir hukuk öğrencisi senin etiketlediğin sorular sayesinde aradığını dakikalar içinde bulacak.

## Senin rolün

- Doğru, açık, anlaşılır 3 soru çıkarmak
- Başka bursiyer arkadaşlarının yazdıklarını gözden geçirmek
- Şüphende olduğun yerleri "Atla" ile geçmek (yanlış kayıt yapmaktan iyidir)
- Yorgunken durmak — kalite hızdan önemli

İyi çalışmalar.
```

- [ ] **Step 3: Write `backend/docs_help/content/02-getting-started.md`**

```markdown
# Hızlı başlangıç

## 1. Eğitim testi

İlk girişinde 5 bilgi sorusu + 3 örnek doküman üzerinde annotation testi göreceksin. Bunu geçmen lazım. 3 deneme hakkın var, panik yapma.

## 2. Ana ekran

Geçtikten sonra ana annotation ekranına yönleneceksin. 3 sekme var:

- **🔄 Review** — başka bursiyerlerin dokunduğu, senin görmediğin dokümanlar (default)
- **🆕 Yeni** — kimse dokunmamış, shuffle ile gelen dokümanlar
- **✓ Doğruladıklarım** — senin "tamamlandı" işaretlediğin dokümanlar

## 3. Akış

1. Sol kolondan bir doküman seç
2. Orta kolonda metni oku
3. Sağda 3 textarea'ya soruları yaz (kopyala-yapıştır da olur)
4. **Sakla** (`Ctrl+Enter`) — bir sonraki dokümana geçer

## 4. İşin doğru gitmediğini fark edersen

- "Ben mi karıştırdım?" → **Atla** (`Ctrl+K`)
- "Çok uzun yazdım" → karakter sayacı turuncu/kırmızı uyarır
- "Bu doküman zor" → orta üstte zorluk etiketi var (Kolay/Orta/Zor)

Detaylar diğer bölümlerde.
```

- [ ] **Step 4: Write `backend/docs_help/content/03-annotation-guide.md`**

```markdown
# Anotasyon Rehberi — İyi Soru Nasıl Yazılır

İdeal soru, **mükellefin sorduğunu** ya da **özelgenin cevapladığını** doğal Türkçe ile özetler. Şu üç prensibe dikkat et:

1. **Spesifik ol** — "Vergilendirme nasıl olur?" çok geniş; "Airbnb üzerinden ev kiralayan kişi gelir vergisinden mi ticari kazançtan mı vergilendirilir?" tam.
2. **Tek konu, tek soru** — "Vergi türü ne ve fatura kesmeli mi?" → 2 soruya böl.
3. **İddialı olma** — "Ev sahibi ticari kazanç ödemek zorunda mı?" hem konuyu hem cevabı içeriyor; "...ödemek zorunda mı?" tarafsız.

## Üç örnek

### ✅ İyi
> Doküman: Bir özelge konutun günlük kiralanmasının vergilendirilmesini açıklıyor.
>
> - "Konutu turizm amaçlı günlük kiralayan kişi hangi kazanç türünden vergilendirilir?"
> - "Turizm amaçlı kiralama için izin belgesi alınması zorunlu mudur?"
> - "Aracılık eden seyahat acentası kiralama gelirini etkiler mi?"

### ⚠️ Kötü (çok genel)
> - "Vergi nasıl ödenir?"
> - "Ne yapmam lazım?"
> - "Cevabı nedir?"

### ⚠️ Kötü (çok dar)
> - "07.1.GİB.4.34 sayılı özelge ne diyor?"
> - "23.01.2026 tarihinde yayımlanan görüş geçerli mi?"

İlki cevabı arayan birinin asla yazmayacağı bir soru. İkincisi belge metadatasını içeriyor.

## Önemli

Bursiyer arkadaşların aynı dokümana farklı sorular yazmış olabilir. Onları "yanlış" olarak görme — perspektif farkı normaldir. Ekleme/değiştirme yap, devam et.
```

- [ ] **Step 5: Write `backend/docs_help/content/04-chain-review.md`**

```markdown
# Chain Review — Birden Fazla Bursiyer

## Akış

A bursiyer bir dokümanı annotate ederse, B bursiyer aynı dokümanı açtığında A'nın yazdığı 3 soru zaten textarea'larda dolu görünür. Ayrıca her sorunun yanında **"by Ahmet · 2 saat önce"** gibi attribution etiketi olur.

B ne yapabilir:
- A'nın sorularını **olduğu gibi kabul edip** Sakla → diff = 0 (değişiklik yok)
- A'nın sorularını **düzenleyip** Sakla → diff > 0 (sistem hangi alanın değiştiğini loglar)
- A'nın sorularını **silip kendi sorularını** yazıp Sakla → diff = 3

Sonra C gelir, B'nin son halini görür ve aynı şekilde devam eder. Zincir böyle uzar.

## "Tamamlandı" Tag'i

`diff = 0` olduğunda (yani sen veya başka biri öncekinin üzerinde değişiklik yapmadıysa), arayüzde **"Bu doküman tamamlandı olarak işaretle"** butonu çıkar. Tıklarsan ✓ rozeti dokümana eklenir, listede görünür. Bu **kilit değil** — sonraki bursiyer hâlâ düzenleyebilir, ama tamamlandı işareti rehber niteliğinde durur.

Tamamlandı tag'i kazandığın **+5 XP** demek (normal Sakla +1).

## Eşzamanlı Çalışma

Sen `doc_42`'yi açtığında bir bursiyer kilit alır. Üst bardan herkese "Mehmet doc_42'de çalışıyor (3dk önce başladı)" bildirimi gider. Başka bir bursiyer aynı dokümana tıklarsa "şu an X kullanıyor, başka doküman seç" mesajı görür. Sen 5dk hareketsiz kalırsan veya sekmeyi kapatırsan kilit otomatik kalkar.
```

- [ ] **Step 6: Write `backend/docs_help/content/05-keyboard-shortcuts.md`**

```markdown
# Klavye Kısayolları

| Kısayol | İşlev |
|---|---|
| `Ctrl+Enter` | Sakla & sıradakine geç |
| `Ctrl+K` | Atla & sıradakine geç |
| `Ctrl+→` | Sonraki doküman |
| `Ctrl+←` | Önceki doküman |
| `Ctrl+/` | Arama kutusuna odaklan |
| `Tab` | Textarea'lar arası gezinti |
| `Esc` | Modali kapat / odağı bırak |

Mac'te `Ctrl` yerine `Cmd` kullanabilirsin — sistem otomatik tanır.

## Verim İpucu

Klavyede kalmaya çalış. Mouse'a uzanmak dakikada 10-15 saniyelik kayıp demek; gün sonunda büyük fark eder.
```

- [ ] **Step 7: Write `backend/docs_help/content/06-rules.md`**

```markdown
# Önemli Kurallar

## 1. Kalite > Hız

Sistem **çok hızlı annotate ettiğini fark ederse** seni uyarır:

> "Yavaşla — son 5 dakikada 5 doküman tamamladın. Yaptığından emin misin?"

Bu uyarı bir ceza değil — kendine bir saniye dur, son birkaç dokümanı gerçekten okudun mu emin ol. Bu mesaj geldikten sonra hâlâ devam edebilirsin.

## 2. Karakter Limiti

- Soru başına **300 karakter üzerinde** turuncu uyarı
- **600 üzerinde** kırmızı uyarı
- İkisi de Sakla'yı **engellemez**, sadece dikkat çeker

İdeal: 50-150 karakter aralığında bir soru.

## 3. Etik

- Yapay zekaya soruyu yazdırıp kopyala-yapıştır yapmak teknik olarak engellenmiyor ama **sistem kalıp tekrarını fark eder** ve admin görür. Yapma. Senin kafanı geliştirmek için bu işi yapıyoruz.
- Boş textarea bırakıp Sakla diyemezsin — boş alan varsa Sakla butonu disabled
- "Bu doküman çok zor" → **Atla** her zaman geçerli, ceza yok

## 4. Şüpheli Durumda

- Doküman içeriği bozuk gözüküyorsa → Atla
- Doküman 2 sayfa ama PDF'i parse edilirken kayıp olmuş → Atla
- Konu seninle alakasız geliyor → yine de yaz, çünkü "anlamadım" da bir veri

## 5. Mola Ver

20 dokümandan sonra 5 dakika gözünü ekrandan ayır. Streak'in kırılmaz, gün sayılmaya devam eder.
```

- [ ] **Step 8: Write `backend/docs_help/content/07-gamification.md`**

```markdown
# Skor & Rozetler

## XP Tablosu

| Aksiyon | XP |
|---|---|
| Sakla | +1 |
| Atla | 0 |
| Tamamlandı işaretle | +5 |
| Mevcut annotation'ı düzenleyerek Sakla (review) | +2 |
| Sonraki bursiyer senin yazdığını korudu (diff=0) | +3 (gecikmeli) |
| Training pass (tek seferlik) | +50 |

## Streak

- Her gün **en az 1 Sakla** → 🔥 streak +1
- Bir gün geçirme → streak 0'a düşer (azat dakikası yok, dikkat)
- Streak yarın kırılacaksa sistem akşam **uyarı toast'u** gönderir

## Günlük Hedef

20 doküman/gün. Üst barda ilerleme çubuğu var. Hedefe ulaşırsan ekstra puan yok ama "bugün hedefi tutturdum" hissi gelsin diye :)

## Rozetler

| Rozet | Kriter |
|---|---|
| 🌱 İlk Annotation | İlk Sakla |
| 🔟 10 Annotation | 10 Sakla |
| 💯 100 Annotation | 100 Sakla |
| 🏅 1000 Annotation | 1000 Sakla |
| ✨ İlk Tamamlama | İlk `is_completed` toggle |
| 🔥 Maratoncu | 7 gün üst üste streak |
| 🎯 Good Reviewer | 20 review yapmış VE bunların 15'i sonraki bursiyer tarafından korunmuş |

## Leaderboard YOK

Sıralama tablosu kasıtlı olarak konmadı. Bu yarış değil — kalite işi. Birbirinizden öğrenmek istediğiniz bir şey olursa Slack/Discord'a yazın.
```

- [ ] **Step 9: Write `backend/docs_help/content/08-faq.md`**

```markdown
# Sık Sorulan Sorular

## "Aynı dokümanı sürekli görüyorum, bu normal mi?"
Hayır. Eğer bir doküman sana 3+ kez geliyorsa admin'e söyle — shuffle algoritmasında bir bug olabilir.

## "Yanlışlıkla tamamlandı dedim, geri alabilir miyim?"
Evet. Aynı doküman üstüne tıkla → "Tamamlandıyı kaldır" butonuna bas. Action loglara kayıt edilir ama kötü bir şey değil.

## "Şifremi unuttum"
Şu an "şifre sıfırla" akışı yok. Admin'e başvur, sana yeni şifre verir. (Paket 11'de admin panelden bunu kendi yapabilir.)

## "Yazdığım soru çok uzun oldu, kırmızı uyarı geldi ama Sakla çalışıyor. Hata mı var?"
Hata yok — kırmızı uyarı sadece "kısalt" rica eder, blocking değil. Yine de o uyarıyı dikkate al; çok uzun sorular sonradan arama indeksine kötü etki ediyor.

## "Diğer bursiyerlerin yazdığı her soruyu beğeniyorum ama 'Sakla' diyorum, +5 hak ediyor muyum?"
Hayır. Sadece **sen `is_completed` butonuna bastığında** +5 alırsın. Pasif kabul (boş textarea'larda dolu cevap olduğu için Sakla'ya basmak) +1'dir. Ama "evet bu cevap doğru" hissini ifade etmek için tamamlandı işareti var, kullan.

## "Ekranda hep aynı isim 'çalışıyor' yazıyor"
Üst barda online bursiyerler ve onların açtıkları dokümanlar görünür. Bir kullanıcı 5 dakikadan uzun süre hareketsiz kalırsa kilit otomatik düşer. Sen tıkladığında hâlâ kilitli görünüyorsa sayfayı yenile.

## "Atla ile Skip arasında fark var mı?"
İkisi aynı şey — UI'da sadece "Atla" yazar.
```

- [ ] **Step 10: Write `backend/docs_help/content/09-thanks.md`**

```markdown
# Teşekkür

Bu projede **insanın katkısı modelin katkısından kıymetli**. Yazdığın her soru, ileride binlerce mükellefin "bana benzer durumda ne demişler?" sorusuna saniyeler içinde cevap bulmasını sağlayacak.

Yapay zeka aklınıza ne kadar yardımcı olursa olsun, doğru bağlamı, doğru tonu, doğru ayrımı **insan eli** ortaya koyuyor. Sen burada olduğun için bu ürün var olabiliyor.

Soru, yorum, "şu işliyor mu acaba" merakı için yöneticine ulaş.

İyi çalışmalar — biraz yavaşla, kahveni iç, döneriz.
```

- [ ] **Step 11: Verify files**

```bash
ls backend/docs_help/content/
```

Expected: 9 markdown files listed.

- [ ] **Step 12: Commit**

```bash
git add backend/docs_help/
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(help): add 9 markdown sections for user manual content"
```

---

## Task 2: Service + Routes (TDD)

**Files:**
- Create: `backend/docs_help/service.py`, `backend/docs_help/routes.py`, `tests/test_help.py`
- Modify: `backend/main.py` (mount router)

- [ ] **Step 1: Write `tests/test_help.py`**

```python
def test_help_returns_all_9_sections(client):
    # Need to be authenticated for /api/help
    # Seed an invite + register + login
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("CODE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "CODE",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    r = client.get("/api/help")
    assert r.status_code == 200
    body = r.json()
    assert "sections" in body
    assert len(body["sections"]) == 9


def test_help_sections_have_id_order_title_body(client):
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("CODE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "CODE",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    r = client.get("/api/help")
    sections = r.json()["sections"]
    for s in sections:
        assert "id" in s
        assert "order" in s
        assert "title" in s
        assert "body" in s
        assert s["body"]  # not empty


def test_help_sections_sorted_by_order(client):
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("CODE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "CODE",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    r = client.get("/api/help")
    sections = r.json()["sections"]
    orders = [s["order"] for s in sections]
    assert orders == sorted(orders)
    assert orders[0] == 1
    assert orders[-1] == 9


def test_help_first_section_is_welcome(client):
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("CODE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "CODE",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    r = client.get("/api/help")
    sections = r.json()["sections"]
    first = sections[0]
    assert first["id"] == "01-welcome"
    assert first["title"].lower().startswith("hoş")


def test_help_unauthenticated_returns_401(client):
    r = client.get("/api/help")
    assert r.status_code == 401


def test_help_works_for_user_without_seen_manual(client):
    """Help endpoint must NOT require has_seen_manual (it IS the manual)."""
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("CODE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": "CODE",
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})

    me = client.get("/api/auth/me").json()
    assert me["has_seen_manual"] is False  # never set

    r = client.get("/api/help")
    assert r.status_code == 200
```

- [ ] **Step 2: Run — expect FAIL (no help router)**

```bash
. .venv/bin/activate && pytest tests/test_help.py -v
```

- [ ] **Step 3: Write `backend/docs_help/service.py`**

```python
"""Help content discovery and parsing.

Markdown files in `content/` are loaded at request time (not cached) — small
file count (~9), small bodies, fine for our scale.
"""
from pathlib import Path
from typing import Optional

CONTENT_DIR = Path(__file__).parent / "content"


def _parse_title(body: str, fallback: str) -> str:
    """First '# ' H1 line, else fallback."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def _parse_order(stem: str) -> Optional[int]:
    """Extract leading numeric prefix (e.g. '01-welcome' → 1)."""
    head = stem.split("-", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def list_help_sections() -> list[dict]:
    """Return all help sections sorted by leading numeric prefix."""
    if not CONTENT_DIR.exists():
        return []
    out = []
    for path in sorted(CONTENT_DIR.glob("*.md")):
        body = path.read_text(encoding="utf-8")
        order = _parse_order(path.stem)
        if order is None:
            continue  # skip files without numeric prefix
        title = _parse_title(body, path.stem)
        out.append({
            "id": path.stem,
            "order": order,
            "title": title,
            "body": body,
        })
    out.sort(key=lambda s: s["order"])
    return out
```

- [ ] **Step 4: Write `backend/docs_help/routes.py`**

```python
"""Help content endpoint."""
import sqlite3

from fastapi import APIRouter, Depends

from backend.users.deps import get_current_user
from backend.docs_help.service import list_help_sections

router = APIRouter(prefix="/api", tags=["help"])


@router.get("/help")
def get_help(
    _user: sqlite3.Row = Depends(get_current_user),
):
    """Return all help sections in order. Auth required, has_seen_manual NOT required."""
    return {"sections": list_help_sections()}
```

- [ ] **Step 5: Modify `backend/main.py` to mount help router**

Add the import after `from backend.users.routes import router as users_router`:
```python
from backend.docs_help.routes import router as help_router
```

Add right after `app.include_router(users_router)`:
```python
app.include_router(help_router)
```

- [ ] **Step 6: Run — expect ALL 6 PASS**

```bash
pytest tests/test_help.py -v
```

- [ ] **Step 7: Verify full suite**

```bash
pytest tests/ -q
```

Expected: 101 tests (95 + 6 new).

- [ ] **Step 8: Commit**

```bash
git add backend/docs_help/service.py backend/docs_help/routes.py backend/main.py tests/test_help.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(help): add /api/help endpoint with auth-only access"
```

---

## Task 3: E2E Verification

- [ ] **Step 1: Server smoke test**

```bash
rm -rf /tmp/p3-e2e && mkdir -p /tmp/p3-e2e
. .venv/bin/activate
DATA_DIR=/tmp/p3-e2e python -m backend.cli migrate
DATA_DIR=/tmp/p3-e2e python -m backend.cli create-invite "BURSIYER-2026"

lsof -ti:8765 | xargs kill -9 2>/dev/null
DATA_DIR=/tmp/p3-e2e uvicorn backend.main:app --port 8765 --log-level error &
until curl -sf http://localhost:8765/api/health >/dev/null 2>&1; do sleep 0.3; done

# Register + login
curl -s -c /tmp/p3-cookies.txt -X POST http://localhost:8765/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"password123","invite_code":"BURSIYER-2026"}' >/dev/null

curl -s -c /tmp/p3-cookies.txt -X POST http://localhost:8765/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"password123"}' >/dev/null

echo "=== /api/help (should return 9 sections) ==="
curl -s -b /tmp/p3-cookies.txt http://localhost:8765/api/help | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'Total sections: {len(data[\"sections\"])}')
for s in data['sections']:
    print(f'  {s[\"order\"]:>2}. {s[\"id\"]:<25} - {s[\"title\"]:<40} ({len(s[\"body\"])} chars)')
"

kill %1 2>/dev/null
```

Expected output: 9 sections listed in order with titles in Turkish.

- [ ] **Step 2: Tag**

```bash
git tag -a paket-3-help -m "Paket 3 — First-time Manual + /help content complete"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Implementing task |
|---|---|
| 9 markdown sections (welcome, getting-started, anotasyon-rehberi, chain-review, kısayollar, kurallar, gamification, SSS, teşekkür) | T1 |
| /api/help endpoint | T2 |
| Auth required | T2 (uses get_current_user) |
| has_seen_manual NOT required | T2 (does not use require_seen_manual) |
| `has_seen_manual=False` ise frontend redirect | Already supported via /api/me/seen-manual (Paket 2) — frontend logic is Paket 16 |

**Placeholder scan:** None. Each markdown file has full Turkish content; service has full implementation; tests have full assertions.

**Type/method consistency:**
- `list_help_sections() → list[dict]` consistent
- `_parse_title(body, fallback) → str` consistent
- `_parse_order(stem) → Optional[int]` consistent
- Section dict keys: `id, order, title, body` — used uniformly across service and tests

**Known compromise:** Markdown files are loaded fresh on every request. For 9 small files this is negligible; for hundreds we'd cache.
