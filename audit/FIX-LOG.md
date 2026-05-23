# FIX-LOG — Phase 5 Pre-flight Hardening

| Finding ID | Sev  | Commit SHA | One-line summary |
|------------|------|------------|------------------|
| FE-1       | High | 79d7295    | Switch vitest env jsdom→happy-dom; 34 AbortSignal cross-realm failures fixed; suite 477→511 passed |
| SEC-1      | High | a8b7ceb    | psycopg.sql.Identifier composables in NeonClient — replaces f-string identifier interpolation |
| BE-1+BE-2  | High | 43ac272    | locks heartbeat + sweep_expired now wrap read-then-write in BEGIN IMMEDIATE |
| BE-3       | High | 350bc5b    | save_annotation + set_complete re-verify lock ownership inside BEGIN IMMEDIATE; 4 new TOCTOU tests |
| BE-4       | High | 0acc20a    | submit_quiz + submit_annotation wrap read-modify-write of annotation_details_json in BEGIN IMMEDIATE; finalize_if_complete joins outer txn via in_txn param; 3 new concurrency tests |
| BE-5+BE-6  | High | 7c168b4    | demote_admin + disable_user re-check count_active_admins inside BEGIN IMMEDIATE; rotate_invite_code wraps deactivate+insert in BEGIN IMMEDIATE; 5 new tests |
| B-01       | High | 43b27f3    | Replace _count_unique_users() COUNT(DISTINCT) scan with EXISTS check + increment-by-1; new idx_ver_doc_user migration; 4 tests |
| B-02       | High | 6240327    | PID-file singleton guard for dispatcher: refuse start if existing PID alive, take over stale PID, emit system_events row on refusal; release on stop(); 5 tests |
| U1         | High | 7991d3f    | POST /api/admin/backup/restore: upload snapshot JSON, WAL-busy 409 refusal, admin audit row (admin_user_id=NULL post-restore, trace_id attribution), python-multipart added to requirements; 4 tests |
| U4         | High | ac22ceb    | /admin/mirror admin page with 10s refresh + threshold colors (warn ≥ 1000, critical ≥ 10000); 4 tests |
| U5         | High | 10de755    | /admin/backup admin page with run-now button + last-20-backup-event history; event_type_prefix query param added to /api/admin/system-events; 3 tests |
| U6         | High | 859d784    | /admin/retention page with preview + confirm-modal-gated run-now; 4 tests |
| BE-10      | Med  | e31d124    | POST /api/admin/mirror/dead-letter/requeue + UI button on /admin/mirror; BEGIN IMMEDIATE reset, rowcount returned, audit row, confirm-modal-gated; 3 backend + 3 frontend tests |
| DR1+DR2+DR3| Doc  | edcec56    | README scrypt→bcrypt(rounds=12) ×3 + 90s→300s ×3; REQUIREMENTS.md MIRROR-01..10 Pending→Complete with commit SHAs |
| DC1 + lint | Dead | a875319    | Delete orphan frontend/src/lib/env.ts (zero importers) + fix 10 eslint errors in U4/U5/U6 (require-await, react/no-unescaped-entities) |
| DC2+DC3    | Dead | (n/a)      | No action: `user_badges` + `user_quiz_answers` do NOT exist in current DB, migrations, or source. Audit hallucinated their presence (referenced as "created in v0001" but v0001_initial_schema.py contains neither). Live DB has 24 tables; orphan tables 0. Verified 2026-05-23 via `sqlite3 ... SELECT name FROM sqlite_master` + `grep` across `backend/` + migrations. |
| W3-T1      | Doc  | a6b6d84    | runbooks/restore-drill.md — copy-only drill with 2 STOP gates; references U1 POST /api/admin/backup/restore route |
| W3-T2      | Doc  | 461a021    | docs/deployment.md refresh: Phase 5 admin surfaces section + Hetzner CPX11 + Oracle A1.Flex ARM appendices + link to runbooks/restore-drill.md |
| W3-T3      | Ops  | 6e2bc73    | .github/workflows/ci.yml — 3 jobs (backend ruff+pytest, frontend tsc+eslint+vitest, docker build smoke); validation PR on personal remote at https://github.com/barandincoguz/AnnotationPlatform/pull/1 |
