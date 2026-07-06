# Harness Status

Last updated: 2026-07-07

## Summary

The annotation-quality harness (WP00–WP08) has been executed twice. A separate
**plain-language performance pipeline** (`plain_language_report.py`) produced a
third, operator-facing report. Use this file to pick the right pipeline and
avoid obsolete artifacts.

## Completed runs

| Run ID | Pipeline | Status | PDF | Notes |
|--------|----------|--------|-----|-------|
| `20260627-1653` | Full harness | **OBSOLETE** | do not use | R07 false positives; see `OBSOLETE_DO_NOT_USE.md` |
| `20260627-1827` | Full harness | **Valid** | `bursiyer-anotasyon-kalite-raporu-20260627-1827.pdf` | Corrected R07 gates; passed `validate_run.py` |
| `20260705-1254` | Plain-language | **Valid** | `bursiyer-anotasyon-performans-raporu-20260705-1254.pdf` | Team performance summary; 6 Jun–3 Jul 2026 scope |

## Two pipelines

### 1. Full harness (WP00–WP08)

For deep rule-compliance analysis, version-chain attribution, common-document
agreement, and evidence-backed person profiles.

**Entry:** `docs/annotation-quality-harness/README.md` → WP00 through WP08.

**Support scripts** (run against a completed `<run_id>` directory):

```bash
python3 analysis/annotation_quality/rebuild_aux_artifacts.py analysis/annotation_quality/<run_id>
python3 analysis/annotation_quality/validate_run.py analysis/annotation_quality/<run_id>
python3 analysis/annotation_quality/render_report_pdf.py analysis/annotation_quality/<run_id>
```

**Output naming:** `bursiyer-anotasyon-kalite-raporu-<run_id>.pdf`

### 2. Plain-language performance report

For hocaya/ekip liderine gönderilecek düz Türkçe performans özeti. Does not
replace the full harness when you need per-rule evidence.

```bash
python3 analysis/annotation_quality/plain_language_report.py \
  --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

**Output naming:** `bursiyer-anotasyon-performans-raporu-<run_id>.pdf`

Requires live Postgres (`NEON_MIRROR_URL`). Writes under
`analysis/annotation_quality/<run_id>/` and copies PDF to `output/pdf/`.

## History

- 2026-06-27: Initial harness for smaller LLM implementation.
- 2026-06-27: Added R07 normalization gates after audit found a false-positive
  bug in a small-model output (`20260627-1653` invalidated).
- 2026-06-27: Corrected run `20260627-1827` passed QA.
- 2026-07-05: Plain-language performance pipeline shipped (`20260705-1254`).

## Next operator actions

When starting a **new full-harness** run:

1. Assign `WP00-environment-and-snapshot.md` to the implementer.
2. Create `analysis/annotation_quality/<run_id>/` with UTC `YYYYMMDD-HHMM`.
3. Run `validate_run.py` before PDF production.

When starting a **new performance** run:

1. Confirm date range with the report recipient.
2. Run `plain_language_report.py` with `--start-date` / `--end-date`.
3. Check `report/pdf_render_check.md` inside the run directory.

## Open operator decisions

- Confirm whether final source is live Neon only or whether local SQLite may be
  accepted if Neon is unavailable.
- Confirm whether admin/test accounts should appear in appendix.
- Confirm report date range if the full database history is not desired.
