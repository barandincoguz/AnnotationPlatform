# Pre-Submit Quality Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Etiketleyici "Tamamla"ya bastığında insan etiketleri ile G0 model tahminini karşılaştırıp uyuşmazlıkları submit öncesinde gösteren, kullanıcıyı hiçbir zaman modele uymaya zorlamayan bir kalite denetim akışı kurmak.

**Architecture:** DQCheck'in saf karşılaştırma çekirdeği AP'ye vendor'lanır ve FastAPI içinde çalışır. Model tahminleri Mac'te çalışan `dqcheck predict-agent` tarafından üretilip HF Space'e outbound HTTPS ile push edilir, `model_predictions` tablosunda önbelleklenir. `/complete` bucket'ı commit edilecek referanslarla yeniden hesaplar; RED/YELLOW ise `audit_ack` beyanı ister. Denetim ekranı sağ paneli devralır, doküman görünür kalır.

**Tech Stack:** Python 3.11 / FastAPI / SQLite (AP), React 18 / TypeScript strict / TanStack Query / Tailwind (frontend), pytest + vitest + Playwright, data-quality-checker (Python 3.11, MLX yalnızca Mac'te).

**Design spec:** `docs/superpowers/specs/2026-08-18-pre-submit-quality-audit-design.md`

## Global Constraints

- **İki repo:** AP = `/Users/student2/AnnotationPlatform`, DQC = `/Users/student2/data-quality-checker`. Her görev hangi repoda çalıştığını "Files" bloğunda mutlak yolla belirtir.
- **Vendored dosyalar değiştirilemez.** `backend/quality/dqcheck_core/*.py` upstream'den birebir kopyadır; AP'ye özgü her şey `adapter.py` içinde yaşar. Formatlama/lint düzeltmesi dahil hiçbir düzenleme yapılmaz (AP CI'da `ruff check` adımı `continue-on-error: true`, bu yüzden 100 karakter satır uzunluğu sorun değildir).
- **AP'ye yeni runtime bağımlılığı eklenmez.** Vendored çekirdek yalnızca stdlib kullanır; `requirements.txt` değişmez.
- **Migration deseni:** `backend/migrations/vNNNN_name.py`, modül seviyesinde `SCHEMA_SQL` + `up(conn)`. Migration'lar `pkgutil` ile otomatik keşfedilir; kayıt listesi yoktur.
- **Backend modül deseni:** `models.py` (Pydantic) + `service.py` (DB mantığı) + `routes.py` (FastAPI) + `__init__.py` (router export).
- **Auth:** kullanıcı rotaları `Depends(require_passed_training)`, internal rotalar `Depends(require_ingest_token)`, admin rotaları `Depends(require_admin)`.
- **Transaction disiplini:** yazan servisler `db.execute("BEGIN IMMEDIATE")` ile başlar, `COMMIT`/`ROLLBACK` ile kapanır; yardımcı fonksiyonlar kendi transaction kontrolünü yapmaz.
- **Frontend `exactOptionalPropertyTypes` açıktır:** `key: undefined` göndermek yasak; koşullu spread (`...(cond && { key: value })`) kullanılır.
- **Türkçe UI metinleri planda birebir verilmiştir** — değiştirilmeden kullanılacak (testler bu stringlere bakıyor).
- **TDD:** her görevde önce başarısız test, sonra minimum implementasyon, sonra yeşil test, sonra commit.
- **Yorumlayıcı:** her iki repo için tek ortam — `/opt/llm-lab/.venv` (Python 3.11.15), kullanıcının `lab` alias'ının açtığı venv. AP'nin, DQC'nin ve MLX'in (mlx 0.31.1, mlx-lm 0.31.2) tüm bağımlılıkları buradadır. Bu makinede bare `python` **yoktur** (`python3`=3.14.6 psycopg import edemez), ve alias etkileşimsiz kabukta genişlemez — komutlar daima mutlak yolla yazılır: `cd <repo> && /opt/llm-lab/.venv/bin/python -m pytest …`. AP frontend: `cd frontend && npx vitest run <dosya>`. Lint: `/opt/llm-lab/.venv/bin/ruff check`.
- **Yeşil baseline (bu dal başlarken ölçüldü):** AP `/opt/llm-lab/.venv/bin/python -m pytest tests/ -q -m "not docker"` → **1180 passed, 1 skipped, 5 deselected, 2 warnings**; DQC `-m "not compute"` → **162 passed**. O 2 uyarı starlette'in `TestClient(timeout=…)` DeprecationWarning'idir; lab venv AP'nin pinlerinden yeni starlette taşıdığı için görünür, kodla ilgisi yoktur ve baseline'ın parçasıdır. "Regresyon yok" bu sayılara göre değerlendirilir.
- **`requirements.txt` değiştirilmez.** Prod'daki `psycopg[binary]==3.2.4` pini bu platformda PyPI'da bulunmadığı için yerel `.venv` psycopg'yi pinsiz kurar; bu yalnızca yerel bir ortam ayrıntısıdır, pin olduğu gibi kalır.
- **Commit formatı:** conventional commit + `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` trailer.
- **Karar sözlüğü:** `decision ∈ {no_discrepancy, accepted_model, human_override, model_unavailable}`, `bucket ∈ {GREEN, YELLOW, RED, QUARANTINE, null}`, `audit_status ∈ {ready, model_unavailable}`, `reason ∈ {no_prediction, model_error, model_truncated, prediction_text_stale}`.

---

## File Structure

**AP — yeni dosyalar**

| Dosya | Sorumluluk |
|-------|-----------|
| `backend/quality/dqcheck_core/*.py` (8 dosya + `__init__.py`) | Vendored DQC çekirdeği; dokunulmaz |
| `backend/quality/dqcheck_core/upstream_manifest.json` | Kaynak commit + dosya sha256 tablosu (makine okur) |
| `backend/quality/dqcheck_core/UPSTREAM.md` | Vendor kuralları, güncelleme prosedürü (insan okur) |
| `backend/quality/adapter.py` | AP↔DQC sözlük köprüsü, `ab_diff`, `audit_references` |
| `backend/quality/service.py` | Tahmin önbelleği, `AuditReport`, karar türetme, audit log yazımı |
| `backend/quality/models.py` | Pydantic şemalar (pre-audit + ingest) |
| `backend/quality/routes.py` | `POST /api/annotations/{id}/pre-audit` |
| `backend/quality/internal_routes.py` | `GET/POST /api/internal/predictions*` |
| `backend/quality/tokens.py` | `require_ingest_token` (sabit zamanlı, güvenli parse) |
| `backend/migrations/v0017_quality_audit.py` | İki tablo + outbox trigger'ları + muafiyet |
| `scripts/export_verified_corpus.py` | Doğrulanmış korpus export'u |
| `frontend/src/lib/quoteMatcher.ts` | Toleranslı alıntı konumlama + segmentleme |
| `frontend/src/components/annotation/QualityAuditPanel.tsx` | Denetim ekranı |

**AP — değişen dosyalar**

| Dosya | Değişiklik |
|-------|-----------|
| `backend/main.py` | quality router'ları mount, `MIRROR_RESTORE_TABLES`'a `annotation_audit_logs` |
| `backend/config.py` | `DQCHECK_INGEST_TOKEN` |
| `backend/annotations/models.py` | `AuditAck` + `CompleteRequest.audit_ack` |
| `backend/annotations/service.py` | `set_complete(..., audit_ack)` + audit değerlendirme/log |
| `backend/annotations/routes.py` | 409 eşlemeleri + `model_quotes` aktarımı |
| `backend/behavioral/service.py` | `char_limit_warning` muafiyeti |
| `backend/migrations/helpers/trigger_generator.py` | `OUTBOX_EXCLUDED_TABLES` += `model_predictions` |
| `backend/cli.py` | `seed-e2e` içine tahmin fixture'ı |
| `frontend/src/api/queries/annotations.ts` | `usePreAuditMutation`, `audit_ack` |
| `frontend/src/components/annotation/DocViewer.tsx` | `highlights` + `activeHighlightId` props |
| `frontend/src/components/annotation/ReferencePanel.tsx` | `model_unavailable` satırı + "Model ile karşılaştır" butonu |
| `frontend/src/routes/AnnotateDoc.tsx` | Denetim durum makinesi, 409 kurtarma, `refsRef` |

**DQC — değişen/yeni dosyalar**

| Dosya | Değişiklik |
|-------|-----------|
| `src/data_quality_checker/predict_agent.py` | Yeni: pull/predict/push döngüsü |
| `src/data_quality_checker/commands.py` | Yeni `predict_agent` handler |
| `src/data_quality_checker/cli.py` | `predict-agent` alt komutu |
| `README.md` | Komut tablosuna satır |

---

# FAZ 1 — Motor ve şema

## Task 1: DQCheck çekirdeğini vendor'la + parity ağı

**Files:**
- Create: `/Users/student2/AnnotationPlatform/backend/quality/__init__.py`
- Create: `/Users/student2/AnnotationPlatform/backend/quality/dqcheck_core/__init__.py`
- Create (kopya): `backend/quality/dqcheck_core/{router,normalization,reference_policy,text,contracts,constants,errors,fingerprints}.py`
- Create: `backend/quality/dqcheck_core/upstream_manifest.json`
- Create: `backend/quality/dqcheck_core/UPSTREAM.md`
- Test: `/Users/student2/AnnotationPlatform/tests/test_dqcheck_parity.py`

**Interfaces:**
- Consumes: hiçbir şey.
- Produces: `backend.quality.dqcheck_core` paketi — `router.route_document`, `router.RouteDecision`, `normalization.{core_identity, full_identity, compact_references, normalize_reference, conflicting_law_identity}`, `reference_policy.{DEFAULT_REFERENCE_POLICY_ID, apply_reference_policy}`, `text.{normalize_text, folded_text, loose_text, evidence_match_mode}`, `contracts.validate_reference_list`, `fingerprints.{fingerprint_json, sha256_text, sha256_file, canonical_json_bytes}`, `constants.REFERENCE_FIELDS`.

- [ ] **Step 1: Paket dizinlerini ve boş `__init__.py`'leri oluştur**

```bash
cd /Users/student2/AnnotationPlatform
mkdir -p backend/quality/dqcheck_core
cat > backend/quality/__init__.py <<'PY'
"""Pre-submit quality audit: vendored DQCheck engine + AP-facing services."""
PY
cat > backend/quality/dqcheck_core/__init__.py <<'PY'
"""Vendored subset of data-quality-checker. DO NOT EDIT — see UPSTREAM.md."""
PY
```

- [ ] **Step 2: Sekiz saf modülü birebir kopyala**

Bu sekiz dosya import kapalı bir kümedir (yalnızca birbirlerini ve stdlib'i kullanır); Flask/MLX çekmezler.

```bash
cd /Users/student2/AnnotationPlatform
SRC=/Users/student2/data-quality-checker/src/data_quality_checker
for f in router normalization reference_policy text contracts constants errors fingerprints; do
  cp "$SRC/$f.py" "backend/quality/dqcheck_core/$f.py"
done
ls backend/quality/dqcheck_core/
```

Expected: `__init__.py constants.py contracts.py errors.py fingerprints.py normalization.py reference_policy.py router.py text.py`

- [ ] **Step 3: Import kapanışını doğrula (Flask/MLX sızıntısı yok)**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python - <<'PY'
import sys
import backend.quality.dqcheck_core.router as r
leaked = sorted(m for m in sys.modules if m.split(".")[0] in {"flask", "mlx", "mlx_lm"})
print("leaked:", leaked)
print("bucket:", r.route_document(human_references=[], model_references=[]).bucket)
PY
```

Expected: `leaked: []` ve `bucket: GREEN`

- [ ] **Step 4: `upstream_manifest.json` üret**

```bash
cd /Users/student2/AnnotationPlatform
UPSTREAM_COMMIT=$(git -C /Users/student2/data-quality-checker rev-parse HEAD)
python - "$UPSTREAM_COMMIT" <<'PY'
import hashlib, json, sys
from pathlib import Path

commit = sys.argv[1]
core = Path("backend/quality/dqcheck_core")
files = {}
for path in sorted(core.glob("*.py")):
    if path.name == "__init__.py":
        continue
    files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
payload = {
    "upstream_repo": "data-quality-checker",
    "upstream_commit": commit,
    "upstream_package_path": "src/data_quality_checker",
    "vendored_at": "2026-08-18",
    "files": files,
}
(core / "upstream_manifest.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps(payload, indent=2, sort_keys=True))
PY
```

Expected: 8 dosya için sha256 içeren JSON basılır.

- [ ] **Step 5: `UPSTREAM.md`'yi yaz**

```markdown
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
/opt/llm-lab/.venv/bin/python -m pytest tests/test_dqcheck_parity.py tests/test_dqcheck_adapter.py -v
```

`DQCHECK_UPSTREAM_PATH` ortam değişkeni tanımlıysa parity testi kopyayı canlı
upstream ile de karşılaştırır; tanımsızsa (CI, Docker) yalnızca manifest
bütünlüğü doğrulanır.
```

- [ ] **Step 6: Parity testini yaz (başarısız olması beklenir — dosya henüz yok)**

```python
"""Vendored dqcheck_core drift guard.

Two layers:
  * manifest integrity — always runs, catches accidental local edits.
  * upstream comparison — runs only when DQCHECK_UPSTREAM_PATH points at a
    checkout of the data-quality-checker repo (dev machines), so CI and the
    Docker build stay green without the sibling repo.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

CORE_DIR = Path(__file__).resolve().parents[1] / "backend" / "quality" / "dqcheck_core"
MANIFEST_PATH = CORE_DIR / "upstream_manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_lists_every_vendored_module():
    vendored = {p.name for p in CORE_DIR.glob("*.py")} - {"__init__.py"}
    assert vendored == set(_manifest()["files"])


def test_vendored_files_match_manifest_hashes():
    for name, expected in _manifest()["files"].items():
        assert _sha256(CORE_DIR / name) == expected, (
            f"{name} vendored copy was edited; revert it or re-run the "
            "UPSTREAM.md update procedure"
        )


def test_vendored_core_imports_without_flask_or_mlx():
    import sys

    import backend.quality.dqcheck_core.router  # noqa: F401

    leaked = {m.split(".")[0] for m in sys.modules} & {"flask", "mlx", "mlx_lm"}
    assert leaked == set()


@pytest.mark.skipif(
    not os.environ.get("DQCHECK_UPSTREAM_PATH"),
    reason="DQCHECK_UPSTREAM_PATH not set (CI/Docker have no sibling checkout)",
)
def test_vendored_files_match_live_upstream():
    upstream = Path(os.environ["DQCHECK_UPSTREAM_PATH"]) / "src" / "data_quality_checker"
    for name in _manifest()["files"]:
        assert _sha256(CORE_DIR / name) == _sha256(upstream / name), (
            f"{name} drifted from upstream; re-vendor per UPSTREAM.md"
        )
```

- [ ] **Step 7: Testi çalıştır**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_dqcheck_parity.py -v
DQCHECK_UPSTREAM_PATH=/Users/student2/data-quality-checker /opt/llm-lab/.venv/bin/python -m pytest tests/test_dqcheck_parity.py -v
```

Expected: ilk komutta 3 passed + 1 skipped; ikinci komutta 4 passed.

- [ ] **Step 8: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add backend/quality tests/test_dqcheck_parity.py
git commit -m "feat(quality): vendor dqcheck comparison core with parity guard

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Adapter — `audit_references` + `ab_diff` + 9 altın kova vakası

**Files:**
- Create: `/Users/student2/AnnotationPlatform/backend/quality/adapter.py`
- Test: `/Users/student2/AnnotationPlatform/tests/test_dqcheck_adapter.py`

**Interfaces:**
- Consumes: Task 1'in `backend.quality.dqcheck_core` paketi.
- Produces:
  - `AUDIT_POLICY_ID: str` (= `"ignore_vuk_213_article_413_v1"`)
  - `AuditOutcome` dataclass: `bucket: str`, `reasons: tuple[str, ...]`, `similarity: float`, `discrepancies: tuple[dict, ...]`, `model_only: tuple[dict, ...]`, `human_only: tuple[dict, ...]`
  - `canonical_tuple(reference: dict[str, str]) -> dict[str, str]` → `{kanun_no, madde, fikra, bent}`
  - `ab_diff(human: list[dict], model: list[dict]) -> list[dict]`
  - `audit_references(*, human_references: list[dict], model_references: list[dict], document_text: str = "", model_status: str = "success", model_truncated: bool = False) -> AuditOutcome`
  - `reference_identities(references: list[dict]) -> set[tuple]` (full identity kümesi; Task 4 `accepted_model` tespitinde kullanır)

- [ ] **Step 1: Altın vaka testlerini yaz**

```python
"""Golden bucket cases for the vendored router + discrepancy alignment."""
from backend.quality.adapter import (
    AUDIT_POLICY_ID,
    audit_references,
    canonical_tuple,
    reference_identities,
)

DOC_TEXT = (
    "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir. "
    "Gelir Vergisi Kanunu'nun 94 uncu maddesi tevkifat esaslarini belirler."
)


def ref(kanun_no="213", kanun_ad="Vergi Usul Kanunu", madde="114", fikra="", bent="",
        source_text="zamanasimi hukmu duzenlenmistir"):
    return {
        "kanun_no": kanun_no, "kanun_ad": kanun_ad, "madde": madde,
        "fikra": fikra, "bent": bent, "source_text": source_text,
    }


def test_case_1_identical_sets_are_green():
    outcome = audit_references(
        human_references=[ref()], model_references=[ref()], document_text=DOC_TEXT
    )
    assert outcome.bucket == "GREEN"
    assert outcome.discrepancies == ()
    assert outcome.similarity == 1.0


def test_case_2_normalization_only_difference_is_green():
    outcome = audit_references(
        human_references=[ref(kanun_ad="VUK", madde="114.")],
        model_references=[ref(kanun_ad="Vergi Usul Kanunu", madde="114")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "GREEN"


def test_case_3_extension_mismatch_is_yellow_detail():
    outcome = audit_references(
        human_references=[ref(fikra="1")],
        model_references=[ref(fikra="2")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "YELLOW"
    assert outcome.reasons == ("extension_mismatch",)
    assert [d["kind"] for d in outcome.discrepancies] == ["detail_mismatch"]
    assert outcome.discrepancies[0]["field_diffs"] == ["fikra"]


def test_case_4_evidence_mismatch_is_yellow():
    outcome = audit_references(
        human_references=[ref(source_text="zamanasimi hukmu duzenlenmistir")],
        model_references=[ref(source_text="tevkifat esaslarini belirler")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "YELLOW"
    assert outcome.reasons == ("evidence_mismatch",)
    assert outcome.discrepancies[0]["field_diffs"] == ["source_text"]


def test_case_5_human_only_core_is_red_and_not_actionable():
    outcome = audit_references(
        human_references=[ref(), ref(kanun_no="193", kanun_ad="Gelir Vergisi Kanunu", madde="94")],
        model_references=[ref()],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "RED"
    assert "missing_core_reference" in outcome.reasons
    kinds = [d["kind"] for d in outcome.discrepancies]
    assert kinds == ["human_only"]
    assert outcome.human_only == ({"kanun_no": "193", "madde": "94", "fikra": "", "bent": ""},)
    assert outcome.model_only == ()


def test_case_6_model_only_core_is_red_and_actionable():
    outcome = audit_references(
        human_references=[ref()],
        model_references=[ref(), ref(kanun_no="193", kanun_ad="Gelir Vergisi Kanunu", madde="94",
                                    source_text="tevkifat esaslarini belirler")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "RED"
    assert "extra_or_different_core_reference" in outcome.reasons
    (discrepancy,) = outcome.discrepancies
    assert discrepancy["kind"] == "model_only"
    assert discrepancy["madde"] == "94"
    assert discrepancy["model_reference"]["source_text"] == "tevkifat esaslarini belirler"
    assert discrepancy["match_mode"] == "normalized_exact"
    assert outcome.model_only == ({"kanun_no": "193", "madde": "94", "fikra": "", "bent": ""},)


def test_case_7_conflicting_law_identity_is_red():
    # The vendored router looks for a law-number/name contradiction WITHIN one
    # candidate's own list, never across human vs model, so the conflict has to
    # live on one side: 213 appears as both VUK and GVK in the human list.
    outcome = audit_references(
        human_references=[ref(), ref(kanun_ad="Gelir Vergisi Kanunu", madde="94")],
        model_references=[ref()],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "RED"
    assert outcome.reasons == ("conflicting_law_identity",)
    assert [d["kind"] for d in outcome.discrepancies] == ["human_only"]


def test_case_8_model_error_is_quarantine():
    outcome = audit_references(
        human_references=[ref()],
        model_references=[],
        document_text=DOC_TEXT,
        model_status="error",
    )
    assert outcome.bucket == "QUARANTINE"
    assert "model_processing_error" in outcome.reasons


def test_case_9_vuk_413_boilerplate_is_filtered_by_policy():
    outcome = audit_references(
        human_references=[ref()],
        model_references=[
            ref(),
            ref(madde="413", source_text="Mukellefler Maliye Bakanligindan izahat isteyebilir"),
        ],
        document_text=DOC_TEXT,
    )
    assert AUDIT_POLICY_ID == "ignore_vuk_213_article_413_v1"
    assert outcome.bucket == "GREEN"
    assert outcome.discrepancies == ()


def test_router_compatible_evidence_stays_green_without_discrepancy_rows():
    """The diff must never contradict the bucket.

    The router treats a quote pair as compatible when one loosely contains the
    other (`normalized_five_field_set_equal` + `evidence_format_or_length_only`
    → GREEN). Deciding "same" on strict source_text equality would emit a
    detail_mismatch row for that consensus and write both identities into the
    audit log's model_only/human_only columns.
    """
    outcome = audit_references(
        human_references=[ref(source_text="zamanasimi hukmu")],
        model_references=[ref(source_text="zamanasimi hukmu duzenlenmistir")],
        document_text=DOC_TEXT,
    )
    assert outcome.bucket == "GREEN"
    assert outcome.discrepancies == ()
    assert outcome.model_only == ()
    assert outcome.human_only == ()


def test_quote_not_present_in_document_reports_no_match_mode():
    outcome = audit_references(
        human_references=[],
        model_references=[ref(source_text="bu cumle dokumanda hic yok")],
        document_text=DOC_TEXT,
    )
    assert outcome.discrepancies[0]["match_mode"] is None


def test_canonical_tuple_shape_is_json_each_friendly():
    assert canonical_tuple(
        {"kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
         "fikra": "1", "bent": "a", "source_text": "x"}
    ) == {"kanun_no": "213", "madde": "114", "fikra": "1", "bent": "a"}


def test_reference_identities_tolerates_none_fields():
    identities = reference_identities([
        {"kanun_no": "213", "kanun_ad": None, "madde": "114",
         "fikra": None, "bent": None, "source_text": "x"}
    ])
    assert len(identities) == 1
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_dqcheck_adapter.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.quality.adapter'`

- [ ] **Step 3: `adapter.py`'yi yaz**

```python
"""AP ↔ DQCheck bridge: policy, routing, and human/model discrepancy alignment.

`dqcheck_core/` is vendored verbatim and must not be edited (see its
UPSTREAM.md). Everything AP-specific lives here.

`ab_diff` is a behavioural reimplementation of
`data_quality_checker.hitl.ab_diff`: that upstream module imports Flask at
module scope and AP must not take a Flask runtime dependency. "a" is always the
human side, "b" the model side.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.quality.dqcheck_core.normalization import (
    core_identity,
    full_identity,
    normalize_reference,
)
from backend.quality.dqcheck_core.reference_policy import DEFAULT_REFERENCE_POLICY_ID
from backend.quality.dqcheck_core.router import route_document
from backend.quality.dqcheck_core.text import evidence_match_mode, normalize_text

AUDIT_POLICY_ID = DEFAULT_REFERENCE_POLICY_ID

# Fields compared when two references share a core identity. Mirrors the
# upstream hitl._DIFF_FIELDS tuple.
_DIFF_FIELDS = ("fikra", "bent", "source_text")

_KIND_BY_STATUS = {
    "only_a": "human_only",
    "only_b": "model_only",
    "differs": "detail_mismatch",
}


@dataclass(frozen=True)
class AuditOutcome:
    bucket: str
    reasons: tuple[str, ...]
    similarity: float
    discrepancies: tuple[dict[str, Any], ...]
    model_only: tuple[dict[str, str], ...]
    human_only: tuple[dict[str, str], ...]


def canonical_tuple(reference: dict[str, str]) -> dict[str, str]:
    """Analysis-friendly identity row (see design spec, rule 5)."""
    return {
        "kanun_no": reference["kanun_no"],
        "madde": reference["madde"],
        "fikra": reference["fikra"],
        "bent": reference["bent"],
    }


def reference_identities(references: list[dict[str, Any]]) -> set[tuple[str, ...]]:
    """Normalized full-identity set; tolerates AP's Optional[str] fields."""
    return {full_identity(normalize_reference(reference)) for reference in references}


def ab_diff(
    human: list[dict[str, str]], model: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Align human (a) and model (b) references by core law-article identity."""
    order: list[tuple[str, ...]] = []
    groups: dict[tuple[str, ...], dict[str, list[dict[str, str]]]] = {}
    for label, references in (("a", human), ("b", model)):
        for reference in references:
            key = core_identity(reference)
            if key not in groups:
                groups[key] = {"a": [], "b": []}
                order.append(key)
            groups[key][label].append(reference)

    rows: list[dict[str, Any]] = []
    for key in order:
        a_refs = groups[key]["a"]
        b_refs = groups[key]["b"]
        if a_refs and not b_refs:
            status = "only_a"
        elif b_refs and not a_refs:
            status = "only_b"
        elif sorted(full_identity(r) for r in a_refs) == sorted(
            full_identity(r) for r in b_refs
        ):
            status = "same"
        else:
            status = "differs"
        field_diffs: list[str] = []
        if status == "differs" and len(a_refs) == 1 and len(b_refs) == 1:
            field_diffs = [
                field
                for field in _DIFF_FIELDS
                if a_refs[0].get(field, "") != b_refs[0].get(field, "")
            ]
        sample = (a_refs or b_refs)[0]
        rows.append(
            {
                "core": {
                    "kanun_no": sample["kanun_no"],
                    "kanun_ad": sample["kanun_ad"],
                    "madde": sample["madde"],
                },
                "status": status,
                "a": a_refs,
                "b": b_refs,
                "field_diffs": field_diffs,
            }
        )
    return rows


def audit_references(
    *,
    human_references: list[dict[str, Any]],
    model_references: list[dict[str, Any]],
    document_text: str = "",
    model_status: str = "success",
    model_truncated: bool = False,
) -> AuditOutcome:
    """Route the pair, then align the two sides into UI-facing discrepancies.

    `route_document` already applies the reference policy and compaction, and
    returns the normalized views it used — we align those, never the raw input,
    so the UI and the bucket can never disagree about what was compared.
    """
    decision = route_document(
        human_references=human_references,
        model_references=model_references,
        model_status=model_status,
        model_truncated=model_truncated,
        reference_policy_id=AUDIT_POLICY_ID,
    )
    human = list(decision.human_references)
    model = list(decision.model_references)
    normalized_document = normalize_text(document_text)

    discrepancies: list[dict[str, Any]] = []
    model_only: list[dict[str, str]] = []
    human_only: list[dict[str, str]] = []
    for row in ab_diff(human, model):
        if row["status"] == "same":
            continue
        kind = _KIND_BY_STATUS[row["status"]]
        model_reference: Optional[dict[str, str]] = row["b"][0] if row["b"] else None
        human_reference: Optional[dict[str, str]] = row["a"][0] if row["a"] else None
        discrepancies.append(
            {
                "kind": kind,
                "kanun_no": row["core"]["kanun_no"],
                "kanun_ad": row["core"]["kanun_ad"],
                "madde": row["core"]["madde"],
                "model_reference": model_reference,
                "human_reference": human_reference,
                "field_diffs": list(row["field_diffs"]),
                "match_mode": (
                    evidence_match_mode(
                        model_reference["source_text"], normalized_document
                    )
                    if model_reference is not None
                    else None
                ),
            }
        )
        if kind in {"model_only", "detail_mismatch"}:
            model_only.extend(canonical_tuple(reference) for reference in row["b"])
        if kind in {"human_only", "detail_mismatch"}:
            human_only.extend(canonical_tuple(reference) for reference in row["a"])

    return AuditOutcome(
        bucket=decision.bucket,
        reasons=decision.reasons,
        similarity=decision.similarity,
        discrepancies=tuple(discrepancies),
        model_only=tuple(model_only),
        human_only=tuple(human_only),
    )
```

- [ ] **Step 4: Testin geçtiğini doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_dqcheck_adapter.py -v
```

Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add backend/quality/adapter.py tests/test_dqcheck_adapter.py
git commit -m "feat(quality): add AP<->dqcheck adapter with golden bucket cases

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Migration v0017 — iki tablo, outbox muafiyeti, mirror restore listesi

**Files:**
- Create: `/Users/student2/AnnotationPlatform/backend/migrations/v0017_quality_audit.py`
- Modify: `/Users/student2/AnnotationPlatform/backend/migrations/helpers/trigger_generator.py` (`OUTBOX_EXCLUDED_TABLES`)
- Modify: `/Users/student2/AnnotationPlatform/backend/main.py` (`MIRROR_RESTORE_TABLES`)
- Test: `/Users/student2/AnnotationPlatform/tests/test_quality_audit_migration.py`

**Interfaces:**
- Consumes: hiçbir şey (şema katmanı).
- Produces: `model_predictions` ve `annotation_audit_logs` tabloları; `annotation_audit_logs` için `_outbox_annotation_audit_logs_{ins,upd,del}` trigger'ları; `model_predictions` için **hiç** trigger yok.

- [ ] **Step 1: Testi yaz**

```python
"""v0017 schema, outbox trigger scope, and backup/mirror wiring."""
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


def _fresh(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    return conn


def test_both_tables_exist_with_expected_columns(db_path):
    conn = _fresh(db_path)
    try:
        pred = {r["name"] for r in conn.execute("PRAGMA table_info('model_predictions')")}
        assert pred == {
            "document_id", "generation", "status", "references_json", "truncated",
            "model_fingerprint", "prediction_fingerprint", "text_sha256", "source",
            "error", "operational_json", "created_at", "updated_at",
        }
        audit = {r["name"] for r in conn.execute("PRAGMA table_info('annotation_audit_logs')")}
        assert audit == {
            "id", "document_id", "user_id", "bucket", "decision", "reason",
            "reasons_json", "similarity", "model_only_json", "human_only_json",
            "prediction_fingerprint", "policy_id", "model_generation", "created_at",
        }
    finally:
        conn.close()


def test_audit_logs_are_mirrored_but_predictions_are_not(db_path):
    conn = _fresh(db_path)
    try:
        triggers = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        assert {
            "_outbox_annotation_audit_logs_ins",
            "_outbox_annotation_audit_logs_upd",
            "_outbox_annotation_audit_logs_del",
        } <= triggers
        assert not any(t.startswith("_outbox_model_predictions") for t in triggers)
    finally:
        conn.close()


def test_predictions_survive_backup_dump_and_audit_logs_are_restorable():
    from backend.backup.service import EXCLUDED_TABLES
    from backend.main import MIRROR_RESTORE_TABLES

    assert "model_predictions" not in EXCLUDED_TABLES
    assert "annotation_audit_logs" not in EXCLUDED_TABLES
    assert "annotation_audit_logs" in MIRROR_RESTORE_TABLES
    assert "model_predictions" not in MIRROR_RESTORE_TABLES


def test_decision_check_constraint_rejects_unknown_values(db_path):
    import sqlite3

    import pytest

    conn = _fresh(db_path)
    try:
        conn.execute(
            "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count,"
            " sentence_count, text_density, estimated_difficulty, created_at)"
            " VALUES ('d1','/tmp/d1.json','metin',1,1,1.0,'Kolay',datetime('now'))"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO annotation_audit_logs(document_id, decision, policy_id, created_at)"
                " VALUES ('d1','made_up_decision','p',datetime('now'))"
            )
    finally:
        conn.close()


def test_prediction_row_is_deleted_with_its_document(db_path):
    conn = _fresh(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count,"
            " sentence_count, text_density, estimated_difficulty, created_at)"
            " VALUES ('d1','/tmp/d1.json','metin',1,1,1.0,'Kolay',datetime('now'))"
        )
        conn.execute(
            "INSERT INTO model_predictions(document_id, generation, status,"
            " references_json, truncated, model_fingerprint, prediction_fingerprint,"
            " text_sha256, source, operational_json, created_at, updated_at)"
            " VALUES ('d1','G0','success','[]',0,'mf','pf','ts','dqcheck_agent','{}',"
            " datetime('now'), datetime('now'))"
        )
        conn.execute("DELETE FROM documents_meta WHERE document_id='d1'")
        assert conn.execute("SELECT COUNT(*) AS c FROM model_predictions").fetchone()["c"] == 0
    finally:
        conn.close()
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_quality_audit_migration.py -v
```

Expected: FAIL — `sqlite3.OperationalError: no such table: model_predictions`

- [ ] **Step 3: Migration'ı yaz**

```python
"""v0017 — pre-submit quality audit: prediction cache + audit decision log.

`annotation_audit_logs` gets outbox triggers (the Neon-backed analysis pipeline
reads it). `model_predictions` deliberately does NOT: its rows carry multi-KB
model output JSON, the GitHub snapshot backup already covers restore, and the
Mac-side predict-agent refills anything missing.
"""
import sqlite3

from backend.migrations.helpers.schema_introspect import introspect_table
from backend.migrations.helpers.trigger_generator import build_triggers_for_table

SCHEMA_SQL = """
CREATE TABLE model_predictions (
    document_id            TEXT PRIMARY KEY
                           REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    generation             TEXT NOT NULL,
    status                 TEXT NOT NULL CHECK(status IN ('success','error')),
    references_json        TEXT NOT NULL DEFAULT '[]',
    truncated              INTEGER NOT NULL DEFAULT 0 CHECK(truncated IN (0,1)),
    model_fingerprint      TEXT NOT NULL,
    prediction_fingerprint TEXT NOT NULL,
    text_sha256            TEXT NOT NULL,
    source                 TEXT NOT NULL,
    error                  TEXT,
    operational_json       TEXT NOT NULL DEFAULT '{}',
    created_at             TIMESTAMP NOT NULL,
    updated_at             TIMESTAMP NOT NULL
);
CREATE INDEX idx_pred_generation ON model_predictions(generation);

CREATE TABLE annotation_audit_logs (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id            TEXT NOT NULL
                           REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    user_id                INTEGER REFERENCES users(id) ON DELETE SET NULL,
    bucket                 TEXT,
    decision               TEXT NOT NULL CHECK(decision IN (
                               'no_discrepancy','accepted_model',
                               'human_override','model_unavailable')),
    reason                 TEXT,
    reasons_json           TEXT NOT NULL DEFAULT '[]',
    similarity             REAL,
    model_only_json        TEXT NOT NULL DEFAULT '[]',
    human_only_json        TEXT NOT NULL DEFAULT '[]',
    prediction_fingerprint TEXT,
    policy_id              TEXT NOT NULL,
    model_generation       TEXT,
    created_at             TIMESTAMP NOT NULL
);
CREATE INDEX idx_audit_doc_time ON annotation_audit_logs(document_id, created_at DESC);
CREATE INDEX idx_audit_decision ON annotation_audit_logs(decision);
CREATE INDEX idx_audit_bucket ON annotation_audit_logs(bucket);
"""


def up(conn: sqlite3.Connection) -> None:
    for raw in SCHEMA_SQL.split(";"):
        stmt = raw.strip()
        if stmt:
            conn.execute(stmt)
    schema = introspect_table(conn, "annotation_audit_logs")
    for stmt in build_triggers_for_table(schema):
        conn.execute(stmt)
```

- [ ] **Step 4: `model_predictions`'ı outbox muafiyetine ekle**

`backend/migrations/helpers/trigger_generator.py` içinde:

```python
OUTBOX_EXCLUDED_TABLES = frozenset({
    "user_sessions",
    "document_locks",
    "system_events",
    # Prediction rows carry multi-KB model output JSON. The GitHub snapshot
    # backup restores them and the Mac-side predict-agent refills gaps, so
    # pushing them through the Neon outbox would be pure cost (v0017).
    "model_predictions",
})
```

- [ ] **Step 5: `MIRROR_RESTORE_TABLES`'a audit log'u ekle**

`backend/main.py` içinde, `"admin_audit_log",` satırından sonra:

```python
    "annotation_audit_logs",
```

- [ ] **Step 6: Testleri çalıştır**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_quality_audit_migration.py -v
/opt/llm-lab/.venv/bin/python -m pytest tests/ -q -m "not docker" -x
```

Expected: yeni dosyada 5 passed; tam suite kırmızıya dönmemiş olmalı (mevcut testler `model_predictions` satırı olmadığı için etkilenmez).

- [ ] **Step 7: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add backend/migrations backend/main.py tests/test_quality_audit_migration.py
git commit -m "feat(quality): add v0017 prediction cache and audit log tables

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# FAZ 2 — Backend HTTP yüzeyi

## Task 4: `quality/service.py` — tahmin önbelleği, rapor, karar türetme

**Files:**
- Create: `/Users/student2/AnnotationPlatform/backend/quality/service.py`
- Test: `/Users/student2/AnnotationPlatform/tests/test_quality_service.py`

**Interfaces:**
- Consumes: Task 2 `adapter.{AUDIT_POLICY_ID, audit_references, reference_identities}`, Task 3 şeması, `dqcheck_core.fingerprints.{fingerprint_json, sha256_text}`.
- Produces:
  - `DocumentNotFound`, `AuditAckRequired(bucket, prediction_fingerprint)`, `AuditAckStale(prediction_fingerprint)`
  - `AuditReport` (frozen dataclass): `audit_status, reason, bucket, reasons, similarity, prediction_fingerprint, model_generation, discrepancies, model_only, human_only` + `to_response() -> dict`
  - `prediction_fingerprint(*, generation, model_fingerprint, references) -> str`
  - `build_report(db, *, document_id, references) -> AuditReport`
  - `evaluate_for_commit(db, *, document_id, references, previous_references, ack_fingerprint) -> tuple[AuditReport, str]`
  - `log_decision(db, *, document_id, user_id, report, decision, now=None) -> None`
  - `upsert_predictions(db, items, *, now=None) -> int`
  - `pending_documents(db, *, limit) -> list[dict]`
  - `model_quotes(db, document_id) -> tuple[str, ...]`
  - `load_prediction(db, document_id) -> Optional[sqlite3.Row]`
  - `derive_decision(report, *, accepted_from_model: bool) -> str`

- [ ] **Step 1: Testi yaz**

```python
"""Prediction cache, audit report, ack contract, and decision derivation."""
import json

import pytest

from backend.quality import service

DOC_TEXT = (
    "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir. "
    "Gelir Vergisi Kanunu'nun 94 uncu maddesi tevkifat esaslarini belirler."
)
VUK_114 = {
    "kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
    "fikra": "", "bent": "", "source_text": "zamanasimi hukmu duzenlenmistir",
}
GVK_94 = {
    "kanun_no": "193", "kanun_ad": "Gelir Vergisi Kanunu", "madde": "94",
    "fikra": "", "bent": "", "source_text": "tevkifat esaslarini belirler",
}


@pytest.fixture
def db(client, ingest_doc):
    from backend import config
    from backend.shared.db import connect

    ingest_doc("d1", pdfText=DOC_TEXT)
    conn = connect(config.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def seed_prediction(conn, *, document_id="d1", references=(VUK_114,), status="success",
                    truncated=0, text=DOC_TEXT, generation="G0"):
    from backend.quality.dqcheck_core.fingerprints import sha256_text

    refs = list(references)
    fingerprint = service.prediction_fingerprint(
        generation=generation, model_fingerprint="mf-1", references=refs
    )
    conn.execute(
        """INSERT OR REPLACE INTO model_predictions(
            document_id, generation, status, references_json, truncated,
            model_fingerprint, prediction_fingerprint, text_sha256, source,
            error, operational_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,NULL,'{}',datetime('now'),datetime('now'))""",
        (document_id, generation, status, json.dumps(refs), truncated,
         "mf-1", fingerprint, sha256_text(text), "dqcheck_agent"),
    )
    return fingerprint


def test_missing_prediction_reports_model_unavailable(db):
    report = service.build_report(db, document_id="d1", references=[VUK_114])
    assert report.audit_status == "model_unavailable"
    assert report.reason == "no_prediction"
    assert report.bucket is None
    assert report.discrepancies == ()


def test_unknown_document_raises(db):
    with pytest.raises(service.DocumentNotFound):
        service.build_report(db, document_id="nope", references=[])


def test_model_error_status_reports_model_error(db):
    seed_prediction(db, status="error", references=[])
    report = service.build_report(db, document_id="d1", references=[VUK_114])
    assert (report.audit_status, report.reason) == ("model_unavailable", "model_error")


def test_truncated_prediction_reports_model_truncated(db):
    seed_prediction(db, truncated=1)
    report = service.build_report(db, document_id="d1", references=[VUK_114])
    assert (report.audit_status, report.reason) == ("model_unavailable", "model_truncated")


def test_prediction_against_older_text_is_stale(db):
    seed_prediction(db, text="tamamen baska bir metin")
    report = service.build_report(db, document_id="d1", references=[VUK_114])
    assert (report.audit_status, report.reason) == (
        "model_unavailable", "prediction_text_stale",
    )


def test_matching_sets_are_green_and_need_no_ack(db):
    fingerprint = seed_prediction(db)
    report, decision = service.evaluate_for_commit(
        db, document_id="d1", references=[VUK_114],
        previous_references=[VUK_114], ack_fingerprint=None,
    )
    assert (report.audit_status, report.bucket) == ("ready", "GREEN")
    assert decision == "no_discrepancy"
    assert report.prediction_fingerprint == fingerprint


def test_red_bucket_without_ack_raises_ack_required(db):
    fingerprint = seed_prediction(db, references=[VUK_114, GVK_94])
    with pytest.raises(service.AuditAckRequired) as excinfo:
        service.evaluate_for_commit(
            db, document_id="d1", references=[VUK_114],
            previous_references=[VUK_114], ack_fingerprint=None,
        )
    assert excinfo.value.bucket == "RED"
    assert excinfo.value.prediction_fingerprint == fingerprint


def test_red_bucket_with_ack_records_human_override(db):
    fingerprint = seed_prediction(db, references=[VUK_114, GVK_94])
    report, decision = service.evaluate_for_commit(
        db, document_id="d1", references=[VUK_114],
        previous_references=[VUK_114], ack_fingerprint=fingerprint,
    )
    assert (report.bucket, decision) == ("RED", "human_override")


def test_ack_for_superseded_prediction_raises_stale(db):
    seed_prediction(db, references=[VUK_114, GVK_94])
    with pytest.raises(service.AuditAckStale):
        service.evaluate_for_commit(
            db, document_id="d1", references=[VUK_114],
            previous_references=[VUK_114], ack_fingerprint="stale-fingerprint",
        )


def test_accepting_a_model_reference_records_accepted_model(db):
    fingerprint = seed_prediction(db, references=[VUK_114, GVK_94])
    report, decision = service.evaluate_for_commit(
        db, document_id="d1", references=[VUK_114, GVK_94],
        previous_references=[VUK_114], ack_fingerprint=fingerprint,
    )
    assert (report.bucket, decision) == ("GREEN", "accepted_model")


def test_decision_log_row_is_queryable_with_json_each(db):
    seed_prediction(db, references=[VUK_114, GVK_94])
    report, decision = service.evaluate_for_commit(
        db, document_id="d1", references=[VUK_114],
        previous_references=[VUK_114],
        ack_fingerprint=service.load_prediction(db, "d1")["prediction_fingerprint"],
    )
    service.log_decision(db, document_id="d1", user_id=None, report=report, decision=decision)
    rows = db.execute(
        """SELECT json_extract(m.value, '$.kanun_no') AS kanun_no,
                  json_extract(m.value, '$.madde')    AS madde
           FROM annotation_audit_logs a, json_each(a.model_only_json) m
           WHERE a.decision='human_override'"""
    ).fetchall()
    assert [(r["kanun_no"], r["madde"]) for r in rows] == [("193", "94")]
    stored = db.execute("SELECT * FROM annotation_audit_logs").fetchone()
    assert stored["policy_id"] == "ignore_vuk_213_article_413_v1"
    assert stored["bucket"] == "RED"


def test_upsert_is_idempotent_and_skips_unknown_documents(db):
    item = {
        "document_id": "d1", "generation": "G0", "status": "success",
        "references": [VUK_114], "truncated": False, "model_fingerprint": "mf-1",
        "text_sha256": "abc", "error": None, "operational": {"latency_seconds": 1.5},
    }
    unknown = {**item, "document_id": "ghost"}
    assert service.upsert_predictions(db, [item, unknown]) == 1
    assert service.upsert_predictions(db, [item]) == 1
    assert db.execute("SELECT COUNT(*) AS c FROM model_predictions").fetchone()["c"] == 1


def test_pending_returns_missing_then_stale(db, ingest_doc):
    ingest_doc("d2", pdfText="ikinci dokuman metni")
    seed_prediction(db, document_id="d1", text="eski metin")  # stale
    pending = service.pending_documents(db, limit=8)
    ids = [row["document_id"] for row in pending]
    assert ids == ["d2", "d1"]
    assert pending[0]["text_sha256"] and pending[1]["text_sha256"]


def test_model_quotes_returns_prediction_source_texts(db):
    seed_prediction(db, references=[VUK_114, GVK_94])
    assert service.model_quotes(db, "d1") == (
        "zamanasimi hukmu duzenlenmistir", "tevkifat esaslarini belirler",
    )
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_quality_service.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.quality.service'`

- [ ] **Step 3: `service.py`'yi yaz**

```python
"""Prediction cache + audit computation for the pre-submit quality audit.

Read path (pre-audit, /complete): one indexed SELECT plus the vendored router —
no inference ever happens inside a request. Write path (internal ingest): a
single BEGIN IMMEDIATE upsert keyed by document_id.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from backend.quality.adapter import (
    AUDIT_POLICY_ID,
    audit_references,
    reference_identities,
)
from backend.quality.dqcheck_core.fingerprints import fingerprint_json, sha256_text

_ACK_REQUIRED_BUCKETS = frozenset({"RED", "YELLOW", "QUARANTINE"})
_STALE_SCAN_LIMIT = 200


class QualityServiceError(Exception):
    """Base."""


class DocumentNotFound(QualityServiceError):
    pass


class AuditAckRequired(QualityServiceError):
    """Bucket needs a human acknowledgement the caller did not provide."""

    def __init__(self, *, bucket: str, prediction_fingerprint: Optional[str]) -> None:
        super().__init__(f"audit acknowledgement required for bucket {bucket}")
        self.bucket = bucket
        self.prediction_fingerprint = prediction_fingerprint


class AuditAckStale(QualityServiceError):
    """Caller acknowledged a prediction that has since been superseded."""

    def __init__(self, *, prediction_fingerprint: Optional[str]) -> None:
        super().__init__("acknowledged prediction is no longer current")
        self.prediction_fingerprint = prediction_fingerprint


@dataclass(frozen=True)
class AuditReport:
    audit_status: str
    reason: Optional[str] = None
    bucket: Optional[str] = None
    reasons: tuple[str, ...] = ()
    similarity: Optional[float] = None
    prediction_fingerprint: Optional[str] = None
    model_generation: Optional[str] = None
    discrepancies: tuple[dict[str, Any], ...] = ()
    model_only: tuple[dict[str, str], ...] = ()
    human_only: tuple[dict[str, str], ...] = ()

    def to_response(self) -> dict[str, Any]:
        """Public shape; model_only/human_only stay server-side (audit log)."""
        return {
            "audit_status": self.audit_status,
            "reason": self.reason,
            "bucket": self.bucket,
            "reasons": list(self.reasons),
            "similarity": self.similarity,
            "prediction_fingerprint": self.prediction_fingerprint,
            "model_generation": self.model_generation,
            "discrepancies": [dict(row) for row in self.discrepancies],
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prediction_fingerprint(
    *, generation: str, model_fingerprint: str, references: list[dict[str, Any]]
) -> str:
    """ETag for one prediction; /complete compares the caller's ack against it."""
    return fingerprint_json(
        {
            "generation": generation,
            "model_fingerprint": model_fingerprint,
            "references": references,
        }
    )


def _document_text(db: sqlite3.Connection, document_id: str) -> str:
    row = db.execute(
        "SELECT pdf_text FROM documents_meta WHERE document_id=?", (document_id,)
    ).fetchone()
    if row is None:
        raise DocumentNotFound(document_id)
    return row["pdf_text"]


def load_prediction(db: sqlite3.Connection, document_id: str) -> Optional[sqlite3.Row]:
    return db.execute(
        "SELECT * FROM model_predictions WHERE document_id=?", (document_id,)
    ).fetchone()


def model_quotes(db: sqlite3.Connection, document_id: str) -> tuple[str, ...]:
    """Source texts the model proposed — behavioral detectors exempt these."""
    row = load_prediction(db, document_id)
    if row is None or row["status"] != "success":
        return ()
    return tuple(
        str(reference.get("source_text") or "")
        for reference in json.loads(row["references_json"])
        if reference.get("source_text")
    )


def _build(
    db: sqlite3.Connection, *, document_id: str, references: list[dict[str, Any]]
) -> tuple[AuditReport, list[dict[str, Any]]]:
    document_text = _document_text(db, document_id)
    row = load_prediction(db, document_id)
    if row is None:
        return AuditReport(audit_status="model_unavailable", reason="no_prediction"), []

    unavailable_reason: Optional[str] = None
    if row["status"] != "success":
        unavailable_reason = "model_error"
    elif row["truncated"]:
        unavailable_reason = "model_truncated"
    elif row["text_sha256"] != sha256_text(document_text):
        unavailable_reason = "prediction_text_stale"
    if unavailable_reason is not None:
        return (
            AuditReport(
                audit_status="model_unavailable",
                reason=unavailable_reason,
                prediction_fingerprint=row["prediction_fingerprint"],
                model_generation=row["generation"],
            ),
            [],
        )

    model_references = json.loads(row["references_json"])
    outcome = audit_references(
        human_references=references,
        model_references=model_references,
        document_text=document_text,
    )
    return (
        AuditReport(
            audit_status="ready",
            bucket=outcome.bucket,
            reasons=outcome.reasons,
            similarity=outcome.similarity,
            prediction_fingerprint=row["prediction_fingerprint"],
            model_generation=row["generation"],
            discrepancies=outcome.discrepancies,
            model_only=outcome.model_only,
            human_only=outcome.human_only,
        ),
        model_references,
    )


def build_report(
    db: sqlite3.Connection, *, document_id: str, references: list[dict[str, Any]]
) -> AuditReport:
    report, _ = _build(db, document_id=document_id, references=references)
    return report


def derive_decision(report: AuditReport, *, accepted_from_model: bool) -> str:
    if report.audit_status != "ready":
        return "model_unavailable"
    if report.bucket in _ACK_REQUIRED_BUCKETS:
        return "human_override"
    return "accepted_model" if accepted_from_model else "no_discrepancy"


def evaluate_for_commit(
    db: sqlite3.Connection,
    *,
    document_id: str,
    references: list[dict[str, Any]],
    previous_references: list[dict[str, Any]],
    ack_fingerprint: Optional[str],
) -> tuple[AuditReport, str]:
    """Recompute the audit for the refs about to be committed.

    Raises AuditAckRequired when the caller must acknowledge a mismatch, and
    AuditAckStale when the prediction changed after the caller's audit. The
    caller is inside a BEGIN IMMEDIATE; both exceptions roll it back.
    """
    report, model_references = _build(
        db, document_id=document_id, references=references
    )
    if report.audit_status != "ready":
        return report, "model_unavailable"
    if report.bucket in _ACK_REQUIRED_BUCKETS and not ack_fingerprint:
        raise AuditAckRequired(
            bucket=str(report.bucket),
            prediction_fingerprint=report.prediction_fingerprint,
        )
    if ack_fingerprint and ack_fingerprint != report.prediction_fingerprint:
        raise AuditAckStale(prediction_fingerprint=report.prediction_fingerprint)

    # Provable acceptance: an identity that is in the commit AND in the model
    # output but was NOT in the previous version came from the model this turn.
    accepted = bool(
        (reference_identities(references) & reference_identities(model_references))
        - reference_identities(previous_references)
    )
    return report, derive_decision(report, accepted_from_model=accepted)


def log_decision(
    db: sqlite3.Connection,
    *,
    document_id: str,
    user_id: Optional[int],
    report: AuditReport,
    decision: str,
    now: Optional[str] = None,
) -> None:
    db.execute(
        """
        INSERT INTO annotation_audit_logs(
            document_id, user_id, bucket, decision, reason, reasons_json,
            similarity, model_only_json, human_only_json,
            prediction_fingerprint, policy_id, model_generation, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_id,
            user_id,
            report.bucket,
            decision,
            report.reason,
            json.dumps(list(report.reasons)),
            report.similarity,
            json.dumps(list(report.model_only), ensure_ascii=False),
            json.dumps(list(report.human_only), ensure_ascii=False),
            report.prediction_fingerprint,
            AUDIT_POLICY_ID,
            report.model_generation,
            now or _now(),
        ),
    )


def upsert_predictions(
    db: sqlite3.Connection, items: list[dict[str, Any]], *, now: Optional[str] = None
) -> int:
    """Idempotent upsert keyed by document_id. Unknown documents are skipped."""
    stamp = now or _now()
    upserted = 0
    db.execute("BEGIN IMMEDIATE")
    try:
        for item in items:
            document_id = item["document_id"]
            known = db.execute(
                "SELECT 1 FROM documents_meta WHERE document_id=?", (document_id,)
            ).fetchone()
            if known is None:
                continue
            references = list(item.get("references") or [])
            db.execute(
                """
                INSERT INTO model_predictions(
                    document_id, generation, status, references_json, truncated,
                    model_fingerprint, prediction_fingerprint, text_sha256,
                    source, error, operational_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    generation=excluded.generation,
                    status=excluded.status,
                    references_json=excluded.references_json,
                    truncated=excluded.truncated,
                    model_fingerprint=excluded.model_fingerprint,
                    prediction_fingerprint=excluded.prediction_fingerprint,
                    text_sha256=excluded.text_sha256,
                    source=excluded.source,
                    error=excluded.error,
                    operational_json=excluded.operational_json,
                    updated_at=excluded.updated_at
                """,
                (
                    document_id,
                    item["generation"],
                    item["status"],
                    json.dumps(references, ensure_ascii=False),
                    1 if item.get("truncated") else 0,
                    item["model_fingerprint"],
                    prediction_fingerprint(
                        generation=item["generation"],
                        model_fingerprint=item["model_fingerprint"],
                        references=references,
                    ),
                    item["text_sha256"],
                    item.get("source") or "dqcheck_agent",
                    item.get("error"),
                    json.dumps(item.get("operational") or {}, ensure_ascii=False),
                    stamp,
                    stamp,
                ),
            )
            upserted += 1
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
    return upserted


_PENDING_MISSING_SQL = """
    SELECT d.document_id, d.pdf_text
    FROM documents_meta d
    LEFT JOIN model_predictions p ON p.document_id = d.document_id
    WHERE p.document_id IS NULL
    ORDER BY d.created_at ASC, d.document_id ASC
    LIMIT ?
"""

_PENDING_STALE_SQL = f"""
    SELECT d.document_id, d.pdf_text, p.text_sha256
    FROM documents_meta d
    JOIN model_predictions p ON p.document_id = d.document_id
    ORDER BY p.updated_at ASC, d.document_id ASC
    LIMIT {_STALE_SCAN_LIMIT}
"""


def pending_documents(db: sqlite3.Connection, *, limit: int) -> list[dict[str, Any]]:
    """Documents the agent should predict: no prediction first, then stale text.

    SQLite cannot hash text, so staleness is filtered in Python over a bounded
    oldest-first window — without it, a document whose text changed after
    ingest would never be re-predicted.
    """
    out: list[dict[str, Any]] = [
        {
            "document_id": row["document_id"],
            "pdf_text": row["pdf_text"],
            "text_sha256": sha256_text(row["pdf_text"]),
        }
        for row in db.execute(_PENDING_MISSING_SQL, (limit,)).fetchall()
    ]
    if len(out) >= limit:
        return out
    for row in db.execute(_PENDING_STALE_SQL).fetchall():
        digest = sha256_text(row["pdf_text"])
        if digest == row["text_sha256"]:
            continue
        out.append(
            {
                "document_id": row["document_id"],
                "pdf_text": row["pdf_text"],
                "text_sha256": digest,
            }
        )
        if len(out) >= limit:
            break
    return out
```

- [ ] **Step 4: Testin geçtiğini doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_quality_service.py -v
```

Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add backend/quality/service.py tests/test_quality_service.py
git commit -m "feat(quality): add prediction cache and audit report service

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Pre-audit endpoint

**Files:**
- Create: `/Users/student2/AnnotationPlatform/backend/quality/models.py`
- Create: `/Users/student2/AnnotationPlatform/backend/quality/routes.py`
- Modify: `/Users/student2/AnnotationPlatform/backend/quality/__init__.py`
- Modify: `/Users/student2/AnnotationPlatform/backend/main.py` (router mount)
- Test: `/Users/student2/AnnotationPlatform/tests/test_pre_audit_endpoint.py`

**Interfaces:**
- Consumes: Task 4 `service.{build_report, DocumentNotFound}`.
- Produces: `POST /api/annotations/{document_id}/pre-audit`; `models.{AuditDiscrepancy, PreAuditRequest, PreAuditResponse, ModelReferenceItem, PredictionIngestItem, PredictionIngestRequest, PredictionIngestResponse, PendingDocument, PendingResponse}`.

- [ ] **Step 1: Testi yaz**

```python
"""POST /api/annotations/{id}/pre-audit contract."""
import json

DOC_TEXT = "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir."
VUK_114 = {
    "kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
    "fikra": None, "bent": None, "source_text": "zamanasimi hukmu duzenlenmistir",
}
GVK_94 = {
    "kanun_no": "193", "kanun_ad": "Gelir Vergisi Kanunu", "madde": "94",
    "fikra": None, "bent": None, "source_text": "zamanasimi hukmu duzenlenmistir",
}


def _seed_prediction(document_id, references):
    from backend import config
    from backend.quality import service
    from backend.quality.dqcheck_core.fingerprints import sha256_text
    from backend.shared.db import connect

    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO model_predictions(
                document_id, generation, status, references_json, truncated,
                model_fingerprint, prediction_fingerprint, text_sha256, source,
                error, operational_json, created_at, updated_at
            ) VALUES (?,?,?,?,0,?,?,?,?,NULL,'{}',datetime('now'),datetime('now'))""",
            (document_id, "G0", "success", json.dumps(references), "mf-1",
             service.prediction_fingerprint(
                 generation="G0", model_fingerprint="mf-1", references=references
             ),
             sha256_text(DOC_TEXT), "dqcheck_agent"),
        )
    finally:
        conn.close()


def test_pre_audit_requires_authentication(client, ingest_doc):
    ingest_doc("d1", pdfText=DOC_TEXT)
    r = client.post("/api/annotations/d1/pre-audit", json={"references": []})
    assert r.status_code == 401


def test_pre_audit_reports_model_unavailable_without_prediction(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    r = c.post("/api/annotations/d1/pre-audit", json={"references": [VUK_114]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["audit_status"] == "model_unavailable"
    assert body["reason"] == "no_prediction"
    assert body["bucket"] is None
    assert body["discrepancies"] == []


def test_pre_audit_returns_green_for_matching_sets(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction("d1", [VUK_114])
    r = c.post("/api/annotations/d1/pre-audit", json={"references": [VUK_114]})
    body = r.json()
    assert body["audit_status"] == "ready"
    assert body["bucket"] == "GREEN"
    assert body["prediction_fingerprint"]
    assert body["model_generation"] == "G0"


def test_pre_audit_returns_actionable_model_only_discrepancy(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction("d1", [VUK_114, GVK_94])
    r = c.post("/api/annotations/d1/pre-audit", json={"references": [VUK_114]})
    body = r.json()
    assert body["bucket"] == "RED"
    assert "extra_or_different_core_reference" in body["reasons"]
    (discrepancy,) = body["discrepancies"]
    assert discrepancy["kind"] == "model_only"
    assert discrepancy["madde"] == "94"
    assert discrepancy["model_reference"]["kanun_ad"] == "Gelir Vergisi Kanunu"
    assert discrepancy["match_mode"] == "normalized_exact"


def test_pre_audit_writes_nothing(passed_user, ingest_doc):
    from backend import config
    from backend.shared.db import connect

    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction("d1", [VUK_114, GVK_94])
    c.post("/api/annotations/d1/pre-audit", json={"references": [VUK_114]})
    conn = connect(config.DB_PATH)
    try:
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM annotation_audit_logs"
        ).fetchone()["c"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM activity_events WHERE event_type='annotation_save'"
        ).fetchone()["c"] == 0
    finally:
        conn.close()


def test_pre_audit_404s_for_unknown_document(passed_user):
    c = passed_user["client"]
    r = c.post("/api/annotations/ghost/pre-audit", json={"references": []})
    assert r.status_code == 404
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_pre_audit_endpoint.py -v
```

Expected: FAIL — 404 (route yok) / `ModuleNotFoundError`

- [ ] **Step 3: `models.py`'yi yaz**

```python
"""Pydantic schemas for the pre-submit quality audit and prediction ingest."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from backend.annotations.models import ReferenceItem


class AuditDiscrepancy(BaseModel):
    kind: Literal["model_only", "human_only", "detail_mismatch"]
    kanun_no: str
    kanun_ad: str
    madde: str
    # Normalized reference dicts (all six fields, empty strings never None) as
    # produced by the vendored normalizer — not AP's ReferenceItem.
    model_reference: Optional[dict[str, str]] = None
    human_reference: Optional[dict[str, str]] = None
    field_diffs: list[str] = Field(default_factory=list)
    match_mode: Optional[str] = None


class PreAuditRequest(BaseModel):
    references: list[ReferenceItem] = Field(max_length=200)


class PreAuditResponse(BaseModel):
    audit_status: Literal["ready", "model_unavailable"]
    reason: Optional[str] = None
    bucket: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    similarity: Optional[float] = None
    prediction_fingerprint: Optional[str] = None
    model_generation: Optional[str] = None
    discrepancies: list[AuditDiscrepancy] = Field(default_factory=list)


class ModelReferenceItem(BaseModel):
    """Model output reference.

    Deliberately NOT ReferenceItem: that model runs AP's `pre_normalize`
    validator and rejects e.g. madde="5/1-a", which would fail a whole 16-item
    agent batch because of one malformed model row. Model references are
    normalized at audit time by the vendored `validate_reference_list`.
    """

    kanun_no: Optional[str] = Field(default=None, max_length=64)
    kanun_ad: Optional[str] = Field(default=None, max_length=512)
    madde: Optional[str] = Field(default=None, max_length=64)
    fikra: Optional[str] = Field(default=None, max_length=64)
    bent: Optional[str] = Field(default=None, max_length=64)
    source_text: str = Field(default="", max_length=4_000)


class PredictionIngestItem(BaseModel):
    document_id: str = Field(min_length=1, max_length=128)
    generation: str = Field(min_length=1, max_length=32)
    status: Literal["success", "error"]
    references: list[ModelReferenceItem] = Field(default_factory=list, max_length=200)
    truncated: bool = False
    model_fingerprint: str = Field(min_length=1, max_length=128)
    text_sha256: str = Field(min_length=64, max_length=64)
    error: Optional[str] = Field(default=None, max_length=2_000)
    operational: dict[str, Any] = Field(default_factory=dict)


class PredictionIngestRequest(BaseModel):
    items: list[PredictionIngestItem] = Field(min_length=1, max_length=16)


class PredictionIngestResponse(BaseModel):
    upserted: int


class PendingDocument(BaseModel):
    document_id: str
    pdf_text: str
    text_sha256: str


class PendingResponse(BaseModel):
    documents: list[PendingDocument]
```

- [ ] **Step 4: `routes.py`'yi yaz**

```python
"""Pre-submit quality audit endpoint. Read-only: writes nothing, logs nothing.

The audit decision is recorded by /complete (inside its transaction), never
here — a manual "compare me" look must not pollute the audit trail.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.quality import service
from backend.quality.models import PreAuditRequest, PreAuditResponse
from backend.users.deps import get_db, require_passed_training

router = APIRouter(prefix="/api", tags=["quality"])


@router.post(
    "/annotations/{document_id}/pre-audit",
    response_model=PreAuditResponse,
)
def pre_audit(
    document_id: str,
    payload: PreAuditRequest,
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(require_passed_training),
):
    """Compare the caller's current references against the cached G0 prediction."""
    try:
        report = service.build_report(
            db,
            document_id=document_id,
            references=[r.model_dump() for r in payload.references],
        )
    except service.DocumentNotFound:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    return report.to_response()
```

- [ ] **Step 5: Router'ı export et ve mount et**

`backend/quality/__init__.py`:

```python
"""Pre-submit quality audit: vendored DQCheck engine + AP-facing services."""
from backend.quality.routes import router  # noqa: F401
```

`backend/main.py` — import bloğuna (`from backend.feedback.routes import ...` satırından sonra):

```python
from backend.quality.routes import router as quality_router
```

ve diğer `app.include_router(...)` çağrılarının yanına:

```python
app.include_router(quality_router)
```

- [ ] **Step 6: Testin geçtiğini doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_pre_audit_endpoint.py -v
```

Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add backend/quality backend/main.py tests/test_pre_audit_endpoint.py
git commit -m "feat(quality): add read-only pre-audit endpoint

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `/complete` — sunucu taraflı yeniden hesaplama + `audit_ack` sözleşmesi

**Files:**
- Modify: `/Users/student2/AnnotationPlatform/backend/annotations/models.py` (`AuditAck`, `CompleteRequest.audit_ack`)
- Modify: `/Users/student2/AnnotationPlatform/backend/annotations/service.py` (`set_complete`)
- Modify: `/Users/student2/AnnotationPlatform/backend/annotations/routes.py` (409 eşlemeleri)
- Test: `/Users/student2/AnnotationPlatform/tests/test_complete_audit_ack.py`

**Interfaces:**
- Consumes: Task 4 `service.{evaluate_for_commit, log_decision, AuditAckRequired, AuditAckStale}`.
- Produces: `CompleteRequest.audit_ack: Optional[AuditAck]`; `set_complete(..., audit_ack: Optional[str] = None)` dönüşüne `audit_bucket: Optional[str]` ve `audit_decision: Optional[str]` eklenir; 409 `audit_required` / `audit_stale` HTTP sözleşmesi.

- [ ] **Step 1: Testi yaz**

```python
"""/complete recomputes the audit and demands an acknowledgement on mismatch."""
import json

DOC_TEXT = "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir."
VUK_114 = {
    "kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
    "fikra": None, "bent": None, "source_text": "zamanasimi hukmu duzenlenmistir",
}
GVK_94 = {
    "kanun_no": "193", "kanun_ad": "Gelir Vergisi Kanunu", "madde": "94",
    "fikra": None, "bent": None, "source_text": "zamanasimi hukmu duzenlenmistir",
}


def _seed_prediction(references):
    from backend import config
    from backend.quality import service
    from backend.quality.dqcheck_core.fingerprints import sha256_text
    from backend.shared.db import connect

    conn = connect(config.DB_PATH)
    try:
        fingerprint = service.prediction_fingerprint(
            generation="G0", model_fingerprint="mf-1", references=references
        )
        conn.execute(
            """INSERT OR REPLACE INTO model_predictions(
                document_id, generation, status, references_json, truncated,
                model_fingerprint, prediction_fingerprint, text_sha256, source,
                error, operational_json, created_at, updated_at
            ) VALUES ('d1','G0','success',?,0,'mf-1',?,?,'dqcheck_agent',NULL,'{}',
                      datetime('now'), datetime('now'))""",
            (json.dumps(references), fingerprint, sha256_text(DOC_TEXT)),
        )
        return fingerprint
    finally:
        conn.close()


def _audit_rows():
    from backend import config
    from backend.shared.db import connect

    conn = connect(config.DB_PATH)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM annotation_audit_logs ORDER BY id ASC"
        ).fetchall()]
    finally:
        conn.close()


def test_complete_without_prediction_succeeds_and_logs_model_unavailable(
    passed_user, ingest_doc
):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    r = c.post("/api/annotations/d1/complete",
               json={"completed": True, "references": [VUK_114]})
    assert r.status_code == 200, r.text
    (row,) = _audit_rows()
    assert row["decision"] == "model_unavailable"
    assert row["reason"] == "no_prediction"
    assert row["bucket"] is None


def test_green_complete_needs_no_ack_and_logs_no_discrepancy(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction([VUK_114])
    r = c.post("/api/annotations/d1/complete",
               json={"completed": True, "references": [VUK_114]})
    assert r.status_code == 200, r.text
    (row,) = _audit_rows()
    assert (row["bucket"], row["decision"]) == ("GREEN", "no_discrepancy")


def test_red_complete_without_ack_is_rejected_with_audit_required(
    passed_user, ingest_doc
):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    fingerprint = _seed_prediction([VUK_114, GVK_94])
    r = c.post("/api/annotations/d1/complete",
               json={"completed": True, "references": [VUK_114]})
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "audit_required"
    assert detail["bucket"] == "RED"
    assert detail["prediction_fingerprint"] == fingerprint
    assert _audit_rows() == []
    annotation = c.get("/api/documents/d1/annotation").json()["annotation"]
    assert annotation is None


def test_red_complete_with_ack_commits_and_logs_human_override(
    passed_user, ingest_doc
):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    fingerprint = _seed_prediction([VUK_114, GVK_94])
    r = c.post("/api/annotations/d1/complete", json={
        "completed": True,
        "references": [VUK_114],
        "audit_ack": {"prediction_fingerprint": fingerprint},
    })
    assert r.status_code == 200, r.text
    (row,) = _audit_rows()
    assert (row["bucket"], row["decision"]) == ("RED", "human_override")
    assert json.loads(row["model_only_json"]) == [
        {"kanun_no": "193", "madde": "94", "fikra": "", "bent": ""}
    ]
    annotation = c.get("/api/documents/d1/annotation").json()["annotation"]
    assert annotation["is_completed"] is True


def test_stale_ack_is_rejected_with_audit_stale(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction([VUK_114, GVK_94])
    r = c.post("/api/annotations/d1/complete", json={
        "completed": True,
        "references": [VUK_114],
        "audit_ack": {"prediction_fingerprint": "a-fingerprint-from-before"},
    })
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "audit_stale"
    assert _audit_rows() == []


def test_accepting_the_model_reference_logs_accepted_model(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    fingerprint = _seed_prediction([VUK_114, GVK_94])
    # First commit records the human's own list (RED + override).
    c.post("/api/annotations", json={"document_id": "d1", "references": [VUK_114]})
    r = c.post("/api/annotations/d1/complete", json={
        "completed": True,
        "references": [VUK_114, GVK_94],
        "audit_ack": {"prediction_fingerprint": fingerprint},
    })
    assert r.status_code == 200, r.text
    (row,) = _audit_rows()
    assert (row["bucket"], row["decision"]) == ("GREEN", "accepted_model")


def test_uncomplete_never_audits(passed_user, ingest_doc):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction([VUK_114])
    c.post("/api/annotations/d1/complete",
           json={"completed": True, "references": [VUK_114]})
    before = len(_audit_rows())
    r = c.post("/api/annotations/d1/complete", json={"completed": False})
    assert r.status_code == 200, r.text
    assert len(_audit_rows()) == before


def test_legacy_flag_only_complete_still_audits_stored_references(
    passed_user, ingest_doc
):
    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    _seed_prediction([VUK_114, GVK_94])
    c.post("/api/annotations", json={"document_id": "d1", "references": [VUK_114]})
    r = c.post("/api/annotations/d1/complete", json={"completed": True})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "audit_required"
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_complete_audit_ack.py -v
```

Expected: FAIL — audit satırı yazılmıyor (`_audit_rows() == []`), 409 yerine 200 dönüyor.

- [ ] **Step 3: `AuditAck` modelini ekle**

`backend/annotations/models.py` — `CompleteRequest`'ten hemen önce:

```python
class AuditAck(BaseModel):
    """Human acknowledgement of a mismatching quality audit.

    Presence of this object IS the acknowledgement ("I saw the comparison and
    I stand by my labels"). The fingerprint lets the server detect that the
    prediction changed after the caller ran the audit (409 audit_stale).
    """

    prediction_fingerprint: str = Field(min_length=1, max_length=128)
```

`CompleteRequest` içine, `references` alanından sonra:

```python
    # Set by the frontend after it ran /pre-audit. Required (409
    # audit_required otherwise) only when the server's own recomputation
    # lands on RED/YELLOW — never a gate on the human's judgement, just a
    # declaration that the comparison was seen.
    audit_ack: Optional[AuditAck] = None
```

- [ ] **Step 4: `set_complete`'i genişlet**

`backend/annotations/service.py` — import bloğuna:

```python
from backend.quality import service as quality_service
```

`set_complete` imzası:

```python
def set_complete(
    db: sqlite3.Connection,
    *,
    document_id: str,
    user_id: int,
    completed: bool,
    references: Optional[list[dict]] = None,
    audit_ack: Optional[str] = None,
) -> dict:
```

Docstring'in "Raises" satırının üzerine ekle:

```
    When `completed=True`, the quality audit is recomputed inside this
    transaction against the references being committed (atomic path) or the
    stored ones (legacy flag-flip path). A RED/YELLOW bucket without
    `audit_ack` raises quality_service.AuditAckRequired; an ack naming a
    superseded prediction raises quality_service.AuditAckStale. Both roll the
    transaction back, so a rejected complete leaves no trace.
```

Transaction içinde, `locks_service.release_if_held(...)` çağrısının **hemen öncesine**:

```python
        # Quality audit — recomputed from committed truth, never from what the
        # client claims. `changed or did_save` skips idempotent same-state
        # pokes (the legacy path already returned early for those).
        audit_report = None
        audit_decision = None
        if completed and (changed or did_save):
            if references is not None:
                final_references = save_result["cleaned"]
                previous_references = [] if is_new else json.loads(cur["references_json"])
            else:
                final_references = json.loads(cur["references_json"])
                previous_references = final_references
            audit_report, audit_decision = quality_service.evaluate_for_commit(
                db,
                document_id=document_id,
                references=final_references,
                previous_references=previous_references,
                ack_fingerprint=audit_ack,
            )
```

`audit.log_activity(...)` çağrısından hemen sonra:

```python
        if audit_report is not None:
            quality_service.log_decision(
                db,
                document_id=document_id,
                user_id=user_id,
                report=audit_report,
                decision=str(audit_decision),
                now=now,
            )
```

Return sözlüğüne iki alan ekle:

```python
        "audit_bucket": audit_report.bucket if audit_report is not None else None,
        "audit_decision": audit_decision,
```

**Dikkat:** legacy dalda `is_new` tanımlı değildir; yukarıdaki blok `references is not None`
kontrolüyle bu dalı hiç okumaz. Legacy dalın erken dönen idempotent `COMMIT` yolu
bu bloktan önce `return` ettiği için orada da audit çalışmaz.

- [ ] **Step 5: Route'ta 409 eşlemelerini ekle**

`backend/annotations/routes.py` — import bloğuna:

```python
from backend.quality import service as quality_service
```

`complete` içindeki `service.set_complete(...)` çağrısına `audit_ack` geçir:

```python
        result = service.set_complete(
            db, document_id=document_id, user_id=user["id"],
            completed=payload.completed,
            references=refs_payload,
            audit_ack=(
                payload.audit_ack.prediction_fingerprint
                if payload.audit_ack is not None
                else None
            ),
        )
```

`except service.LockOwnedByOther:` bloğundan önce iki dal ekle:

```python
    except quality_service.AuditAckRequired as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "audit_required",
                "message": (
                    "Model karşılaştırmasında farklılık var. Lütfen kalite "
                    "denetimini görüntüleyip onaylayın."
                ),
                "bucket": exc.bucket,
                "prediction_fingerprint": exc.prediction_fingerprint,
            },
        )
    except quality_service.AuditAckStale as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "audit_stale",
                "message": (
                    "Yeni model tahmini alındı, lütfen son kez teyit edip "
                    "Tamamla'ya basınız."
                ),
                "prediction_fingerprint": exc.prediction_fingerprint,
            },
        )
```

- [ ] **Step 6: Testleri çalıştır (yeni + mevcut regresyon)**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_complete_audit_ack.py -v
/opt/llm-lab/.venv/bin/python -m pytest tests/test_annotations_routes.py tests/test_annotations_service.py \
                 tests/test_annotations_lock_ownership.py -q
```

Expected: yeni dosyada 8 passed; mevcut annotation testleri değişmeden geçer (tahmin satırı olmayan dokümanlar `model_unavailable` yolundan akar, ack istemez).

- [ ] **Step 7: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add backend/annotations tests/test_complete_audit_ack.py
git commit -m "feat(annotations): recompute quality audit inside complete and require ack

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Internal ingest yüzeyi + token koruması

**Files:**
- Create: `/Users/student2/AnnotationPlatform/backend/quality/tokens.py`
- Create: `/Users/student2/AnnotationPlatform/backend/quality/internal_routes.py`
- Modify: `/Users/student2/AnnotationPlatform/backend/config.py`
- Modify: `/Users/student2/AnnotationPlatform/backend/main.py`
- Modify: `/Users/student2/AnnotationPlatform/.env.example`
- Test: `/Users/student2/AnnotationPlatform/tests/test_predictions_ingest.py`

**Interfaces:**
- Consumes: Task 4 `service.{pending_documents, upsert_predictions}`, Task 5 `models.{PendingResponse, PredictionIngestRequest, PredictionIngestResponse}`.
- Produces: `GET /api/internal/predictions/pending`, `POST /api/internal/predictions`, `tokens.require_ingest_token`.

- [ ] **Step 1: Testi yaz**

```python
"""Internal prediction ingest: token contract + idempotent upsert."""
import pytest

from backend.quality.tokens import parse_bearer_token

DOC_TEXT = "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir."
TOKEN = "t" * 48


@pytest.fixture
def token_client(client, monkeypatch):
    monkeypatch.setattr("backend.config.DQCHECK_INGEST_TOKEN", TOKEN)
    return client


def _item(document_id="d1", **overrides):
    from backend.quality.dqcheck_core.fingerprints import sha256_text

    payload = {
        "document_id": document_id,
        "generation": "G0",
        "status": "success",
        "references": [{
            "kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
            "fikra": None, "bent": None,
            "source_text": "zamanasimi hukmu duzenlenmistir",
        }],
        "truncated": False,
        "model_fingerprint": "mf-1",
        "text_sha256": sha256_text(DOC_TEXT),
        "operational": {"latency_seconds": 12.5},
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("raw,expected", [
    (None, None),
    ("", None),
    ("Bearer", None),
    ("Bearer ", None),
    ("Basic abc", None),
    ("bearer abc", "abc"),
    ("Bearer  abc  ", "abc"),
    ("Bearer abc def", "abc def"),
    (12345, None),
])
def test_bearer_parsing_never_raises(raw, expected):
    assert parse_bearer_token(raw) == expected


def test_endpoints_are_503_when_token_is_unset(client, monkeypatch):
    monkeypatch.setattr("backend.config.DQCHECK_INGEST_TOKEN", "")
    r = client.get("/api/internal/predictions/pending")
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "prediction_ingest_disabled"


def test_missing_or_wrong_token_is_401(token_client):
    assert token_client.get("/api/internal/predictions/pending").status_code == 401
    r = token_client.get(
        "/api/internal/predictions/pending",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "invalid_ingest_token"


def test_pending_lists_documents_without_predictions(token_client, ingest_doc):
    ingest_doc("d1", pdfText=DOC_TEXT)
    r = token_client.get(
        "/api/internal/predictions/pending?limit=4",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 200, r.text
    (row,) = r.json()["documents"]
    assert row["document_id"] == "d1"
    assert row["pdf_text"] == DOC_TEXT
    assert len(row["text_sha256"]) == 64


def test_pending_limit_is_capped_at_16(token_client):
    r = token_client.get(
        "/api/internal/predictions/pending?limit=99",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 422


def test_ingest_upserts_and_is_idempotent(token_client, ingest_doc):
    ingest_doc("d1", pdfText=DOC_TEXT)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    r = token_client.post("/api/internal/predictions",
                          json={"items": [_item()]}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"upserted": 1}
    r = token_client.post("/api/internal/predictions",
                          json={"items": [_item()]}, headers=headers)
    assert r.json() == {"upserted": 1}

    pending = token_client.get("/api/internal/predictions/pending", headers=headers)
    assert pending.json()["documents"] == []


def test_unknown_document_is_skipped_not_rejected(token_client, ingest_doc):
    ingest_doc("d1", pdfText=DOC_TEXT)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    r = token_client.post(
        "/api/internal/predictions",
        json={"items": [_item(), _item(document_id="ghost")]},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json() == {"upserted": 1}


def test_malformed_model_reference_does_not_fail_the_batch(token_client, ingest_doc):
    """madde="5/1-a" is rejected by AP's ReferenceItem but must be accepted here."""
    ingest_doc("d1", pdfText=DOC_TEXT)
    item = _item(references=[{
        "kanun_no": "3065", "kanun_ad": "Katma Değer Vergisi Kanunu",
        "madde": "5/1-a", "fikra": None, "bent": None, "source_text": "x",
    }])
    r = token_client.post("/api/internal/predictions", json={"items": [item]},
                          headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200, r.text
    assert r.json() == {"upserted": 1}


def test_batch_size_is_capped_at_16(token_client, ingest_doc):
    ingest_doc("d1", pdfText=DOC_TEXT)
    r = token_client.post(
        "/api/internal/predictions",
        json={"items": [_item() for _ in range(17)]},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 422
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_predictions_ingest.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.quality.tokens'`

- [ ] **Step 3: `tokens.py`'yi yaz**

```python
"""Service-token guard for the Mac-side predict-agent endpoints.

No user session is involved: the caller is a long-running agent on the
operator's machine, authenticated with a shared secret from the environment.
"""
import secrets
from typing import Any, Optional

from fastapi import Header, HTTPException

from backend import config


def parse_bearer_token(raw: Any) -> Optional[str]:
    """Extract the credential from an Authorization header.

    Never raises: a non-string, empty, schemeless, or credential-less header
    simply yields None so the caller answers 401 instead of 500.
    """
    if not isinstance(raw, str):
        return None
    parts = raw.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def require_ingest_token(authorization: Optional[str] = Header(default=None)) -> None:
    """503 when the feature is unconfigured, 401 when the token does not match."""
    expected = config.DQCHECK_INGEST_TOKEN
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "prediction_ingest_disabled",
                "message": "DQCHECK_INGEST_TOKEN is not configured on this instance.",
            },
        )
    provided = parse_bearer_token(authorization)
    if provided is None or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_ingest_token",
                "message": "Invalid prediction ingest credentials.",
            },
        )
```

- [ ] **Step 4: `internal_routes.py`'yi yaz**

```python
"""Prediction ingest endpoints for the Mac-side `dqcheck predict-agent`.

Not part of the annotator API surface: guarded by a service token, never
mounted under the SPA, and intentionally free of user-session semantics.
"""
import sqlite3

from fastapi import APIRouter, Depends, Query

from backend.quality import service
from backend.quality.models import (
    PendingResponse,
    PredictionIngestRequest,
    PredictionIngestResponse,
)
from backend.quality.tokens import require_ingest_token
from backend.users.deps import get_db

router = APIRouter(
    prefix="/api/internal",
    tags=["internal"],
    dependencies=[Depends(require_ingest_token)],
)


@router.get("/predictions/pending", response_model=PendingResponse)
def pending_predictions(
    limit: int = Query(default=8, ge=1, le=16),
    db: sqlite3.Connection = Depends(get_db),
):
    """Documents needing a prediction: none stored, or stored against older text."""
    return {"documents": service.pending_documents(db, limit=limit)}


@router.post("/predictions", response_model=PredictionIngestResponse)
def ingest_predictions(
    payload: PredictionIngestRequest,
    db: sqlite3.Connection = Depends(get_db),
):
    """Idempotent upsert. Items for unknown documents are skipped, not rejected."""
    upserted = service.upsert_predictions(
        db, [item.model_dump() for item in payload.items]
    )
    return {"upserted": upserted}
```

- [ ] **Step 5: Config, mount ve `.env.example`**

`backend/config.py` — `SPACE_ID = ...` satırının altına:

```python
# Shared secret for the Mac-side `dqcheck predict-agent` ingest endpoints.
# Empty (the default) disables /api/internal/predictions* with HTTP 503.
DQCHECK_INGEST_TOKEN = os.environ.get("DQCHECK_INGEST_TOKEN", "")
```

`backend/main.py` — quality router mount'unun yanına:

```python
from backend.quality.internal_routes import router as quality_internal_router
...
app.include_router(quality_internal_router)
```

`.env.example` — sonuna:

```bash
# Prediction ingest (Mac-side `dqcheck predict-agent` → this instance).
# Generate with: openssl rand -hex 32
# Empty → /api/internal/predictions* answer 503 and the audit degrades to
# "model kontrolü yapılamadı" without blocking any annotator.
DQCHECK_INGEST_TOKEN=
```

- [ ] **Step 6: Testleri çalıştır**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_predictions_ingest.py -v
```

Expected: 17 passed (9 parametrize + 8 test)

- [ ] **Step 7: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add backend/quality backend/config.py backend/main.py .env.example \
        tests/test_predictions_ingest.py
git commit -m "feat(quality): add token-guarded prediction ingest endpoints

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Davranışsal dedektör izolasyonu

**Files:**
- Modify: `/Users/student2/AnnotationPlatform/backend/behavioral/service.py`
- Modify: `/Users/student2/AnnotationPlatform/backend/annotations/routes.py` (iki `run_after_save` çağrısı)
- Test: `/Users/student2/AnnotationPlatform/tests/test_behavioral_audit_isolation.py`

**Interfaces:**
- Consumes: Task 4 `service.model_quotes`, `dqcheck_core.text.folded_text`.
- Produces: `detect_char_limit_warning(db, *, references, exempt_quotes=())`, `run_after_save(db, *, user_id, username, references, model_quotes=())`.

- [ ] **Step 1: Testi yaz**

```python
"""Audit flow must not distort speed_warning or blame users for model quotes."""
import json

LONG_MODEL_QUOTE = "M" + "odel alintisi " * 40          # > 300 chars
LONG_HUMAN_QUOTE = "K" + "endi alintim " * 40           # > 300 chars
DOC_TEXT = "kisa dokuman metni"


def test_char_limit_warning_exempts_quotes_that_match_model_output():
    from backend.behavioral.service import detect_char_limit_warning

    references = [{"kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
                   "fikra": None, "bent": None, "source_text": LONG_MODEL_QUOTE}]
    # No exemption → warns.
    assert detect_char_limit_warning(_FakeDb(), references=references) is not None
    # Exempted → silent.
    assert detect_char_limit_warning(
        _FakeDb(), references=references, exempt_quotes=(LONG_MODEL_QUOTE,)
    ) is None


def test_char_limit_warning_still_fires_for_the_users_own_long_quote():
    from backend.behavioral.service import detect_char_limit_warning

    references = [{"kanun_no": "213", "kanun_ad": None, "madde": "114",
                   "fikra": None, "bent": None, "source_text": LONG_HUMAN_QUOTE}]
    verdict = detect_char_limit_warning(
        _FakeDb(), references=references, exempt_quotes=(LONG_MODEL_QUOTE,)
    )
    assert verdict is not None
    assert verdict["fields"][0]["field"] == "source_text"


def test_exemption_tolerates_whitespace_and_case_differences():
    from backend.behavioral.service import detect_char_limit_warning

    stored = LONG_MODEL_QUOTE.replace(" ", "\n").upper()
    references = [{"kanun_no": "213", "kanun_ad": None, "madde": "114",
                   "fikra": None, "bent": None, "source_text": stored}]
    assert detect_char_limit_warning(
        _FakeDb(), references=references, exempt_quotes=(LONG_MODEL_QUOTE,)
    ) is None


def test_pre_audit_calls_do_not_change_the_speed_warning_save_count(
    passed_user, ingest_doc
):
    from backend import config
    from backend.shared.db import connect

    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)

    def _save_count():
        conn = connect(config.DB_PATH)
        try:
            return conn.execute(
                "SELECT COUNT(*) AS c FROM activity_events"
                " WHERE event_type='annotation_save'"
            ).fetchone()["c"]
        finally:
            conn.close()

    before = _save_count()
    for _ in range(10):
        r = c.post("/api/annotations/d1/pre-audit", json={"references": []})
        assert r.status_code == 200
    assert _save_count() == before


def test_accepting_a_suggestion_via_draft_does_not_count_as_a_save(
    passed_user, ingest_doc
):
    from backend import config
    from backend.shared.db import connect

    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    reference = {"kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
                 "fikra": None, "bent": None, "source_text": "x"}
    for _ in range(8):
        assert c.put("/api/drafts/d1", json={"references": [reference]}).status_code == 200
    conn = connect(config.DB_PATH)
    try:
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM activity_events WHERE event_type='annotation_save'"
        ).fetchone()["c"] == 0
    finally:
        conn.close()


class _FakeDb:
    """char_limit thresholds come from settings; defaults apply when unset."""

    def execute(self, *_args, **_kwargs):
        class _Cursor:
            def fetchone(self):
                return None

            def fetchall(self):
                return []

        return _Cursor()
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_behavioral_audit_isolation.py -v
```

Expected: FAIL — `detect_char_limit_warning() got an unexpected keyword argument 'exempt_quotes'`

- [ ] **Step 3: Dedektörü ve orkestratörü güncelle**

`backend/behavioral/service.py` — import bloğuna:

```python
from backend.quality.dqcheck_core.text import folded_text
```

`detect_char_limit_warning` imzası ve gövdesi:

```python
def detect_char_limit_warning(
    db, *, references: list[dict], exempt_quotes: tuple[str, ...] = ()
) -> Optional[dict]:
    """Return a verdict if any reference's `kanun_ad` or `source_text` exceeds
    the warn or alert threshold. Returns the worst severity across all hits.
    None if every field is below warn.

    `exempt_quotes` carries the model's own proposed source texts. A quote the
    platform itself put in front of the annotator must not then be reported as
    "too long" — that would punish the user for accepting our suggestion.
    Comparison is whitespace/case/punctuation-insensitive (`folded_text`).
    """
    if not references:
        return None

    warn = S.get_int(db, "char_limit.warn_threshold", default=300)
    alert = S.get_int(db, "char_limit.alert_threshold", default=600)
    exempt = {folded_text(quote) for quote in exempt_quotes if quote}

    hits: list[dict] = []
    for idx, ref in enumerate(references):
        for field in _CHECKED_FIELDS:
            value = ref.get(field) or ""
            length = len(value)
            if length <= warn:
                continue
            if field == "source_text" and folded_text(value) in exempt:
                continue
            level = "alert" if length > alert else "warn"
            hits.append(
                {"ref_index": idx, "field": field, "length": length, "level": level}
            )

    if not hits:
        return None

    worst = "alert" if any(h["level"] == "alert" for h in hits) else "warn"
    return {
        "level": worst,
        "fields": hits,
        "warn_threshold": warn,
        "alert_threshold": alert,
    }
```

`run_after_save` imzası ve char_limit dalı:

```python
async def run_after_save(
    db,
    *,
    user_id: int,
    username: str,
    references: list[dict],
    model_quotes: tuple[str, ...] = (),
) -> None:
```

```python
        verdict = detect_char_limit_warning(
            db, references=references, exempt_quotes=model_quotes
        )
```

- [ ] **Step 4: Route'larda model alıntılarını aktar**

`backend/annotations/routes.py` — `save()` içindeki `behavioral_service.run_after_save(...)` çağrısı:

```python
        await behavioral_service.run_after_save(
            db,
            user_id=user["id"],
            username=user["username"],
            references=result["current_references"],
            model_quotes=quality_service.model_quotes(db, payload.document_id),
        )
```

`complete()` içindeki çağrı:

```python
            await behavioral_service.run_after_save(
                db,
                user_id=user["id"],
                username=user["username"],
                references=refs_payload or [],
                model_quotes=quality_service.model_quotes(db, document_id),
            )
```

- [ ] **Step 5: Testleri çalıştır**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_behavioral_audit_isolation.py -v
/opt/llm-lab/.venv/bin/python -m pytest tests/test_behavioral_char_limit.py tests/test_behavioral_speed.py \
                 tests/test_behavioral_orchestrator.py tests/test_behavioral_integration.py -q
```

Expected: yeni dosyada 5 passed; mevcut davranışsal testler değişmeden geçer (`exempt_quotes` varsayılanı boş).

- [ ] **Step 6: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add backend/behavioral backend/annotations/routes.py \
        tests/test_behavioral_audit_isolation.py
git commit -m "fix(behavioral): exempt model quotes from char limit warnings

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# FAZ 3 — Mac tarafı tahmin ajanı (DQC deposu)

## Task 9: `dqcheck predict-agent`

**Files:**
- Create: `/Users/student2/data-quality-checker/src/data_quality_checker/predict_agent.py`
- Modify: `/Users/student2/data-quality-checker/src/data_quality_checker/commands.py`
- Modify: `/Users/student2/data-quality-checker/src/data_quality_checker/cli.py`
- Modify: `/Users/student2/data-quality-checker/README.md` (komut tablosu)
- Test: `/Users/student2/data-quality-checker/tests/test_predict_agent.py`

**Interfaces:**
- Consumes: `processing.{MlxG0Backend, EchoHumanBackend, PredictionBackend}`, `config.AppConfig`, `errors.ConfigurationError`.
- Produces:
  - `resolve_token(env_name: str, environ: Mapping[str, str]) -> str`
  - `HttpTransport(base_url, token, timeout=60.0)` — `get_pending(limit) -> list[dict]`, `post_predictions(items) -> int`
  - `build_backend(config, *, fake: bool = False) -> PredictionBackend`
  - `AgentStats(pending, predicted, upserted, failed)`
  - `run_agent(*, transport, backend, batch_size=4, poll_seconds=30.0, once=False, sleep=time.sleep, log=print, max_cycles=None) -> AgentStats` (`max_cycles` yalnızca testlerde döngüyü sınırlar)
  - `commands.predict_agent(args, config) -> int`

- [ ] **Step 1: Testi yaz**

```python
"""Predict-agent loop: pull, predict, push. No network, no MLX."""
import pytest

from data_quality_checker.errors import ConfigurationError
from data_quality_checker.predict_agent import (
    AgentStats,
    resolve_token,
    run_agent,
)
from data_quality_checker.processing import PredictionResult

DOCUMENT = {
    "document_id": "d1",
    "pdf_text": "Vergi Usul Kanunu'nun 114 uncu maddesi.",
    "text_sha256": "a" * 64,
}
REFERENCE = {
    "kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
    "fikra": "", "bent": "", "source_text": "114 uncu maddesi",
}


class FakeTransport:
    def __init__(self, batches):
        self._batches = list(batches)
        self.posted = []
        self.requested_limits = []

    def get_pending(self, limit):
        self.requested_limits.append(limit)
        return self._batches.pop(0) if self._batches else []

    def post_predictions(self, items):
        self.posted.append(items)
        return len(items)


class FakeBackend:
    model_fingerprint = "fake-fingerprint"

    def __init__(self, result=None, raises=None):
        self._result = result or PredictionResult(
            status="success", references=[REFERENCE], raw_output="[]",
            operational={"truncated": False, "latency_seconds": 1.0},
        )
        self._raises = raises
        self.calls = []

    def predict(self, document):
        self.calls.append(document)
        if self._raises is not None:
            raise self._raises
        return self._result


def test_resolve_token_requires_a_non_empty_environment_variable():
    assert resolve_token("TOKEN", {"TOKEN": "abc"}) == "abc"
    with pytest.raises(ConfigurationError):
        resolve_token("TOKEN", {})
    with pytest.raises(ConfigurationError):
        resolve_token("TOKEN", {"TOKEN": "   "})


def test_empty_pending_posts_nothing():
    transport = FakeTransport([[]])
    stats = run_agent(
        transport=transport, backend=FakeBackend(), once=True, sleep=lambda _s: None
    )
    assert transport.posted == []
    assert stats == AgentStats(pending=0, predicted=0, upserted=0, failed=0)


def test_successful_batch_posts_the_ingest_payload():
    transport = FakeTransport([[DOCUMENT]])
    backend = FakeBackend()
    stats = run_agent(
        transport=transport, backend=backend, batch_size=4, once=True,
        sleep=lambda _s: None,
    )
    (batch,) = transport.posted
    (item,) = batch
    assert item == {
        "document_id": "d1",
        "generation": "G0",
        "status": "success",
        "references": [REFERENCE],
        "truncated": False,
        "model_fingerprint": "fake-fingerprint",
        "text_sha256": "a" * 64,
        "error": None,
        "operational": {"truncated": False, "latency_seconds": 1.0},
    }
    assert stats.upserted == 1
    assert transport.requested_limits == [4]
    # The model reads exactly the text the platform sent.
    assert backend.calls[0]["text"] == DOCUMENT["pdf_text"]


def test_model_level_error_is_cached_so_the_document_is_not_retried_forever():
    result = PredictionResult(
        status="error", references=[], raw_output="",
        error="input_token_count=9001 exceeds pinned max_sequence_length",
        operational={"truncated": False},
    )
    transport = FakeTransport([[DOCUMENT]])
    run_agent(
        transport=transport, backend=FakeBackend(result=result), once=True,
        sleep=lambda _s: None,
    )
    (batch,) = transport.posted
    assert batch[0]["status"] == "error"
    assert batch[0]["references"] == []


def test_environment_failure_posts_nothing_and_never_fabricates_a_prediction():
    transport = FakeTransport([[DOCUMENT]])
    stats = run_agent(
        transport=transport,
        backend=FakeBackend(raises=RuntimeError("Metal allocator died")),
        once=True,
        sleep=lambda _s: None,
    )
    assert transport.posted == []
    assert stats.failed == 1
    assert stats.predicted == 0


def test_post_failure_is_counted_and_does_not_crash_the_loop():
    class ExplodingTransport(FakeTransport):
        def post_predictions(self, items):
            raise OSError("connection reset")

    transport = ExplodingTransport([[DOCUMENT]])
    stats = run_agent(
        transport=transport, backend=FakeBackend(), once=True, sleep=lambda _s: None
    )
    assert stats.failed == 1
    assert stats.upserted == 0


def test_loop_backs_off_after_a_failed_batch():
    delays = []
    transport = FakeTransport([[DOCUMENT], []])
    run_agent(
        transport=transport,
        backend=FakeBackend(raises=RuntimeError("boom")),
        poll_seconds=30.0,
        once=False,
        sleep=delays.append,
        log=lambda _m: None,
        max_cycles=2,
    )
    assert delays and delays[0] == 60.0
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/data-quality-checker
/opt/llm-lab/.venv/bin/python -m pytest tests/test_predict_agent.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'data_quality_checker.predict_agent'`

- [ ] **Step 3: `predict_agent.py`'yi yaz**

```python
"""Serve G0 predictions to a remote annotation platform.

The platform runs on Hugging Face Spaces (Linux, no MLX) and cannot reach this
machine; this agent therefore runs locally and pushes outbound only. It is
stateless: it asks the platform which documents lack a prediction, runs G0, and
posts the results. A restarted agent — or a platform whose ephemeral database
was wiped — converges again by asking the same question.

Failure policy: a *model-level* error (token limit, unparseable output) is a
deterministic property of that document and is cached as `status="error"`, so the
platform reports "model kontrolü yapılamadı" instead of retrying forever. A
*raised* exception means the environment broke (MLX allocator, missing weights);
nothing is posted, because fabricating a prediction would be worse than having
none.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .config import AppConfig
from .errors import ConfigurationError, ContractError
from .processing import EchoHumanBackend, MlxG0Backend, PredictionBackend

DEFAULT_GENERATION = "G0"
MAX_BACKOFF_SECONDS = 600.0


@dataclass(eq=True)
class AgentStats:
    pending: int = 0
    predicted: int = 0
    upserted: int = 0
    failed: int = 0


def resolve_token(env_name: str, environ: Mapping[str, str]) -> str:
    token = str(environ.get(env_name, "")).strip()
    if not token:
        raise ConfigurationError(
            f"{env_name} is empty; export the platform's DQCHECK_INGEST_TOKEN value"
        )
    return token


class HttpTransport:
    """Minimal stdlib HTTP client for the platform's internal endpoints."""

    def __init__(self, *, base_url: str, token: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    def _request(self, method: str, path: str, payload: Any | None = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, method=method
        )
        request.add_header("Authorization", f"Bearer {self._token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            body = response.read().decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ContractError(f"platform returned non-JSON body: {exc}") from exc

    def get_pending(self, limit: int) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/api/internal/predictions/pending?limit={limit}")
        documents = payload.get("documents")
        if not isinstance(documents, list):
            raise ContractError("pending response has no documents list")
        return documents

    def post_predictions(self, items: list[dict[str, Any]]) -> int:
        payload = self._request("POST", "/api/internal/predictions", {"items": items})
        return int(payload.get("upserted", 0))


def build_backend(config: AppConfig, *, fake: bool = False) -> PredictionBackend:
    return EchoHumanBackend() if fake else MlxG0Backend(config)


def _predict_one(
    backend: PredictionBackend, document: Mapping[str, Any]
) -> dict[str, Any]:
    result = backend.predict(
        {"text": document["pdf_text"], "human_references": []}
    )
    return {
        "document_id": document["document_id"],
        "generation": DEFAULT_GENERATION,
        "status": result.status,
        "references": list(result.references),
        "truncated": bool(result.operational.get("truncated")),
        "model_fingerprint": backend.model_fingerprint,
        "text_sha256": document["text_sha256"],
        "error": result.error,
        "operational": dict(result.operational),
    }


def run_agent(
    *,
    transport: Any,
    backend: PredictionBackend,
    batch_size: int = 4,
    poll_seconds: float = 30.0,
    once: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
    max_cycles: int | None = None,
) -> AgentStats:
    """Pull → predict → push. `once` runs a single cycle (used by tests and cron).

    `max_cycles` bounds the loop for tests; production runs leave it None.
    """
    stats = AgentStats()
    consecutive_failures = 0
    cycles = 0
    while True:
        cycles += 1
        pending = transport.get_pending(batch_size)
        stats.pending = len(pending)
        batch_failed = False
        items: list[dict[str, Any]] = []
        for document in pending:
            try:
                items.append(_predict_one(backend, document))
            except Exception as exc:  # environment-level failure
                stats.failed += 1
                batch_failed = True
                log(f"predict failed for {document.get('document_id')}: {exc}")
                break
            stats.predicted += 1
        if items:
            try:
                upserted = transport.post_predictions(items)
                stats.upserted += upserted
                log(
                    f"pending={len(pending)} predicted={len(items)} upserted={upserted}"
                )
            except Exception as exc:
                stats.failed += 1
                batch_failed = True
                log(f"ingest failed for {len(items)} item(s): {exc}")
        elif not pending:
            log("pending=0 idle")

        consecutive_failures = consecutive_failures + 1 if batch_failed else 0
        if once or (max_cycles is not None and cycles >= max_cycles):
            return stats
        if consecutive_failures:
            delay = min(poll_seconds * (2**consecutive_failures), MAX_BACKOFF_SECONDS)
            log(f"backing off {delay:.0f}s after {consecutive_failures} failed cycle(s)")
            sleep(delay)
        elif not pending:
            sleep(poll_seconds)
```

- [ ] **Step 4: Testin geçtiğini doğrula**

```bash
cd /Users/student2/data-quality-checker
/opt/llm-lab/.venv/bin/python -m pytest tests/test_predict_agent.py -v
```

Expected: 7 passed

- [ ] **Step 5: Command handler'ı ekle**

`src/data_quality_checker/commands.py` — `serve` handler'ından sonra:

```python
def predict_agent(args: Namespace, config: AppConfig) -> int:
    import os

    from .predict_agent import HttpTransport, build_backend, resolve_token, run_agent

    token = resolve_token(args.token_env, os.environ)
    transport = HttpTransport(base_url=args.space_url, token=token)
    backend = build_backend(config, fake=args.fake_backend)
    stats = run_agent(
        transport=transport,
        backend=backend,
        batch_size=args.batch_size,
        poll_seconds=args.poll_seconds,
        once=args.once,
    )
    print(
        json.dumps(
            {
                "pending": stats.pending,
                "predicted": stats.predicted,
                "upserted": stats.upserted,
                "failed": stats.failed,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0
```

- [ ] **Step 6: CLI alt komutunu ekle**

`src/data_quality_checker/cli.py` — `serve` bloğundan sonra:

```python
    agent = subparsers.add_parser(
        "predict-agent",
        help="serve G0 predictions to a remote annotation platform",
    )
    agent.add_argument("--space-url", required=True)
    agent.add_argument("--token-env", default="DQCHECK_INGEST_TOKEN")
    agent.add_argument("--batch-size", type=int, default=4)
    agent.add_argument("--poll-seconds", type=float, default=30.0)
    agent.add_argument("--once", action="store_true")
    agent.add_argument("--fake-backend", action="store_true", help=argparse.SUPPRESS)
    agent.set_defaults(handler=commands.predict_agent)
```

- [ ] **Step 7: CLI'nin yardım çıktısını ve arg parse'ını doğrula**

```bash
cd /Users/student2/data-quality-checker
/opt/llm-lab/.venv/bin/python -m data_quality_checker predict-agent --help
/opt/llm-lab/.venv/bin/python - <<'PY'
from data_quality_checker.cli import build_parser
args = build_parser().parse_args([
    "predict-agent", "--space-url", "https://example.hf.space", "--once",
])
print(args.space_url, args.token_env, args.batch_size, args.poll_seconds, args.once)
PY
```

Expected: yardım metni basılır; ikinci komut `https://example.hf.space DQCHECK_INGEST_TOKEN 4 30.0 True` yazar.

- [ ] **Step 8: README komut tablosuna satır ekle**

`README.md` içindeki komut tablosunda `dqcheck serve` satırının altına:

```markdown
| `dqcheck predict-agent` | Streams G0 predictions to a remote annotation platform (outbound HTTPS only). |
```

- [ ] **Step 9: Tüm DQC testlerini çalıştır ve commit et**

```bash
cd /Users/student2/data-quality-checker
/opt/llm-lab/.venv/bin/python -m pytest tests/ -q -m "not compute"
/opt/llm-lab/.venv/bin/ruff check src/data_quality_checker/predict_agent.py
git add src/data_quality_checker/predict_agent.py src/data_quality_checker/commands.py \
        src/data_quality_checker/cli.py README.md tests/test_predict_agent.py
git commit -m "feat(agent): add predict-agent that pushes G0 predictions to the platform

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# FAZ 4 — Frontend

## Task 10: OpenAPI tipleri + sorgu kancaları

**Files:**
- Modify: `/Users/student2/AnnotationPlatform/frontend/src/api/types.ts` (üretilir, elle yazılmaz)
- Modify: `/Users/student2/AnnotationPlatform/frontend/src/api/queries/annotations.ts`
- Modify: `/Users/student2/AnnotationPlatform/frontend/src/hooks/useAnnotation.ts`
- Test: `/Users/student2/AnnotationPlatform/frontend/src/api/queries/annotations.audit.test.tsx`

**Interfaces:**
- Consumes: Task 5 + Task 6 HTTP sözleşmeleri.
- Produces:
  - `usePreAuditMutation()` → `mutateAsync({ document_id, references }) => PreAuditResponse`
  - `CompleteBody.audit_ack?: { prediction_fingerprint: string }`
  - `type PreAuditResult = components['schemas']['PreAuditResponse']`
  - `type AuditDiscrepancy = components['schemas']['AuditDiscrepancy']`

- [ ] **Step 1: OpenAPI şemasını ve tipleri yeniden üret**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m backend.cli openapi-dump --output openapi.json
cd frontend && npm run gen:types:from-file
git diff --stat src/api/types.ts
```

Expected: `types.ts` içinde `PreAuditResponse`, `AuditDiscrepancy`, `AuditAck`, `PredictionIngestRequest`, `PendingResponse` şemaları görünür.

- [ ] **Step 2: Testi yaz**

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { useCompleteAnnotationMutation, usePreAuditMutation } from '@/api/queries/annotations'
import { ApiError } from '@/api/client'
// Shared server: src/test/setup.ts already owns listen()/resetHandlers()/close().
// A second setupServer() in a test file installs a competing interceptor.
import { server } from '@/test/msw-server'

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('usePreAuditMutation', () => {
  it('posts the current references and returns the audit result', async () => {
    const seen = vi.fn()
    server.use(
      http.post('http://localhost/api/annotations/:docId/pre-audit', async ({ request, params }) => {
        seen({ docId: params.docId, body: await request.json() })
        return HttpResponse.json({
          audit_status: 'ready',
          reason: null,
          bucket: 'RED',
          reasons: ['extra_or_different_core_reference'],
          similarity: 0.5,
          prediction_fingerprint: 'fp-1',
          model_generation: 'G0',
          discrepancies: [],
        })
      }),
    )
    const { result } = renderHook(() => usePreAuditMutation(), { wrapper })
    const audit = await result.current.mutateAsync({
      document_id: 'd1',
      references: [],
    })
    expect(audit.bucket).toBe('RED')
    expect(audit.prediction_fingerprint).toBe('fp-1')
    expect(seen).toHaveBeenCalledWith({ docId: 'd1', body: { references: [] } })
  })
})

describe('useCompleteAnnotationMutation', () => {
  it('sends audit_ack only when provided', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post('http://localhost/api/annotations/:docId/complete', async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json({ ok: true })
      }),
    )
    const { result } = renderHook(() => useCompleteAnnotationMutation(), { wrapper })
    await result.current.mutateAsync({ document_id: 'd1', completed: true, references: [] })
    await result.current.mutateAsync({
      document_id: 'd1',
      completed: true,
      references: [],
      audit_ack: { prediction_fingerprint: 'fp-1' },
    })
    expect(bodies[0]).toEqual({ completed: true, references: [] })
    expect(bodies[1]).toEqual({
      completed: true,
      references: [],
      audit_ack: { prediction_fingerprint: 'fp-1' },
    })
  })

  it('surfaces audit_stale as a typed ApiError code', async () => {
    server.use(
      http.post('http://localhost/api/annotations/:docId/complete', () =>
        HttpResponse.json(
          {
            detail: {
              error: 'audit_stale',
              message: 'Yeni model tahmini alındı, lütfen son kez teyit edip Tamamla\'ya basınız.',
            },
          },
          { status: 409 },
        ),
      ),
    )
    const { result } = renderHook(() => useCompleteAnnotationMutation(), { wrapper })
    await expect(
      result.current.mutateAsync({ document_id: 'd1', completed: true, references: [] }),
    ).rejects.toMatchObject({ code: 'audit_stale' })
    await waitFor(() => expect(result.current.error).toBeInstanceOf(ApiError))
  })
})
```

- [ ] **Step 3: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform/frontend
npx vitest run src/api/queries/annotations.audit.test.tsx
```

Expected: FAIL — `usePreAuditMutation is not exported`

- [ ] **Step 4: Sorgu kancalarını ekle**

`frontend/src/api/queries/annotations.ts` — dosya sonuna:

```ts
export type PreAuditResult = components['schemas']['PreAuditResponse']
export type AuditDiscrepancy = components['schemas']['AuditDiscrepancy']

interface PreAuditBody {
  document_id: string
  references: components['schemas']['ReferenceItem'][]
}

/**
 * Read-only comparison against the cached G0 prediction. Writes nothing on the
 * server — the audit decision is recorded by /complete, inside its transaction.
 */
export function usePreAuditMutation() {
  return useMutation({
    mutationFn: async ({ document_id, references }: PreAuditBody) =>
      unwrap(
        await client.POST('/api/annotations/{document_id}/pre-audit', {
          params: { path: { document_id } },
          body: { references },
        }),
      ),
  })
}
```

Aynı dosyadaki `CompleteBody` arayüzüne alan ekle:

```ts
  // Present only after the user saw a RED/YELLOW audit. The server recomputes
  // the bucket itself; this ack merely declares "I saw the comparison" and
  // carries the fingerprint so a prediction that changed meanwhile yields
  // 409 audit_stale instead of a silently different commit.
  audit_ack?: { prediction_fingerprint: string }
```

`mutationFn`'i koşullu spread ile güncelle:

```ts
    mutationFn: async ({ document_id, completed, references, audit_ack }: CompleteBody) =>
      unwrapVoid(
        await client.POST('/api/annotations/{document_id}/complete', {
          params: { path: { document_id } },
          body: {
            completed,
            ...(references !== undefined && { references }),
            ...(audit_ack !== undefined && { audit_ack }),
          },
        }),
      ),
```

`frontend/src/hooks/useAnnotation.ts` re-export listesine ekle:

```ts
  usePreAuditMutation,
```

- [ ] **Step 5: Testin geçtiğini ve tiplerin tuttuğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform/frontend
npx vitest run src/api/queries/annotations.audit.test.tsx
npx tsc --noEmit
```

Expected: 3 passed; tsc çıktısı boş.

- [ ] **Step 6: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add openapi.json frontend/src/api frontend/src/hooks/useAnnotation.ts
git commit -m "feat(frontend): add pre-audit mutation and audit_ack support

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: `quoteMatcher` — boşluk/noktalama toleranslı alıntı konumlama

**Files:**
- Create: `/Users/student2/AnnotationPlatform/frontend/src/lib/quoteMatcher.ts`
- Test: `/Users/student2/AnnotationPlatform/frontend/src/lib/quoteMatcher.test.ts`

**Interfaces:**
- Consumes: hiçbir şey (saf fonksiyonlar).
- Produces:
  - `type QuoteMatchMode = 'exact' | 'folded' | 'loose'`
  - `interface QuoteMatch { start: number; end: number; mode: QuoteMatchMode }`
  - `interface QuoteTarget { id: string; quote: string; near?: string }`
  - `interface QuoteSegment { text: string; quoteId: string | null }`
  - `findQuote(haystack: string, quote: string, near?: string): QuoteMatch | null`
  - `buildSegments(text: string, targets: QuoteTarget[]): QuoteSegment[]`

- [ ] **Step 1: Testi yaz**

```ts
import { describe, expect, it } from 'vitest'

import { buildSegments, findQuote } from '@/lib/quoteMatcher'

const DOC = [
  'T.C.',
  'GELIR IDARESI BASKANLIGI',
  '',
  'Vergi Usul Kanunu\'nun 114 uncu maddesinde zamanasimi',
  'hukmu duzenlenmistir. Ayrica 114 uncu madde geregince',
  'zamanasimi hukmu tekrar anilmistir.',
].join('\n')

describe('findQuote', () => {
  it('finds a quote that appears verbatim', () => {
    const match = findQuote(DOC, 'GELIR IDARESI BASKANLIGI')
    expect(match).not.toBeNull()
    expect(DOC.slice(match!.start, match!.end)).toBe('GELIR IDARESI BASKANLIGI')
    expect(match!.mode).toBe('exact')
  })

  it('finds a quote whose newlines were collapsed to spaces by DQCheck', () => {
    // The model stores this as a single line; the document wraps it.
    const match = findQuote(DOC, 'zamanasimi hukmu duzenlenmistir')
    expect(match).not.toBeNull()
    expect(match!.mode).toBe('folded')
    expect(DOC.slice(match!.start, match!.end)).toBe('zamanasimi\nhukmu duzenlenmistir')
  })

  it('tolerates case and typographic punctuation differences', () => {
    const match = findQuote(DOC, 'VERGI USUL KANUNU’NUN 114 UNCU MADDESINDE')
    expect(match).not.toBeNull()
    expect(match!.mode).toBe('folded')
  })

  it('falls back to alphanumeric-only matching', () => {
    const match = findQuote(DOC, 'hukmu, duzenlenmistir!!! ...')
    expect(match).not.toBeNull()
    expect(match!.mode).toBe('loose')
  })

  it('returns null when the quote is absent', () => {
    expect(findQuote(DOC, 'bu cumle dokumanda hic yok')).toBeNull()
  })

  it('returns null for empty input', () => {
    expect(findQuote('', 'x')).toBeNull()
    expect(findQuote(DOC, '   ')).toBeNull()
  })

  it('prefers the occurrence nearest the madde hint when a quote repeats', () => {
    const first = findQuote(DOC, 'zamanasimi hukmu')
    const hinted = findQuote(DOC, 'zamanasimi hukmu', '114 uncu madde geregince')
    expect(first).not.toBeNull()
    expect(hinted).not.toBeNull()
    expect(hinted!.start).toBeGreaterThan(first!.start)
  })

  it('takes the first occurrence when no hint is given', () => {
    const match = findQuote(DOC, 'zamanasimi hukmu')
    expect(match!.start).toBe(DOC.indexOf('zamanasimi'))
  })
})

describe('buildSegments', () => {
  it('reconstructs the original text exactly', () => {
    const segments = buildSegments(DOC, [
      { id: 'a', quote: 'zamanasimi hukmu duzenlenmistir' },
      { id: 'b', quote: 'GELIR IDARESI BASKANLIGI' },
    ])
    expect(segments.map((s) => s.text).join('')).toBe(DOC)
  })

  it('marks each located quote with its id', () => {
    const segments = buildSegments(DOC, [{ id: 'a', quote: 'GELIR IDARESI BASKANLIGI' }])
    const marked = segments.filter((s) => s.quoteId !== null)
    expect(marked).toHaveLength(1)
    expect(marked[0]!.quoteId).toBe('a')
    expect(marked[0]!.text).toBe('GELIR IDARESI BASKANLIGI')
  })

  it('skips quotes it cannot locate without breaking the text', () => {
    const segments = buildSegments(DOC, [{ id: 'ghost', quote: 'yok boyle bir sey' }])
    expect(segments).toHaveLength(1)
    expect(segments[0]!.quoteId).toBeNull()
    expect(segments[0]!.text).toBe(DOC)
  })

  it('keeps the first span when two quotes overlap', () => {
    const segments = buildSegments(DOC, [
      { id: 'outer', quote: 'zamanasimi hukmu duzenlenmistir' },
      { id: 'inner', quote: 'hukmu duzenlenmistir' },
    ])
    expect(segments.map((s) => s.text).join('')).toBe(DOC)
    expect(segments.filter((s) => s.quoteId === 'inner')).toHaveLength(0)
  })
})
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform/frontend
npx vitest run src/lib/quoteMatcher.test.ts
```

Expected: FAIL — `Failed to resolve import "@/lib/quoteMatcher"`

- [ ] **Step 3: `quoteMatcher.ts`'i yaz**

```ts
/**
 * Locate a model-proposed quote inside the document text the viewer renders.
 *
 * Why not `text.indexOf(quote)`: DQCheck normalizes its `source_text` with
 * `normalize_text`, which collapses EVERY whitespace run — newlines included —
 * into single spaces. `DocViewer` renders `normalizeOzelgeText(pdf_text)`, which
 * preserves newlines. PDF-extracted özelge text wraps about every 80 characters,
 * so most quotes straddle a line break and a plain substring search fails.
 *
 * Three escalating levels are tried in order: `exact` (verbatim), `folded`
 * (whitespace collapsed, typographic punctuation normalized, lowercased) and
 * `loose` (folded plus every non-alphanumeric character dropped). Each level
 * keeps an index map back to original offsets, so the caller always gets
 * coordinates into the string it rendered.
 *
 * When a level yields several matches the one closest to `near` — normally the
 * reference's `madde` token — wins; with no usable hint the first match wins.
 */

export type QuoteMatchMode = 'exact' | 'folded' | 'loose'

export interface QuoteMatch {
  start: number
  end: number
  mode: QuoteMatchMode
}

export interface QuoteTarget {
  id: string
  quote: string
  near?: string
}

export interface QuoteSegment {
  text: string
  quoteId: string | null
}

interface Projection {
  text: string
  map: number[]
}

const PUNCTUATION: Record<string, string> = {
  '“': '"',
  '”': '"',
  '‘': "'",
  '’': "'",
  '–': '-',
  '—': '-',
}

// Mirrors data_quality_checker.text._LOOSE_RE (Turkish lowercase alphabet).
const ALPHANUMERIC = /[0-9a-zçğıöşü]/

function identity(input: string): Projection {
  return { text: input, map: Array.from(input, (_char, index) => index) }
}

function fold(input: string, { loose }: { loose: boolean }): Projection {
  const chars: string[] = []
  const map: number[] = []
  let pendingSpace = false
  for (let index = 0; index < input.length; index += 1) {
    const original = input[index] as string
    const substituted = PUNCTUATION[original] ?? original
    // `toLowerCase` (not the tr locale) mirrors Python's str.casefold, which
    // maps "I" to "i" — locale-aware lowering would produce "ı" and stop
    // matching DQCheck's folded text.
    const lowered = substituted.toLowerCase()
    const isSpace = /\s/.test(substituted)
    const dropped = loose && !isSpace && !ALPHANUMERIC.test(lowered)
    if (isSpace || dropped) {
      pendingSpace = chars.length > 0
      continue
    }
    if (pendingSpace) {
      chars.push(' ')
      map.push(index)
      pendingSpace = false
    }
    // A single source char can lower into several code units ("İ" → "i̇"); each
    // unit maps back to the same original offset so map and text stay aligned.
    for (const unit of lowered) {
      chars.push(unit)
      map.push(index)
    }
  }
  return { text: chars.join(''), map }
}

const LEVELS: Array<{ mode: QuoteMatchMode; project: (input: string) => Projection }> = [
  { mode: 'exact', project: identity },
  { mode: 'folded', project: (input) => fold(input, { loose: false }) },
  { mode: 'loose', project: (input) => fold(input, { loose: true }) },
]

function occurrences(haystack: string, needle: string): number[] {
  const found: number[] = []
  if (!needle) return found
  let from = 0
  for (;;) {
    const index = haystack.indexOf(needle, from)
    if (index < 0) return found
    found.push(index)
    from = index + 1
  }
}

function pickNearest(candidates: number[], projected: string, hint: string): number {
  const first = candidates[0] as number
  if (candidates.length === 1 || !hint) return first
  const hintPositions = occurrences(projected, hint)
  if (hintPositions.length === 0) return first
  let best = first
  let bestDistance = Number.POSITIVE_INFINITY
  for (const candidate of candidates) {
    for (const hintPosition of hintPositions) {
      const distance = Math.abs(candidate - hintPosition)
      if (distance < bestDistance) {
        bestDistance = distance
        best = candidate
      }
    }
  }
  return best
}

export function findQuote(haystack: string, quote: string, near?: string): QuoteMatch | null {
  const trimmed = quote.trim()
  if (!haystack || !trimmed) return null

  for (const level of LEVELS) {
    const projection = level.project(haystack)
    const needle = level.project(trimmed).text
    if (!needle) continue
    const candidates = occurrences(projection.text, needle)
    if (candidates.length === 0) continue
    const hint = near ? level.project(near).text : ''
    const start = pickNearest(candidates, projection.text, hint)
    const startOriginal = projection.map[start] as number
    const endOriginal = (projection.map[start + needle.length - 1] as number) + 1
    return { start: startOriginal, end: endOriginal, mode: level.mode }
  }
  return null
}

export function buildSegments(text: string, targets: QuoteTarget[]): QuoteSegment[] {
  const spans: Array<{ start: number; end: number; id: string }> = []
  for (const target of targets) {
    const match = findQuote(text, target.quote, target.near)
    if (match) spans.push({ start: match.start, end: match.end, id: target.id })
  }
  spans.sort((left, right) => left.start - right.start || right.end - left.end)

  const segments: QuoteSegment[] = []
  let cursor = 0
  for (const span of spans) {
    if (span.start < cursor) continue // overlapping span: the first one wins
    if (span.start > cursor) {
      segments.push({ text: text.slice(cursor, span.start), quoteId: null })
    }
    segments.push({ text: text.slice(span.start, span.end), quoteId: span.id })
    cursor = span.end
  }
  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), quoteId: null })
  }
  return segments
}
```

- [ ] **Step 4: Testin geçtiğini doğrula**

```bash
cd /Users/student2/AnnotationPlatform/frontend
npx vitest run src/lib/quoteMatcher.test.ts
npx tsc --noEmit
```

Expected: 13 passed; tsc temiz.

- [ ] **Step 5: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add frontend/src/lib/quoteMatcher.ts frontend/src/lib/quoteMatcher.test.ts
git commit -m "feat(frontend): add whitespace-tolerant quote matcher

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: DocViewer — `<mark>` highlight + yumuşak kaydırma

**Files:**
- Modify: `/Users/student2/AnnotationPlatform/frontend/src/components/annotation/DocViewer.tsx`
- Test: `/Users/student2/AnnotationPlatform/frontend/src/components/annotation/DocViewer.highlight.test.tsx`

**Interfaces:**
- Consumes: Task 11 `buildSegments`, `QuoteTarget`.
- Produces: `DocViewerProps` genişler → `highlights?: QuoteTarget[]`, `activeHighlightId?: string | null`. Varsayılanlar mevcut `<DocViewer docId={...} />` çağrılarını bozmaz.

- [ ] **Step 1: Testi yaz**

Paylaşılan MSW sunucusunu kullanır (global `src/test/setup.ts` `listen`/`close` sahibidir), doküman fixture'ı `makeDocumentDetail`'den gelir:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ReactElement } from 'react'

import { DocViewer } from '@/components/annotation/DocViewer'
import { makeDocumentDetail } from '@/test/msw-handlers'
// Shared server: src/test/setup.ts owns listen()/resetHandlers()/close().
import { server } from '@/test/msw-server'

const PDF_TEXT = "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi\nhukmu duzenlenmistir."

beforeEach(() => {
  server.use(
    http.get('http://localhost/api/documents/d1', () =>
      HttpResponse.json(makeDocumentDetail({ document_id: 'd1', pdf_text: PDF_TEXT })),
    ),
  )
})

function renderViewer(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('DocViewer highlights', () => {
  it('renders plain text when no highlights are given', async () => {
    renderViewer(<DocViewer docId="d1" />)
    await waitFor(() => expect(screen.getByText(/zamanasimi/)).toBeInTheDocument())
    expect(document.querySelector('mark')).toBeNull()
  })

  it('marks a quote whose newline was collapsed by the model', async () => {
    renderViewer(
      <DocViewer
        docId="d1"
        highlights={[{ id: 'm1', quote: 'zamanasimi hukmu duzenlenmistir' }]}
      />,
    )
    await waitFor(() => expect(document.querySelector('mark')).not.toBeNull())
    const mark = document.querySelector('mark')!
    expect(mark.getAttribute('data-highlight-id')).toBe('m1')
    expect(mark.textContent).toBe('zamanasimi\nhukmu duzenlenmistir')
  })

  it('scrolls the active highlight into view', async () => {
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    renderViewer(
      <DocViewer
        docId="d1"
        highlights={[{ id: 'm1', quote: 'zamanasimi hukmu duzenlenmistir' }]}
        activeHighlightId="m1"
      />,
    )
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled())
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
  })

  it('leaves the document intact when the quote cannot be located', async () => {
    renderViewer(
      <DocViewer docId="d1" highlights={[{ id: 'ghost', quote: 'yok boyle bir cumle' }]} />,
    )
    await waitFor(() => expect(screen.getByText(/zamanasimi/)).toBeInTheDocument())
    expect(document.querySelector('mark')).toBeNull()
  })
})
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform/frontend
npx vitest run src/components/annotation/DocViewer.highlight.test.tsx
```

Expected: FAIL — `mark` elementi bulunamıyor (prop henüz yok).

- [ ] **Step 3: DocViewer'ı güncelle**

Import bloğuna ekle:

```tsx
import { buildSegments, type QuoteTarget } from '@/lib/quoteMatcher'
```

`DocViewerProps` arayüzünü değiştir:

```tsx
interface DocViewerProps {
  docId: string
  /** Model-proposed quotes to mark in the body. Empty → text renders as before. */
  highlights?: QuoteTarget[]
  /** Which highlight the audit panel is pointing at; scrolled into view. */
  activeHighlightId?: string | null
}
```

Dosya kapsamında sabit bir boş dizi tanımla (her render'da yeni referans üretip
`useMemo`'yu boşa çalıştırmamak için), `TR_FORMATTER` tanımının yanına:

```tsx
const NO_HIGHLIGHTS: QuoteTarget[] = []
```

Bileşen imzası ve gövdesi:

```tsx
export function DocViewer({
  docId,
  highlights = NO_HIGHLIGHTS,
  activeHighlightId = null,
}: DocViewerProps) {
```

`cleaned` useMemo'sundan sonra iki hook ekle:

```tsx
  // Segment only when there is something to mark: the common (no-audit) path
  // keeps rendering one text node exactly as before.
  const segments = useMemo(
    () => (highlights.length > 0 ? buildSegments(cleaned, highlights) : null),
    [cleaned, highlights],
  )

  useEffect(() => {
    if (!activeHighlightId) return
    const node = scrollContainerRef.current?.querySelector(
      `[data-highlight-id="${activeHighlightId}"]`,
    )
    node?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeHighlightId])
```

`<article>` içeriğini değiştir:

```tsx
        <article className="min-w-0 max-w-full whitespace-pre-wrap break-words px-5 py-5 font-serif text-[15px] leading-[1.7] text-foreground/95 [overflow-wrap:anywhere]">
          {segments === null
            ? cleaned
            : segments.map((segment, index) =>
                segment.quoteId === null ? (
                  <span key={index}>{segment.text}</span>
                ) : (
                  <mark
                    key={index}
                    data-highlight-id={segment.quoteId}
                    className={cn(
                      'rounded-sm bg-warning/25 px-0.5 text-foreground',
                      segment.quoteId === activeHighlightId &&
                        'bg-warning/50 ring-1 ring-warning',
                    )}
                  >
                    {segment.text}
                  </mark>
                ),
              )}
        </article>
```

- [ ] **Step 4: Testleri çalıştır (yeni + mevcut DocViewer regresyonu)**

```bash
cd /Users/student2/AnnotationPlatform/frontend
npx vitest run src/components/annotation/DocViewer.highlight.test.tsx \
                src/components/annotation/DocViewer.test.tsx
npx tsc --noEmit
```

Expected: yeni dosyada 4 passed; mevcut DocViewer testleri değişmeden geçer.

- [ ] **Step 5: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add frontend/src/components/annotation/DocViewer.tsx \
        frontend/src/components/annotation/DocViewer.highlight.test.tsx
git commit -m "feat(frontend): mark and scroll to model quotes in DocViewer

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: `QualityAuditPanel` — denetim ekranı

**Files:**
- Create: `/Users/student2/AnnotationPlatform/frontend/src/components/annotation/QualityAuditPanel.tsx`
- Test: `/Users/student2/AnnotationPlatform/frontend/src/components/annotation/QualityAuditPanel.test.tsx`

**Interfaces:**
- Consumes: Task 10 `PreAuditResult`, `AuditDiscrepancy`.
- Produces:
  - `discrepancyKey(discrepancy: AuditDiscrepancy): string` — highlight id ve "eklendi" anahtarı
  - `QualityAuditPanel` props: `result`, `acceptedKeys: ReadonlySet<string>`, `staleNotice?: string | null`, `isCompleting: boolean`, `onAccept(discrepancy)`, `onHover(highlightId: string | null)`, `onComplete()`, `onOverride()`, `onBackToEdit()`

- [ ] **Step 1: Testi yaz**

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { QualityAuditPanel, discrepancyKey } from './QualityAuditPanel'
import type { AuditDiscrepancy, PreAuditResult } from '@/api/queries/annotations'

const MODEL_ONLY: AuditDiscrepancy = {
  kind: 'model_only',
  kanun_no: '193',
  kanun_ad: 'Gelir Vergisi Kanunu',
  madde: '94',
  model_reference: {
    kanun_no: '193', kanun_ad: 'Gelir Vergisi Kanunu', madde: '94',
    fikra: '1', bent: 'b', source_text: 'tevkifat esaslarini belirler',
  },
  human_reference: null,
  field_diffs: [],
  match_mode: 'normalized_exact',
}

const HUMAN_ONLY: AuditDiscrepancy = {
  kind: 'human_only',
  kanun_no: '3065',
  kanun_ad: 'Katma Değer Vergisi Kanunu',
  madde: '17',
  model_reference: null,
  human_reference: {
    kanun_no: '3065', kanun_ad: 'Katma Değer Vergisi Kanunu', madde: '17',
    fikra: '', bent: '', source_text: 'istisna hukmu',
  },
  field_diffs: [],
  match_mode: null,
}

const DETAIL: AuditDiscrepancy = {
  kind: 'detail_mismatch',
  kanun_no: '213',
  kanun_ad: 'Vergi Usul Kanunu',
  madde: '114',
  model_reference: {
    kanun_no: '213', kanun_ad: 'Vergi Usul Kanunu', madde: '114',
    fikra: '2', bent: '', source_text: 'zamanasimi',
  },
  human_reference: {
    kanun_no: '213', kanun_ad: 'Vergi Usul Kanunu', madde: '114',
    fikra: '1', bent: '', source_text: 'zamanasimi',
  },
  field_diffs: ['fikra'],
  match_mode: 'loose_alphanumeric',
}

function makeResult(overrides: Partial<PreAuditResult> = {}): PreAuditResult {
  return {
    audit_status: 'ready',
    reason: null,
    bucket: 'RED',
    reasons: ['extra_or_different_core_reference'],
    similarity: 0.5,
    prediction_fingerprint: 'fp-1',
    model_generation: 'G0',
    discrepancies: [MODEL_ONLY, HUMAN_ONLY, DETAIL],
    ...overrides,
  }
}

function renderPanel(props: Partial<React.ComponentProps<typeof QualityAuditPanel>> = {}) {
  const handlers = {
    onAccept: vi.fn(),
    onHover: vi.fn(),
    onComplete: vi.fn(),
    onOverride: vi.fn(),
    onBackToEdit: vi.fn(),
  }
  render(
    <QualityAuditPanel
      result={makeResult()}
      acceptedKeys={new Set()}
      isCompleting={false}
      {...handlers}
      {...props}
    />,
  )
  return handlers
}

describe('QualityAuditPanel', () => {
  it('always shows the cognitive safeguard warning', () => {
    renderPanel()
    expect(screen.getByText('Model Karşılaştırma & Kalite Denetimi')).toBeInTheDocument()
    expect(
      screen.getByText(/Model yanılıyor olabilir/),
    ).toBeInTheDocument()
    expect(screen.getByText('Kanun veya madde listesi uyuşmuyor')).toBeInTheDocument()
  })

  it('offers an add button only for references the model found', async () => {
    const handlers = renderPanel()
    const addButtons = screen.getAllByRole('button', { name: 'Model Önerisini Listeme Ekle' })
    // model_only + detail_mismatch carry a model reference; human_only does not.
    expect(addButtons).toHaveLength(2)
    expect(screen.getByText('Sizde var, model bulamadı')).toBeInTheDocument()
    await userEvent.click(addButtons[0]!)
    expect(handlers.onAccept).toHaveBeenCalledWith(MODEL_ONLY)
  })

  it('marks an already-accepted suggestion and disables its button', () => {
    renderPanel({ acceptedKeys: new Set([discrepancyKey(MODEL_ONLY)]) })
    const accepted = screen.getByRole('button', { name: 'Eklendi' })
    expect(accepted).toBeDisabled()
  })

  it('warns when the model quote cannot be found in the document', () => {
    renderPanel({ result: makeResult({ discrepancies: [{ ...MODEL_ONLY, match_mode: null }] }) })
    expect(screen.getByText('Alıntı doküman metninde bulunamadı')).toBeInTheDocument()
  })

  it('names the differing fields for a detail mismatch', () => {
    renderPanel({ result: makeResult({ bucket: 'YELLOW', discrepancies: [DETAIL] }) })
    expect(screen.getByText('Referans ayrıntıları uyuşmuyor')).toBeInTheDocument()
    expect(screen.getByText(/fıkra/)).toBeInTheDocument()
  })

  it('reports hover targets so the document can scroll', async () => {
    const handlers = renderPanel()
    const row = screen.getByTestId(`audit-row-${discrepancyKey(MODEL_ONLY)}`)
    await userEvent.hover(row)
    expect(handlers.onHover).toHaveBeenCalledWith(discrepancyKey(MODEL_ONLY))
    await userEvent.unhover(row)
    expect(handlers.onHover).toHaveBeenLastCalledWith(null)
  })

  it('wires the three free actions', async () => {
    const handlers = renderPanel()
    await userEvent.click(
      screen.getByRole('button', { name: 'Benim Etiketim Doğru, Yine de Tamamla' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Düzenlemeye Geri Dön' }))
    await userEvent.click(screen.getByRole('button', { name: 'Tamamla' }))
    expect(handlers.onOverride).toHaveBeenCalledTimes(1)
    expect(handlers.onBackToEdit).toHaveBeenCalledTimes(1)
    expect(handlers.onComplete).toHaveBeenCalledTimes(1)
  })

  it('shows the soft notice when a fresher prediction arrived', () => {
    renderPanel({
      staleNotice: 'Yeni model tahmini alındı, lütfen son kez teyit edip Tamamla\'ya basınız.',
    })
    expect(screen.getByRole('status')).toHaveTextContent('Yeni model tahmini alındı')
  })

  it('disables actions while a commit is in flight', () => {
    renderPanel({ isCompleting: true })
    expect(screen.getByRole('button', { name: 'Tamamla' })).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Benim Etiketim Doğru, Yine de Tamamla' }),
    ).toBeDisabled()
  })
})
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform/frontend
npx vitest run src/components/annotation/QualityAuditPanel.test.tsx
```

Expected: FAIL — `Failed to resolve import "./QualityAuditPanel"`

- [ ] **Step 3: Bileşeni yaz**

```tsx
import { AlertTriangle, ArrowLeft, Check, Plus, ShieldCheck } from 'lucide-react'

import type { AuditDiscrepancy, PreAuditResult } from '@/api/queries/annotations'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

const BUCKET_LABEL: Record<string, string> = {
  RED: 'Kanun veya madde listesi uyuşmuyor',
  YELLOW: 'Referans ayrıntıları uyuşmuyor',
  QUARANTINE: 'Teknik inceleme gerekiyor',
}

const KIND_LABEL: Record<AuditDiscrepancy['kind'], string> = {
  model_only: 'Model buldu, sizde yok',
  human_only: 'Sizde var, model bulamadı',
  detail_mismatch: 'Ayrıntı farkı (fıkra / bent / alıntı)',
}

const FIELD_LABEL: Record<string, string> = {
  fikra: 'fıkra',
  bent: 'bent',
  source_text: 'metinden alıntı',
}

type ReferenceLike = Record<string, string> | null | undefined

/** Stable id for a discrepancy: highlight target + "already accepted" key. */
export function discrepancyKey(discrepancy: AuditDiscrepancy): string {
  const reference = discrepancy.model_reference ?? discrepancy.human_reference
  return [
    discrepancy.kind,
    discrepancy.kanun_no,
    discrepancy.madde,
    reference?.fikra ?? '',
    reference?.bent ?? '',
  ].join(':')
}

function referenceLabel(reference: ReferenceLike): string {
  if (!reference) return '—'
  const law = reference.kanun_ad || reference.kanun_no || 'Kanun belirtilmemiş'
  const article = reference.madde ? ` m.${reference.madde}` : ''
  const fikra = reference.fikra ? `/${reference.fikra}` : ''
  const bent = reference.bent ? `-${reference.bent}` : ''
  return `${law}${article}${fikra}${bent}`
}

interface QualityAuditPanelProps {
  result: PreAuditResult
  acceptedKeys: ReadonlySet<string>
  staleNotice?: string | null
  isCompleting: boolean
  onAccept: (discrepancy: AuditDiscrepancy) => void
  onHover: (highlightId: string | null) => void
  onComplete: () => void
  onOverride: () => void
  onBackToEdit: () => void
}

export function QualityAuditPanel({
  result,
  acceptedKeys,
  staleNotice = null,
  isCompleting,
  onAccept,
  onHover,
  onComplete,
  onOverride,
  onBackToEdit,
}: QualityAuditPanelProps) {
  const bucket = result.bucket ?? ''
  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden">
      <header className="space-y-2 border-b border-border/60 bg-card/60 px-5 py-3">
        <h2 className="font-display text-[1.0625rem] font-bold tracking-tight text-foreground">
          Model Karşılaştırma & Kalite Denetimi
        </h2>
        <p
          role="note"
          className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/[0.07] px-2.5 py-1.5 text-[12px] font-medium leading-normal text-foreground/90"
        >
          <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5 shrink-0 translate-y-[2px] text-warning" />
          <span>
            ⚠️ Unutmayınız: Model yanılıyor olabilir. Lütfen aşağıdaki tespitleri kaynak
            metne göre değerlendiriniz.
          </span>
        </p>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.12em]',
              bucket === 'RED'
                ? 'border-destructive/30 bg-destructive/10 text-destructive'
                : 'border-warning/30 bg-warning/10 text-warning',
            )}
          >
            {bucket}
          </span>
          <span className="text-[13px] font-semibold text-foreground/90">
            {BUCKET_LABEL[bucket] ?? 'Belgeyi kontrol edin'}
          </span>
        </div>
        {staleNotice && (
          <p
            role="status"
            className="rounded-md border border-accent/30 bg-accent/[0.07] px-2.5 py-1.5 text-[12px] font-medium leading-normal text-foreground/90"
          >
            {staleNotice}
          </p>
        )}
      </header>

      <div className="min-w-0 flex-1 space-y-2 overflow-auto px-5 py-3">
        {result.discrepancies.map((discrepancy) => {
          const key = discrepancyKey(discrepancy)
          const model = discrepancy.model_reference
          const accepted = acceptedKeys.has(key)
          const canAccept = Boolean(model?.source_text)
          return (
            <section
              key={key}
              data-testid={`audit-row-${key}`}
              onMouseEnter={() => onHover(key)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(key)}
              onBlur={() => onHover(null)}
              className="space-y-1.5 rounded-md border border-border/60 bg-card/45 px-3 py-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
                  {KIND_LABEL[discrepancy.kind]}
                </span>
                {discrepancy.match_mode === null && model && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-destructive">
                    <AlertTriangle aria-hidden="true" className="h-3 w-3" />
                    Alıntı doküman metninde bulunamadı
                  </span>
                )}
              </div>

              {model && (
                <p className="text-[13px] leading-snug text-foreground/90">
                  <span className="font-semibold">Model:</span> {referenceLabel(model)}
                </p>
              )}
              {discrepancy.human_reference && (
                <p className="text-[13px] leading-snug text-foreground/90">
                  <span className="font-semibold">Sizde:</span>{' '}
                  {referenceLabel(discrepancy.human_reference)}
                </p>
              )}
              {discrepancy.field_diffs.length > 0 && (
                <p className="text-[12px] text-muted-foreground">
                  Farklı alanlar:{' '}
                  {discrepancy.field_diffs
                    .map((field) => FIELD_LABEL[field] ?? field)
                    .join(', ')}
                </p>
              )}
              {model?.source_text && (
                <blockquote className="border-l-2 border-warning/40 pl-2 font-serif text-[12px] leading-snug text-foreground/80">
                  {model.source_text}
                </blockquote>
              )}

              {canAccept && (
                <Button
                  type="button"
                  size="sm"
                  variant={accepted ? 'outline' : 'default'}
                  disabled={accepted || isCompleting}
                  onClick={() => onAccept(discrepancy)}
                  className="min-w-0 max-w-full whitespace-normal px-2 text-center leading-tight"
                >
                  {accepted ? <Check /> : <Plus />}
                  {accepted ? 'Eklendi' : 'Model Önerisini Listeme Ekle'}
                </Button>
              )}
            </section>
          )
        })}
      </div>

      <Separator />
      <footer className="space-y-2 bg-card/60 p-5">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={isCompleting}
          onClick={onOverride}
          className="w-full min-w-0 whitespace-normal px-2 text-center leading-tight"
        >
          <ShieldCheck />
          Benim Etiketim Doğru, Yine de Tamamla
        </Button>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={isCompleting}
            onClick={onBackToEdit}
            className="min-w-0 max-w-full whitespace-normal px-2 text-center leading-tight"
          >
            <ArrowLeft />
            Düzenlemeye Geri Dön
          </Button>
          <Button
            type="button"
            size="sm"
            variant="success"
            disabled={isCompleting}
            onClick={onComplete}
            className="min-w-0 max-w-full whitespace-normal px-2 text-center leading-tight"
          >
            <Check />
            Tamamla
          </Button>
        </div>
      </footer>
    </div>
  )
}
```

- [ ] **Step 4: Testin geçtiğini doğrula**

```bash
cd /Users/student2/AnnotationPlatform/frontend
npx vitest run src/components/annotation/QualityAuditPanel.test.tsx
npx tsc --noEmit
npx eslint src/components/annotation/QualityAuditPanel.tsx
```

Expected: 9 passed; tsc ve eslint temiz.

- [ ] **Step 5: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add frontend/src/components/annotation/QualityAuditPanel.tsx \
        frontend/src/components/annotation/QualityAuditPanel.test.tsx
git commit -m "feat(frontend): add quality audit panel with free-choice actions

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: `AnnotateDoc` bağlantısı — durum makinesi, 409 kurtarma, debounce yarışı

**Files:**
- Modify: `/Users/student2/AnnotationPlatform/frontend/src/routes/AnnotateDoc.tsx`
- Modify: `/Users/student2/AnnotationPlatform/frontend/src/components/annotation/ReferencePanel.tsx`
- Modify: `/Users/student2/AnnotationPlatform/frontend/src/components/annotation/ReferencePanel.test.tsx` (yeni zorunlu proplar)
- Test: `/Users/student2/AnnotationPlatform/frontend/src/routes/AnnotateDoc.audit.test.tsx`

**Interfaces:**
- Consumes: Task 10 `usePreAuditMutation`, Task 12 `DocViewer` props, Task 13 `QualityAuditPanel` + `discrepancyKey`.
- Produces: `ReferencePanel` iki yeni prop alır — `modelUnavailableReason?: string | null`, `onCompare: () => void`, `isAuditing: boolean`.

- [ ] **Step 1: Testi yaz**

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { makeDocumentDetail } from '@/test/msw-handlers'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { AnnotateDoc } from './AnnotateDoc'

const PDF_TEXT =
  "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir. " +
  'Gelir Vergisi Kanunu 94 uncu maddesi tevkifat esaslarini belirler.'

const MODEL_ONLY_DISCREPANCY = {
  kind: 'model_only' as const,
  kanun_no: '193',
  kanun_ad: 'Gelir Vergisi Kanunu',
  madde: '94',
  model_reference: {
    kanun_no: '193', kanun_ad: 'Gelir Vergisi Kanunu', madde: '94',
    fikra: '', bent: '', source_text: 'tevkifat esaslarini belirler',
  },
  human_reference: null,
  field_diffs: [],
  match_mode: 'normalized_exact',
}

function redAudit(fingerprint = 'fp-1') {
  return {
    audit_status: 'ready',
    reason: null,
    bucket: 'RED',
    reasons: ['extra_or_different_core_reference'],
    similarity: 0.5,
    prediction_fingerprint: fingerprint,
    model_generation: 'G0',
    discrepancies: [MODEL_ONLY_DISCREPANCY],
  }
}

function greenAudit(fingerprint = 'fp-1') {
  return { ...redAudit(fingerprint), bucket: 'GREEN', reasons: [], discrepancies: [] }
}

function unavailableAudit() {
  return {
    audit_status: 'model_unavailable',
    reason: 'no_prediction',
    bucket: null,
    reasons: [],
    similarity: null,
    prediction_fingerprint: null,
    model_generation: null,
    discrepancies: [],
  }
}

beforeEach(() => {
  useAuthStore.getState().setUser({
    id: 1, username: 'tester', email: null, role: 'user', is_active: true,
    has_seen_manual: true, has_passed_training: true, avatar_color: null,
    created_at: '2026-05-01T00:00:00+00:00',
  })
  server.use(
    http.get('http://localhost/api/documents/doc-1', () =>
      HttpResponse.json(makeDocumentDetail({ document_id: 'doc-1', pdf_text: PDF_TEXT })),
    ),
    http.get('http://localhost/api/documents/doc-1/annotation', () =>
      HttpResponse.json({
        annotation: {
          document_id: 'doc-1',
          references: [{
            kanun_no: '213', kanun_ad: 'Vergi Usul Kanunu', madde: '114',
            fikra: null, bent: null, source_text: 'zamanasimi hukmu duzenlenmistir',
          }],
          is_completed: false,
          last_editor_user_id: 1,
          completed_by_user_id: null,
          edit_count: 1,
          unique_users_count: 1,
          created_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-01T00:00:00Z',
        },
        chain: [],
      }),
    ),
  )
})

function renderDoc() {
  return renderWithProviders(
    <Routes>
      <Route path="/docs/:docId" element={<AnnotateDoc />} />
      <Route path="/" element={<div data-testid="route-root" />} />
    </Routes>,
    { initialEntries: ['/docs/doc-1'], wildcardEntry: true },
  )
}

async function clickComplete() {
  const button = await screen.findByRole('button', { name: /tamamlandı işaretle/i })
  await waitFor(() => expect(button).not.toBeDisabled())
  await userEvent.click(button)
}

describe('AnnotateDoc quality audit', () => {
  it('opens the audit panel instead of completing when the buckets mismatch', async () => {
    const completes: unknown[] = []
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(redAudit()),
      ),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push(await request.json())
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    await clickComplete()
    expect(
      await screen.findByText('Model Karşılaştırma & Kalite Denetimi'),
    ).toBeInTheDocument()
    expect(completes).toHaveLength(0)
  })

  it('marks the model quote in the document body while the panel is open', async () => {
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(redAudit()),
      ),
    )
    renderDoc()
    await clickComplete()
    await screen.findByText('Model Karşılaştırma & Kalite Denetimi')
    await waitFor(() => {
      const mark = document.querySelector('mark')
      expect(mark?.textContent).toBe('tevkifat esaslarini belirler')
    })
  })

  it('completes straight through when the audit is green', async () => {
    const completes: Array<Record<string, unknown>> = []
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(greenAudit()),
      ),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push((await request.json()) as Record<string, unknown>)
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    await clickComplete()
    await waitFor(() => expect(completes).toHaveLength(1))
    expect(completes[0]!.audit_ack).toEqual({ prediction_fingerprint: 'fp-1' })
    expect(screen.queryByText('Model Karşılaştırma & Kalite Denetimi')).toBeNull()
  })

  it('completes without an ack and shows a neutral notice when no prediction exists', async () => {
    const completes: Array<Record<string, unknown>> = []
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(unavailableAudit()),
      ),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push((await request.json()) as Record<string, unknown>)
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    await clickComplete()
    await waitFor(() => expect(completes).toHaveLength(1))
    expect(completes[0]!.audit_ack).toBeUndefined()
  })

  it('accepting a suggestion and immediately completing sends the accepted reference', async () => {
    const completes: Array<{ references?: Array<Record<string, unknown>> }> = []
    let auditCalls = 0
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () => {
        auditCalls += 1
        return HttpResponse.json(auditCalls === 1 ? redAudit() : greenAudit())
      }),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push((await request.json()) as { references?: Array<Record<string, unknown>> })
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    await clickComplete()
    await screen.findByText('Model Karşılaştırma & Kalite Denetimi')
    // No waiting between accept and complete: this is the debounce race (rule 2).
    await userEvent.click(
      screen.getByRole('button', { name: 'Model Önerisini Listeme Ekle' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Tamamla' }))
    await waitFor(() => expect(completes).toHaveLength(1))
    const sent = completes[0]!.references ?? []
    expect(sent).toHaveLength(2)
    expect(sent.map((r) => r.madde)).toContain('94')
  })

  it('override commits immediately with the ack', async () => {
    const completes: Array<Record<string, unknown>> = []
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(redAudit()),
      ),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push((await request.json()) as Record<string, unknown>)
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    await clickComplete()
    await screen.findByText('Model Karşılaştırma & Kalite Denetimi')
    await userEvent.click(
      screen.getByRole('button', { name: 'Benim Etiketim Doğru, Yine de Tamamla' }),
    )
    await waitFor(() => expect(completes).toHaveLength(1))
    expect(completes[0]!.audit_ack).toEqual({ prediction_fingerprint: 'fp-1' })
  })

  it('recovers softly from 409 audit_stale by re-auditing and reopening the panel', async () => {
    let auditCalls = 0
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () => {
        auditCalls += 1
        // First call: green (so the flow tries to commit). Second call (after
        // the 409): the agent's fresher prediction disagrees.
        return HttpResponse.json(auditCalls === 1 ? greenAudit('fp-1') : redAudit('fp-2'))
      }),
      http.post('http://localhost/api/annotations/doc-1/complete', () =>
        HttpResponse.json(
          {
            detail: {
              error: 'audit_stale',
              message: 'Yeni model tahmini alındı, lütfen son kez teyit edip Tamamla\'ya basınız.',
              prediction_fingerprint: 'fp-2',
            },
          },
          { status: 409 },
        ),
      ),
    )
    renderDoc()
    await clickComplete()
    expect(await screen.findByRole('status')).toHaveTextContent('Yeni model tahmini alındı')
    expect(screen.getByText('Model Karşılaştırma & Kalite Denetimi')).toBeInTheDocument()
  })

  it('lets the user compare on demand without completing', async () => {
    const completes: unknown[] = []
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(redAudit()),
      ),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push(await request.json())
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    const compare = await screen.findByRole('button', { name: 'Model ile karşılaştır' })
    await waitFor(() => expect(compare).not.toBeDisabled())
    await userEvent.click(compare)
    expect(
      await screen.findByText('Model Karşılaştırma & Kalite Denetimi'),
    ).toBeInTheDocument()
    expect(completes).toHaveLength(0)
  })

  it('returns to editing from the panel', async () => {
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(redAudit()),
      ),
    )
    renderDoc()
    await clickComplete()
    await screen.findByText('Model Karşılaştırma & Kalite Denetimi')
    await userEvent.click(screen.getByRole('button', { name: 'Düzenlemeye Geri Dön' }))
    await waitFor(() =>
      expect(screen.queryByText('Model Karşılaştırma & Kalite Denetimi')).toBeNull(),
    )
    expect(screen.getByRole('button', { name: /yeni referans/i })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform/frontend
npx vitest run src/routes/AnnotateDoc.audit.test.tsx
```

Expected: FAIL — panel açılmıyor, `Model ile karşılaştır` butonu yok.

- [ ] **Step 3: `ReferencePanel`'e iki prop ekle**

`ReferencePanelProps` içine:

```tsx
  /**
   * Non-null when the last audit could not run (no prediction, model error,
   * truncated output, stale text). Shown as a neutral notice — never as a
   * green "model agrees" claim.
   */
  modelUnavailableReason?: string | null
  /** Manual "compare me against the model" trigger. */
  onCompare: () => void
  isAuditing: boolean
```

Bileşen imzasına ekle (`isCompleted,` satırından sonra):

```tsx
  modelUnavailableReason = null,
  onCompare,
  isAuditing,
```

`footer` içinde, `{!isValid && refs.length > 0 && (...)}` bloğunun hemen ardına:

```tsx
        {modelUnavailableReason && (
          <p
            role="note"
            data-testid="model-unavailable-notice"
            className="rounded-md border border-border/60 bg-muted/40 px-3 py-2 text-[13px] leading-relaxed text-muted-foreground"
          >
            Bu doküman için model kontrolü yapılamadı — kendi değerlendirmenizle devam edin.
          </p>
        )}
```

Aksiyon satırında `Atla` butonundan önce:

```tsx
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onCompare}
            disabled={!canEdit || isSaving || isAuditing}
            title="Etiketlerinizi model tahminiyle karşılaştırın; hiçbir şey kaydedilmez."
            className="min-w-0 max-w-full whitespace-normal px-2 text-center leading-tight"
          >
            {isAuditing ? 'Karşılaştırılıyor…' : 'Model ile karşılaştır'}
          </Button>
```

- [ ] **Step 4: `AnnotateDoc`'u bağla**

Import bloğuna ekle:

```tsx
import { useEffect, useMemo, useRef } from 'react'   // mevcut react importuna ekle
import { QualityAuditPanel, discrepancyKey } from '@/components/annotation/QualityAuditPanel'
import { usePreAuditMutation } from '@/hooks/useAnnotation'
import type { AuditDiscrepancy, PreAuditResult } from '@/api/queries/annotations'
import type { QuoteTarget } from '@/lib/quoteMatcher'
```

`AnnotateDocInner` gövdesinin başına (mevcut `const [modalOpen, setModalOpen] = useState(true)` satırından sonra) durum makinesini ekle:

```tsx
  type AuditState =
    | { phase: 'idle' }
    | { phase: 'running' }
    | { phase: 'open'; result: PreAuditResult; staleNotice: string | null }

  const [audit, setAudit] = useState<AuditState>({ phase: 'idle' })
  const [acceptedKeys, setAcceptedKeys] = useState<ReadonlySet<string>>(new Set())
  const [activeHighlightId, setActiveHighlightId] = useState<string | null>(null)
  const [modelUnavailableReason, setModelUnavailableReason] = useState<string | null>(null)
  const preAuditMutation = usePreAuditMutation()
  // Mirror of the live reference list. `refs.list` lags by one render after a
  // reducer dispatch and the draft PUT is debounced, so a "Tamamla" click in
  // the same tick as an accepted suggestion must read from here.
  const refsRef = useRef<ReferenceItem[]>([])
```

`refs` tanımının ardına senkronizasyon efekti:

```tsx
  useEffect(() => {
    refsRef.current = refs.list
  }, [refs.list])
```

`handleComplete`'i aşağıdaki üç fonksiyonla değiştir (mevcut gövdedeki kilit/refetch/navigate akışı `finalizeComplete` içine taşınır, davranışı korunur):

```tsx
  const runPreAudit = async (references: ReferenceItem[]) =>
    preAuditMutation.mutateAsync({ document_id: docId, references })

  const finalizeComplete = async (
    targetCompleted: boolean,
    cleanedRefs: ReferenceItem[],
    ack: { prediction_fingerprint: string } | undefined,
    attempt = 0,
  ) => {
    draft.blockSavesUntilFurtherNotice()
    try {
      await completeMutation.mutateAsync({
        document_id: docId,
        completed: targetCompleted,
        ...(targetCompleted && { references: cleanedRefs }),
        ...(ack !== undefined && { audit_ack: ack }),
      })
    } catch (err) {
      draft.unblockSaves()
      const code = err instanceof ApiError ? err.code : ''
      const auditConflict = code === 'audit_stale' || code === 'audit_required'
      if (!auditConflict || attempt >= 1) {
        setAudit({ phase: 'idle' })
        return
      }
      // The predict-agent pushed a fresher prediction while the user worked.
      // Re-audit quietly, then either reopen the panel with a soft notice or
      // commit once more with the fresh fingerprint. Never a scary error.
      try {
        const fresh = await runPreAudit(cleanedRefs)
        if (fresh.audit_status === 'ready' && fresh.bucket !== 'GREEN') {
          setAudit({
            phase: 'open',
            result: fresh,
            staleNotice:
              'Yeni model tahmini alındı, lütfen son kez teyit edip Tamamla\'ya basınız.',
          })
          return
        }
        await finalizeComplete(
          targetCompleted,
          cleanedRefs,
          fresh.prediction_fingerprint
            ? { prediction_fingerprint: fresh.prediction_fingerprint }
            : undefined,
          attempt + 1,
        )
      } catch {
        setAudit({ phase: 'idle' })
        toast.error('Model kontrolü yenilenemedi, lütfen tekrar deneyin.')
      }
      return
    }

    setAudit({ phase: 'idle' })

    let lockReleaseFailed = false
    try {
      await lock.release()
    } catch {
      lockReleaseFailed = true
    }

    await qc.refetchQueries({ queryKey: feedKeys.tab(currentTab) })

    const next = await pickNextInFeedAcrossPages({
      qc,
      currentTab,
      currentDocId: docId,
      sort: currentSort,
    })

    if (lockReleaseFailed) {
      toast.warning('Kilit serbest bırakılamadı; 5 dakika içinde otomatik temizlenir.')
    }
    toast.success(
      targetCompleted
        ? 'Doküman tamamlandı olarak işaretlendi.'
        : 'Tamamlanma işareti geri alındı.',
    )

    if (next.type === 'next') {
      navigate(`/docs/${next.id}`, { replace: true })
    } else {
      navigate('/', { replace: true })
    }
  }

  const handleComplete = async () => {
    const targetCompleted = !isCompleted
    const { list: cleanedRefs, hasDuplicates } = checkAndRemoveDuplicateReferences(
      refsRef.current,
    )
    if (targetCompleted && hasDuplicates) {
      toast.warning('Yinelenen anotasyon silindi.')
      refs.updateAll(cleanedRefs)
      refsRef.current = cleanedRefs
    }

    // Uncomplete reverses a prior commit; there is nothing to audit.
    if (!targetCompleted) {
      await finalizeComplete(false, cleanedRefs, undefined)
      return
    }

    setAudit({ phase: 'running' })
    let result: PreAuditResult
    try {
      result = await runPreAudit(cleanedRefs)
    } catch {
      // The audit is advisory infrastructure — it must never block a submit.
      setAudit({ phase: 'idle' })
      toast.warning('Model kontrolü çalıştırılamadı; kaydınız etkilenmedi.')
      await finalizeComplete(true, cleanedRefs, undefined)
      return
    }

    if (result.audit_status === 'model_unavailable') {
      setModelUnavailableReason(result.reason ?? 'no_prediction')
      setAudit({ phase: 'idle' })
      await finalizeComplete(true, cleanedRefs, undefined)
      return
    }
    setModelUnavailableReason(null)
    const ack = result.prediction_fingerprint
      ? { prediction_fingerprint: result.prediction_fingerprint }
      : undefined
    if (result.bucket === 'GREEN') {
      setAudit({ phase: 'idle' })
      await finalizeComplete(true, cleanedRefs, ack)
      return
    }
    setAudit({ phase: 'open', result, staleNotice: null })
  }
```

Panel yardımcılarını `handleSkip`'ten önce ekle:

```tsx
  const handleCompare = async () => {
    setAudit({ phase: 'running' })
    try {
      const result = await runPreAudit(refsRef.current)
      if (result.audit_status === 'model_unavailable') {
        setModelUnavailableReason(result.reason ?? 'no_prediction')
        setAudit({ phase: 'idle' })
        return
      }
      setModelUnavailableReason(null)
      if (result.bucket === 'GREEN') {
        setAudit({ phase: 'idle' })
        toast.success('Model tahmini ile etiketleriniz uyuşuyor.')
        return
      }
      setAudit({ phase: 'open', result, staleNotice: null })
    } catch {
      setAudit({ phase: 'idle' })
      toast.warning('Model kontrolü çalıştırılamadı.')
    }
  }

  const handleAcceptSuggestion = (discrepancy: AuditDiscrepancy) => {
    const model = discrepancy.model_reference
    if (!model?.source_text) return
    const next: ReferenceItem[] = [
      ...refsRef.current,
      {
        kanun_no: model.kanun_no || null,
        kanun_ad: model.kanun_ad || null,
        madde: model.madde || null,
        fikra: model.fikra || null,
        bent: model.bent || null,
        source_text: model.source_text,
      },
    ]
    // Synchronous write closes the debounce race: a "Tamamla" click in this
    // same tick still commits the accepted suggestion.
    refsRef.current = next
    refs.updateAll(next)
    setAcceptedKeys((prev) => new Set(prev).add(discrepancyKey(discrepancy)))
    toast.success('Model önerisi listenize eklendi.')
  }

  const handleOverride = async () => {
    if (audit.phase !== 'open') return
    const ack = audit.result.prediction_fingerprint
      ? { prediction_fingerprint: audit.result.prediction_fingerprint }
      : undefined
    await finalizeComplete(true, refsRef.current, ack)
  }

  const highlights = useMemo<QuoteTarget[]>(() => {
    if (audit.phase !== 'open') return []
    return audit.result.discrepancies
      .filter((discrepancy) => discrepancy.model_reference?.source_text)
      .map((discrepancy) => ({
        id: discrepancyKey(discrepancy),
        quote: discrepancy.model_reference!.source_text,
        ...(discrepancy.madde && { near: discrepancy.madde }),
      }))
  }, [audit])
```

Ana render bloğunu güncelle:

```tsx
  return (
    <div className="grid h-full grid-cols-[minmax(0,60%)_minmax(0,40%)] overflow-hidden">
      <div className="min-w-0 overflow-hidden border-r border-border">
        <DocViewer docId={docId} highlights={highlights} activeHighlightId={activeHighlightId} />
      </div>
      <div className="min-w-0 overflow-hidden">
        {audit.phase === 'open' ? (
          <QualityAuditPanel
            result={audit.result}
            acceptedKeys={acceptedKeys}
            staleNotice={audit.staleNotice}
            isCompleting={completeMutation.isPending}
            onAccept={handleAcceptSuggestion}
            onHover={setActiveHighlightId}
            onComplete={() => {
              void handleComplete()
            }}
            onOverride={() => {
              void handleOverride()
            }}
            onBackToEdit={() => {
              setAudit({ phase: 'idle' })
              setActiveHighlightId(null)
            }}
          />
        ) : (
          <ReferencePanel
            refs={refs.list}
            docText={docQuery.data?.pdf_text ?? ''}
            onAdd={refs.add}
            onUpdate={refs.update}
            onRemove={refs.remove}
            onSave={() => {
              void handleSave()
            }}
            onSkip={() => {
              void handleSkip()
            }}
            onComplete={() => {
              void handleComplete()
            }}
            onCompare={() => {
              void handleCompare()
            }}
            canEdit={canEdit}
            isSaving={saveMutation.isPending}
            isCompleting={completeMutation.isPending}
            isAuditing={audit.phase === 'running'}
            modelUnavailableReason={modelUnavailableReason}
            error={errorForPanel}
            draftSaveStatus={draft.saveStatus}
            isValid={isValid}
            hasAnnotation={hasAnnotation}
            isCompleted={isCompleted}
          />
        )}
      </div>
    </div>
  )
```

`handleSave` içindeki `checkAndRemoveDuplicateReferences(refs.list)` çağrısını
`checkAndRemoveDuplicateReferences(refsRef.current)` yap (aynı yarış, kaydetme yolu için).

- [ ] **Step 5: Testleri çalıştır (yeni + mevcut AnnotateDoc + ReferencePanel regresyonu)**

```bash
cd /Users/student2/AnnotationPlatform/frontend
npx vitest run src/routes/AnnotateDoc.audit.test.tsx
npx vitest run src/routes/AnnotateDoc.test.tsx \
                src/components/annotation/ReferencePanel.test.tsx
npx tsc --noEmit
npx eslint src
```

Expected: yeni dosyada 9 passed. Mevcut `ReferencePanel.test.tsx` yeni zorunlu propları
(`onCompare`, `isAuditing`) geçirmediği için tip hatası verirse, o testteki render
yardımcısına `onCompare={() => {}} isAuditing={false}` eklenir — testin iddiaları
değişmez.

- [ ] **Step 6: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add frontend/src/routes/AnnotateDoc.tsx frontend/src/routes/AnnotateDoc.audit.test.tsx \
        frontend/src/components/annotation/ReferencePanel.tsx \
        frontend/src/components/annotation/ReferencePanel.test.tsx
git commit -m "feat(frontend): wire pre-submit audit into the annotate flow

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: Playwright uçtan uca akış

**Files:**
- Modify: `/Users/student2/AnnotationPlatform/backend/cli.py` (`cmd_seed_e2e` — tahmin fixture'ı)
- Modify: `/Users/student2/AnnotationPlatform/frontend/e2e/helpers.ts` (yeni export yok, sabit eklenir)
- Create: `/Users/student2/AnnotationPlatform/frontend/e2e/quality-audit.spec.ts`

**Interfaces:**
- Consumes: Task 6 + Task 14 (uçtan uca akış), `E2E_DOC_IDS.alpha` (= `e2e-doc-alpha`).
- Produces: `e2e-doc-alpha` için tohumlanmış G0 tahmini — insanın gireceği referans (193/37) **artı** modelin fazladan bulduğu 213/114 → ilk denetim RED.

- [ ] **Step 1: Seed'e tahmin fixture'ı ekle**

`backend/cli.py` — `cmd_seed_e2e` içinde dokümanlar ingest edildikten **sonra**
(fonksiyonun sonundaki `return 0`'dan önce):

```python
    # Quality-audit fixture: the model agrees with what the e2e test types for
    # GVK 37 and additionally claims VUK 114, so the first audit lands on RED
    # with exactly one actionable model_only discrepancy.
    from backend.quality import service as quality_service
    from backend.quality.dqcheck_core.fingerprints import sha256_text

    alpha_text = docs[0]["pdfText"]
    alpha_prediction = [
        {
            "kanun_no": "193",
            "kanun_ad": "Gelir Vergisi Kanunu",
            "madde": "37",
            "fikra": "",
            "bent": "",
            "source_text": "Kira gelirinin vergilendirilmesi hakkinda ozelge talebi.",
        },
        {
            "kanun_no": "213",
            "kanun_ad": "Vergi Usul Kanunu",
            "madde": "114",
            "fikra": "",
            "bent": "",
            "source_text": "Konuyla ilgili aciklamalar asagida yer almaktadir.",
        },
    ]
    conn = connect(db_path)
    try:
        quality_service.upsert_predictions(
            conn,
            [
                {
                    "document_id": "e2e-doc-alpha",
                    "generation": "G0",
                    "status": "success",
                    "references": alpha_prediction,
                    "truncated": False,
                    "model_fingerprint": "e2e-seed-fingerprint",
                    "text_sha256": sha256_text(alpha_text),
                    "source": "e2e_seed",
                    "operational": {},
                }
            ],
        )
    finally:
        conn.close()
```

> Not: `docs[0]` alpha dokümanıdır; `pdfText` ile `text_sha256` aynı kaynaktan
> türetildiği için tahmin asla "bayat" görünmez.

- [ ] **Step 2: Seed'i çalıştır ve fixture'ı doğrula**

```bash
cd /Users/student2/AnnotationPlatform
DB_PATH=/tmp/anotasyon-e2e-data/db/anotasyon-e2e.db \
  /opt/llm-lab/.venv/bin/python -m backend.cli seed-e2e --reset
/opt/llm-lab/.venv/bin/python - <<'PY'
import sqlite3
conn = sqlite3.connect("/tmp/anotasyon-e2e-data/db/anotasyon-e2e.db")
conn.row_factory = sqlite3.Row
row = conn.execute(
    "SELECT document_id, generation, status, references_json FROM model_predictions"
).fetchone()
print(dict(row))
PY
```

Expected: `e2e-doc-alpha` / `G0` / `success` ve iki referanslı JSON basılır.

- [ ] **Step 3: E2E spec'i yaz**

```ts
import { expect, test } from '@playwright/test'

import { E2E_DOC_IDS, loginAs } from './helpers'

const HUMAN_QUOTE = 'Kira gelirinin vergilendirilmesi hakkinda ozelge talebi.'

test.describe('Pre-submit quality audit', () => {
  test('RED audit → accept the model suggestion → complete', async ({ page }) => {
    await loginAs(page, 'alice')
    await page.goto(`/docs/${E2E_DOC_IDS.alpha}`)

    // Enter the human's single reference: GVK 37 with the model's own quote,
    // so the only disagreement left is the model's extra VUK 114.
    await page.getByRole('button', { name: 'Yeni Referans' }).click()
    await page.getByLabel(/kanun no/i).first().fill('193')
    await page.getByLabel(/^madde/i).first().fill('37')
    await page.getByLabel(/metinden alıntı/i).first().fill(HUMAN_QUOTE)

    const [auditResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/annotations/${E2E_DOC_IDS.alpha}/pre-audit`)
          && response.request().method() === 'POST',
      ),
      page.getByRole('button', { name: /tamamlandı işaretle/i }).click(),
    ])
    expect(auditResponse.ok()).toBeTruthy()
    expect((await auditResponse.json()).bucket).toBe('RED')

    // The audit panel takes over the right pane; the document stays visible.
    await expect(page.getByText('Model Karşılaştırma & Kalite Denetimi')).toBeVisible()
    await expect(page.getByText(/Model yanılıyor olabilir/)).toBeVisible()
    await expect(page.getByText('Model buldu, sizde yok')).toBeVisible()

    // The claimed quote is marked in the document body.
    await expect(
      page.locator('mark', { hasText: 'Konuyla ilgili aciklamalar' }),
    ).toBeVisible()

    await page.getByRole('button', { name: 'Model Önerisini Listeme Ekle' }).click()
    await expect(page.getByRole('button', { name: 'Eklendi' })).toBeDisabled()

    const [completeResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/annotations/${E2E_DOC_IDS.alpha}/complete`)
          && response.request().method() === 'POST',
      ),
      page.getByRole('button', { name: 'Tamamla' }).click(),
    ])
    expect(completeResponse.ok()).toBeTruthy()
  })

  test('override keeps the human labels and still completes', async ({ page }) => {
    await loginAs(page, 'bob')
    await page.goto(`/docs/${E2E_DOC_IDS.alpha}`)

    await page.getByRole('button', { name: 'Yeni Referans' }).click()
    await page.getByLabel(/kanun no/i).first().fill('193')
    await page.getByLabel(/^madde/i).first().fill('37')
    await page.getByLabel(/metinden alıntı/i).first().fill(HUMAN_QUOTE)

    await page.getByRole('button', { name: /tamamlandı işaretle/i }).click()
    await expect(page.getByText('Model Karşılaştırma & Kalite Denetimi')).toBeVisible()

    const [completeResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/annotations/${E2E_DOC_IDS.alpha}/complete`)
          && response.request().method() === 'POST',
      ),
      page.getByRole('button', { name: 'Benim Etiketim Doğru, Yine de Tamamla' }).click(),
    ])
    expect(completeResponse.ok()).toBeTruthy()
  })
})
```

- [ ] **Step 4: E2E'yi çalıştır**

```bash
cd /Users/student2/AnnotationPlatform/frontend
npx playwright test e2e/quality-audit.spec.ts --reporter=line
```

Expected: 2 passed. Etiket seçicileri (`getByLabel`) `ReferenceCard.tsx`'teki
gerçek etiketlerle uyuşmuyorsa, o dosyadaki `<Label>` metinlerine göre düzeltilir —
spec'in iddiaları değişmez.

- [ ] **Step 5: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add backend/cli.py frontend/e2e/quality-audit.spec.ts
git commit -m "test(e2e): cover the pre-submit audit accept and override paths

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# FAZ 5 — Yeniden eğitim export'u ve operasyon

## Task 16: `export_verified_corpus.py`

**Files:**
- Create: `/Users/student2/AnnotationPlatform/scripts/export_verified_corpus.py`
- Test: `/Users/student2/AnnotationPlatform/tests/test_export_verified_corpus.py`

**Interfaces:**
- Consumes: `annotations`, `annotation_audit_logs`, `documents_meta`; vendored `fingerprints.{directory_manifest, manifest_fingerprint, sha256_file}`.
- Produces: `export_corpus(db, out_dir, *, generated_at, force=False) -> dict`, `main(argv=None) -> int`.

- [ ] **Step 1: Testi yaz**

```python
"""Verified-corpus export: selection rule, deterministic ids, stable manifest."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from export_verified_corpus import export_corpus  # noqa: E402

DOC_TEXT = "Vergi Usul Kanunu'nun 114 uncu maddesi."
REFERENCE = {
    "kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
    "fikra": None, "bent": None, "source_text": "114 uncu maddesi",
}
STAMP = "2026-08-18T00:00:00+00:00"


@pytest.fixture
def db(client, ingest_doc):
    from backend import config
    from backend.shared.db import connect

    for document_id in ("d-beta", "d-alpha", "d-plain", "d-open"):
        ingest_doc(document_id, pdfText=DOC_TEXT)
    conn = connect(config.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def _complete(conn, document_id, *, audited=True, decision="human_override", users=1):
    conn.execute(
        """INSERT INTO annotations(document_id, references_json, is_completed,
             last_editor_user_id, completed_by_user_id, edit_count,
             unique_users_count, created_at, updated_at)
           VALUES (?, ?, 1, NULL, NULL, 1, ?, ?, ?)""",
        (document_id, json.dumps([REFERENCE]), users, STAMP, STAMP),
    )
    if audited:
        conn.execute(
            """INSERT INTO annotation_audit_logs(document_id, user_id, bucket,
                 decision, reasons_json, similarity, model_only_json,
                 human_only_json, prediction_fingerprint, policy_id,
                 model_generation, created_at)
               VALUES (?, NULL, 'RED', ?, '["missing_core_reference"]', 0.5,
                       '[]', '[]', 'fp-1', 'ignore_vuk_213_article_413_v1',
                       'G0', ?)""",
            (document_id, decision, STAMP),
        )


def test_only_completed_and_audited_documents_are_exported(db, tmp_path):
    _complete(db, "d-beta")
    _complete(db, "d-alpha")
    _complete(db, "d-plain", audited=False)          # completed, never audited
    db.execute(
        """INSERT INTO annotations(document_id, references_json, is_completed,
             edit_count, unique_users_count, created_at, updated_at)
           VALUES ('d-open', '[]', 0, 1, 1, ?, ?)""",
        (STAMP, STAMP),
    )

    out = tmp_path / "gt_v4"
    summary = export_corpus(db, out, generated_at=STAMP)

    assert summary["count"] == 2
    assert sorted(p.name for p in (out / "validated").glob("doc_*.json")) == [
        "doc_1.json", "doc_2.json",
    ]
    # Deterministic ids: sorted by document_id, so d-alpha is 1 and d-beta is 2.
    assert json.loads((out / "id_map.json").read_text(encoding="utf-8")) == {
        "d-alpha": 1, "d-beta": 2,
    }


def test_exported_document_carries_text_references_and_provenance(db, tmp_path):
    _complete(db, "d-alpha")
    out = tmp_path / "gt_v4"
    export_corpus(db, out, generated_at=STAMP)
    payload = json.loads((out / "validated" / "doc_1.json").read_text(encoding="utf-8"))
    assert payload["doc_id"] == 1
    assert payload["source_document_id"] == "d-alpha"
    assert payload["text"] == DOC_TEXT
    assert payload["references"] == [REFERENCE]


def test_sidecar_carries_the_latest_audit_row(db, tmp_path):
    _complete(db, "d-alpha", decision="human_override", users=2)
    db.execute(
        """INSERT INTO annotation_audit_logs(document_id, user_id, bucket,
             decision, reasons_json, similarity, model_only_json, human_only_json,
             prediction_fingerprint, policy_id, model_generation, created_at)
           VALUES ('d-alpha', NULL, 'GREEN', 'accepted_model', '[]', 1.0, '[]', '[]',
                   'fp-2', 'ignore_vuk_213_article_413_v1', 'G0', ?)""",
        (STAMP,),
    )
    out = tmp_path / "gt_v4"
    export_corpus(db, out, generated_at=STAMP)
    (line,) = (out / "audit_sidecar.jsonl").read_text(encoding="utf-8").splitlines()
    row = json.loads(line)
    assert row == {
        "doc_id": 1,
        "source_document_id": "d-alpha",
        "bucket": "GREEN",
        "decision": "accepted_model",
        "reasons": [],
        "similarity": 1.0,
        "prediction_fingerprint": "fp-2",
        "policy_id": "ignore_vuk_213_article_413_v1",
        "model_generation": "G0",
        "unique_users_count": 2,
        "audit_at": STAMP,
    }


def test_manifest_fingerprint_is_stable_across_identical_runs(db, tmp_path):
    _complete(db, "d-alpha")
    first = export_corpus(db, tmp_path / "a", generated_at=STAMP)
    second = export_corpus(db, tmp_path / "b", generated_at="2027-01-01T00:00:00+00:00")
    assert first["manifest_fingerprint"] == second["manifest_fingerprint"]


def test_refuses_to_overwrite_a_non_empty_directory_without_force(db, tmp_path):
    _complete(db, "d-alpha")
    out = tmp_path / "gt_v4"
    export_corpus(db, out, generated_at=STAMP)
    with pytest.raises(SystemExit):
        export_corpus(db, out, generated_at=STAMP)
    summary = export_corpus(db, out, generated_at=STAMP, force=True)
    assert summary["count"] == 1
```

- [ ] **Step 2: Testin başarısız olduğunu doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_export_verified_corpus.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'export_verified_corpus'`

- [ ] **Step 3: Script'i yaz**

```python
#!/usr/bin/env python3
"""Export platform-verified annotations as a NEW ground-truth generation.

DQCheck's canonical corpus is sealed: `g0.validate_canonical_sources` demands
exactly 500 doc_*.json files whose directory manifest matches a pinned sha256
(`constants.CANONICAL_GT_MANIFEST_SHA256`), plus a seed-42 394/50/50 split
manifest. Appending platform data to that directory would break the published
reproducibility claim, so this script writes a separate generation directory.
Teaching `train-g0` to consume it is a deliberate, later decision.

Selection rule (design spec, decision 13): every document that is completed AND
has at least one audit row. Human labels are the ground truth — GREEN,
accepted_model and human_override all qualify, because the documents where the
model was wrong are exactly the ones worth learning from. Narrower filters stay
possible afterwards: bucket, decision and unique_users_count all travel in the
sidecar.

Usage:
    /opt/llm-lab/.venv/bin/python scripts/export_verified_corpus.py \
        --out /Users/student2/data-quality-checker/data/ground_truth/gt_v4_platform_2026-08-18
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import config  # noqa: E402
from backend.quality.dqcheck_core.fingerprints import (  # noqa: E402
    directory_manifest,
    manifest_fingerprint,
)
from backend.shared.db import connect  # noqa: E402

SCHEMA_VERSION = 1

_SELECT_DOCUMENTS = """
    SELECT a.document_id, a.references_json, a.unique_users_count, d.pdf_text
    FROM annotations a
    JOIN documents_meta d ON d.document_id = a.document_id
    WHERE a.is_completed = 1
      AND EXISTS (
          SELECT 1 FROM annotation_audit_logs l
          WHERE l.document_id = a.document_id
      )
    ORDER BY a.document_id ASC
"""

_SELECT_LATEST_AUDIT = """
    SELECT bucket, decision, reasons_json, similarity, prediction_fingerprint,
           policy_id, model_generation, created_at
    FROM annotation_audit_logs
    WHERE document_id = ?
    ORDER BY id DESC
    LIMIT 1
"""


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def export_corpus(
    db: sqlite3.Connection,
    out_dir: Path,
    *,
    generated_at: str,
    force: bool = False,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    validated_dir = out_dir / "validated"
    if validated_dir.exists() and any(validated_dir.iterdir()) and not force:
        raise SystemExit(
            f"{validated_dir} already contains an export; pass --force to replace it"
        )
    validated_dir.mkdir(parents=True, exist_ok=True)
    for stale in validated_dir.glob("doc_*.json"):
        stale.unlink()

    rows = db.execute(_SELECT_DOCUMENTS).fetchall()
    id_map: dict[str, int] = {}
    sidecar_lines: list[str] = []
    for doc_id, row in enumerate(rows, start=1):
        document_id = row["document_id"]
        id_map[document_id] = doc_id
        _write_json(
            validated_dir / f"doc_{doc_id}.json",
            {
                "doc_id": doc_id,
                "source_document_id": document_id,
                "text": row["pdf_text"],
                "references": json.loads(row["references_json"]),
            },
        )
        audit = db.execute(_SELECT_LATEST_AUDIT, (document_id,)).fetchone()
        sidecar_lines.append(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "source_document_id": document_id,
                    "bucket": audit["bucket"],
                    "decision": audit["decision"],
                    "reasons": json.loads(audit["reasons_json"]),
                    "similarity": audit["similarity"],
                    "prediction_fingerprint": audit["prediction_fingerprint"],
                    "policy_id": audit["policy_id"],
                    "model_generation": audit["model_generation"],
                    "unique_users_count": row["unique_users_count"],
                    "audit_at": audit["created_at"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    _write_json(out_dir / "id_map.json", id_map)
    (out_dir / "audit_sidecar.jsonl").write_text(
        "".join(f"{line}\n" for line in sidecar_lines), encoding="utf-8"
    )

    manifest_rows = directory_manifest(
        sorted(validated_dir.glob("doc_*.json")), root=out_dir
    )
    # The fingerprint covers file contents only — never `generated_at` — so two
    # exports of the same data are provably identical.
    fingerprint = manifest_fingerprint(manifest_rows)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "count": len(rows),
        "files": manifest_rows,
        "manifest_fingerprint": fingerprint,
    }
    _write_json(out_dir / "manifest.json", summary)
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    db = connect(args.db)
    try:
        summary = export_corpus(
            db,
            args.out,
            generated_at=datetime.now(timezone.utc).isoformat(),
            force=args.force,
        )
    finally:
        db.close()
    print(
        json.dumps(
            {
                "out": str(args.out),
                "count": summary["count"],
                "manifest_fingerprint": summary["manifest_fingerprint"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Testin geçtiğini doğrula**

```bash
cd /Users/student2/AnnotationPlatform
/opt/llm-lab/.venv/bin/python -m pytest tests/test_export_verified_corpus.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add scripts/export_verified_corpus.py tests/test_export_verified_corpus.py
git commit -m "feat(scripts): export verified corpus as a separate GT generation

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: Operasyon dokümanı — HF Space secret'ı ve ajan runbook'u

**Files:**
- Modify: `/Users/student2/AnnotationPlatform/docs/deployment.md`
- Create: `/Users/student2/AnnotationPlatform/docs/quality-audit-operations.md`

**Interfaces:**
- Consumes: Task 7 (`DQCHECK_INGEST_TOKEN`), Task 9 (`dqcheck predict-agent`), Task 16 (export).
- Produces: operatör runbook'u; kod yüzeyi değişmez.

- [ ] **Step 1: `docs/deployment.md` ortam değişkeni tablosuna satır ekle**

`DISABLE_SPA_MOUNT` satırının altına:

```markdown
| `DQCHECK_INGEST_TOKEN` | no | recommended | `<64 hex chars>` | Shared secret for `/api/internal/predictions*`. Empty → those endpoints answer 503 and the quality audit degrades to "model kontrolü yapılamadı" without blocking annotators. On Hugging Face Spaces set it as a **Space secret**, not in the Dockerfile. |
```

- [ ] **Step 2: `docs/quality-audit-operations.md`'yi yaz**

```markdown
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

Bu dizin DQC'nin **mühürlü** `gt_v3_triangulated_2026-05-15` korpusuna dokunmaz;
`train-g0`'ın yeni nesli kabul etmesi ayrı bir iştir (bkz. tasarım dokümanı
"Kapsam dışı").
```

- [ ] **Step 3: Commit**

```bash
cd /Users/student2/AnnotationPlatform
git add docs/deployment.md docs/quality-audit-operations.md
git commit -m "docs: add quality audit operations runbook

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# Doğrulama matrisi

Faz sonlarında koşulacak tam doğrulama:

```bash
# AP backend
cd /Users/student2/AnnotationPlatform
DQCHECK_UPSTREAM_PATH=/Users/student2/data-quality-checker \
  /opt/llm-lab/.venv/bin/python -m pytest tests/ -q -m "not docker"

# AP frontend
cd frontend
npx tsc --noEmit && npx eslint src && npx vitest run

# AP e2e (seed önce)
cd /Users/student2/AnnotationPlatform
DB_PATH=/tmp/anotasyon-e2e-data/db/anotasyon-e2e.db /opt/llm-lab/.venv/bin/python -m backend.cli seed-e2e --reset
cd frontend && npx playwright test e2e/quality-audit.spec.ts --reporter=line

# DQC
cd /Users/student2/data-quality-checker
/opt/llm-lab/.venv/bin/python -m pytest tests/ -q -m "not compute"
/opt/llm-lab/.venv/bin/ruff check src/data_quality_checker
```

Sözleşme ↔ görev izlenebilirliği:

| Tasarım kararı | Görev | Doğrulayan test |
|----------------|-------|-----------------|
| 1 — vendored çekirdek | 1, 2 | `test_dqcheck_parity.py`, `test_dqcheck_adapter.py` |
| 2 — `model_predictions` önbelleği | 3, 4 | `test_quality_audit_migration.py`, `test_quality_service.py` |
| 3 — Mac→Space push | 7, 9 | `test_predictions_ingest.py`, `test_predict_agent.py` |
| 4 — ajan `pdf_text` okur | 7, 9 | `test_predictions_ingest.py::test_pending_lists_documents_without_predictions`, `test_predict_agent.py::test_successful_batch_posts_the_ingest_payload` |
| 5 — backup dahil / mirror hariç | 3 | `test_quality_audit_migration.py::test_audit_logs_are_mirrored_but_predictions_are_not` |
| 6 — `model_unavailable` sözleşmesi | 4, 5, 14 | `test_quality_service.py`, `test_pre_audit_endpoint.py`, `AnnotateDoc.audit.test.tsx` |
| 7 — sunucu yeniden hesaplar + ack | 6 | `test_complete_audit_ack.py` |
| 8 — audit log aynı transaction'da | 6 | `test_complete_audit_ack.py::test_red_complete_without_ack_is_rejected_with_audit_required` |
| 9 — öneri kabulü kayıt üretmez | 8, 14 | `test_behavioral_audit_isolation.py`, `AnnotateDoc.audit.test.tsx` |
| 10 — highlight sözleşmesi | 11, 12 | `quoteMatcher.test.ts`, `DocViewer.highlight.test.tsx` |
| 11 — sağ panel kabuğu | 13, 14 | `QualityAuditPanel.test.tsx`, `quality-audit.spec.ts` |
| 12 — sabit politika + kanıt sorgusu | 2, 4, 17 | `test_dqcheck_adapter.py::test_case_9...`, `test_quality_service.py::test_decision_log_row_is_queryable_with_json_each` |
| 13 — ayrı nesil export | 16 | `test_export_verified_corpus.py` |
| 14 — char_limit muafiyeti | 8 | `test_behavioral_audit_isolation.py` |
| 15 — tetikleme noktaları | 14 | `AnnotateDoc.audit.test.tsx::lets the user compare on demand...` |
| Kural 1 — `audit_stale` yumuşak kurtarma | 14 | `AnnotateDoc.audit.test.tsx::recovers softly from 409 audit_stale...` |
| Kural 2 — debounce yarışı | 14 | `AnnotateDoc.audit.test.tsx::accepting a suggestion and immediately completing...` |
| Kural 3 — çoklu eşleşme | 11 | `quoteMatcher.test.ts::prefers the occurrence nearest the madde hint...` |
| Kural 4 — token parse/karşılaştırma | 7 | `test_predictions_ingest.py::test_bearer_parsing_never_raises` |
| Kural 5 — kanonik tuple formatı | 2, 4 | `test_dqcheck_adapter.py::test_canonical_tuple_shape_is_json_each_friendly` |

# Bilinen sınırlar (bilinçli)

- Canlı MLX inference yok: HF donanımı MLX çalıştırmaz, tahminler daima önbellekten okunur.
- `reference_policy` v2 madde seti bu turda yazılmaz; kanıt sorgusu (Task 17) veriyi toplar.
- `train-g0` v4 neslini kabul etmez; export artefaktı üretir, adaptasyon ayrı iştir.
- `model_predictions` Neon mirror'da yoktur; Space sıfırlanırsa GitHub snapshot + ajan doldurur.
- Denetim kararları için admin panel raporu yoktur; SQL sorguları runbook'ta.
- Manuel "Model ile karşılaştır" audit satırı yazmaz — yalnızca commit kararları zincire girer.
