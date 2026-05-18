# Project: Annotation Platform

**Defined:** 2026-05-18 (retroactive — Phase 1-3 already shipped under polish workflow)
**Tracking start:** Phase 4 (Neon Postgres dual-write mirror)

## Core Value

A collaborative web app for annotating Turkish tax-authority rulings
(*özelge*) with structured legal references — built for scholarship
annotators, queried by tax practitioners.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLite (WAL + FK + busy-timeout), uvicorn (1 worker)
- **Frontend:** React 18, Vite 5, TypeScript strict, TanStack Query, Zustand, Tailwind + shadcn/ui
- **Source data:** External Neon Postgres (`documents` table, 17923 rows) — read-only role for one-shot import (Phase 4 makes it bidirectional via the mirror).

## Constraints

- Single uvicorn worker is mandatory (SQLite write-lock semantics).
- All writes go through service-layer functions; no raw SQL from routes.
- `BEGIN IMMEDIATE` wraps every multi-statement write to serialise writers.
- Annotation chain is append-only; every state change writes a version row.
- Production secrets must come from env, never hard-coded.
- No `rehype-raw` in the frontend markdown pipeline (XSS bypass).

## Project History (retroactive)

| Phase | Status | Tag / commits | Summary |
|-------|--------|---------------|---------|
| Phase 1 | Complete | `b536e22` | Canonical `workflow_state` + `has_draft` on `FeedItem`. Server-side state classification, COALESCE sort, LEFT JOIN drafts on verified tab. |
| Phase 2 | Complete | `c93fbda` + `924e4e2` | Atomic complete-with-refs (single `BEGIN IMMEDIATE` save+flag+draft-delete). Skip clears caller draft. Route fires save + complete SSE events; idempotence + AnnotationNotFound inside BEGIN (TOCTOU fix). |
| Phase 3 | Complete | `ca5555f` | Frontend simplification: single-POST complete, workflow_state UI branding, useDraft empty→DELETE, feed invalidate on transitions, SSE annotation_completed listener. |
| Phase 4 | Pending | (this plan) | Neon Postgres dual-write mirror via outbox pattern. |

Tests at start of Phase 4 planning: **872 backend pass + 3 skip**, **511 frontend pass**, lint + typecheck clean.

## Out of Scope (Phase 4)

- Bidirectional sync (Neon → SQLite). Mirror is one-way only.
- Postgres becoming the primary. SQLite remains canonical.
- 2-phase commit / distributed transaction guarantees. Eventual consistency is acceptable.
- Schema migration from Neon (Zeynep's `documents` table) into our `documents_meta`. That import is already done (Neon→SQLite ETL, May 18).
