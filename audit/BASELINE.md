# Wave 0 Baseline — 2026-05-23

| Metric | Value |
|--------|-------|
| Backend pytest passing | 946 |
| Backend pytest skipped | 3 |
| Frontend vitest passing | 477 |
| TypeScript errors | 0 |
| ESLint errors/warnings | 0 / 0 |
| Ruff errors | 65 (21 auto-fixable; 29 more with --unsafe-fixes) |
| mypy in toolchain | NO |
| Docker image build time | 31s |
| Docker image size | 89.3 MB (93,642,123 bytes) |
| Cold-boot to /api/health 200 | 1s |
| Mirror queue depth at boot | 0 |
| Phase 4 latency baseline (from `4-SUMMARY.md`) | wrk ≤0.02 ms p95 delta over `/api/health` |

## Deviations from expected (Wave 1 audit candidates)

### DEVIATION-1: Frontend vitest — 34 tests failing (7 test files)
- Expected: all tests passing
- Observed: 34 failed | 477 passed (511 total) across 7 failed | 89 passed (96 files)
- Failing test files: `src/App.test.tsx`, `src/hooks/useDraft.test.tsx`, `src/hooks/useLock.test.tsx`, `src/routes/AnnotateDoc.test.tsx`, plus additional files (20 unique test cases listed in run output)
- Action: Wave 1 audit candidate

### DEVIATION-2: Ruff — 65 lint errors
- Expected: 0
- Observed: 65 errors (F841, E402, and others); 21 auto-fixable with `ruff check --fix`, 29 more with `--unsafe-fixes`
- Action: Wave 1 audit candidate

### DEVIATION-3: backend/tests/ suite — 2 failures (separate from main suite)
- Expected (per task spec): main suite at `tests/` → 946 passed, 3 skipped ✓
- Additional: `backend/tests/test_prod_enforcement.py` has 2 failures due to missing `ALLOWED_ORIGINS` env var in test environment
- Files: `test_prod_accepts_strong_secret`, `test_prod_warns_no_backup_url`
- Action: Wave 1 audit candidate (test env config gap)

### DEVIATION-4: mypy not in toolchain
- Expected: possibly YES (task asked to record for downstream gate)
- Observed: `which mypy` → not found; not referenced in `requirements-dev.txt` or `pyproject.toml`
- Action: Wave 1 audit candidate (static type checking gap)

Recorded by: Phase 5 Wave 0 baseline task.
