# Vendored DQCheck core

Bu dizin `data-quality-checker` deposundaki saf (stdlib-only) karşılaştırma
çekirdeğinin **birebir kopyasıdır**. Kaynak commit ve dosya sha256'ları
`upstream_manifest.json` içindedir.

## Neden vendor?

Prod ortamı bir Hugging Face Space'tir ve Docker build context'i yalnızca bu
repoyu kopyalar (`COPY requirements.txt pyproject.toml ./`). DQC deposunun git
remote'u yoktur; path veya git bağımlılığı prod build'inde çözülemez. Kopyalanan
sekiz modül yalnızca stdlib kullandığı için AP'ye yeni runtime bağımlılığı da
eklemez.

## Kurallar

1. **Bu dizindeki `.py` dosyaları düzenlenmez.** Lint/format düzeltmesi bile
   yapılmaz — `tests/test_dqcheck_parity.py` sha256 karşılaştırmasıyla kırılır.
2. AP'ye özgü her şey `backend/quality/adapter.py` içinde yaşar.
3. `data_quality_checker.hitl.ab_diff` **kopyalanmadı**: `hitl.py` modül
   seviyesinde Flask import ediyor. Eşdeğer mantık `adapter.ab_diff` içinde
   yeniden yazılmıştır ve `tests/test_dqcheck_adapter.py` ile davranışsal olarak
   sabitlenmiştir.

## Güncelleme prosedürü

```bash
SRC=/Users/student2/data-quality-checker/src/data_quality_checker
for f in router normalization reference_policy text contracts constants errors fingerprints; do
  cp "$SRC/$f.py" backend/quality/dqcheck_core/$f.py
done
# upstream_manifest.json'u yeniden üret (plan Task 1 Step 4), sonra:
python -m pytest tests/test_dqcheck_parity.py tests/test_dqcheck_adapter.py -v
```

`DQCHECK_UPSTREAM_PATH` ortam değişkeni tanımlıysa parity testi kopyayı canlı
upstream ile de karşılaştırır; tanımsızsa (CI, Docker) yalnızca manifest
bütünlüğü doğrulanır.
