# Annotation Quality Report Harness

Bu klasor, bursiyer anotasyon kalite analizini daha kucuk bir LLM modeline devretmek icin hazirlanmis karar-tamam harness'tir. Modelin tek basina buyuk resmi yorumlamasini bekleme; dosyalari sirasiyla okut, her work package bittiginde ciktilari kontrol et.

## Goal

Canli Neon mirror verisini kullanarak bursiyerlerin anotasyonlarini incelemek, sik yapilan hatalari ve karistirilan nuanslari kanitli orneklerle cikarmak, isimli kisi bazli degerlendirme yapmak ve hocaya gonderilecek Turkce PDF raporu uretmek.

## Entrypoint Order

1. `00-operator-protocol.md`
2. `01-context/repo-facts.md`
3. `01-context/research-notes.md`
4. `02-contracts/data-contract.md`
5. `02-contracts/quality-rubric.md`
6. `03-work-packages/WP00-environment-and-snapshot.md`
7. `03-work-packages/WP01-baseline-metrics.md`
8. `03-work-packages/WP02-rule-compliance.md`
9. `03-work-packages/WP03-law-article-analysis.md`
10. `03-work-packages/WP04-version-chain-attribution.md`
11. `03-work-packages/WP05-common-document-agreement.md`
12. `03-work-packages/WP06-person-profiles.md`
13. `03-work-packages/WP07-report-draft.md`
14. `03-work-packages/WP08-pdf-production.md`
15. `06-qa/acceptance-gates.md`

## Directory Contract

Runtime artifacts must not be mixed into this harness. The implementer should create:

```text
analysis/annotation_quality/<run_id>/
  snapshot/
  intermediate/
  findings/
  figures/
  report/
  logs/

output/pdf/
  bursiyer-anotasyon-kalite-raporu-<run_id>.pdf
```

`run_id` must be UTC `YYYYMMDD-HHMM`.

## Small LLM Rules

- Work one work package at a time.
- Do not invent metrics if a query fails. Write `BLOCKED` with the failing command and error.
- Never join `activity_events` or `behavioral_events` directly to `annotation_versions` without pre-aggregating by user. That multiplies counts.
- Do not use current `annotation_references` for user attribution. Use `annotation_versions` snapshots and diffs.
- Do not mark a finding as a person error unless there is evidence: user, document id, version id or timestamp, field, value, rule violated.
- Separate `confirmed_error`, `probable_issue`, `interpretation_difference`, and `system_normalization`.

## Useful Support Files

- SQL templates: `04-sql/query-library.md`
- Report outline: `05-report/report-outline.md`
- Small model prompt: `prompts/small-llm-system-prompt.md`
- Per-task prompt template: `prompts/work-package-prompt-template.md`
- Run status + pipeline choice: `STATUS.md`

## Alternative pipeline (plain-language performance)

For a düz Türkçe team-performance summary (not rule-level evidence), use
`analysis/annotation_quality/plain_language_report.py` instead of WP00–WP08.
See `STATUS.md` for completed runs and PDF naming (`bursiyer-anotasyon-performans-raporu-<run_id>.pdf`).

