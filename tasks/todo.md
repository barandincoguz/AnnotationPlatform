# Backup Hardening Todo

## Plan

- [x] Confirm workspace is writable after ownership fix.
- [x] Add regression tests for backup git command failures:
  - `git add`, `git commit`, and `git rev-parse` failures must raise `GitRemoteError`.
  - No raw PAT may appear in raised messages.
- [x] Add regression test proving backup remote config does not persist the PAT in `.git/config`.
- [x] Add regression test proving an existing backup repo refreshes `origin` when `BACKUP_REPO_URL` or `GITHUB_PAT` changes.
- [x] Add regression test proving production config warns when `BACKUP_REPO_URL` is set but `GITHUB_PAT` is missing.
- [x] Add regression test proving concurrent backup cycles are serialized.
- [x] Implement minimal backup hardening:
  - Check every git subprocess return code that affects correctness.
  - Use a non-secret remote URL in `.git/config`.
  - Pass PAT only at push/clone time where needed.
  - Refresh existing `origin` remote safely.
  - Serialize backup cycles with a process-local lock.
  - Improve production warning for partial backup config.
- [x] Run focused backup and production-enforcement tests.
- [x] Run local bare-repo smoke test for snapshot commit/push without leaking PAT into `.git/config`.
- [x] Review diff for unintended changes.
- [ ] Deploy only after verification passes.

## Review

- Backup hardening tests: `84 passed` for backup/prod-enforcement focused suite.
- Backend suite: `1142 passed, 5 deselected` with `pytest tests backend/tests -q -m 'not docker'`.
- Frontend: `npm run typecheck`, `npm run lint`, and CI-style `npx vitest run --pool=threads --poolOptions.threads.minThreads=1 --poolOptions.threads.maxThreads=2` passed.
- Smoke: local bare git remote received an `auto-backup` commit; `backup/.git/config` kept a PAT-free origin URL.
- Deploy is not executed yet because this local environment has no `docker` command, no `hf` CLI, no app deploy workflow, and no production env/backup secrets loaded.
