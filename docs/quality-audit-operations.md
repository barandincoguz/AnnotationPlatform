# Kalite Denetimi — Operasyon Runbook'u

Tasarım: `docs/superpowers/specs/2026-08-18-pre-submit-quality-audit-design.md`

## Bileşenler

| Nerede | Ne | Ayakta kalması gerekiyor mu |
|--------|----|------------------------------|
| HF Space (prod) | Karşılaştırma motoru (vendored), `model_predictions` önbelleği, denetim ekranı | Evet — annotator akışı buna bağlı |
| Mac (yerel) | `dqcheck predict-agent`, MLX + G0 | Hayır — durursa yalnızca önbellek tazelenmez |

## Kurulum (bir kez)

1. Token üret: `openssl rand -hex 32`
2. HF Space → Settings → Variables and secrets → **Secret** olarak `DQCHECK_INGEST_TOKEN`.
3. Mac'te aynı değeri dışa aktar:
   ```bash
   export DQCHECK_INGEST_TOKEN=<aynı değer>
   ```
4. Bağlantıyı doğrula:
   ```bash
   curl -s -H "Authorization: Bearer $DQCHECK_INGEST_TOKEN" \
     "https://<space>.hf.space/api/internal/predictions/pending?limit=1" | head
   ```
   `{"documents":[...]}` → tamam. `503` → secret Space'te tanımlı değil.
   `401` → değerler uyuşmuyor.

## Ajanı çalıştırma

```bash
cd /Users/student2/data-quality-checker
dqcheck --config configs/default.json predict-agent \
  --space-url https://<space>.hf.space \
  --batch-size 4 --poll-seconds 30
```

Tek turluk deneme: `--once` ekle. MLX olmadan sözleşmeyi denemek için
`--fake-backend` (modelin yerine insan referanslarını yansıtır; yalnızca test).

Sürekli çalıştırmak için `launchd` (macOS'ta oturum kapansa da ayakta kalır) veya
uzun ömürlü bir `tmux` oturumu kullan. Ajan durumsuzdur: öldürüp yeniden
başlatmak güvenlidir, kaldığı yeri Space'e sorarak bulur.

## Sağlık kontrolü

```sql
-- Kaç dokümanda tahmin var?
SELECT COUNT(*) FROM model_predictions;
-- Denetim kararlarının dağılımı
SELECT decision, COUNT(*) FROM annotation_audit_logs GROUP BY decision;
-- Politika v2 adayları: modelin ısrar ettiği, insanın reddettiği kimlikler
SELECT json_extract(m.value,'$.kanun_no') AS kanun_no,
       json_extract(m.value,'$.madde')    AS madde,
       COUNT(*)                           AS override_count
FROM annotation_audit_logs a, json_each(a.model_only_json) m
WHERE a.decision='human_override' AND a.bucket='RED'
GROUP BY 1, 2
ORDER BY override_count DESC;
```

## Arıza senaryoları

| Belirti | Sebep | Ne yapılır |
|---------|-------|------------|
| Panelde hiç uyuşmazlık çıkmıyor, "model kontrolü yapılamadı" yazıyor | Tahmin yok | Ajan çalışıyor mu? `pending` endpoint'i ne diyor? |
| Ajan `401` alıyor | Token uyuşmazlığı | Space secret'ı ile yerel env'i karşılaştır |
| Ajan `503` alıyor | Space'te secret tanımsız | HF Space Settings'ten ekle, Space'i restart et |
| `predict failed ... Metal` | MLX ortamı bozuldu | Ajan zaten geri çekiliyor; MLX'i onarınca kendiliğinden devam eder. Sahte tahmin **yazılmaz** |
| Kullanıcı 409 `audit_stale` görüyor | Ajan çalışırken yeni tahmin geldi | Beklenen davranış: panel kendini yeniler, kullanıcı teyit eder |
| Space sıfırlandı, tahminler gitti | Ephemeral disk | GitHub snapshot'ından restore + ajan eksikleri doldurur (idempotent) |

## Yeniden eğitim export'u

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python scripts/export_verified_corpus.py \
  --out /Users/student2/data-quality-checker/data/ground_truth/gt_v4_platform_$(date -u +%Y-%m-%d)
```
