# Pre-Submit Quality Audit Design

**Date:** 2026-08-18
**Status:** Approved
**Approach:** Vendored DQC çekirdeği + Mac→Space push ajanı + sağ panel denetim ekranı

## Amaç

Etiketleyici bir özelgeyi etiketleyip **"Tamamla"**ya bastığında, insan etiketleri ile
G0 model tahmini arasındaki uyuşmazlıkları submit'ten önce tespit etmek ve kullanıcıya
kaynak metin üzerinden değerlendirebileceği bir kalite denetim ekranı sunmak.

> **Altın Kural — "Model de yanlış olabilir."**
> Sistem kullanıcıyı model tahminini kabul etmeye **asla** zorlamaz. Uyuşmazlık
> varsa yalnızca *beyan* istenir ("gördüm, kendi etiketimde ısrar ediyorum");
> karar her zaman uzmanın kalır. Model tahmini yoksa veya bozuksa bu durum
> açıkça söylenir — sessizce "uyum var" gibi davranılmaz.

## Topoloji

Prod ortamı bir Hugging Face Space'tir (`sdk: docker`, `app_port: 7860`, `DATA_DIR=/data`,
kalıcı disk yok). MLX yalnızca Apple Silicon'da çalışır, HF donanımında çalışmaz.
Space'e inbound erişim vardır ama Space Mac'e ulaşamaz. Bu üç gerçek akış yönünü belirler:

```
Mac (7/24, MLX sıcak)                    HF Space (prod, 7860)
┌──────────────────────────┐             ┌────────────────────────────────┐
│ dqcheck predict-agent    │ ==GET====>  │ /api/internal/predictions/     │
│   MlxG0Backend (G0)      │   pending   │   pending   (token'lı)         │
│   ~10–60 sn / doküman    │ ==POST===>  │ /api/internal/predictions      │
└──────────────────────────┘   ingest    │   → model_predictions (upsert) │
     yalnızca outbound                   │                                │
                                         │ submit → tek SELECT + vendored │
                                         │          router (mikrosaniye)  │
                                         └────────────────────────────────┘
```

MLX çökerse ajan döngüsü durur; Space etkilenmez, hiçbir kullanıcı bloklanmaz,
önbellek yalnızca tazelenmez.

## Kararlar

| # | Karar |
|---|-------|
| 1 | DQC'nin saf çekirdeği (`router`, `normalization`, `reference_policy`, `text`, `contracts`, `constants`, `errors`, `fingerprints` — 8 modül, stdlib) `backend/quality/dqcheck_core/` altına **birebir vendor'lanır**; parity testi sapmayı yakalar. `hitl.ab_diff` Flask bağımlılığı yüzünden vendor'lanmaz, adapter'da yeniden yazılır. |
| 2 | Model tahminleri AP'nin SQLite'ında `model_predictions` tablosunda önbelleklenir (Mod A). Submit yolunda inference yok. |
| 3 | Tahminler Mac'ten Space'e **push** edilir: `dqcheck predict-agent` → `GET /pending` → G0 → `POST /predictions` (bearer token). Tunnel yok, inbound yok. |
| 4 | Ajan inference'ı **Space'ten gelen `pdf_text`** üzerinde yapar — model, annotator'ın gördüğü metnin aynısını okur. |
| 5 | `model_predictions` ve `annotation_audit_logs` Neon mirror'a dahildir ve Space restart'ında restore edilir. Tahmin yazıları yalnız gerçek `dqcheck_agent` / `mlx-g0` ve review edilmiş G0 model fingerprint allowlist'i ile kabul edilir; fixture veya bilinmeyen model satırları mirror'a giremez. |
| 6 | Tahmin yok / `status='error'` / `truncated` / metin bayat → `audit_status: "model_unavailable"` + `reason`, `bucket` boş. Panel açılmaz, complete akar, audit'e `model_unavailable` yazılır. Asla uyum sayılmaz. |
| 7 | `/complete` bucket'ı **commit edilecek referanslarla kendisi yeniden hesaplar**. RED/YELLOW ise `audit_ack` şarttır (yoksa 409 `audit_required`); ack'teki `prediction_fingerprint` güncel değilse 409 `audit_stale`. |
| 8 | Denetim kararı ayrı `annotation_audit_logs` tablosuna, `set_complete`'in **aynı transaction'ı içinde** yazılır. |
| 9 | Öneri kabulü yalnızca yerel state + taslak (`PUT /api/drafts`). Ekstra `annotation_save` yok → `speed_warning`, versiyon zinciri ve XP etkilenmez. |
| 10 | Highlight: sunucu alıntıyı `evidence_match_mode` ile doğrular, konumlandırmayı istemci render ettiği string üzerinde boşluk/noktalama toleranslı eşleştiriciyle yapar. |
| 11 | Denetim ekranı sağ paneli devralır (`QualityAuditPanel.tsx`), overlay yoktur — doküman %60'ta görünür kalır, hover → `scrollIntoView`. |
| 12 | Referans politikası sabit: `ignore_vuk_213_article_413_v1`. Her audit satırı `policy_id` taşır; v2 adayları override analizinden çıkar. |
| 13 | Yeniden eğitim export'u DQC'nin mühürlü GT kapısına dokunmaz; ayrı nesil dizini üretir. Gold ölçütü: `is_completed=1` + audit kaydı olan her doküman. |
| 14 | `char_limit_warning` model alıntılarıyla birebir örtüşen ihlalleri atlar. |
| 15 | Tetikleme: "Tamamla"da otomatik + panelde manuel "Model ile karşılaştır" butonu. "Kontrole Gönder"de denetim çalışmaz. |

## Veritabanı

Migration: `backend/migrations/v0017_quality_audit.py`

### `model_predictions`

| Kolon | Tip | Kısıt |
|-------|-----|-------|
| `document_id` | TEXT PRIMARY KEY | FK → documents_meta(document_id) ON DELETE CASCADE |
| `generation` | TEXT NOT NULL | örn. `G0` |
| `status` | TEXT NOT NULL | CHECK IN ('success','error') |
| `references_json` | TEXT NOT NULL DEFAULT '[]' | model referans listesi |
| `truncated` | INTEGER NOT NULL DEFAULT 0 | CHECK IN (0,1) |
| `model_fingerprint` | TEXT NOT NULL | DQC `MlxG0Backend.model_fingerprint` |
| `prediction_fingerprint` | TEXT NOT NULL | sha256(canonical json) — ETag |
| `text_sha256` | TEXT NOT NULL | modelin okuduğu `pdf_text`'in sha256'sı |
| `source` | TEXT NOT NULL | `dqcheck_agent` |
| `error` | TEXT | model hata mesajı |
| `operational_json` | TEXT NOT NULL DEFAULT '{}' | latency, token sayıları |
| `created_at` / `updated_at` | TIMESTAMP NOT NULL | — |

İndeks: `idx_pred_generation (generation)`
Outbox: **muaf** (`OUTBOX_EXCLUDED_TABLES`'a eklenir)

### `annotation_audit_logs`

| Kolon | Tip | Kısıt |
|-------|-----|-------|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | — |
| `document_id` | TEXT NOT NULL | FK → documents_meta ON DELETE CASCADE |
| `user_id` | INTEGER | FK → users ON DELETE SET NULL |
| `bucket` | TEXT | GREEN/YELLOW/RED/QUARANTINE veya NULL |
| `decision` | TEXT NOT NULL | CHECK IN ('no_discrepancy','accepted_model','human_override','model_unavailable') |
| `reason` | TEXT | model_unavailable alt nedeni |
| `reasons_json` | TEXT NOT NULL DEFAULT '[]' | router reason listesi |
| `similarity` | REAL | — |
| `model_only_json` | TEXT NOT NULL DEFAULT '[]' | kanonik tuple dizisi |
| `human_only_json` | TEXT NOT NULL DEFAULT '[]' | kanonik tuple dizisi |
| `prediction_fingerprint` | TEXT | — |
| `policy_id` | TEXT NOT NULL | — |
| `model_generation` | TEXT | — |
| `created_at` | TIMESTAMP NOT NULL | — |

İndeksler: `idx_audit_doc_time (document_id, created_at DESC)`, `idx_audit_decision (decision)`, `idx_audit_bucket (bucket)`
Outbox: **dahil** (`build_triggers_for_table`)

**Kanonik tuple formatı (Kural 5):** `model_only_json` / `human_only_json` her satırda
`{"kanun_no": "213", "madde": "114", "fikra": "", "bent": ""}` tutar; böylece
`json_each` + `json_extract` ile doğrudan dağılım analizi yapılabilir.

## Backend

### Modül: `backend/quality/`

```
backend/quality/
├── __init__.py            → router export
├── dqcheck_core/          → vendored DQC (8 dosya, değiştirilmez)
│   ├── upstream_manifest.json
│   └── UPSTREAM.md
├── adapter.py             → AP dict ↔ DQC dict, ab_diff, audit_references()
├── service.py             → tahmin okuma/yazma, AuditReport, karar türetme
├── models.py              → Pydantic şemalar
├── routes.py              → POST /api/annotations/{id}/pre-audit
├── internal_routes.py     → GET/POST /api/internal/predictions*
└── tokens.py              → require_ingest_token
```

### Endpoint'ler

| Method | Path | Auth | Amaç |
|--------|------|------|------|
| POST | `/api/annotations/{document_id}/pre-audit` | `require_passed_training` | Salt-okuma denetim; hiçbir şey yazmaz |
| GET | `/api/internal/predictions/pending?limit=N` | `require_ingest_token` | Tahmini olmayan/bayat dokümanlar + `pdf_text` |
| POST | `/api/internal/predictions` | `require_ingest_token` | Idempotent upsert (`{"items": [...]}`, max 16) |
| POST | `/api/annotations/{document_id}/complete` | mevcut | `audit_ack` alanı eklenir; 409 `audit_required` / `audit_stale` |

### Karar türetme (tamamen sunucu taraflı)

```
tahmin yok / status='error' / truncated / text_sha256 uyuşmuyor → model_unavailable
bucket RED|YELLOW                                              → human_override   (ack şart)
bucket GREEN ve commit'te modelden gelen yeni referans var      → accepted_model
bucket GREEN, aksi halde                                        → no_discrepancy
```

`accepted_model` istemci beyanına değil kanıta dayanır:
`{full_identity(commit)} ∩ {full_identity(model)} − {full_identity(önceki sürüm)}` boş değilse
kullanıcı bu turda modelden bir referans almıştır.

### Token güvenliği (Kural 4)

`Authorization: Bearer <token>` başlığı `split(None, 1)` ile parse edilir; parça sayısı
2 değilse veya şema `bearer` değilse `None` döner — `IndexError`/`TypeError` mümkün değildir.
Karşılaştırma `secrets.compare_digest` ile sabit zamanlıdır. `DQCHECK_INGEST_TOKEN`
tanımsızsa endpoint'ler **503** `prediction_ingest_disabled` döner (500 değil).

Model tahmini gövdesi `ModelReferenceItem` ile doğrulanır — `ReferenceItem`'in
`pre_normalize` validator'ı **kullanılmaz**: tek bozuk model referansı (örn. `madde="5/1-a"`)
yüzünden 16'lık batch'in tamamı 422 olmamalıdır. Normalizasyon zaten denetim anında
DQC'nin `validate_reference_list` katmanında yapılır.

## Frontend

```
frontend/src/
├── components/annotation/QualityAuditPanel.tsx   → denetim ekranı (sağ panel)
├── components/annotation/DocViewer.tsx           → highlights + activeQuote props
├── lib/quoteMatcher.ts                           → toleranslı alıntı konumlama
├── api/queries/annotations.ts                    → usePreAuditMutation + audit_ack
└── routes/AnnotateDoc.tsx                        → denetim durum makinesi
```

Denetim durum makinesi:

```
idle ──"Tamamla"──> running ──model_unavailable──> complete (ack'siz)
                          ├──GREEN──────────────> complete (ack'li)
                          └──YELLOW|RED─────────> open (panel)

open ──"Listeme ekle"────> open        (yerel state + taslak)
     ──"Tamamla"─────────> running     (yeniden denetim)
     ──"Yine de tamamla"─> complete (ack'li, human_override)
     ──"Düzenlemeye dön"─> idle
```

## DQC tarafı

Yeni CLI alt komutu (`cli.py` + `commands.py` + `predict_agent.py`):

```bash
dqcheck --config configs/default.json predict-agent \
  --space-url https://<space>.hf.space \
  --token-env DQCHECK_INGEST_TOKEN \
  --batch-size 4 --poll-seconds 30 [--once]
```

Ajan durumsuzdur: DQC store'una yazmaz, yalnızca Space'i sorar ve sonuç gönderir.
`--once` ve enjekte edilebilir transport sayesinde ağ olmadan test edilir.
Canlı ingest yolunda fixture/fake backend seçeneği yoktur; bu davranış yalnızca
izole birim/E2E testlerinin sınırları içinde simüle edilir.

## Export

`scripts/export_verified_corpus.py --out data/ground_truth/gt_v4_platform_<tarih>`

```
gt_v4_platform_2026-08-18/
├── validated/doc_1.json …            {doc_id, text, references, source_document_id}
├── manifest.json                     {schema_version, generated_at, count, files[], manifest_fingerprint}
├── audit_sidecar.jsonl               {doc_id, source_document_id, bucket, decision, unique_users_count, …}
└── id_map.json                       {evrakOid: doc_id}
```

`doc_id` ataması deterministik: `document_id`'ye göre sıralı 1..N. DQC'nin
`validate_canonical_sources` kapısına **dokunulmaz**; v4'ün eğitim hattına alınması
ayrı ve bilinçli bir iştir.

## Beş ek kural (kod yazarken tuzaklar)

1. **`audit_stale` yumuşak kurtarma.** Kullanıcı etiketlerken ajan yeni tahmin push
   edebilir; `/complete` 409 `audit_stale` döner. Frontend panik göstermez: yeni denetimi
   sessizce çeker, paneli güncel uyuşmazlıklarla açar ve şu bilgiyi gösterir —
   *"Yeni model tahmini alındı, lütfen son kez teyit edip Tamamla'ya basınız."*
2. **Taslak debounce yarışı.** Öneri kabulünden yarım saniye sonra "Tamamla"ya basılırsa
   debounce'lu taslak PUT'u henüz gitmemiş olabilir. Bu yüzden kabul edilen liste
   senkron olarak `refsRef.current`'a yazılır ve `handleComplete` payload'ını
   `refs.list` yerine bu ref'ten alır.
3. **Çoklu alıntı eşleşmesi.** Aynı madde metinde birden fazla geçebilir. Eşleştirici
   sırayla `exact → folded → loose` dener; bir seviyede birden fazla eşleşme varsa
   referansın `madde` token'ına en yakın olanı seçer, o da yoksa ilk eşleşmeye kaydırır.
4. **Token parse ve karşılaştırma.** Yukarıdaki "Token güvenliği" bölümü.
5. **Kanonik tuple formatı.** Yukarıdaki `annotation_audit_logs` bölümü.

## Kapsam dışı

- Canlı (submit anında) MLX inference — HF donanımında imkânsız.
- `reference_policy` v2 madde seti — önce override kanıtı toplanacak.
- DQC `validate_canonical_sources`'ın v4 nesli kabul etmesi.
- Prediction cache için çok-nesilli model registry/fingerprint rollout'u.
- Denetim kararlarının admin panelinde raporlanması.
