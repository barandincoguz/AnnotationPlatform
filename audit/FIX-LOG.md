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
| U4         | High | TBD        | /admin/mirror admin page with 10s refresh + threshold colors (warn ≥ 1000, critical ≥ 10000); 4 tests |
