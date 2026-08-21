# D12 Completion Sweep — Wave 2.5 → Commit Crosswalk

**Completed:** 2026-05-23

## Item → Commit

| Item | Severity | Commits | Description |
|------|----------|---------|-------------|
| **U1** — Backup restore HTTP route | High | `7991d3f` (+ `2506a1e` SHA backfill) | `POST /api/admin/backup/restore` accepts uploaded snapshot JSON, refuses on hot DB (409 db_busy via `PRAGMA wal_checkpoint(PASSIVE)`), wraps `restore_from_snapshot`, writes admin audit row. New `python-multipart` dep. 4 tests. |
| **U4** — Mirror health admin page | High | `ac22ceb` | `/admin/mirror` page with 10 s refresh + threshold colors (warn ≥ 1000 queue, critical ≥ 10000, warn ≥ 1 dead-letter). Surfaces all 6 fields of `/api/admin/mirror/health`. 4 tests. |
| **U5** — Backup admin page | High | `10de755` (+ `f5391cf` SHA backfill) | `/admin/backup` with "Şimdi yedek al" button + last-20 `backup_*` event history. Adds optional `event_type_prefix` query param to `/api/admin/system-events`. 3 tests. |
| **U6** — Retention admin page | High | `859d784` | `/admin/retention` with preview + confirm-modal-gated run-now; per-table breakdown + policy snapshot; disabled when total=0. 4 tests. |
| **BE-10** — Dead-letter requeue operator path | Med (promoted to W2.5) | `e31d124` (+ `7451c2f` SHA backfill) | `POST /api/admin/mirror/dead-letter/requeue` resets `retry_count=0` + clears error inside BEGIN IMMEDIATE; admin-only, audited. UI button on `/admin/mirror` (only when `dead_letter_count > 0`) confirm-modal-gated. 3 backend + 3 frontend tests. |
| **DR1+DR2+DR3** — Doc-reality drift | Doc | `edcec56` (+ `82deb75` SHA backfill) | README scrypt → bcrypt(rounds=12) ×3; README 90 s → 300 s lock TTL ×3; REQUIREMENTS.md MIRROR-01..10 Pending → Complete with commit SHAs. |
| **DC1** — Delete orphan `lib/env.ts` | Dead | `a875319` (+ `076a7ce` SHA backfill) | `frontend/src/lib/env.ts` had zero importers; deleted. Same commit fixed 10 eslint errors in U4/U5/U6 (require-await + react/no-unescaped-entities). |
| **DC2+DC3** — Drop orphan tables | Dead | `0a63112` (no-action) | Verification revealed `user_badges` and `user_quiz_answers` do NOT exist in current DB, migrations, or source. Audit had hallucinated their presence. No migration written. |

## Test-count delta

| Surface | Wave 0 baseline | Post-Wave-2.5 |
|---------|-----------------|----------------|
| Backend pytest passing | 946 | 977 + the new tests from U1 (+4), U5 (+1 backend filter test), BE-10 (+3) ≈ 985+ |
| Frontend vitest passing | 477 / 511 | 511 + U4 (+4) + U5 (+3) + U6 (+4) + BE-10 (+3) = 525 |

(Exact post-2.5 counts to be re-measured during Wave 4 validation.)

## User-deferred (Phase 6 backlog)

These audit-discovered Medium items were marked APPLY-W3 in the Wave 1 backlog triage and explicitly NOT included in Wave 2.5:
- U2 Admin notification broadcast
- U3 Gamification leaderboard endpoint
- U7 Export admin UI
- U8 Gold-doc "create new" admin UI
- U9 Quiz "create new" admin UI
- U10 Active locks list UI + missing `GET /api/locks` backend endpoint

## Gate

Wave 2.5 exit gate: surface this crosswalk + perform a manual smoke of the new admin pages before Wave 3.
