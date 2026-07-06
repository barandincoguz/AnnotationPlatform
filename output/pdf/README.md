# PDF Outputs

Generated bursiyer reports land here. Two pipelines produce different report
types — pick the file that matches your audience.

## Current reports (use these)

| File | Pipeline | Audience | Run |
|------|----------|----------|-----|
| `bursiyer-anotasyon-performans-raporu-20260705-1254.pdf` | **Plain-language** (`plain_language_report.py`) | Hoca / ekip lideri — performans özeti, düz Türkçe | `20260705-1254` |
| `bursiyer-anotasyon-kalite-raporu-20260627-1827.pdf` | **Full harness** (WP00–WP08) | Detaylı kural uyumu + kanıtlı bulgular | `20260627-1827` |

**Default recommendation:** send the **20260705-1254 performans** PDF for
periodic team reviews; use the **20260627-1827 kalite** PDF when you need
rule-level evidence and per-person finding attribution.

## Obsolete — do not use

| File / run | Reason |
|------------|--------|
| `bursiyer-anotasyon-kalite-raporu-20260627-1653.pdf` (if present) | Failed QA: R07 law number/name mismatch false positives; inconsistent per-user counts |
| `analysis/annotation_quality/20260627-1653/` | Marked `OBSOLETE_DO_NOT_USE.md` — same root cause |

## Regenerating

### Plain-language performance report

```bash
# Requires NEON_MIRROR_URL (or equivalent live Postgres) in environment
python3 analysis/annotation_quality/plain_language_report.py \
  --start-date 2026-06-06 --end-date 2026-07-03
```

Output: `analysis/annotation_quality/<run_id>/` + PDF in this directory.

### Full quality harness

Follow `docs/annotation-quality-harness/00-operator-protocol.md` through
WP08, then:

```bash
python3 analysis/annotation_quality/validate_run.py analysis/annotation_quality/<run_id>
python3 analysis/annotation_quality/render_report_pdf.py analysis/annotation_quality/<run_id>
```

See `docs/annotation-quality-harness/STATUS.md` for run history and operator
decisions still open.
