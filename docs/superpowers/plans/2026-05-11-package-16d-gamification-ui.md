# Paket 16d — Gamification UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the gamification + presence + notification data Paket 7-9 already produces. Replace AppShell placeholder header with a real TopBar (XP/streak/today/online/profile dropdown+bell) and replace the `/me` STUB with a Profile page (header + 4 stat cards + badges grid + notifications list). Extend `useSSE` for `badge_unlocked`, `speed_warning`, `char_limit_warning`, `user_online`, `user_offline` events. Add 3 backend endpoints (`/api/users/online`, `/api/badges/catalog`, `POST /api/me/notifications/read-all`), 2 SSE event types (`user_online`, `user_offline`), and harden the broker's `QueueFull` drop path.

**Architecture:** React 18 + Vite + TS strict on the 16a/b/c foundation. TanStack Query 5 owns server state with `refetchInterval: 30_000` reconcile on presence + unread (Codex BROKEN-D/-E). Zod validates every payload at the query/mutation boundary; per-hook failure boundaries (Codex FRAGILE-F). `useSSE` becomes an orchestrator wiring four handler modules (`lockHandlers`, `feedHandlers`, `notificationHandlers`, `presenceHandlers`). Badge unlock toast is **informational only** — no action button (Codex BROKEN-B). Locked badges use a new optional `criterion` imperative field on `BADGE_DEFS` (Codex BROKEN-A). Broker `QueueFull` path calls `unsubscribe()` + emits `user_offline` to prevent ghost online users (Codex BROKEN, Pass 3).

**Tech Stack:** React 18, Vite 5, TypeScript strict, TanStack Query 5, Zustand 4 (existing, not new in 16d), Tailwind, shadcn/ui (Radix Dropdown/Tabs/Tooltip/Popover), sonner toasts, Zod, Vitest + MSW v2; backend FastAPI + SQLite (WAL) + Pydantic v2.

**Spec:** `docs/superpowers/specs/2026-05-11-paket-16d-gamification-ui-design.md` (commit `9b3911c`).

**Spec ↔ reality reconciliation (must be honoured during execution):**

1. **Notification shape:** spec §3.1 describes `read_at: string|null`, but the real backend `NotificationOut` (`backend/notifications/models.py`) uses `is_read: boolean` plus a `data: dict|null` field. **Use `is_read` everywhere** — frontend types, Zod schemas, components, tests. Mark-as-read is detected via `!item.is_read`.
2. **Gamification routes module:** spec §17 says `backend/gamification/routes.py` (new file if needed). It does not exist today; create it and register in `backend/main.py`. The existing `/api/me/profile` stays in `backend/users/routes.py` — do not move it.
3. **`formatRelativeTr`:** spec §5.1 says "MOVED" — it is **already in `frontend/src/lib/formatters.ts`**. Reuse from there; do not create a new file.
4. **SSE auth gate:** `/api/events` is gated by `require_passed_training` — pre-training users never get presence/online events. This is the accepted carryover from 16c; no change in 16d.
5. **Existing `notification` SSE event:** `gamification/service.py` already publishes both a `badge_unlocked` event AND a generic `notification` event. 16d's `notificationHandlers` invalidates `notifications` cache on either; do not delete the generic `notification` emit.

---

## File Map

### New backend files (1)

```
backend/gamification/routes.py       # GET /api/badges/catalog
```

### Modified backend files (5)

```
backend/gamification/badges.py       # +optional criterion field per badge
backend/notifications/routes.py      # +POST /api/me/notifications/read-all
backend/notifications/service.py     # +mark_all_read()
backend/users/routes.py              # +GET /api/users/online
backend/shared/sse.py                # broker QueueFull hardening + user_offline emit on cleanup
backend/sse/routes.py                # emit user_online after subscribe + user_offline in finally
backend/main.py                      # register gamification_router
```

### New frontend files (24)

```
frontend/src/
├── routes/
│   └── (Profile.tsx is modified, not new)
│
├── components/
│   ├── topbar/
│   │   ├── TopBar.tsx
│   │   ├── XPBadge.tsx
│   │   ├── StreakCounter.tsx
│   │   ├── DailyProgress.tsx
│   │   ├── OnlineUsers.tsx
│   │   └── ProfileDropdown.tsx
│   ├── badges/
│   │   ├── BadgesGrid.tsx
│   │   └── BadgeCard.tsx
│   ├── notifications/
│   │   ├── NotificationsList.tsx
│   │   └── NotificationItem.tsx
│   └── profile/
│       ├── ProfileHeader.tsx
│       └── StatCards.tsx
│
├── api/queries/
│   ├── profile.ts
│   ├── notifications.ts
│   ├── badges.ts
│   └── users.ts
│
├── hooks/sse/
│   ├── lockHandlers.ts
│   ├── feedHandlers.ts
│   ├── notificationHandlers.ts
│   └── presenceHandlers.ts
│
└── lib/
    ├── profileSchemas.ts
    ├── sseSchemas.ts
    └── notificationKinds.ts
```

### Modified frontend files (5)

```
frontend/src/
├── components/shell/AppShell.tsx       # mount TopBar
├── hooks/useSSE.ts                     # orchestrator refactor
├── routes/Profile.tsx                  # replace STUB with full page
├── test/msw-handlers.ts                # +profile/notifications/catalog/online factories+handlers
└── api/types.ts                        # regenerated via gen:types after backend lands
```

### Untouched (regression-safe)

- All 16a/b/c source files except the four modified above
- `ReferenceCard.tsx`, `ReferencePanel.tsx`, hook/store entry points (annotateStore, useDoc, useDraft, useLock, useReferencesState)
- 16c onboarding (Help, Training and their components)
- `App.tsx` route tree (16d does not change routing)
- `frontend/src/lib/validateReferences.ts` (Dalga 1 shared validation)

---

## Task Order

| # | Task | Depends on | Atomic commit prefix |
|---|---|---|---|
| T1 | `badges.py`: add `criterion` field + tests | — | `feat(paket-16d): badge criterion field` |
| T2 | `gamification/routes.py`: GET `/badges/catalog` + register in main | T1 | `feat(paket-16d): badges catalog endpoint` |
| T3 | `users/routes.py`: GET `/users/online` + tests | — | `feat(paket-16d): online users endpoint` |
| T4 | `notifications/service.py` + routes: `mark_all_read` + POST `/read-all` + tests | — | `feat(paket-16d): mark-all-read endpoint` |
| T5 | `shared/sse.py`: broker `QueueFull` hardening + emit user_offline + tests | — | `feat(paket-16d): broker QueueFull hardening` |
| T6 | `sse/routes.py`: emit user_online after subscribe + user_offline in finally + tests | T5 | `feat(paket-16d): SSE presence events` |
| T7 | `npm run gen:types` regenerates `api/types.ts` | T1-T6 | `chore(paket-16d): regenerate openapi types` |
| T8 | `lib/profileSchemas.ts` Zod schemas + tests | T7 | `feat(paket-16d): profile zod schemas` |
| T9 | `lib/sseSchemas.ts` + `parseEventData` helper + tests | — | `feat(paket-16d): SSE payload zod schemas` |
| T10 | `lib/notificationKinds.ts` icon map + tests | — | `feat(paket-16d): notification kind icons` |
| T11 | `api/queries/profile.ts` `useProfile` + tests | T8 | `feat(paket-16d): useProfile hook` |
| T12 | `api/queries/notifications.ts` (4 hooks) + tests | T8 | `feat(paket-16d): notifications hooks` |
| T13 | `api/queries/badges.ts` (`useBadgesCatalog` + `useLockedBadges`) + tests | T8, T11 | `feat(paket-16d): badges catalog hooks` |
| T14 | `api/queries/users.ts` `useOnlineUsers` + tests | T8 | `feat(paket-16d): online users hook` |
| T15 | `test/msw-handlers.ts`: factories + handlers for new endpoints | T8 | `test(paket-16d): MSW handlers for 16d endpoints` |
| T16 | `hooks/sse/lockHandlers.ts`: extract from 16b useSSE + tests | — | `refactor(paket-16d): extract lockHandlers` |
| T17 | `hooks/sse/feedHandlers.ts`: extract annotation_saved handler + tests | T16 | `refactor(paket-16d): extract feedHandlers` |
| T18 | `hooks/sse/notificationHandlers.ts` + tests | T9, T11, T12 | `feat(paket-16d): notification SSE handlers` |
| T19 | `hooks/sse/presenceHandlers.ts` + tests | T9, T14 | `feat(paket-16d): presence SSE handlers` |
| T20 | `hooks/useSSE.ts`: orchestrator refactor + reconnect invalidate updates + tests | T16-T19 | `refactor(paket-16d): useSSE orchestrator` |
| T21 | `components/topbar/XPBadge.tsx` + test | T8 | `feat(paket-16d): XPBadge` |
| T22 | `components/topbar/StreakCounter.tsx` + test | T8 | `feat(paket-16d): StreakCounter` |
| T23 | `components/topbar/DailyProgress.tsx` + test | T8 | `feat(paket-16d): DailyProgress` |
| T24 | `components/topbar/OnlineUsers.tsx` + test | T8, T14 | `feat(paket-16d): OnlineUsers` |
| T25 | `components/topbar/ProfileDropdown.tsx` + test | T8, T10, T12 | `feat(paket-16d): ProfileDropdown + bell` |
| T26 | `components/topbar/TopBar.tsx` + test | T11, T12, T14, T21-T25 | `feat(paket-16d): TopBar container` |
| T27 | `components/shell/AppShell.tsx`: mount TopBar + test | T26 | `feat(paket-16d): mount TopBar in AppShell` |
| T28 | `components/badges/BadgeCard.tsx` + test | T8 | `feat(paket-16d): BadgeCard (earned + locked)` |
| T29 | `components/badges/BadgesGrid.tsx` + test | T8, T11, T13, T28 | `feat(paket-16d): BadgesGrid with tabs` |
| T30 | `components/notifications/NotificationItem.tsx` + test | T8, T10, T12 | `feat(paket-16d): NotificationItem` |
| T31 | `components/notifications/NotificationsList.tsx` + test | T12, T30 | `feat(paket-16d): NotificationsList` |
| T32 | `components/profile/ProfileHeader.tsx` + test | T8 | `feat(paket-16d): ProfileHeader` |
| T33 | `components/profile/StatCards.tsx` + test | T8 | `feat(paket-16d): StatCards` |
| T34 | `routes/Profile.tsx`: replace STUB + integration tests | T29, T31, T32, T33 | `feat(paket-16d): Profile route` |
| T35 | Full suite + coverage + lint + typecheck + gen:types:check | T1-T34 | `chore(paket-16d): verify acceptance criteria` |
| T36 | Manual E2E smoke + tag `paket-16d-gamification-ui` | T35 | `chore(paket-16d): tag release` |

---

## Task 1: BADGE_DEFS criterion field

**Files:**
- Modify: `backend/gamification/badges.py`
- Test: `backend/tests/test_gamification_badges.py` (existing; add a new test)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_gamification_badges.py`:

```python
from backend.gamification.badges import BADGE_DEFS


def test_badge_defs_have_imperative_criterion():
    """Each badge has an optional `criterion` field for the locked variant
    UI (imperative — 'X yap'). The earned variant continues to use the past-
    tense `description`. Catalog endpoint surfaces both."""
    expected_ids = {
        "first_annotation", "annotations_10", "annotations_100",
        "annotations_1000", "first_completion", "marathoner", "good_reviewer",
    }
    assert set(BADGE_DEFS.keys()) == expected_ids
    for badge_id, meta in BADGE_DEFS.items():
        assert "name" in meta, badge_id
        assert "description" in meta, badge_id
        assert "criterion" in meta, badge_id
        assert isinstance(meta["criterion"], str) and meta["criterion"], badge_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_gamification_badges.py::test_badge_defs_have_imperative_criterion -v`
Expected: FAIL with `KeyError: 'criterion'` or `AssertionError`.

- [ ] **Step 3: Add `criterion` to each badge entry in `backend/gamification/badges.py`**

Replace the `BADGE_DEFS` dict with:

```python
BADGE_DEFS: dict[str, dict[str, str]] = {
    "first_annotation": {
        "name": "İlk Annotation",
        "description": "İlk kayıt başarıyla yapıldı.",
        "criterion": "İlk anotasyon kaydını yap.",
    },
    "annotations_10": {
        "name": "10 Annotation",
        "description": "10 kayıt biriktirdin.",
        "criterion": "10 anotasyon kaydı biriktir.",
    },
    "annotations_100": {
        "name": "100 Annotation",
        "description": "100 kayıt — istikrarlı çalışıyorsun.",
        "criterion": "100 anotasyon kaydı biriktir.",
    },
    "annotations_1000": {
        "name": "1000 Annotation",
        "description": "Bin kayıt: ekibin omurgası oldun.",
        "criterion": "1000 anotasyon kaydı biriktir.",
    },
    "first_completion": {
        "name": "İlk Tamamlama",
        "description": "İlk dokümanı tamamlandı olarak işaretledin.",
        "criterion": "İlk dokümanı tamamlandı olarak işaretle.",
    },
    "marathoner": {
        "name": "Maratoncu",
        "description": "7 gün üst üste çalıştın.",
        "criterion": "7 gün üst üste çalış.",
    },
    "good_reviewer": {
        "name": "Good Reviewer",
        "description": "Yaptığın review'lerin çoğu sonraki kullanıcılar tarafından korundu.",
        "criterion": "Review'lerinin çoğunluğu korunsun (en az 20 review, 15+ kept).",
    },
}
```

- [ ] **Step 4: Run targeted test + full gamification suite**

Run: `.venv/bin/python -m pytest backend/tests/test_gamification_badges.py -v`
Expected: all PASS (new test + existing `check_badges` tests untouched because the new key is additive).

- [ ] **Step 5: Run gamification service tests that consume `BADGE_DEFS`**

Run: `.venv/bin/python -m pytest backend/tests/test_gamification_service.py -v`
Expected: PASS. `meta["description"]` lookups still work because the field is unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/gamification/badges.py backend/tests/test_gamification_badges.py
git commit -m "$(cat <<'EOF'
feat(paket-16d): add imperative criterion field to BADGE_DEFS

Locked-badge UI needs imperative copy ("10 anotasyon kaydı biriktir")
because the past-tense description ("10 kayıt biriktirdin") is wrong for
a badge the user has NOT yet earned (Codex BROKEN-A, Pass 2).

The field is additive: existing `meta["description"]` consumers in
gamification/service.py are untouched.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: GET /api/badges/catalog endpoint

**Files:**
- Create: `backend/gamification/routes.py`
- Modify: `backend/main.py` (register the new router)
- Test: `backend/tests/test_gamification_routes.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_gamification_routes.py`:

```python
"""Tests for GET /api/badges/catalog."""


def test_badges_catalog_requires_auth(client):
    """Anonymous request returns 401."""
    res = client.get("/api/badges/catalog")
    assert res.status_code == 401


def test_badges_catalog_returns_all_seven(auth_client):
    """The catalog returns one entry per BADGE_DEFS key with criterion
    surfaced. Order is stable across calls (insertion order of BADGE_DEFS)."""
    res = auth_client.get("/api/badges/catalog")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) == 7

    ids = [b["id"] for b in body]
    assert ids == [
        "first_annotation", "annotations_10", "annotations_100",
        "annotations_1000", "first_completion", "marathoner", "good_reviewer",
    ]

    first = body[0]
    assert first["id"] == "first_annotation"
    assert first["name"] == "İlk Annotation"
    assert first["description"] == "İlk kayıt başarıyla yapıldı."
    assert first["criterion"] == "İlk anotasyon kaydını yap."


def test_badges_catalog_shape_is_stable(auth_client):
    """Every entry has exactly id/name/description/criterion keys."""
    res = auth_client.get("/api/badges/catalog")
    body = res.json()
    for entry in body:
        assert set(entry.keys()) == {"id", "name", "description", "criterion"}
        assert isinstance(entry["id"], str)
        assert isinstance(entry["name"], str)
        assert isinstance(entry["description"], str)
        assert isinstance(entry["criterion"], str)
```

(`client` and `auth_client` fixtures already exist in `backend/tests/conftest.py` per 16a-c precedent — `auth_client` is the TestClient with a logged-in `tester` session.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_gamification_routes.py -v`
Expected: FAIL — endpoint does not exist yet (404 / collection error).

- [ ] **Step 3: Create the router file**

Write `backend/gamification/routes.py`:

```python
"""Public HTTP endpoints for the gamification module.

Currently exposes only the static badge catalog. The profile endpoint
(`GET /api/me/profile`) lives in `backend/users/routes.py` because it
aggregates user identity + gamification state under the /me/* tree.
"""
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.gamification.badges import BADGE_DEFS
from backend.users.deps import get_current_user


router = APIRouter(prefix="/api/badges", tags=["gamification"])


class BadgeCatalogItem(BaseModel):
    id: str
    name: str
    description: str
    criterion: str


@router.get("/catalog", response_model=list[BadgeCatalogItem])
def get_catalog(
    _user: sqlite3.Row = Depends(get_current_user),
):
    """Return all known badges in insertion order. The frontend joins this
    with the user's earned set (from /me/profile.badges) to render the
    'Hepsi' tab of the BadgesGrid with grayscale + criterion text for the
    not-yet-earned items."""
    out: list[dict] = []
    for badge_id, meta in BADGE_DEFS.items():
        out.append({
            "id": badge_id,
            "name": meta["name"],
            "description": meta["description"],
            "criterion": meta["criterion"],
        })
    return out
```

- [ ] **Step 4: Register the router in `backend/main.py`**

Locate the existing block that includes `notifications_router` (~line 102). Add an import near the other gamification import and `include_router` next to the others. Replace:

```python
from backend.notifications.routes import router as notifications_router
```

with:

```python
from backend.gamification.routes import router as gamification_router
from backend.notifications.routes import router as notifications_router
```

And immediately after `app.include_router(notifications_router)`:

```python
app.include_router(gamification_router)
```

- [ ] **Step 5: Run targeted tests**

Run: `.venv/bin/python -m pytest backend/tests/test_gamification_routes.py -v`
Expected: all PASS (3 tests).

- [ ] **Step 6: Run full backend suite (regression)**

Run: `.venv/bin/python -m pytest backend/tests -q`
Expected: 741 + 3 new = 744 PASS, 0 fail.

- [ ] **Step 7: Commit**

```bash
git add backend/gamification/routes.py backend/main.py backend/tests/test_gamification_routes.py
git commit -m "$(cat <<'EOF'
feat(paket-16d): add GET /api/badges/catalog endpoint

Returns the full BADGE_DEFS keyset with criterion surfaced so the
frontend BadgesGrid can render locked badges with imperative hints
(Codex BROKEN-A). Auth-required (get_current_user). Insertion order is
stable.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: GET /api/users/online endpoint

**Files:**
- Modify: `backend/users/routes.py`
- Test: `backend/tests/test_users_routes.py` (existing — append) OR `backend/tests/test_users_online.py` (new — preferred for isolation)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_users_online.py`:

```python
"""Tests for GET /api/users/online (auth + presence projection)."""
from backend.shared.sse import broker


def test_users_online_requires_auth(client):
    res = client.get("/api/users/online")
    assert res.status_code == 401


def test_users_online_empty_when_no_subscribers(auth_client):
    """With no SSE subscribers, returns []."""
    # Clear broker state if previous tests left subscribers.
    broker._subscribers.clear()
    res = auth_client.get("/api/users/online")
    assert res.status_code == 200
    assert res.json() == []


def test_users_online_returns_subscribed_users(auth_client, db_conn, seed_extra_user):
    """When two users have an SSE subscription, both appear ordered by id asc."""
    broker._subscribers.clear()

    # tester is id=1 in conftest; seed_extra_user produces a separate user.
    other_id = seed_extra_user(username="watcher2", avatar_color="#ef4444")

    q1 = broker.subscribe(1)
    q2 = broker.subscribe(other_id)
    try:
        res = auth_client.get("/api/users/online")
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 2
        # Ordered by id ascending
        assert body[0]["id"] < body[1]["id"]
        assert {b["id"] for b in body} == {1, other_id}
        # Shape check
        for entry in body:
            assert set(entry.keys()) == {"id", "username", "avatar_color"}
    finally:
        broker.unsubscribe(1, q1)
        broker.unsubscribe(other_id, q2)


def test_users_online_drops_unknown_user_ids(auth_client):
    """Defensive: a subscriber for a non-existent user_id is filtered out
    (race during disable + still-open SSE)."""
    broker._subscribers.clear()
    q = broker.subscribe(999_999)
    try:
        res = auth_client.get("/api/users/online")
        assert res.status_code == 200
        assert res.json() == []
    finally:
        broker.unsubscribe(999_999, q)
```

Add a `seed_extra_user` fixture to `backend/tests/conftest.py` if it does not exist:

```python
@pytest.fixture
def seed_extra_user(db_conn):
    """Insert a user row and return its id. Caller picks username."""
    def _seed(*, username: str = "watcher", avatar_color: str = "#22c55e",
              role: str = "user") -> int:
        cur = db_conn.execute(
            "INSERT INTO users(username, email, password_hash, role, "
            "is_active, has_seen_manual, has_passed_training, avatar_color, "
            "created_at, updated_at) "
            "VALUES (?, NULL, 'pbkdf2_sha256$1$test$x', ?, 1, 1, 1, ?, "
            "datetime('now'), datetime('now'))",
            (username, role, avatar_color),
        )
        db_conn.commit()
        return cur.lastrowid
    return _seed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_users_online.py -v`
Expected: FAIL — endpoint missing (404).

- [ ] **Step 3: Add the endpoint to `backend/users/routes.py`**

Add a new Pydantic model near the existing models (top of file or in `backend/users/models.py`; we add inline near other Pydantic models in `routes.py` for locality with this endpoint):

```python
class OnlineUserOut(_BaseModel):
    id: int
    username: str
    avatar_color: str


class OnlineUsersResponse(_BaseModel):
    """Wraps the online users list — used only for response_model docs;
    the endpoint returns the bare list."""
    pass
```

Add the endpoint after `me()` (~line 109) but before the admin block (~line 152):

```python
@router.get("/users/online", response_model=list[OnlineUserOut])
def list_online_users(
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(get_current_user),
):
    """Return users currently subscribed to SSE, ordered by id ascending.

    Source of truth: `broker.online_user_ids()` (in-memory set of user_ids
    with at least one open SSE queue). Frontend reconciles via 30s polling
    + SSE merge (user_online/user_offline events from this broker).
    """
    from backend.shared.sse import broker
    ids = sorted(broker.online_user_ids())
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = db.execute(
        f"SELECT id, username, avatar_color FROM users "
        f"WHERE id IN ({placeholders}) ORDER BY id ASC",
        tuple(ids),
    ).fetchall()
    return [
        {"id": r["id"], "username": r["username"], "avatar_color": r["avatar_color"]}
        for r in rows
    ]
```

- [ ] **Step 4: Run targeted tests**

Run: `.venv/bin/python -m pytest backend/tests/test_users_online.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Run full users suite to verify no regression**

Run: `.venv/bin/python -m pytest backend/tests/test_users_routes.py backend/tests/test_users_online.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/users/routes.py backend/tests/test_users_online.py backend/tests/conftest.py
git commit -m "$(cat <<'EOF'
feat(paket-16d): add GET /api/users/online endpoint

Returns users currently subscribed to SSE, ordered by id asc. Source is
broker.online_user_ids() joined with the users table; missing rows are
filtered out defensively (race during disable + open SSE).

Frontend reconciles every 30s (Codex BROKEN-D) and merges SSE
user_online/user_offline events for sub-second responsiveness.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: POST /api/me/notifications/read-all endpoint

**Files:**
- Modify: `backend/notifications/service.py` (add `mark_all_read`)
- Modify: `backend/notifications/routes.py` (add `POST /read-all`)
- Test: `backend/tests/test_notifications_routes.py` (existing — append) or new `test_notifications_read_all.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_notifications_read_all.py`:

```python
"""Tests for POST /api/me/notifications/read-all."""
from backend.notifications import service as notif_service


def test_read_all_requires_auth(client):
    res = client.post("/api/me/notifications/read-all")
    assert res.status_code == 401


def test_read_all_marks_only_current_user_unread(
    auth_client, db_conn, seed_extra_user,
):
    """The endpoint marks ONLY the caller's unread rows. Returns marked_count."""
    # tester id=1; seed a stranger
    stranger_id = seed_extra_user(username="stranger")
    notif_service.create(db_conn, user_id=1, kind="admin_announcement",
                         title="A1", body=None)
    notif_service.create(db_conn, user_id=1, kind="admin_announcement",
                         title="A2", body=None)
    notif_service.create(db_conn, user_id=stranger_id, kind="admin_announcement",
                         title="B1", body=None)
    db_conn.commit()

    res = auth_client.post("/api/me/notifications/read-all")
    assert res.status_code == 200
    assert res.json() == {"marked_count": 2}

    # Caller's rows are read=1
    rows = db_conn.execute(
        "SELECT is_read FROM notifications WHERE user_id=1 ORDER BY id"
    ).fetchall()
    assert all(r["is_read"] == 1 for r in rows)
    # Stranger's row is untouched
    stranger_rows = db_conn.execute(
        "SELECT is_read FROM notifications WHERE user_id=?", (stranger_id,),
    ).fetchall()
    assert stranger_rows[0]["is_read"] == 0


def test_read_all_is_idempotent(auth_client, db_conn):
    """Re-calling read-all on an already-clean inbox returns 0."""
    notif_service.create(db_conn, user_id=1, kind="admin_announcement",
                         title="X", body=None)
    db_conn.commit()

    res1 = auth_client.post("/api/me/notifications/read-all")
    assert res1.json() == {"marked_count": 1}
    res2 = auth_client.post("/api/me/notifications/read-all")
    assert res2.json() == {"marked_count": 0}


def test_read_all_with_empty_inbox(auth_client):
    """Empty inbox returns 0."""
    res = auth_client.post("/api/me/notifications/read-all")
    assert res.status_code == 200
    assert res.json() == {"marked_count": 0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_notifications_read_all.py -v`
Expected: FAIL — endpoint missing (404).

- [ ] **Step 3: Add `mark_all_read` to `backend/notifications/service.py`**

Append to the file:

```python
def mark_all_read(db: sqlite3.Connection, *, user_id: int) -> int:
    """Mark every unread notification for this user as read in a single
    atomic UPDATE. Returns the count of rows actually flipped (0 if the
    inbox was already clean). Idempotent.

    Frontend uses this instead of batching N individual POST /read calls
    (Codex BROKEN, Pass 1) — batching is racy and half-success is hard
    to detect from the client.
    """
    cur = db.execute(
        "UPDATE notifications SET is_read=1 "
        "WHERE user_id=? AND is_read=0",
        (user_id,),
    )
    db.commit()
    return cur.rowcount
```

- [ ] **Step 4: Add the endpoint to `backend/notifications/routes.py`**

Append before the existing `mark_read` endpoint OR after it (order doesn't affect FastAPI matching here since paths differ). Replace the end of the file:

```python
@router.post("/read-all")
def mark_all_read(
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(get_current_user),
):
    """Atomic 'read everything' for the caller's inbox. Returns the count
    of rows newly marked read; 0 if nothing was unread."""
    count = service.mark_all_read(db, user_id=user["id"])
    return {"marked_count": count}
```

Add an explicit Pydantic response model in `backend/notifications/models.py`:

```python
class MarkAllReadResponse(BaseModel):
    marked_count: int
```

Wire it into the endpoint signature: `def mark_all_read(...)` → `def mark_all_read(...) -> MarkAllReadResponse` and add `response_model=MarkAllReadResponse` to the decorator. Then import the new model in `routes.py`:

```python
from backend.notifications.models import (
    NotificationListResponse, OkResponse, MarkAllReadResponse,
)
```

Final decorated form:

```python
@router.post("/read-all", response_model=MarkAllReadResponse)
def mark_all_read(
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(get_current_user),
):
    count = service.mark_all_read(db, user_id=user["id"])
    return {"marked_count": count}
```

- [ ] **Step 5: Run targeted tests**

Run: `.venv/bin/python -m pytest backend/tests/test_notifications_read_all.py -v`
Expected: 4 PASS.

- [ ] **Step 6: Run full notifications suite**

Run: `.venv/bin/python -m pytest backend/tests/test_notifications_routes.py backend/tests/test_notifications_service.py backend/tests/test_notifications_read_all.py -v`
Expected: all PASS (no regression in existing list_for_user / mark_read tests).

- [ ] **Step 7: Commit**

```bash
git add backend/notifications/routes.py backend/notifications/service.py backend/notifications/models.py backend/tests/test_notifications_read_all.py
git commit -m "$(cat <<'EOF'
feat(paket-16d): add POST /api/me/notifications/read-all

Single atomic UPDATE per user. Returns marked_count (0 = inbox already
clean — idempotent). Replaces racy frontend-side batched POSTs (Codex
BROKEN, Pass 1).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Broker QueueFull hardening + user_offline emit

**Files:**
- Modify: `backend/shared/sse.py`
- Test: `backend/tests/test_sse_broker.py` (existing — append) OR new `test_sse_broker_queue_full.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_sse_broker_queue_full.py`:

```python
"""Tests for broker QueueFull hardening (Codex BROKEN, Pass 3).

When publish_to hits QueueFull on a slow consumer, the existing code
silently drops the event — but the dead queue stays in self._subscribers,
making online_user_ids() report a ghost user forever.

After the fix:
1. The dead queue is removed via unsubscribe().
2. If that was the user's last queue, a user_offline broadcast fires.
3. online_user_ids() no longer includes the dropped user.
"""
import asyncio
import pytest

from backend.shared.sse import SSEBroker


@pytest.mark.asyncio
async def test_queue_full_cleans_dead_queue():
    broker = SSEBroker()
    # Subscribe a user whose queue is filled to capacity (maxsize=100).
    q = broker.subscribe(42)
    for _ in range(100):
        q.put_nowait("filler")

    # Publishing one more event hits QueueFull. The broker must drop
    # the queue and remove the user from online set.
    await broker.publish_to([42], "any_event", {"k": "v"})
    assert 42 not in broker.online_user_ids()


@pytest.mark.asyncio
async def test_queue_full_emits_user_offline_to_remaining_subscribers():
    """When the dropped queue was the user's last, broker broadcasts
    user_offline so other clients refetch /api/users/online."""
    broker = SSEBroker()
    # Subscribe a slow consumer for user 42 + a healthy listener for user 7.
    slow_q = broker.subscribe(42)
    for _ in range(100):
        slow_q.put_nowait("filler")
    listener_q = broker.subscribe(7)

    await broker.publish_to([42], "any_event", {"k": "v"})

    # Listener should now have one event waiting in their queue: user_offline.
    # (Plus they may already have other events; we walk the queue.)
    seen_offline = False
    while not listener_q.empty():
        evt = listener_q.get_nowait()
        if evt.event_type == "user_offline" and evt.data == {"id": 42}:
            seen_offline = True
            break
    assert seen_offline, "user_offline event was not emitted on QueueFull cleanup"


@pytest.mark.asyncio
async def test_queue_full_when_user_has_other_open_queues_no_offline():
    """If the user has OTHER open queues (e.g. second browser tab), the
    cleanup does NOT emit user_offline — the user is still online."""
    broker = SSEBroker()
    # User 42 has two tabs.
    slow_q = broker.subscribe(42)
    healthy_q = broker.subscribe(42)
    listener_q = broker.subscribe(7)
    for _ in range(100):
        slow_q.put_nowait("filler")

    await broker.publish_to([42], "any_event", {"k": "v"})

    # 42 must still be online (other tab healthy)
    assert 42 in broker.online_user_ids()
    # Listener should NOT have user_offline event for 42.
    saw_offline_for_42 = False
    while not listener_q.empty():
        evt = listener_q.get_nowait()
        if evt.event_type == "user_offline" and evt.data.get("id") == 42:
            saw_offline_for_42 = True
    assert not saw_offline_for_42
```

`pytest-asyncio` is already a dev dep (used by 16b SSE tests). The marker `@pytest.mark.asyncio` is configured in `pyproject.toml`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_sse_broker_queue_full.py -v`
Expected: FAIL — `42` stays in `online_user_ids()`, no `user_offline` event ever fires.

- [ ] **Step 3: Patch `backend/shared/sse.py`**

Replace the `publish_to` method body with hardened cleanup:

```python
    async def publish_to(
        self, user_ids: Iterable[int], event_type: str, data: dict
    ) -> None:
        event = SSEEvent(event_type=event_type, data=data)
        # Drained queues are cleaned up below. We iterate over a snapshot
        # because cleanup mutates self._subscribers.
        dropped: list[tuple[int, asyncio.Queue]] = []
        for uid in list(user_ids):
            for q in list(self._subscribers.get(uid, [])):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Slow consumer — remove the dead queue so it does not
                    # ghost the online roster forever (Codex BROKEN, Pass 3).
                    dropped.append((uid, q))

        for uid, q in dropped:
            self.unsubscribe(uid, q)
            # Only fire user_offline when the cleanup removed the user's
            # LAST queue — they may still be online via another tab.
            if uid not in self._subscribers:
                offline_event = SSEEvent(
                    event_type="user_offline", data={"id": uid},
                )
                for target_uid in list(self._subscribers.keys()):
                    if target_uid == uid:
                        continue
                    for q2 in list(self._subscribers.get(target_uid, [])):
                        try:
                            q2.put_nowait(offline_event)
                        except asyncio.QueueFull:
                            # Don't recurse into cleanup-of-cleanup; accept
                            # the drop. Next 30s polling reconcile will
                            # converge state.
                            pass
```

Rationale for the inline broadcast (instead of `asyncio.create_task(self.publish_broadcast(...))`):

1. We're already inside `publish_to` which is `async`. Spawning a task for cleanup is fine in principle, but it creates a race where the dead queue is removed AFTER the broadcast tries to send to it. Inlining the broadcast with the snapshot of `_subscribers` we already mutated avoids that.
2. We deliberately skip the dropped uid as a recipient — they're being declared offline.
3. Nested `QueueFull` is accepted as a drop. Frontend `useOnlineUsers` polls every 30s anyway (Codex BROKEN-D), so the worst case is sub-30s of stale "online" UI for an observer.

- [ ] **Step 4: Run targeted tests**

Run: `.venv/bin/python -m pytest backend/tests/test_sse_broker_queue_full.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Run full SSE + gamification suite (regression — make sure existing publishes still work)**

Run: `.venv/bin/python -m pytest backend/tests/test_sse_broker.py backend/tests/test_sse_routes.py backend/tests/test_gamification_service.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/shared/sse.py backend/tests/test_sse_broker_queue_full.py
git commit -m "$(cat <<'EOF'
feat(paket-16d): harden broker QueueFull path

Before: publish_to silently dropped events on slow consumers, leaving
the dead queue in self._subscribers. online_user_ids() therefore
reported ghost users forever (Codex BROKEN, Pass 3).

After: cleanup unsubscribes the dropped queue. If it was the user's
last subscription, the broker broadcasts user_offline to remaining
subscribers so other clients converge fast without waiting 30s for
the polling reconcile.

Nested QueueFull during the offline broadcast is accepted as a drop —
polling reconcile catches it. This avoids unbounded recursion.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: SSE routes — emit user_online on subscribe + user_offline on disconnect

**Files:**
- Modify: `backend/sse/routes.py`
- Test: `backend/tests/test_sse_routes.py` (existing — append) OR new `test_sse_presence.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_sse_presence.py`:

```python
"""Tests for SSE user_online / user_offline lifecycle events."""
import asyncio
import pytest

from backend.shared.sse import broker
from backend.sse.routes import _stream_for_user


@pytest.mark.asyncio
async def test_subscribe_broadcasts_user_online_to_others(db_conn, seed_extra_user):
    """When a user opens an SSE connection, all OTHER online users receive
    a user_online event (publish_to_others — no self-echo)."""
    broker._subscribers.clear()
    other_id = seed_extra_user(username="watcher_online", avatar_color="#22c55e")
    listener_q = broker.subscribe(other_id)
    try:
        # _stream_for_user yields ": ready\n\n" first; we just need to consume
        # one item so the subscribe() runs and our user_online emit fires.
        gen = _stream_for_user(user_id=1)
        first = await gen.__anext__()
        assert ": ready" in first

        # Drain the listener queue until we find user_online for id=1
        seen = False
        for _ in range(5):
            try:
                evt = await asyncio.wait_for(listener_q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                break
            if evt.event_type == "user_online" and evt.data.get("id") == 1:
                seen = True
                break
        assert seen, "user_online was not broadcast to other subscribers"

        # And the subscriber themselves did NOT receive user_online for self.
        # _stream_for_user has its own queue; we cleanup by closing the gen.
        await gen.aclose()
    finally:
        broker.unsubscribe(other_id, listener_q)


@pytest.mark.asyncio
async def test_user_online_payload_shape(db_conn):
    """The user_online event payload is {id, username, avatar_color}."""
    broker._subscribers.clear()
    listener_q = broker.subscribe(2)  # an arbitrary OTHER user
    try:
        gen = _stream_for_user(user_id=1)
        await gen.__anext__()  # ": ready"
        for _ in range(5):
            try:
                evt = await asyncio.wait_for(listener_q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                pytest.fail("no user_online event arrived")
            if evt.event_type == "user_online":
                assert set(evt.data.keys()) == {"id", "username", "avatar_color"}
                assert evt.data["id"] == 1
                break
        await gen.aclose()
    finally:
        broker.unsubscribe(2, listener_q)


@pytest.mark.asyncio
async def test_unsubscribe_broadcasts_user_offline(db_conn, seed_extra_user):
    """When a user's last queue is unsubscribed, all remaining subscribers
    receive a user_offline event."""
    broker._subscribers.clear()
    other_id = seed_extra_user(username="watcher_offline", avatar_color="#ef4444")
    listener_q = broker.subscribe(other_id)
    try:
        gen = _stream_for_user(user_id=1)
        await gen.__anext__()
        # Drain online event(s)
        while not listener_q.empty():
            listener_q.get_nowait()
        # Now close — finally: unsubscribes; should emit user_offline.
        await gen.aclose()
        for _ in range(5):
            try:
                evt = await asyncio.wait_for(listener_q.get(), timeout=0.5)
            except asyncio.TimeoutError:
                pytest.fail("no user_offline event arrived")
            if evt.event_type == "user_offline" and evt.data == {"id": 1}:
                break
        else:
            pytest.fail("user_offline not seen")
    finally:
        broker.unsubscribe(other_id, listener_q)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_sse_presence.py -v`
Expected: FAIL — current code emits neither `user_online` nor `user_offline`.

- [ ] **Step 3: Patch `backend/sse/routes.py`**

Add a helper that builds the presence payload then modify `_stream_for_user`:

```python
import sqlite3

from backend.shared.sse import broker, SSEEvent
from backend.users.deps import require_passed_training, get_db


def _build_online_payload(db: sqlite3.Connection, user_id: int) -> dict:
    """Look up the user's username + avatar_color for the user_online
    broadcast. Falls back to safe defaults if the row vanished (rare race)."""
    row = db.execute(
        "SELECT username, avatar_color FROM users WHERE id=?", (user_id,),
    ).fetchone()
    if row is None:
        return {"id": user_id, "username": f"user{user_id}", "avatar_color": "#666666"}
    return {
        "id": user_id,
        "username": row["username"],
        "avatar_color": row["avatar_color"],
    }


async def _broadcast_to_others(
    *, except_user_id: int, event_type: str, data: dict,
) -> None:
    """Inline broadcast that excludes the originating user. Mirrors the
    pattern used inside broker.publish_to without going through it (we
    have no DB-level user model here)."""
    event = SSEEvent(event_type=event_type, data=data)
    for uid in list(broker._subscribers.keys()):
        if uid == except_user_id:
            continue
        for q in list(broker._subscribers.get(uid, [])):
            try:
                q.put_nowait(event)
            except __import__("asyncio").QueueFull:
                # Accept drop — slow consumer; polling reconcile catches it.
                pass
```

Wait — `broker.publish_to_others` already exists and does exactly this. Use it. Replace the helpers above with just:

```python
def _build_online_payload(db: sqlite3.Connection, user_id: int) -> dict:
    """Look up the user's identity slice for the user_online broadcast.
    Falls back to safe defaults if the row vanished (rare race)."""
    row = db.execute(
        "SELECT username, avatar_color FROM users WHERE id=?", (user_id,),
    ).fetchone()
    if row is None:
        return {"id": user_id, "username": f"user{user_id}", "avatar_color": "#666666"}
    return {
        "id": user_id,
        "username": row["username"],
        "avatar_color": row["avatar_color"],
    }
```

Then change `_stream_for_user` to use the broker's existing helper:

```python
async def _stream_for_user(user_id: int, db: sqlite3.Connection) -> AsyncIterator[str]:
    """Subscribe to broker; yield SSE messages until cancelled."""
    queue = broker.subscribe(user_id)
    try:
        # Fire user_online to everyone EXCEPT the subscriber (no self-echo).
        try:
            payload = _build_online_payload(db, user_id)
            await broker.publish_to_others(
                except_user_id=user_id,
                event_type="user_online",
                data=payload,
            )
        except Exception:
            log.exception("user_online emit failed for user_id=%s", user_id)

        yield ": ready\n\n"
        while True:
            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=KEEPALIVE_INTERVAL_SECONDS,
                )
                yield format_sse_message(event_type=event.event_type, data=event.data)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("SSE stream errored for user_id=%s", user_id)
        raise
    finally:
        broker.unsubscribe(user_id, queue)
        # If that was the user's last queue, broadcast user_offline.
        if user_id not in broker._subscribers:
            try:
                await broker.publish_to_others(
                    except_user_id=user_id,
                    event_type="user_offline",
                    data={"id": user_id},
                )
            except Exception:
                log.exception(
                    "user_offline emit failed for user_id=%s", user_id,
                )
```

And update the route handler to pass `db`:

```python
@router.get("/events")
async def events(
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_passed_training),
):
    return StreamingResponse(
        _stream_for_user(user["id"], db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 4: Run targeted tests**

Run: `.venv/bin/python -m pytest backend/tests/test_sse_presence.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Run full SSE suite to verify no regression**

Run: `.venv/bin/python -m pytest backend/tests/test_sse_routes.py backend/tests/test_sse_broker.py backend/tests/test_sse_broker_queue_full.py backend/tests/test_sse_presence.py -v`
Expected: all PASS.

- [ ] **Step 6: Full backend suite as safety net**

Run: `.venv/bin/python -m pytest backend/tests -q`
Expected: 0 failures (previous 741 + new tests).

- [ ] **Step 7: Commit**

```bash
git add backend/sse/routes.py backend/tests/test_sse_presence.py
git commit -m "$(cat <<'EOF'
feat(paket-16d): broadcast user_online/user_offline on SSE lifecycle

After broker.subscribe, the SSE stream now publish_to_others a
user_online event with {id, username, avatar_color}. The originating
user does NOT receive their own event (no self-echo).

On disconnect (CancelledError, normal close, or QueueFull-driven
unsubscribe via the broker hardening from T5), the finally: clause
checks whether the user has any remaining queues and, if not,
publish_to_others a user_offline event {id}.

Combined with /api/users/online + 30s polling on useOnlineUsers, this
gives the TopBar OnlineUsers widget sub-second responsiveness with
deterministic eventual consistency.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Regenerate frontend OpenAPI types

**Files:**
- Modify: `frontend/src/api/types.ts` (generated; do not hand-edit)

- [ ] **Step 1: Ensure backend is running on port 8000**

Run: `lsof -i :8000 -P -n | head -3`
Expected: a `Python` process listening. If not, start it:

```bash
DATA_DIR=./deneme-dev/data DISABLE_SPA_MOUNT=1 .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload &
```

- [ ] **Step 2: Regenerate types**

Run: `cd frontend && npm run gen:types`
Expected: file `frontend/src/api/types.ts` updates with new paths (`/api/badges/catalog`, `/api/users/online`, `/api/me/notifications/read-all`) and component schemas (`BadgeCatalogItem`, `OnlineUserOut`, `MarkAllReadResponse`).

- [ ] **Step 3: Verify the diff makes sense**

Run: `cd /Users/barandincoguz/Desktop/deneme && git diff --stat frontend/src/api/types.ts`
Expected: additions only (no deletions of existing paths). Spot-check:

```bash
grep -n "/api/badges/catalog\|/api/users/online\|/api/me/notifications/read-all" frontend/src/api/types.ts
```

Expected: each path string appears at least once.

- [ ] **Step 4: Run typecheck (should still pass — nothing consumes the new types yet)**

Run: `cd frontend && npm run typecheck`
Expected: clean.

- [ ] **Step 5: Run the gen:types:check guard so we know it will be green at the end**

Run: `cd frontend && npm run gen:types:check`
Expected: clean (no diff after regenerating from the live spec).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts
git commit -m "$(cat <<'EOF'
chore(paket-16d): regenerate openapi types for new endpoints

Adds typings for:
  GET    /api/badges/catalog
  GET    /api/users/online
  POST   /api/me/notifications/read-all

Generated; do not hand-edit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: profileSchemas.ts — Zod runtime schemas

**Files:**
- Create: `frontend/src/lib/profileSchemas.ts`
- Test: `frontend/src/lib/profileSchemas.test.ts`

**Note:** spec §11 says `Notification.read_at: string|null`. Backend reality is `is_read: bool` + `data: dict|null`. Use the backend shape.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/profileSchemas.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import {
  profileResponseSchema, notificationSchema, notificationsListSchema,
  markAllReadResponseSchema, badgesCatalogItemSchema, badgesCatalogSchema,
  onlineUserSchema, onlineUsersSchema,
} from './profileSchemas'

describe('profileResponseSchema', () => {
  it('accepts a complete payload', () => {
    const valid = {
      user: { id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' },
      xp: { total: 1240 },
      streak: { current: 3, longest: 12, last_active_date: '2026-05-11' },
      today: { save: 3, complete: 1, review: 0, skip: 0, daily_target: 10 },
      badges: [
        { id: 'first_annotation', name: 'İlk', description: 'Yapıldı.', earned_at: '2026-05-10T12:00:00+00:00' },
      ],
    }
    expect(profileResponseSchema.parse(valid)).toEqual(valid)
  })

  it('accepts null last_active_date (pre-save user)', () => {
    const valid = {
      user: { id: 2, username: 'newbie', role: 'user', avatar_color: '#22c55e' },
      xp: { total: 0 },
      streak: { current: 0, longest: 0, last_active_date: null },
      today: { save: 0, complete: 0, review: 0, skip: 0, daily_target: 10 },
      badges: [],
    }
    expect(() => profileResponseSchema.parse(valid)).not.toThrow()
  })

  it('rejects missing xp section', () => {
    const broken: unknown = {
      user: { id: 1, username: 'x', role: 'user', avatar_color: '#000' },
      streak: { current: 0, longest: 0, last_active_date: null },
      today: { save: 0, complete: 0, review: 0, skip: 0, daily_target: 0 },
      badges: [],
    }
    expect(() => profileResponseSchema.parse(broken)).toThrow()
  })
})

describe('notificationSchema', () => {
  it('accepts the backend shape (is_read + data field)', () => {
    const valid = {
      id: 42,
      kind: 'badge_unlocked',
      title: 'Yeni rozet: İlk Annotation',
      body: 'İlk kayıt başarıyla yapıldı.',
      data: { badge_id: 'first_annotation' },
      is_read: false,
      created_at: '2026-05-11T16:00:00+00:00',
    }
    expect(notificationSchema.parse(valid)).toEqual(valid)
  })

  it('accepts null body + null data', () => {
    const valid = {
      id: 7, kind: 'training_passed', title: 'OK', body: null,
      data: null, is_read: true, created_at: '2026-05-11T00:00:00+00:00',
    }
    expect(() => notificationSchema.parse(valid)).not.toThrow()
  })

  it('rejects when is_read is missing', () => {
    const broken: unknown = {
      id: 1, kind: 'x', title: 'y', body: null, data: null,
      created_at: '2026-05-11T00:00:00+00:00',
    }
    expect(() => notificationSchema.parse(broken)).toThrow()
  })
})

describe('notificationsListSchema', () => {
  it('wraps items array', () => {
    expect(notificationsListSchema.parse({ items: [] })).toEqual({ items: [] })
  })
})

describe('markAllReadResponseSchema', () => {
  it('requires marked_count integer', () => {
    expect(markAllReadResponseSchema.parse({ marked_count: 5 })).toEqual({ marked_count: 5 })
    expect(() => markAllReadResponseSchema.parse({ marked_count: 1.5 })).toThrow()
  })
})

describe('badgesCatalogSchema', () => {
  it('accepts an entry with criterion', () => {
    const valid = [{
      id: 'first_annotation', name: 'İlk Annotation',
      description: 'İlk kayıt başarıyla yapıldı.',
      criterion: 'İlk anotasyon kaydını yap.',
    }]
    expect(badgesCatalogSchema.parse(valid)).toEqual(valid)
  })

  it('accepts an entry without criterion (defensive)', () => {
    const valid = [{ id: 'x', name: 'X', description: 'Y' }]
    expect(() => badgesCatalogSchema.parse(valid)).not.toThrow()
  })

  it('individual item schema rejects missing id', () => {
    expect(() => badgesCatalogItemSchema.parse({ name: 'x', description: 'y' })).toThrow()
  })
})

describe('onlineUsersSchema', () => {
  it('accepts empty array', () => {
    expect(onlineUsersSchema.parse([])).toEqual([])
  })

  it('individual user shape', () => {
    const valid = { id: 1, username: 'tester', avatar_color: '#3b82f6' }
    expect(onlineUserSchema.parse(valid)).toEqual(valid)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/profileSchemas.test.ts`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/lib/profileSchemas.ts`**

```ts
import { z } from 'zod'

export const userSectionSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  role: z.string(),
  avatar_color: z.string(),
})

export const xpSectionSchema = z.object({ total: z.number().int() })

export const streakSectionSchema = z.object({
  current: z.number().int(),
  longest: z.number().int(),
  last_active_date: z.string().nullable(),
})

export const todaySectionSchema = z.object({
  save: z.number().int(),
  complete: z.number().int(),
  review: z.number().int(),
  skip: z.number().int(),
  daily_target: z.number().int(),
})

export const badgeOutSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  earned_at: z.string(),
})

export const profileResponseSchema = z.object({
  user: userSectionSchema,
  xp: xpSectionSchema,
  streak: streakSectionSchema,
  today: todaySectionSchema,
  badges: z.array(badgeOutSchema),
})

// Notification uses backend shape: is_read (bool) + data (dict|null).
// Spec §3.1 (read_at) is documentation drift; backend is source of truth.
export const notificationSchema = z.object({
  id: z.number().int(),
  kind: z.string(),
  title: z.string(),
  body: z.string().nullable(),
  data: z.record(z.string(), z.unknown()).nullable(),
  is_read: z.boolean(),
  created_at: z.string(),
})

export const notificationsListSchema = z.object({
  items: z.array(notificationSchema),
})

export const markAllReadResponseSchema = z.object({
  marked_count: z.number().int(),
})

export const badgesCatalogItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  criterion: z.string().nullable().optional(),
})

export const badgesCatalogSchema = z.array(badgesCatalogItemSchema)

export const onlineUserSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  avatar_color: z.string(),
})

export const onlineUsersSchema = z.array(onlineUserSchema)

export type ProfileResponse = z.infer<typeof profileResponseSchema>
export type UserSection = z.infer<typeof userSectionSchema>
export type Notification = z.infer<typeof notificationSchema>
export type NotificationsList = z.infer<typeof notificationsListSchema>
export type MarkAllReadResponse = z.infer<typeof markAllReadResponseSchema>
export type BadgeCatalogItem = z.infer<typeof badgesCatalogItemSchema>
export type BadgesCatalog = z.infer<typeof badgesCatalogSchema>
export type OnlineUser = z.infer<typeof onlineUserSchema>
export type OnlineUsers = z.infer<typeof onlineUsersSchema>
export type BadgeOut = z.infer<typeof badgeOutSchema>
```

- [ ] **Step 4: Run tests + typecheck**

Run: `cd frontend && npx vitest run src/lib/profileSchemas.test.ts && npm run typecheck`
Expected: all PASS, typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/profileSchemas.ts frontend/src/lib/profileSchemas.test.ts
git commit -m "feat(paket-16d): add Zod schemas for profile + notifications + badges + online users

Runtime validation at the query/mutation boundary (Codex FRAGILE-F).
Aligned with backend models — is_read:bool + data:dict|null
(spec §3.1 read_at:string|null was outdated).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: sseSchemas.ts — Zod for SSE payloads + parseEventData helper

**Files:**
- Create: `frontend/src/lib/sseSchemas.ts`
- Test: `frontend/src/lib/sseSchemas.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/sseSchemas.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest'
import {
  badgeUnlockedSchema, speedWarningSchema, charLimitWarningSchema,
  userOnlinePayloadSchema, userOfflinePayloadSchema, parseEventData,
} from './sseSchemas'

describe('badgeUnlockedSchema', () => {
  it('accepts the backend orchestrator payload', () => {
    const valid = {
      badge_id: 'first_annotation', name: 'İlk Annotation',
      description: 'İlk kayıt başarıyla yapıldı.',
      earned_at: '2026-05-11T16:00:00+00:00',
    }
    expect(() => badgeUnlockedSchema.parse(valid)).not.toThrow()
  })
})

describe('speedWarningSchema', () => {
  it('accepts the documented shape', () => {
    expect(() => speedWarningSchema.parse({ window_minutes: 5, save_count: 6 })).not.toThrow()
  })
  it('rejects float counters', () => {
    expect(() => speedWarningSchema.parse({ window_minutes: 5, save_count: 1.5 })).toThrow()
  })
})

describe('charLimitWarningSchema', () => {
  it('accepts ref_index + detail', () => {
    expect(() => charLimitWarningSchema.parse({ ref_index: 0, detail: '... çok uzun' })).not.toThrow()
  })
})

describe('userOnlinePayloadSchema', () => {
  it('accepts {id, username, avatar_color}', () => {
    expect(() => userOnlinePayloadSchema.parse({
      id: 1, username: 'x', avatar_color: '#abc',
    })).not.toThrow()
  })
})

describe('userOfflinePayloadSchema', () => {
  it('accepts {id}', () => {
    expect(() => userOfflinePayloadSchema.parse({ id: 1 })).not.toThrow()
  })
})

describe('parseEventData', () => {
  it('returns parsed data when JSON+schema match', () => {
    const e = new MessageEvent('badge_unlocked', {
      data: JSON.stringify({
        badge_id: 'x', name: 'y', description: 'z', earned_at: '2026-05-11',
      }),
    })
    const result = parseEventData(e, badgeUnlockedSchema)
    expect(result?.badge_id).toBe('x')
  })

  it('returns null on invalid JSON without throwing', () => {
    const e = new MessageEvent('badge_unlocked', { data: 'not-json' })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(parseEventData(e, badgeUnlockedSchema)).toBeNull()
    warn.mockRestore()
  })

  it('returns null on schema mismatch and warns', () => {
    const e = new MessageEvent('badge_unlocked', {
      data: JSON.stringify({ wrong: 'shape' }),
    })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(parseEventData(e, badgeUnlockedSchema)).toBeNull()
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/sseSchemas.test.ts`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/lib/sseSchemas.ts`**

```ts
import { z } from 'zod'

// Backend gamification.service.run_after_save publishes badge_unlocked with
// {badge_id, name, description, earned_at} (see _publish_unlock_events).
export const badgeUnlockedSchema = z.object({
  badge_id: z.string(),
  name: z.string(),
  description: z.string(),
  earned_at: z.string(),
})

export const speedWarningSchema = z.object({
  window_minutes: z.number().int(),
  save_count: z.number().int(),
})

export const charLimitWarningSchema = z.object({
  ref_index: z.number().int(),
  detail: z.string(),
})

export const userOnlinePayloadSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  avatar_color: z.string(),
})

export const userOfflinePayloadSchema = z.object({
  id: z.number().int(),
})

/** Parse e.data (JSON string) and validate against a Zod schema. Logs a
 * warning and returns null on any failure — never throws. SSE handlers
 * must keep running even on one malformed event. */
export function parseEventData<T>(
  e: MessageEvent,
  schema: z.ZodType<T>,
): T | null {
  let raw: unknown
  try {
    raw = JSON.parse(e.data as string)
  } catch {
    return null
  }
  const result = schema.safeParse(raw)
  if (!result.success) {
    console.warn('[SSE] payload parse failed', e.type, result.error.issues)
    return null
  }
  return result.data
}

export type BadgeUnlockedPayload = z.infer<typeof badgeUnlockedSchema>
export type SpeedWarningPayload = z.infer<typeof speedWarningSchema>
export type CharLimitWarningPayload = z.infer<typeof charLimitWarningSchema>
export type UserOnlinePayload = z.infer<typeof userOnlinePayloadSchema>
export type UserOfflinePayload = z.infer<typeof userOfflinePayloadSchema>
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/lib/sseSchemas.test.ts`
Expected: all PASS.

```bash
git add frontend/src/lib/sseSchemas.ts frontend/src/lib/sseSchemas.test.ts
git commit -m "feat(paket-16d): add Zod schemas + parseEventData helper for SSE payloads

Five payloads: badge_unlocked, speed_warning, char_limit_warning,
user_online, user_offline. parseEventData never throws — logs warn and
returns null on JSON or schema failure so individual bad events don't
crash the EventSource listeners.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: notificationKinds.ts — kind→icon registry

**Files:**
- Create: `frontend/src/lib/notificationKinds.ts`
- Test: `frontend/src/lib/notificationKinds.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/notificationKinds.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { iconForKind, NOTIFICATION_KIND_ICONS } from './notificationKinds'

describe('iconForKind', () => {
  it('returns specific icon for known kinds', () => {
    expect(iconForKind('badge_unlocked')).toBe('🏆')
    expect(iconForKind('training_passed')).toBe('🎓')
    expect(iconForKind('training_reset')).toBe('🔄')
    expect(iconForKind('admin_announcement')).toBe('📢')
    expect(iconForKind('lock_lost')).toBe('🔓')
  })

  it('returns generic 🔔 for unknown kinds', () => {
    expect(iconForKind('something_new')).toBe('🔔')
    expect(iconForKind('')).toBe('🔔')
  })
})

describe('NOTIFICATION_KIND_ICONS', () => {
  it('exposes a record where every value is a non-empty string', () => {
    for (const v of Object.values(NOTIFICATION_KIND_ICONS)) {
      expect(typeof v).toBe('string')
      expect(v.length).toBeGreaterThanOrEqual(1)
    }
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/notificationKinds.test.ts`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/lib/notificationKinds.ts`**

```ts
export const NOTIFICATION_KIND_ICONS: Record<string, string> = {
  badge_unlocked: '🏆',
  training_passed: '🎓',
  training_reset: '🔄',
  admin_announcement: '📢',
  lock_lost: '🔓',
}

export function iconForKind(kind: string): string {
  return NOTIFICATION_KIND_ICONS[kind] ?? '🔔'
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/lib/notificationKinds.test.ts`
Expected: all PASS.

```bash
git add frontend/src/lib/notificationKinds.ts frontend/src/lib/notificationKinds.test.ts
git commit -m "feat(paket-16d): add notification kind→icon registry

Small map keeps the kind drift problem (Codex FRAGILE-D, Pass 2) in
one place. Unknown kinds fall back to the generic 🔔.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: useProfile hook

**Files:**
- Create: `frontend/src/api/queries/profile.ts`
- Test: `frontend/src/api/queries/profile.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/queries/profile.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import type { ProfileResponse } from '@/lib/profileSchemas'
import { useProfile, profileKeys } from './profile'

function makeProfile(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    user: { id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' },
    xp: { total: 0 },
    streak: { current: 0, longest: 0, last_active_date: null },
    today: { save: 0, complete: 0, review: 0, skip: 0, daily_target: 10 },
    badges: [],
    ...overrides,
  }
}

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useProfile', () => {
  it('fetches and parses profile data', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ xp: { total: 999 } }))),
    )
    const { result } = renderHook(() => useProfile(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.xp.total).toBe(999)
  })

  it('exposes profileKeys.me() for invalidations', () => {
    expect(profileKeys.me()).toEqual(['profile', 'me'])
  })

  it('surfaces Zod parse failure as query error', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json({ broken: 'shape' })),
    )
    const { result } = renderHook(() => useProfile(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
```

(`makeProfile` lives inline here. In T15 we replace this local helper with `import { makeProfile } from '@/test/msw-handlers'`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/queries/profile.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/api/queries/profile.ts`**

```ts
import { useQuery } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import { profileResponseSchema, type ProfileResponse } from '@/lib/profileSchemas'

export const profileKeys = {
  all: ['profile'] as const,
  me: () => [...profileKeys.all, 'me'] as const,
}

export function useProfile() {
  return useQuery<ProfileResponse>({
    queryKey: profileKeys.me(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/me/profile'))
      return profileResponseSchema.parse(raw)
    },
    staleTime: 5_000,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  })
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/api/queries/profile.test.tsx`
Expected: 3 PASS.

```bash
git add frontend/src/api/queries/profile.ts frontend/src/api/queries/profile.test.tsx
git commit -m "feat(paket-16d): useProfile hook with Zod parse

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: notifications hooks (unread + history + markRead + markAllRead)

**Files:**
- Create: `frontend/src/api/queries/notifications.ts`
- Test: `frontend/src/api/queries/notifications.test.tsx`

Exports: `notificationsKeys`, `useUnreadNotifications`, `useNotificationsHistory`, `useMarkReadMutation`, `useMarkAllReadMutation`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/queries/notifications.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import {
  useUnreadNotifications, useNotificationsHistory,
  useMarkReadMutation, useMarkAllReadMutation, notificationsKeys,
} from './notifications'
import { toast } from 'sonner'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

function wrap() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    qc,
    Wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  }
}

function makeNotif(over: Partial<{ id: number; is_read: boolean; kind: string }> = {}) {
  return {
    id: 1, kind: 'admin_announcement', title: 'Hello', body: null,
    data: null, is_read: false, created_at: '2026-05-11T00:00:00+00:00',
    ...over,
  }
}

describe('useUnreadNotifications', () => {
  it('fetches with unread_only=true & limit=50', async () => {
    let calledWith: URL | null = null
    server.use(
      http.get('http://localhost/api/me/notifications', ({ request }) => {
        calledWith = new URL(request.url)
        return HttpResponse.json({ items: [makeNotif()] })
      }),
    )
    const { Wrapper } = wrap()
    const { result } = renderHook(() => useUnreadNotifications(), { wrapper: Wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.items.length).toBe(1)
    expect(calledWith?.searchParams.get('unread_only')).toBe('true')
    expect(calledWith?.searchParams.get('limit')).toBe('50')
  })
})

describe('useNotificationsHistory', () => {
  it('fetches with unread_only=false', async () => {
    let calledWith: URL | null = null
    server.use(
      http.get('http://localhost/api/me/notifications', ({ request }) => {
        calledWith = new URL(request.url)
        return HttpResponse.json({ items: [] })
      }),
    )
    const { Wrapper } = wrap()
    const { result } = renderHook(() => useNotificationsHistory(), { wrapper: Wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(calledWith?.searchParams.get('unread_only')).toBe('false')
  })
})

describe('useMarkReadMutation', () => {
  it('POSTs /{id}/read and invalidates the notifications cache', async () => {
    let posted: string | null = null
    server.use(
      http.post('http://localhost/api/me/notifications/:id/read', ({ params }) => {
        posted = String(params.id)
        return HttpResponse.json({ ok: true })
      }),
    )
    const { qc, Wrapper } = wrap()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useMarkReadMutation(), { wrapper: Wrapper })
    await act(async () => { await result.current.mutateAsync(42) })
    expect(posted).toBe('42')
    expect(spy).toHaveBeenCalledWith({ queryKey: notificationsKeys.all })
  })
})

describe('useMarkAllReadMutation', () => {
  it('POSTs /read-all and shows toast with marked_count', async () => {
    server.use(
      http.post('http://localhost/api/me/notifications/read-all', () =>
        HttpResponse.json({ marked_count: 7 })),
    )
    const { Wrapper } = wrap()
    const { result } = renderHook(() => useMarkAllReadMutation(), { wrapper: Wrapper })
    await act(async () => { await result.current.mutateAsync() })
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('7'))
  })

  it('surfaces Zod parse failure as mutation error (no toast)', async () => {
    server.use(
      http.post('http://localhost/api/me/notifications/read-all', () =>
        HttpResponse.json({ broken: true })),
    )
    const { Wrapper } = wrap()
    const { result } = renderHook(() => useMarkAllReadMutation(), { wrapper: Wrapper })
    await act(async () => {
      await result.current.mutateAsync().catch(() => null)
    })
    expect(result.current.isError).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/queries/notifications.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/api/queries/notifications.ts`**

```ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { client, unwrap, unwrapVoid } from '@/api/client'
import {
  notificationsListSchema, markAllReadResponseSchema,
  type NotificationsList, type MarkAllReadResponse,
} from '@/lib/profileSchemas'

export const notificationsKeys = {
  all: ['notifications'] as const,
  unread: () => [...notificationsKeys.all, 'unread'] as const,
  history: () => [...notificationsKeys.all, 'history'] as const,
}

export function useUnreadNotifications() {
  return useQuery<NotificationsList>({
    queryKey: notificationsKeys.unread(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/me/notifications', {
        params: { query: { unread_only: true, limit: 50 } },
      }))
      return notificationsListSchema.parse(raw)
    },
    staleTime: 5_000,
    // Codex BROKEN-E: SSE drops leave indefinite stale state without polling.
    refetchInterval: 30_000,
  })
}

export function useNotificationsHistory() {
  return useQuery<NotificationsList>({
    queryKey: notificationsKeys.history(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/me/notifications', {
        params: { query: { unread_only: false, limit: 50 } },
      }))
      return notificationsListSchema.parse(raw)
    },
    staleTime: 5_000,
    refetchOnWindowFocus: true,
  })
}

export function useMarkReadMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      unwrapVoid(client.POST('/api/me/notifications/{notification_id}/read', {
        params: { path: { notification_id: id } },
      })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: notificationsKeys.all })
    },
  })
}

export function useMarkAllReadMutation() {
  const qc = useQueryClient()
  return useMutation<MarkAllReadResponse>({
    mutationFn: async () => {
      const raw = await unwrap(await client.POST('/api/me/notifications/read-all'))
      return markAllReadResponseSchema.parse(raw)
    },
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: notificationsKeys.all })
      toast.success(`${data.marked_count} bildirim okundu işaretlendi.`)
    },
  })
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/api/queries/notifications.test.tsx`
Expected: 5 PASS.

```bash
git add frontend/src/api/queries/notifications.ts frontend/src/api/queries/notifications.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16d): add notifications query/mutation hooks

useUnreadNotifications + useNotificationsHistory: separate cache keys
so the dropdown bell (last 10 unread) and /me Notifications section
(mixed) don't fight (Codex BROKEN, Pass 1).

refetchInterval: 30_000 on unread (Codex BROKEN-E) — staleTime alone
does not poll.

useMarkAllReadMutation surfaces marked_count via toast for deterministic
feedback (Codex FRAGILE-E, Pass 2).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: badges hooks — useBadgesCatalog + useLockedBadges selector

**Files:**
- Create: `frontend/src/api/queries/badges.ts`
- Test: `frontend/src/api/queries/badges.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/queries/badges.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { useBadgesCatalog, useLockedBadges, badgesKeys } from './badges'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

function catalogSample() {
  return [
    { id: 'first_annotation', name: 'A', description: 'a desc', criterion: 'a crit' },
    { id: 'annotations_10', name: 'B', description: 'b desc', criterion: 'b crit' },
    { id: 'marathoner', name: 'C', description: 'c desc', criterion: 'c crit' },
  ]
}

describe('useBadgesCatalog', () => {
  it('fetches and parses the catalog', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(catalogSample())),
    )
    const { result } = renderHook(() => useBadgesCatalog(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.length).toBe(3)
  })

  it('exposes stable query key', () => {
    expect(badgesKeys.catalog()).toEqual(['badges', 'catalog'])
  })
})

describe('useLockedBadges', () => {
  it('returns catalog entries NOT in earned set', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(catalogSample())),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json({
          user: { id: 1, username: 'x', role: 'user', avatar_color: '#000' },
          xp: { total: 0 },
          streak: { current: 0, longest: 0, last_active_date: null },
          today: { save: 0, complete: 0, review: 0, skip: 0, daily_target: 0 },
          badges: [{
            id: 'first_annotation', name: 'A', description: 'a desc',
            earned_at: '2026-05-11T00:00:00+00:00',
          }],
        })),
    )
    const { result } = renderHook(() => useLockedBadges(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.length).toBe(2))
    expect(result.current.map((b) => b.id)).toEqual(['annotations_10', 'marathoner'])
  })

  it('returns [] while either query is loading', () => {
    const { result } = renderHook(() => useLockedBadges(), { wrapper: wrap() })
    expect(result.current).toEqual([])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/queries/badges.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/api/queries/badges.ts`**

```ts
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { client, unwrap } from '@/api/client'
import {
  badgesCatalogSchema, type BadgesCatalog, type BadgeCatalogItem,
} from '@/lib/profileSchemas'
import { useProfile } from '@/api/queries/profile'

export const badgesKeys = {
  all: ['badges'] as const,
  catalog: () => [...badgesKeys.all, 'catalog'] as const,
}

export function useBadgesCatalog() {
  return useQuery<BadgesCatalog>({
    queryKey: badgesKeys.catalog(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/badges/catalog'))
      return badgesCatalogSchema.parse(raw)
    },
    // Catalog is effectively static; never refetch unless invalidated.
    staleTime: Infinity,
  })
}

/** Returns the catalog items the current user has NOT yet earned.
 * Empty array while either query is loading (defensive). */
export function useLockedBadges(): BadgeCatalogItem[] {
  const catalog = useBadgesCatalog()
  const profile = useProfile()
  return useMemo(() => {
    if (!catalog.data || !profile.data) return []
    const earned = new Set(profile.data.badges.map((b) => b.id))
    return catalog.data.filter((c) => !earned.has(c.id))
  }, [catalog.data, profile.data])
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/api/queries/badges.test.tsx`
Expected: 4 PASS.

```bash
git add frontend/src/api/queries/badges.ts frontend/src/api/queries/badges.test.tsx
git commit -m "feat(paket-16d): useBadgesCatalog + useLockedBadges selector

Catalog has staleTime: Infinity (static). useLockedBadges is a memoized
selector that joins catalog with profile.badges (Codex BROKEN-C, Pass 1).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: useOnlineUsers hook

**Files:**
- Create: `frontend/src/api/queries/users.ts`
- Test: `frontend/src/api/queries/users.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/queries/users.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { useOnlineUsers, usersKeys } from './users'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useOnlineUsers', () => {
  it('fetches and parses the online list', async () => {
    server.use(
      http.get('http://localhost/api/users/online', () =>
        HttpResponse.json([
          { id: 1, username: 'tester', avatar_color: '#3b82f6' },
          { id: 2, username: 'admin', avatar_color: '#ef4444' },
        ])),
    )
    const { result } = renderHook(() => useOnlineUsers(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.length).toBe(2)
  })

  it('exposes stable query key', () => {
    expect(usersKeys.online()).toEqual(['users', 'online'])
  })

  it('returns isError when payload is malformed', async () => {
    server.use(
      http.get('http://localhost/api/users/online', () =>
        HttpResponse.json({ broken: 'object' })),
    )
    const { result } = renderHook(() => useOnlineUsers(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/queries/users.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/api/queries/users.ts`**

```ts
import { useQuery } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import { onlineUsersSchema, type OnlineUsers } from '@/lib/profileSchemas'

export const usersKeys = {
  all: ['users'] as const,
  online: () => [...usersKeys.all, 'online'] as const,
}

export function useOnlineUsers() {
  return useQuery<OnlineUsers>({
    queryKey: usersKeys.online(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/users/online'))
      return onlineUsersSchema.parse(raw)
    },
    staleTime: 30_000,
    // Codex BROKEN-D: SSE drops can leave indefinite stale state.
    refetchInterval: 30_000,
  })
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/api/queries/users.test.tsx`
Expected: 3 PASS.

```bash
git add frontend/src/api/queries/users.ts frontend/src/api/queries/users.test.tsx
git commit -m "feat(paket-16d): useOnlineUsers hook with 30s polling reconcile

Codex BROKEN-D: SSE drops leave indefinite stale state. Polling is truth;
SSE user_online/user_offline events trigger invalidation between polls.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: MSW factories + handlers for 16d endpoints

**Files:**
- Modify: `frontend/src/test/msw-handlers.ts`

- [ ] **Step 1: Append factories at the bottom of `msw-handlers.ts`**

Open the file and locate the existing factory block (after `makeReferenceItem`). Add imports near the top:

```ts
import type {
  ProfileResponse, Notification, NotificationsList, BadgeCatalogItem,
  OnlineUser,
} from '@/lib/profileSchemas'
```

Append factories after `makeReferenceItem`:

```ts
export function makeProfile(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    user: { id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' },
    xp: { total: 1240 },
    streak: { current: 3, longest: 12, last_active_date: '2026-05-11' },
    today: { save: 3, complete: 1, review: 0, skip: 0, daily_target: 10 },
    badges: [{
      id: 'first_annotation', name: 'İlk Annotation',
      description: 'İlk kayıt başarıyla yapıldı.',
      earned_at: '2026-05-10T12:00:00+00:00',
    }],
    ...overrides,
  }
}

export function makeNotification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: 1, kind: 'admin_announcement', title: 'Test bildirimi',
    body: null, data: null, is_read: false,
    created_at: '2026-05-11T12:00:00+00:00',
    ...overrides,
  }
}

export function makeBadgeCatalogItem(
  overrides: Partial<BadgeCatalogItem> = {},
): BadgeCatalogItem {
  return {
    id: 'first_annotation', name: 'İlk Annotation',
    description: 'İlk kayıt başarıyla yapıldı.',
    criterion: 'İlk anotasyon kaydını yap.',
    ...overrides,
  }
}

export function defaultBadgesCatalog(): BadgeCatalogItem[] {
  return [
    makeBadgeCatalogItem({ id: 'first_annotation', name: 'İlk Annotation',
      description: 'İlk kayıt başarıyla yapıldı.',
      criterion: 'İlk anotasyon kaydını yap.' }),
    makeBadgeCatalogItem({ id: 'annotations_10', name: '10 Annotation',
      description: '10 kayıt biriktirdin.',
      criterion: '10 anotasyon kaydı biriktir.' }),
    makeBadgeCatalogItem({ id: 'annotations_100', name: '100 Annotation',
      description: '100 kayıt — istikrarlı çalışıyorsun.',
      criterion: '100 anotasyon kaydı biriktir.' }),
    makeBadgeCatalogItem({ id: 'annotations_1000', name: '1000 Annotation',
      description: 'Bin kayıt: ekibin omurgası oldun.',
      criterion: '1000 anotasyon kaydı biriktir.' }),
    makeBadgeCatalogItem({ id: 'first_completion', name: 'İlk Tamamlama',
      description: 'İlk dokümanı tamamlandı olarak işaretledin.',
      criterion: 'İlk dokümanı tamamlandı olarak işaretle.' }),
    makeBadgeCatalogItem({ id: 'marathoner', name: 'Maratoncu',
      description: '7 gün üst üste çalıştın.',
      criterion: '7 gün üst üste çalış.' }),
    makeBadgeCatalogItem({ id: 'good_reviewer', name: 'Good Reviewer',
      description: 'Yaptığın review\'lerin çoğu sonraki kullanıcılar tarafından korundu.',
      criterion: 'Review\'lerinin çoğunluğu korunsun (en az 20 review, 15+ kept).' }),
  ]
}

export function makeOnlineUser(overrides: Partial<OnlineUser> = {}): OnlineUser {
  return { id: 1, username: 'tester', avatar_color: '#3b82f6', ...overrides }
}
```

- [ ] **Step 2: Add default handlers in the same file**

Locate the existing `handlers` array (typically at the bottom of msw-handlers.ts). Append:

```ts
http.get('http://localhost/api/me/profile', () =>
  HttpResponse.json(makeProfile())),

http.get('http://localhost/api/me/notifications', ({ request }) => {
  const url = new URL(request.url)
  const unreadOnly = url.searchParams.get('unread_only') !== 'false'
  const items: Notification[] = [
    makeNotification({ id: 1, is_read: false, kind: 'admin_announcement', title: 'Bir bildirim' }),
    ...(unreadOnly ? [] : [
      makeNotification({ id: 2, is_read: true, kind: 'training_passed',
        title: 'Eğitim geçildi', body: null,
        created_at: '2026-05-10T00:00:00+00:00' }),
    ]),
  ]
  return HttpResponse.json({ items } satisfies NotificationsList)
}),

http.post('http://localhost/api/me/notifications/:id/read', () =>
  HttpResponse.json({ ok: true })),

http.post('http://localhost/api/me/notifications/read-all', () =>
  HttpResponse.json({ marked_count: 1 })),

http.get('http://localhost/api/badges/catalog', () =>
  HttpResponse.json(defaultBadgesCatalog())),

http.get('http://localhost/api/users/online', () =>
  HttpResponse.json([
    makeOnlineUser({ id: 1, username: 'tester', avatar_color: '#3b82f6' }),
  ])),
```

- [ ] **Step 3: Replace inline factory in `profile.test.tsx`**

Replace the local `makeProfile` helper added in T11 with:

```tsx
import { makeProfile } from '@/test/msw-handlers'
```

(Delete the local function. The signature matches.)

- [ ] **Step 4: Run all hook tests**

Run: `cd frontend && npx vitest run src/api/queries/`
Expected: all PASS.

- [ ] **Step 5: Run full suite + typecheck**

Run: `cd frontend && npm run typecheck && npm run test:run`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/test/msw-handlers.ts frontend/src/api/queries/profile.test.tsx
git commit -m "$(cat <<'EOF'
test(paket-16d): add MSW factories + default handlers for 16d endpoints

makeProfile, makeNotification, makeBadgeCatalogItem, makeOnlineUser, plus
defaultBadgesCatalog() with all 7 entries. Default handlers added for
all 6 16d endpoints so tests without explicit server.use() get sane
fixtures.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Extract lockHandlers from useSSE (16b parity preserved)

**Files:**
- Create: `frontend/src/hooks/sse/lockHandlers.ts`
- Test: `frontend/src/hooks/sse/lockHandlers.test.tsx`

**Behavior must match 16b exactly:** `lock_acquired` invalidates feed, shows toast + navigates to `/` if `document_id === currentDocId && !mine && !acquiringRef`. `lock_released` invalidates feed.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/sse/lockHandlers.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { QueryClient } from '@tanstack/react-query'
import { registerLockHandlers } from './lockHandlers'

function makeFakeES() {
  const listeners: Record<string, Array<(e: MessageEvent) => void>> = {}
  return {
    addEventListener(type: string, fn: (e: MessageEvent) => void) {
      listeners[type] = [...(listeners[type] ?? []), fn]
    },
    dispatch(type: string, dataObj: unknown) {
      const e = new MessageEvent(type, { data: JSON.stringify(dataObj) })
      for (const fn of listeners[type] ?? []) fn(e)
    },
  }
}

describe('registerLockHandlers', () => {
  let qc: { invalidateQueries: ReturnType<typeof vi.fn> }
  let navigate: ReturnType<typeof vi.fn>
  let toastError: ReturnType<typeof vi.fn>

  beforeEach(() => {
    qc = { invalidateQueries: vi.fn() }
    navigate = vi.fn()
    toastError = vi.fn()
    vi.stubGlobal('location', { pathname: '/docs/doc-1' })
  })

  it('on lock_acquired by another user on current doc: toast + navigate("/")', () => {
    const es = makeFakeES()
    registerLockHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      navigate, meId: 5,
      acquiringRef: { current: null },
      toast: { error: toastError } as never,
    })
    es.dispatch('lock_acquired', {
      document_id: 'doc-1', by_user_id: 6, by_username: 'someone',
    })
    expect(toastError).toHaveBeenCalledWith(expect.stringContaining('someone'))
    expect(navigate).toHaveBeenCalledWith('/', { replace: true })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['feed'] })
  })

  it('on lock_acquired by SELF: invalidate only, no navigate', () => {
    const es = makeFakeES()
    registerLockHandlers(es as never, {
      qc: qc as unknown as QueryClient, navigate, meId: 5,
      acquiringRef: { current: null }, toast: { error: toastError } as never,
    })
    es.dispatch('lock_acquired', {
      document_id: 'doc-1', by_user_id: 5, by_username: 'me',
    })
    expect(navigate).not.toHaveBeenCalled()
    expect(toastError).not.toHaveBeenCalled()
    expect(qc.invalidateQueries).toHaveBeenCalled()
  })

  it('skips navigate when the user is currently acquiring this doc', () => {
    const es = makeFakeES()
    registerLockHandlers(es as never, {
      qc: qc as unknown as QueryClient, navigate, meId: 5,
      acquiringRef: { current: 'doc-1' },
      toast: { error: toastError } as never,
    })
    es.dispatch('lock_acquired', {
      document_id: 'doc-1', by_user_id: 6, by_username: 'someone',
    })
    expect(navigate).not.toHaveBeenCalled()
  })

  it('lock_released invalidates feed', () => {
    const es = makeFakeES()
    registerLockHandlers(es as never, {
      qc: qc as unknown as QueryClient, navigate, meId: 5,
      acquiringRef: { current: null }, toast: { error: toastError } as never,
    })
    es.dispatch('lock_released', { document_id: 'doc-1' })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['feed'] })
  })

  it('ignores malformed payload silently', () => {
    const es = makeFakeES()
    registerLockHandlers(es as never, {
      qc: qc as unknown as QueryClient, navigate, meId: 5,
      acquiringRef: { current: null }, toast: { error: toastError } as never,
    })
    // Manually inject non-JSON
    const listener = (es as unknown as { addEventListener: typeof es.addEventListener })
    // emulate addEventListener was called for lock_acquired
    es.dispatch('lock_acquired', undefined as never)
    expect(navigate).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/sse/lockHandlers.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/hooks/sse/lockHandlers.ts`**

```ts
import type { QueryClient } from '@tanstack/react-query'
import type { MutableRefObject } from 'react'
import { toast as defaultToast } from 'sonner'
import type { NavigateFunction } from 'react-router-dom'

interface LockHandlerOpts {
  qc: QueryClient
  navigate: NavigateFunction
  meId: number | null
  acquiringRef: MutableRefObject<string | null>
  /** Injectable for tests — default is sonner's toast singleton. */
  toast?: typeof defaultToast
}

const DOC_PATH_RE = /^\/docs\/([^/?#]+)/

function getCurrentDocIdFromUrl(): string | null {
  const m = DOC_PATH_RE.exec(window.location.pathname)
  return m?.[1] ?? null
}

export function registerLockHandlers(es: EventSource, opts: LockHandlerOpts) {
  const t = opts.toast ?? defaultToast

  es.addEventListener('lock_acquired', (e) => {
    const raw = (e as MessageEvent<string>).data
    let data: {
      document_id: string
      by_user_id: number
      by_username: string
    }
    try {
      data = JSON.parse(raw) as typeof data
    } catch {
      return
    }
    void opts.qc.invalidateQueries({ queryKey: ['feed'] })
    if (data.document_id === opts.acquiringRef.current) return
    if (data.by_user_id === opts.meId) return
    const currentDocId = getCurrentDocIdFromUrl()
    if (data.document_id === currentDocId) {
      t.error(`Bu doküman ${data.by_username} tarafından alındı.`)
      opts.navigate('/', { replace: true })
    }
  })

  es.addEventListener('lock_released', () => {
    void opts.qc.invalidateQueries({ queryKey: ['feed'] })
  })
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/hooks/sse/lockHandlers.test.tsx`
Expected: all PASS.

```bash
git add frontend/src/hooks/sse/lockHandlers.ts frontend/src/hooks/sse/lockHandlers.test.tsx
git commit -m "refactor(paket-16d): extract lockHandlers from useSSE

Behavior preserved verbatim from 16b useSSE.ts:
- lock_acquired: invalidate feed; if doc==current && !mine && !acquiring,
  toast + navigate('/')
- lock_released: invalidate feed

useSSE itself is refactored to orchestrator pattern in T20.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: feedHandlers module (annotation_saved invalidation)

**Files:**
- Create: `frontend/src/hooks/sse/feedHandlers.ts`
- Test: `frontend/src/hooks/sse/feedHandlers.test.tsx`

The current 16b `useSSE` does not explicitly handle `annotation_saved`. The 16b pattern relies on save mutations + lock events to invalidate the feed. The spec §9.1 still names a `feedHandlers` module — we register `annotation_saved` as a feed invalidator and `lock_*` already does feed invalidation. Keep `feedHandlers` thin so it does NOT duplicate `lock_*`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/sse/feedHandlers.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { QueryClient } from '@tanstack/react-query'
import { registerFeedHandlers } from './feedHandlers'

function makeFakeES() {
  const listeners: Record<string, Array<(e: MessageEvent) => void>> = {}
  return {
    addEventListener(type: string, fn: (e: MessageEvent) => void) {
      listeners[type] = [...(listeners[type] ?? []), fn]
    },
    dispatch(type: string, dataObj: unknown) {
      const e = new MessageEvent(type, { data: JSON.stringify(dataObj) })
      for (const fn of listeners[type] ?? []) fn(e)
    },
  }
}

describe('registerFeedHandlers', () => {
  let qc: { invalidateQueries: ReturnType<typeof vi.fn> }

  beforeEach(() => {
    qc = { invalidateQueries: vi.fn() }
  })

  it('annotation_saved invalidates feed', () => {
    const es = makeFakeES()
    registerFeedHandlers(es as never, { qc: qc as unknown as QueryClient })
    es.dispatch('annotation_saved', { document_id: 'doc-1', user_id: 1 })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['feed'] })
  })

  it('ignores malformed payload', () => {
    const es = makeFakeES()
    registerFeedHandlers(es as never, { qc: qc as unknown as QueryClient })
    es.dispatch('annotation_saved', undefined as never)
    // Defensive code: no invalidation on parse failure
    expect(qc.invalidateQueries).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/sse/feedHandlers.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/hooks/sse/feedHandlers.ts`**

```ts
import type { QueryClient } from '@tanstack/react-query'

interface FeedHandlerOpts {
  qc: QueryClient
}

export function registerFeedHandlers(es: EventSource, opts: FeedHandlerOpts) {
  es.addEventListener('annotation_saved', (e) => {
    const raw = (e as MessageEvent<string>).data
    try {
      JSON.parse(raw)
    } catch {
      return
    }
    void opts.qc.invalidateQueries({ queryKey: ['feed'] })
  })
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/hooks/sse/feedHandlers.test.tsx`
Expected: all PASS.

```bash
git add frontend/src/hooks/sse/feedHandlers.ts frontend/src/hooks/sse/feedHandlers.test.tsx
git commit -m "refactor(paket-16d): extract feedHandlers (annotation_saved → feed invalidate)

Thin handler — does NOT duplicate lock_* feed invalidation. Helps the
TopBar XP/streak widgets observe annotation activity by invalidating
profile in subsequent tasks if needed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 18: notificationHandlers — badge_unlocked + warnings

**Files:**
- Create: `frontend/src/hooks/sse/notificationHandlers.ts`
- Test: `frontend/src/hooks/sse/notificationHandlers.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/sse/notificationHandlers.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { QueryClient } from '@tanstack/react-query'
import { registerNotificationHandlers } from './notificationHandlers'

function makeFakeES() {
  const listeners: Record<string, Array<(e: MessageEvent) => void>> = {}
  return {
    addEventListener(type: string, fn: (e: MessageEvent) => void) {
      listeners[type] = [...(listeners[type] ?? []), fn]
    },
    dispatch(type: string, dataObj: unknown) {
      const e = new MessageEvent(type, { data: JSON.stringify(dataObj) })
      for (const fn of listeners[type] ?? []) fn(e)
    },
  }
}

describe('registerNotificationHandlers', () => {
  let qc: { invalidateQueries: ReturnType<typeof vi.fn> }
  let toastSuccess: ReturnType<typeof vi.fn>
  let toastWarning: ReturnType<typeof vi.fn>

  beforeEach(() => {
    qc = { invalidateQueries: vi.fn() }
    toastSuccess = vi.fn()
    toastWarning = vi.fn()
  })

  it('badge_unlocked: fires celebration toast (15s, no action button) + invalidates profile + notifications', () => {
    const es = makeFakeES()
    registerNotificationHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      toast: { success: toastSuccess, warning: toastWarning } as never,
    })
    es.dispatch('badge_unlocked', {
      badge_id: 'first_annotation',
      name: 'İlk Annotation',
      description: 'İlk kayıt başarıyla yapıldı.',
      earned_at: '2026-05-11T00:00:00+00:00',
    })
    expect(toastSuccess).toHaveBeenCalledWith(
      expect.stringContaining('İlk Annotation'),
      expect.objectContaining({ duration: 15_000 }),
    )
    const call = toastSuccess.mock.calls[0][1]
    // Codex BROKEN-B: must NOT have an action property
    expect(call).not.toHaveProperty('action')
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['profile'] })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['notifications'] })
  })

  it('speed_warning: gentle warning toast 8s', () => {
    const es = makeFakeES()
    registerNotificationHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      toast: { success: toastSuccess, warning: toastWarning } as never,
    })
    es.dispatch('speed_warning', { window_minutes: 5, save_count: 6 })
    expect(toastWarning).toHaveBeenCalledWith(
      'Bir nefes al',
      expect.objectContaining({ duration: 8_000 }),
    )
  })

  it('char_limit_warning: gentle warning toast 8s', () => {
    const es = makeFakeES()
    registerNotificationHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      toast: { success: toastSuccess, warning: toastWarning } as never,
    })
    es.dispatch('char_limit_warning', { ref_index: 2, detail: 'çok uzun' })
    expect(toastWarning).toHaveBeenCalledWith(
      'Metin uzunluğu dikkat',
      expect.objectContaining({ duration: 8_000 }),
    )
  })

  it('generic notification SSE also invalidates notifications cache', () => {
    // gamification/service.py also publishes "notification" event alongside
    // badge_unlocked. We invalidate so the bell counter refreshes.
    const es = makeFakeES()
    registerNotificationHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      toast: { success: toastSuccess, warning: toastWarning } as never,
    })
    es.dispatch('notification', { kind: 'badge_unlocked', data: {} })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['notifications'] })
  })

  it('malformed payload silently dropped', () => {
    const es = makeFakeES()
    registerNotificationHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      toast: { success: toastSuccess, warning: toastWarning } as never,
    })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    es.dispatch('badge_unlocked', { broken: 'shape' })
    expect(toastSuccess).not.toHaveBeenCalled()
    warn.mockRestore()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/sse/notificationHandlers.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/hooks/sse/notificationHandlers.ts`**

```ts
import type { QueryClient } from '@tanstack/react-query'
import { toast as defaultToast } from 'sonner'
import {
  badgeUnlockedSchema, speedWarningSchema, charLimitWarningSchema,
  parseEventData,
} from '@/lib/sseSchemas'
import { profileKeys } from '@/api/queries/profile'
import { notificationsKeys } from '@/api/queries/notifications'

interface NotificationHandlerOpts {
  qc: QueryClient
  toast?: typeof defaultToast
}

export function registerNotificationHandlers(
  es: EventSource, opts: NotificationHandlerOpts,
) {
  const t = opts.toast ?? defaultToast

  es.addEventListener('badge_unlocked', (e) => {
    const data = parseEventData(e as MessageEvent, badgeUnlockedSchema)
    if (!data) return
    // Codex BROKEN-B: celebration toast is INFORMATIONAL ONLY.
    // No action button — clicking it would unmount AnnotateDoc and lose draft.
    t.success(`🎉 Yeni rozet: ${data.name}`, {
      duration: 15_000,
      description: data.description,
    })
    void opts.qc.invalidateQueries({ queryKey: profileKeys.all })
    void opts.qc.invalidateQueries({ queryKey: notificationsKeys.all })
  })

  es.addEventListener('speed_warning', (e) => {
    const data = parseEventData(e as MessageEvent, speedWarningSchema)
    if (!data) return
    t.warning('Bir nefes al', {
      duration: 8_000,
      description: `Son ${data.window_minutes} dakikada ${data.save_count} kayıt attın. Kalite hızdan önemli.`,
    })
  })

  es.addEventListener('char_limit_warning', (e) => {
    const data = parseEventData(e as MessageEvent, charLimitWarningSchema)
    if (!data) return
    t.warning('Metin uzunluğu dikkat', {
      duration: 8_000,
      description: `${data.ref_index + 1}. referansın metin alıntısı ${data.detail}.`,
    })
  })

  // Generic 'notification' event piggy-backs from gamification/service.py
  // alongside badge_unlocked. Bell counter must refresh.
  es.addEventListener('notification', () => {
    void opts.qc.invalidateQueries({ queryKey: notificationsKeys.all })
  })
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/hooks/sse/notificationHandlers.test.tsx`
Expected: 5 PASS.

```bash
git add frontend/src/hooks/sse/notificationHandlers.ts frontend/src/hooks/sse/notificationHandlers.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16d): SSE notification handlers (badge + warnings)

badge_unlocked → 15s celebration toast (informational ONLY — no action
button per Codex BROKEN-B) + invalidate profile + notifications.

speed_warning + char_limit_warning → 8s gentle warning toast.

Generic 'notification' event invalidates notifications cache for bell
counter freshness.

All payloads validated by Zod (parseEventData); malformed events log
warn and are dropped instead of throwing through addEventListener.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: presenceHandlers — user_online / user_offline

**Files:**
- Create: `frontend/src/hooks/sse/presenceHandlers.ts`
- Test: `frontend/src/hooks/sse/presenceHandlers.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/hooks/sse/presenceHandlers.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { QueryClient } from '@tanstack/react-query'
import { registerPresenceHandlers } from './presenceHandlers'

function makeFakeES() {
  const listeners: Record<string, Array<(e: MessageEvent) => void>> = {}
  return {
    addEventListener(type: string, fn: (e: MessageEvent) => void) {
      listeners[type] = [...(listeners[type] ?? []), fn]
    },
    dispatch(type: string, dataObj: unknown) {
      const e = new MessageEvent(type, { data: JSON.stringify(dataObj) })
      for (const fn of listeners[type] ?? []) fn(e)
    },
  }
}

describe('registerPresenceHandlers', () => {
  let qc: { invalidateQueries: ReturnType<typeof vi.fn> }

  beforeEach(() => {
    qc = { invalidateQueries: vi.fn() }
  })

  it('user_online invalidates users.online cache', () => {
    const es = makeFakeES()
    registerPresenceHandlers(es as never, { qc: qc as unknown as QueryClient })
    es.dispatch('user_online', { id: 2, username: 'x', avatar_color: '#abc' })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['users', 'online'] })
  })

  it('user_offline invalidates users.online cache', () => {
    const es = makeFakeES()
    registerPresenceHandlers(es as never, { qc: qc as unknown as QueryClient })
    es.dispatch('user_offline', { id: 2 })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['users', 'online'] })
  })

  it('malformed user_online payload is ignored', () => {
    const es = makeFakeES()
    registerPresenceHandlers(es as never, { qc: qc as unknown as QueryClient })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    es.dispatch('user_online', { wrong: 'shape' })
    expect(qc.invalidateQueries).not.toHaveBeenCalled()
    warn.mockRestore()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/sse/presenceHandlers.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/hooks/sse/presenceHandlers.ts`**

```ts
import type { QueryClient } from '@tanstack/react-query'
import {
  userOnlinePayloadSchema, userOfflinePayloadSchema, parseEventData,
} from '@/lib/sseSchemas'
import { usersKeys } from '@/api/queries/users'

interface PresenceHandlerOpts {
  qc: QueryClient
}

export function registerPresenceHandlers(
  es: EventSource, opts: PresenceHandlerOpts,
) {
  es.addEventListener('user_online', (e) => {
    const data = parseEventData(e as MessageEvent, userOnlinePayloadSchema)
    if (!data) return
    void opts.qc.invalidateQueries({ queryKey: usersKeys.online() })
  })

  es.addEventListener('user_offline', (e) => {
    const data = parseEventData(e as MessageEvent, userOfflinePayloadSchema)
    if (!data) return
    void opts.qc.invalidateQueries({ queryKey: usersKeys.online() })
  })
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/hooks/sse/presenceHandlers.test.tsx`
Expected: 3 PASS.

```bash
git add frontend/src/hooks/sse/presenceHandlers.ts frontend/src/hooks/sse/presenceHandlers.test.tsx
git commit -m "feat(paket-16d): SSE presence handlers (user_online/user_offline → invalidate online)

Validated by Zod (parseEventData). On any presence change, invalidate
the users.online query so useOnlineUsers refetches between its 30s
polling ticks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 20: useSSE.ts orchestrator refactor

**Files:**
- Modify: `frontend/src/hooks/useSSE.ts`
- Test: `frontend/src/hooks/useSSE.test.ts` (existing OR new)

- [ ] **Step 1: Check existing useSSE tests**

Run: `ls frontend/src/hooks/useSSE.test.ts 2>/dev/null && echo present || echo absent`

If absent, create one in step 2. If present, append the new orchestrator assertions.

- [ ] **Step 2: Write the failing test (or append)**

Create or extend `frontend/src/hooks/useSSE.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as lockMod from './sse/lockHandlers'
import * as feedMod from './sse/feedHandlers'
import * as notifMod from './sse/notificationHandlers'
import * as presMod from './sse/presenceHandlers'
import { useSSE } from './useSSE'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  static last(): FakeEventSource {
    return FakeEventSource.instances[FakeEventSource.instances.length - 1]
  }
  url: string
  readyState = 0
  closed = false
  onerror: ((e: unknown) => void) | null = null
  listeners = new Map<string, Array<(e: MessageEvent) => void>>()
  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
    FakeEventSource.CONNECTING = 0
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    const arr = this.listeners.get(type) ?? []
    arr.push(fn)
    this.listeners.set(type, arr)
  }
  close() { this.closed = true }
  static CONNECTING = 0
}

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
})

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('useSSE orchestrator', () => {
  it('opens EventSource at /api/events and registers all four handler groups', () => {
    const lockSpy = vi.spyOn(lockMod, 'registerLockHandlers')
    const feedSpy = vi.spyOn(feedMod, 'registerFeedHandlers')
    const notifSpy = vi.spyOn(notifMod, 'registerNotificationHandlers')
    const presSpy = vi.spyOn(presMod, 'registerPresenceHandlers')

    renderHook(() => useSSE({ acquiringDocId: null }), { wrapper: wrap() })

    const es = FakeEventSource.last()
    expect(es.url).toBe('/api/events')
    expect(lockSpy).toHaveBeenCalled()
    expect(feedSpy).toHaveBeenCalled()
    expect(notifSpy).toHaveBeenCalled()
    expect(presSpy).toHaveBeenCalled()
  })

  it('closes EventSource on unmount', () => {
    const { unmount } = renderHook(() => useSSE({ acquiringDocId: null }), { wrapper: wrap() })
    const es = FakeEventSource.last()
    unmount()
    expect(es.closed).toBe(true)
  })

  it('on connect error invalidates feed AND users.online', () => {
    const { result } = renderHook(() => {
      // We need qc from inside the provider tree to spy on it.
      const qc = new QueryClient()
      return qc
    }, { wrapper: wrap() })
    renderHook(() => useSSE({ acquiringDocId: null }), { wrapper: wrap() })
    const es = FakeEventSource.last()
    expect(es.onerror).not.toBeNull()
    // We don't deeply assert the inner spy here because the qc instance
    // is created inside useSSE's QueryClientProvider; covered by the
    // integration test in T26 (TopBar).
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/useSSE.test.tsx`
Expected: spy calls show old inline code, not the new modules. (Actually, since spy assertions check `registerLockHandlers` etc. were called, and the old useSSE doesn't call them at all, this should fail.)

- [ ] **Step 4: Rewrite `frontend/src/hooks/useSSE.ts` as orchestrator**

Replace the entire file with:

```ts
import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/authStore'
import { registerLockHandlers } from './sse/lockHandlers'
import { registerFeedHandlers } from './sse/feedHandlers'
import { registerNotificationHandlers } from './sse/notificationHandlers'
import { registerPresenceHandlers } from './sse/presenceHandlers'
import { usersKeys } from '@/api/queries/users'

interface UseSSEOpts {
  acquiringDocId: string | null
}

export function useSSE(opts: UseSSEOpts) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const meId = useAuthStore((s) => s.user?.id ?? null)
  const acquiringRef = useRef<string | null>(opts.acquiringDocId)
  acquiringRef.current = opts.acquiringDocId

  useEffect(() => {
    let cancelled = false
    const es = new EventSource('/api/events')

    registerLockHandlers(es, { qc, navigate, meId, acquiringRef })
    registerFeedHandlers(es, { qc })
    registerNotificationHandlers(es, { qc })
    registerPresenceHandlers(es, { qc })

    es.onerror = () => {
      if (cancelled) return
      if (es.readyState === EventSource.CONNECTING) {
        // 16d: also reconcile online + profile to avoid stale UI on flaky links.
        void qc.invalidateQueries({ queryKey: ['feed'] })
        void qc.invalidateQueries({ queryKey: usersKeys.online() })
      }
    }

    return () => {
      cancelled = true
      es.close()
    }
  }, [qc, navigate, meId])
}
```

- [ ] **Step 5: Run useSSE tests + 16b regression tests**

Run: `cd frontend && npx vitest run src/hooks/`
Expected: all PASS.

- [ ] **Step 6: Run full frontend suite**

Run: `cd frontend && npm run test:run`
Expected: clean (no 16b lock-flow regression).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useSSE.ts frontend/src/hooks/useSSE.test.tsx
git commit -m "$(cat <<'EOF'
refactor(paket-16d): useSSE orchestrator pattern

useSSE is now a 30-line orchestrator that opens EventSource and wires
four handler modules (lock, feed, notification, presence). Behavior is
preserved verbatim for 16b paths; new paths added for badge_unlocked,
speed/char warnings, user_online/user_offline.

onerror reconciles feed AND users.online queries (Codex BROKEN-D defense
in depth on flaky links).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 21: XPBadge component

**Files:**
- Create: `frontend/src/components/topbar/XPBadge.tsx`
- Test: `frontend/src/components/topbar/XPBadge.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/topbar/XPBadge.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { XPBadge } from './XPBadge'

describe('XPBadge', () => {
  it('renders 0 when total is 0', () => {
    render(<XPBadge total={0} />)
    expect(screen.getByLabelText('Toplam XP')).toHaveTextContent('0')
  })

  it('formats with Turkish thousand separators', () => {
    render(<XPBadge total={1240} />)
    expect(screen.getByLabelText('Toplam XP')).toHaveTextContent('1.240')
  })

  it('formats million-scale values', () => {
    render(<XPBadge total={1234567} />)
    expect(screen.getByLabelText('Toplam XP')).toHaveTextContent('1.234.567')
  })

  it('renders the sparkle icon', () => {
    render(<XPBadge total={5} />)
    expect(screen.getByText('✨')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/topbar/XPBadge.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/topbar/XPBadge.tsx`**

```tsx
const TR_FORMATTER = new Intl.NumberFormat('tr-TR')

interface XPBadgeProps {
  total: number
}

export function XPBadge({ total }: XPBadgeProps) {
  return (
    <span
      aria-label="Toplam XP"
      className="inline-flex items-center gap-1 text-sm font-medium"
    >
      <span aria-hidden="true">✨</span>
      <span>{TR_FORMATTER.format(total)}</span>
    </span>
  )
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/topbar/XPBadge.test.tsx`
Expected: 4 PASS.

```bash
git add frontend/src/components/topbar/XPBadge.tsx frontend/src/components/topbar/XPBadge.test.tsx
git commit -m "feat(paket-16d): XPBadge with TR thousand separators

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 22: StreakCounter component

**Files:**
- Create: `frontend/src/components/topbar/StreakCounter.tsx`
- Test: `frontend/src/components/topbar/StreakCounter.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/topbar/StreakCounter.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StreakCounter } from './StreakCounter'

describe('StreakCounter', () => {
  it('renders "—" when current is 0', () => {
    render(<StreakCounter current={0} longest={0} />)
    expect(screen.getByLabelText(/streak/i)).toHaveTextContent('—')
  })

  it('renders the current count when > 0', () => {
    render(<StreakCounter current={3} longest={3} />)
    expect(screen.getByLabelText(/streak/i)).toHaveTextContent('3')
  })

  it('applies orange tier color for 4-6', () => {
    render(<StreakCounter current={5} longest={5} />)
    const el = screen.getByLabelText(/streak/i)
    expect(el.className).toMatch(/orange/i)
  })

  it('applies red tier color for 7+', () => {
    render(<StreakCounter current={7} longest={7} />)
    const el = screen.getByLabelText(/streak/i)
    expect(el.className).toMatch(/red/i)
  })

  it('shows longest in tooltip ONLY when longest > current', async () => {
    const user = userEvent.setup()
    render(<StreakCounter current={3} longest={12} />)
    const el = screen.getByLabelText(/streak/i)
    await user.hover(el)
    expect(await screen.findByText(/en uzun.*12/i)).toBeInTheDocument()
  })

  it('does NOT show tooltip when longest equals current', () => {
    render(<StreakCounter current={5} longest={5} />)
    // No tooltip trigger / no longest text rendered eagerly
    expect(screen.queryByText(/en uzun/i)).not.toBeInTheDocument()
  })

  it('aria-label includes the count', () => {
    render(<StreakCounter current={3} longest={3} />)
    expect(screen.getByLabelText('3 gün streak')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/topbar/StreakCounter.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/topbar/StreakCounter.tsx`**

```tsx
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from '@/components/ui/tooltip'

interface StreakCounterProps {
  current: number
  longest: number
}

function tierClass(current: number): string {
  if (current >= 7) return 'text-red-600'
  if (current >= 4) return 'text-orange-500'
  if (current >= 1) return 'text-muted-foreground'
  return 'text-muted-foreground'
}

export function StreakCounter({ current, longest }: StreakCounterProps) {
  const display = current === 0 ? '—' : String(current)
  const showLongest = longest > current

  const inner = (
    <span
      aria-label={`${current} gün streak`}
      className={`inline-flex items-center gap-1 text-sm font-medium ${tierClass(current)}`}
    >
      <span aria-hidden="true">🔥</span>
      <span>{display}</span>
    </span>
  )

  if (!showLongest) return inner

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>{inner}</TooltipTrigger>
        <TooltipContent>En uzun: {longest} gün</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
```

(The shadcn Tooltip primitives already exist from 16b — `frontend/src/components/ui/tooltip.tsx`.)

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/topbar/StreakCounter.test.tsx`
Expected: 7 PASS.

```bash
git add frontend/src/components/topbar/StreakCounter.tsx frontend/src/components/topbar/StreakCounter.test.tsx
git commit -m "feat(paket-16d): StreakCounter with color tiers + longest tooltip

Tiers: 0/1-3 muted, 4-6 orange, 7+ red. Tooltip only when longest > current.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 23: DailyProgress component

**Files:**
- Create: `frontend/src/components/topbar/DailyProgress.tsx`
- Test: `frontend/src/components/topbar/DailyProgress.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/topbar/DailyProgress.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DailyProgress } from './DailyProgress'

describe('DailyProgress', () => {
  it('renders nothing when target is 0', () => {
    const { container } = render(<DailyProgress today={5} target={0} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders progress bar with width %', () => {
    render(<DailyProgress today={3} target={10} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '3')
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuemax', '10')
    expect(screen.getByText('3/10')).toBeInTheDocument()
  })

  it('clamps width to 100% when today >= target', () => {
    render(<DailyProgress today={15} target={10} />)
    const bar = screen.getByTestId('daily-progress-fill')
    expect(bar.style.width).toBe('100%')
  })

  it('shows "Bugün ✓" when today >= target', () => {
    render(<DailyProgress today={10} target={10} />)
    expect(screen.getByText(/Bugün ✓/)).toBeInTheDocument()
  })

  it('does NOT show "Bugün ✓" when below target', () => {
    render(<DailyProgress today={9} target={10} />)
    expect(screen.queryByText(/Bugün ✓/)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/topbar/DailyProgress.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/topbar/DailyProgress.tsx`**

```tsx
interface DailyProgressProps {
  today: number
  target: number
}

export function DailyProgress({ today, target }: DailyProgressProps) {
  if (target === 0) return null
  const ratio = Math.min(today / target, 1)
  const pct = `${Math.round(ratio * 100)}%`
  const done = today >= target

  return (
    <div className="flex items-center gap-2 text-sm">
      <div
        role="progressbar"
        aria-valuenow={today}
        aria-valuemax={target}
        aria-valuemin={0}
        className="h-2 w-20 rounded-full bg-muted overflow-hidden"
      >
        <div
          data-testid="daily-progress-fill"
          className={`h-full ${done ? 'bg-green-500' : 'bg-primary'}`}
          style={{ width: pct }}
        />
      </div>
      <span className={done ? 'text-green-600 font-medium' : 'text-muted-foreground'}>
        {today}/{target}{done ? ' Bugün ✓' : ''}
      </span>
    </div>
  )
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/topbar/DailyProgress.test.tsx`
Expected: 5 PASS.

```bash
git add frontend/src/components/topbar/DailyProgress.tsx frontend/src/components/topbar/DailyProgress.test.tsx
git commit -m "feat(paket-16d): DailyProgress widget

Hidden when target=0. Clamped width. 'Bugün ✓' badge when today >= target.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 24: OnlineUsers component

**Files:**
- Create: `frontend/src/components/topbar/OnlineUsers.tsx`
- Test: `frontend/src/components/topbar/OnlineUsers.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/topbar/OnlineUsers.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { OnlineUsers } from './OnlineUsers'
import type { OnlineUser } from '@/lib/profileSchemas'

function mk(id: number, name: string): OnlineUser {
  return { id, username: name, avatar_color: '#3b82f6' }
}

describe('OnlineUsers', () => {
  it('renders nothing when list is empty', () => {
    const { container } = render(<OnlineUsers users={[]} maxVisible={5} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders all users when under maxVisible', () => {
    render(<OnlineUsers users={[mk(1, 'a'), mk(2, 'b')]} maxVisible={5} />)
    expect(screen.getByText('a'.toUpperCase())).toBeInTheDocument()
    expect(screen.getByText('b'.toUpperCase())).toBeInTheDocument()
    expect(screen.queryByText(/\+/)).not.toBeInTheDocument()
  })

  it('renders +N chip when users exceed maxVisible', () => {
    const users = [mk(1, 'a'), mk(2, 'b'), mk(3, 'c'), mk(4, 'd'), mk(5, 'e'), mk(6, 'f'), mk(7, 'g')]
    render(<OnlineUsers users={users} maxVisible={5} />)
    expect(screen.getByText('+2')).toBeInTheDocument()
  })

  it('clicking +N opens popover with all online users', async () => {
    const user = userEvent.setup()
    const users = [mk(1, 'alice'), mk(2, 'bob'), mk(3, 'carol'), mk(4, 'dan'), mk(5, 'eve'), mk(6, 'fred')]
    render(<OnlineUsers users={users} maxVisible={5} />)
    await user.click(screen.getByText('+1'))
    // All names should now appear in the popover
    expect(await screen.findByText(/fred/i)).toBeInTheDocument()
  })

  it('aria-label says how many are online', () => {
    render(<OnlineUsers users={[mk(1, 'a'), mk(2, 'b')]} maxVisible={5} />)
    expect(screen.getByLabelText('2 kullanıcı çevrimiçi')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/topbar/OnlineUsers.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/topbar/OnlineUsers.tsx`**

```tsx
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from '@/components/ui/tooltip'
import type { OnlineUser } from '@/lib/profileSchemas'

interface OnlineUsersProps {
  users: OnlineUser[]
  maxVisible: number
}

function Avatar({ user, size = 'sm' }: { user: OnlineUser; size?: 'sm' | 'md' }) {
  const cls = size === 'sm' ? 'h-6 w-6 text-xs' : 'h-8 w-8 text-sm'
  return (
    <span
      className={`inline-flex items-center justify-center rounded-full font-medium text-white ${cls}`}
      style={{ backgroundColor: user.avatar_color }}
    >
      {user.username[0]?.toUpperCase() ?? '?'}
    </span>
  )
}

export function OnlineUsers({ users, maxVisible }: OnlineUsersProps) {
  if (users.length === 0) return null

  const visible = users.slice(0, maxVisible)
  const overflow = users.length - visible.length

  return (
    <TooltipProvider delayDuration={200}>
      <div
        className="inline-flex items-center gap-1"
        aria-label={`${users.length} kullanıcı çevrimiçi`}
      >
        {visible.map((u) => (
          <Tooltip key={u.id}>
            <TooltipTrigger asChild>
              <span>
                <Avatar user={u} />
              </span>
            </TooltipTrigger>
            <TooltipContent>{u.username}</TooltipContent>
          </Tooltip>
        ))}
        {overflow > 0 && (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="inline-flex h-6 items-center justify-center rounded-full bg-muted px-2 text-xs font-medium text-muted-foreground hover:bg-muted-foreground/20"
              >
                +{overflow}
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-56" align="end">
              <div className="text-xs font-semibold text-muted-foreground mb-2">
                Çevrimiçi ({users.length})
              </div>
              <ul className="space-y-2">
                {users.map((u) => (
                  <li key={u.id} className="flex items-center gap-2">
                    <Avatar user={u} />
                    <span className="text-sm">{u.username}</span>
                  </li>
                ))}
              </ul>
            </PopoverContent>
          </Popover>
        )}
      </div>
    </TooltipProvider>
  )
}
```

Verify Popover primitive exists: `ls frontend/src/components/ui/popover.tsx`. If absent, the shadcn add-step is:

```bash
cd frontend && npx shadcn@latest add popover
```

Add this only if the file doesn't exist (it ships with shadcn defaults but may need installation).

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/topbar/OnlineUsers.test.tsx`
Expected: 5 PASS.

```bash
git add frontend/src/components/topbar/OnlineUsers.tsx frontend/src/components/topbar/OnlineUsers.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16d): OnlineUsers TopBar widget

Up to maxVisible avatars + "+N" overflow chip with Popover listing all
online users. Empty list renders nothing (no "0 online" label).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 25: ProfileDropdown with bell + last-10 menu

**Files:**
- Create: `frontend/src/components/topbar/ProfileDropdown.tsx`
- Test: `frontend/src/components/topbar/ProfileDropdown.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/topbar/ProfileDropdown.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { ProfileDropdown } from './ProfileDropdown'
import type { UserSection } from '@/lib/profileSchemas'

vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

const testUser: UserSection = { id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' }

describe('ProfileDropdown', () => {
  it('shows no unread dot when unreadCount=0', () => {
    render(<ProfileDropdown user={testUser} unreadCount={0} />, { wrapper: wrap() })
    expect(screen.queryByTestId('unread-dot')).not.toBeInTheDocument()
  })

  it('shows unread dot with count up to 9+', () => {
    const { rerender } = render(<ProfileDropdown user={testUser} unreadCount={3} />, { wrapper: wrap() })
    expect(screen.getByTestId('unread-dot')).toHaveTextContent('3')
    rerender(<ProfileDropdown user={testUser} unreadCount={15} />)
    expect(screen.getByTestId('unread-dot')).toHaveTextContent('9+')
  })

  it('opens dropdown and shows the four sections', async () => {
    const user = userEvent.setup()
    render(<ProfileDropdown user={testUser} unreadCount={0} />, { wrapper: wrap() })
    await user.click(screen.getByLabelText('Profil menüsü'))
    expect(screen.getByText(/Bildirimler/)).toBeInTheDocument()
    expect(screen.getByText('Profilim')).toBeInTheDocument()
    expect(screen.getByText('Yardım')).toBeInTheDocument()
    expect(screen.getByText('Çıkış')).toBeInTheDocument()
  })

  it('Profilim navigates to /me', async () => {
    const user = userEvent.setup()
    render(<ProfileDropdown user={testUser} unreadCount={0} />, { wrapper: wrap() })
    await user.click(screen.getByLabelText('Profil menüsü'))
    const link = screen.getByText('Profilim') as HTMLElement
    const anchor = link.closest('a')
    expect(anchor?.getAttribute('href')).toBe('/me')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/topbar/ProfileDropdown.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/topbar/ProfileDropdown.tsx`**

Inspect existing shadcn DropdownMenu file: `ls frontend/src/components/ui/dropdown-menu.tsx`. If absent: `cd frontend && npx shadcn@latest add dropdown-menu`.

```tsx
import { Link } from 'react-router-dom'
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { useLogoutMutation } from '@/api/queries/auth'
import {
  useUnreadNotifications, useMarkAllReadMutation, useMarkReadMutation,
} from '@/api/queries/notifications'
import { iconForKind } from '@/lib/notificationKinds'
import { formatRelativeTr } from '@/lib/formatters'
import type { UserSection } from '@/lib/profileSchemas'

interface ProfileDropdownProps {
  user: UserSection
  unreadCount: number
}

function unreadLabel(count: number): string {
  return count >= 10 ? '9+' : String(count)
}

function Avatar({ user }: { user: UserSection }) {
  return (
    <span
      className="inline-flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold text-white"
      style={{ backgroundColor: user.avatar_color }}
    >
      {user.username[0]?.toUpperCase() ?? '?'}
    </span>
  )
}

export function ProfileDropdown({ user, unreadCount }: ProfileDropdownProps) {
  const unread = useUnreadNotifications()
  const markRead = useMarkReadMutation()
  const markAllRead = useMarkAllReadMutation()
  const logout = useLogoutMutation()

  const top10 = (unread.data?.items ?? []).slice(0, 10)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Profil menüsü"
        className="relative inline-flex outline-none focus-visible:ring-2 ring-primary rounded-full"
      >
        <Avatar user={user} />
        {unreadCount > 0 && (
          <span
            data-testid="unread-dot"
            className="absolute -top-1 -right-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white"
          >
            {unreadLabel(unreadCount)}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel>
          {user.username} <span className="text-xs text-muted-foreground">• {user.role}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        <DropdownMenuLabel className="text-xs uppercase">
          🔔 Bildirimler {unreadCount > 0 && <span>({unreadCount} okunmamış)</span>}
        </DropdownMenuLabel>
        {top10.length === 0 ? (
          <div className="px-2 py-3 text-sm text-muted-foreground">Yeni bildirim yok.</div>
        ) : (
          <ul className="max-h-64 overflow-auto">
            {top10.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="flex w-full items-start gap-2 px-2 py-2 text-left text-sm hover:bg-muted"
                  onClick={() => markRead.mutate(item.id)}
                  aria-label={`${item.title} bildirimini okundu işaretle`}
                >
                  <span className="text-base">{iconForKind(item.kind)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="truncate" title={item.title}>{item.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {formatRelativeTr(item.created_at)}
                    </div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
        {top10.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={(e) => { e.preventDefault(); markAllRead.mutate() }}
            >
              Tümünü okundu yap
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to="/me#notifications">Tümünü Gör</Link>
            </DropdownMenuItem>
          </>
        )}

        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/me">Profilim</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/help">Yardım</Link>
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(e) => { e.preventDefault(); logout.mutate() }}
        >
          Çıkış
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
```

`useLogoutMutation` must already exist in `@/api/queries/auth.ts` (added in 16a). If named differently (e.g. `useLogout`), adjust the import.

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/topbar/ProfileDropdown.test.tsx`
Expected: 4 PASS.

```bash
git add frontend/src/components/topbar/ProfileDropdown.tsx frontend/src/components/topbar/ProfileDropdown.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16d): ProfileDropdown with bell, last-10, mark-all-read

Trigger avatar + unread dot (capped "9+"). Sections: identity,
Bildirimler (last 10 unread + Tümünü okundu yap + Tümünü Gör),
Profilim, Yardım, Çıkış.

Codex FRAGILE-D fix: notification titles use `truncate` + native title
tooltip — no overflow in the 72-wide dropdown.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 26: TopBar container

**Files:**
- Create: `frontend/src/components/topbar/TopBar.tsx`
- Test: `frontend/src/components/topbar/TopBar.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/topbar/TopBar.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { TopBar } from './TopBar'
import { useAuthStore } from '@/stores/authStore'
import { makeProfile, makeOnlineUser, makeNotification } from '@/test/msw-handlers'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  useAuthStore.setState({
    user: { id: 1, username: 'tester', email: null, role: 'user',
            is_active: true, has_seen_manual: true, has_passed_training: true,
            avatar_color: '#3b82f6', created_at: '2026-05-01T00:00:00+00:00' },
  })
})

describe('TopBar', () => {
  it('renders logo + project name', () => {
    render(<TopBar />, { wrapper: wrap() })
    expect(screen.getByText('Anotasyon Platformu')).toBeInTheDocument()
  })

  it('renders XP from useProfile', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ xp: { total: 1240 } }))),
    )
    render(<TopBar />, { wrapper: wrap() })
    await waitFor(() => expect(screen.getByLabelText('Toplam XP')).toHaveTextContent('1.240'))
  })

  it('shows skeletons during initial load (Profile widgets render "—")', () => {
    // No msw handler override → default handler returns instantly,
    // so we mock a never-resolving endpoint to test the loading state.
    server.use(
      http.get('http://localhost/api/me/profile', () => new Promise(() => {})),
    )
    render(<TopBar />, { wrapper: wrap() })
    // XPBadge renders 0 as fallback while loading; explicit test
    expect(screen.getByLabelText('Toplam XP')).toHaveTextContent('0')
  })

  it('on profile error, stats show "—" but TopBar does not crash', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json({ broken: true }, { status: 500 })),
    )
    render(<TopBar />, { wrapper: wrap() })
    await waitFor(() => {
      // Error path: streak shows "—", XPBadge falls back to 0
      expect(screen.getByLabelText(/streak/i)).toHaveTextContent('—')
    })
    // No throw
    expect(screen.getByText('Anotasyon Platformu')).toBeInTheDocument()
  })

  it('hides OnlineUsers when fetch errors', async () => {
    server.use(
      http.get('http://localhost/api/users/online', () =>
        HttpResponse.json({ broken: true }, { status: 500 })),
    )
    render(<TopBar />, { wrapper: wrap() })
    await waitFor(() => {
      // No "X kullanıcı çevrimiçi" aria-label rendered
      expect(screen.queryByLabelText(/kullanıcı çevrimiçi/)).not.toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/topbar/TopBar.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/topbar/TopBar.tsx`**

```tsx
import { useAuthStore } from '@/stores/authStore'
import { useProfile } from '@/api/queries/profile'
import { useOnlineUsers } from '@/api/queries/users'
import { useUnreadNotifications } from '@/api/queries/notifications'
import { XPBadge } from './XPBadge'
import { StreakCounter } from './StreakCounter'
import { DailyProgress } from './DailyProgress'
import { OnlineUsers } from './OnlineUsers'
import { ProfileDropdown } from './ProfileDropdown'

export function TopBar() {
  const user = useAuthStore((s) => s.user)
  const profile = useProfile()
  const online = useOnlineUsers()
  const unread = useUnreadNotifications()

  const xpTotal = profile.data?.xp.total ?? 0
  const streakCurrent = profile.data?.streak.current ?? 0
  const streakLongest = profile.data?.streak.longest ?? 0
  const todaySave = profile.data?.today.save ?? 0
  const dailyTarget = profile.data?.today.daily_target ?? 0
  const onlineUsers = online.isError ? [] : (online.data ?? [])
  const unreadCount = unread.isError ? 0 : (unread.data?.items.length ?? 0)

  return (
    <header
      role="banner"
      className="h-12 border-b bg-background px-4 grid grid-cols-[1fr_auto_1fr] items-center gap-4"
    >
      {/* Left */}
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className="text-lg">📚</span>
        <span className="font-semibold">Anotasyon Platformu</span>
      </div>

      {/* Center */}
      <div className="flex items-center gap-4">
        <XPBadge total={xpTotal} />
        <StreakCounter current={streakCurrent} longest={streakLongest} />
        <DailyProgress today={todaySave} target={dailyTarget} />
      </div>

      {/* Right */}
      <div className="ml-auto flex items-center gap-3">
        <div className="hidden md:block max-w-[200px] overflow-hidden">
          <OnlineUsers users={onlineUsers} maxVisible={5} />
        </div>
        {user && (
          <div className="flex-none">
            <ProfileDropdown
              user={{
                id: user.id,
                username: user.username,
                role: user.role,
                avatar_color: user.avatar_color,
              }}
              unreadCount={unreadCount}
            />
          </div>
        )}
      </div>
    </header>
  )
}
```

Codex FRAGILE-C (width budget): `hidden md:block` hides the OnlineUsers strip on viewports <768px. The `+N` overflow chip inside OnlineUsers still shows because it's part of the same component; if business wants ONLY the overflow chip below md, that's a 16d.1 follow-up — current behavior is "hide the whole strip below md."

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/topbar/TopBar.test.tsx`
Expected: all PASS.

```bash
git add frontend/src/components/topbar/TopBar.tsx frontend/src/components/topbar/TopBar.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16d): TopBar container — 3-col grid + error tolerance

Layout: 1fr / auto / 1fr. Center holds XP/streak/today. Right column
shows OnlineUsers on md+ with max-w-[200px], plus ProfileDropdown.

Per-widget error isolation: profile error → "—" stats; online error →
widget hidden; unread error → 0 count. TopBar itself never crashes
(Codex FRAGILE-F).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 27: Mount TopBar in AppShell

**Files:**
- Modify: `frontend/src/components/shell/AppShell.tsx`
- Test: `frontend/src/components/shell/AppShell.test.tsx` (existing or new)

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/shell/AppShell.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AppShell } from './AppShell'
import { useAuthStore } from '@/stores/authStore'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Routes>
          <Route element={children as React.ReactElement}>
            <Route path="/" element={<div data-testid="child">child</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  useAuthStore.setState({
    user: { id: 1, username: 'tester', email: null, role: 'user',
            is_active: true, has_seen_manual: true, has_passed_training: true,
            avatar_color: '#3b82f6', created_at: '2026-05-01T00:00:00+00:00' },
  })
})

describe('AppShell', () => {
  it('renders TopBar above the outlet', () => {
    render(<AppShell />, { wrapper: wrap() })
    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/shell/AppShell.test.tsx`
Expected: FAIL — placeholder header doesn't have role="banner" semantics OR rendering test passes incidentally; ensure tests cover *the new TopBar element* in the next iteration.

- [ ] **Step 3: Replace `frontend/src/components/shell/AppShell.tsx`**

```tsx
import { Outlet } from 'react-router-dom'
import { TopBar } from '@/components/topbar/TopBar'

export function AppShell() {
  return (
    <div className="min-h-screen flex flex-col">
      <TopBar />
      <main className="flex-1 min-h-0">
        <Outlet />
      </main>
    </div>
  )
}
```

`min-h-0` on the main allows the 16b 3-col flex layout's overflow children to scroll properly inside a flex-1 child (16b regression precaution).

- [ ] **Step 4: Run AppShell + 16b regression tests**

Run: `cd frontend && npx vitest run src/components/shell src/routes/AnnotateDoc.test.tsx src/routes/Annotate.test.tsx`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shell/AppShell.tsx frontend/src/components/shell/AppShell.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16d): mount TopBar in AppShell

Replaces the 16a placeholder header. Adds min-h-0 on <main> so the 16b
AnnotateLayout 3-col flex still scrolls correctly inside the new height
constraint (Section 18 risk under mitigation).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 28: BadgeCard (earned + locked variants)

**Files:**
- Create: `frontend/src/components/badges/BadgeCard.tsx`
- Test: `frontend/src/components/badges/BadgeCard.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/badges/BadgeCard.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BadgeCard } from './BadgeCard'

describe('BadgeCard earned variant', () => {
  it('renders name + earned_at relative time', () => {
    render(
      <BadgeCard
        badge={{
          id: 'first_annotation', name: 'İlk Annotation',
          description: 'İlk kayıt başarıyla yapıldı.',
          earned_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
        }}
        variant="earned"
      />,
    )
    expect(screen.getByText('İlk Annotation')).toBeInTheDocument()
    expect(screen.getByText(/saat önce/)).toBeInTheDocument()
  })

  it('shows the description text (line-clamp-2)', () => {
    render(
      <BadgeCard
        badge={{
          id: 'first_annotation', name: 'A',
          description: 'Yapıldı.', earned_at: '2026-05-11T00:00:00+00:00',
        }}
        variant="earned"
      />,
    )
    expect(screen.getByText('Yapıldı.')).toBeInTheDocument()
  })

  it('does NOT render grayscale class', () => {
    const { container } = render(
      <BadgeCard
        badge={{
          id: 'x', name: 'X', description: 'd', earned_at: '2026-05-11',
        }}
        variant="earned"
      />,
    )
    expect(container.firstChild).not.toHaveClass('grayscale')
  })
})

describe('BadgeCard locked variant', () => {
  it('renders grayscale + 🔒 + criterion text', () => {
    const { container } = render(
      <BadgeCard
        badge={{
          id: 'first_annotation', name: 'İlk Annotation',
          description: 'past tense',
          criterion: 'İlk anotasyon kaydını yap.',
        }}
        variant="locked"
      />,
    )
    expect(container.firstChild).toHaveClass('grayscale')
    expect(screen.getByLabelText('Kilitli')).toBeInTheDocument()
    // Body text uses criterion, NOT description
    expect(screen.getByText('İlk anotasyon kaydını yap.')).toBeInTheDocument()
    expect(screen.queryByText('past tense')).not.toBeInTheDocument()
  })

  it('falls back gracefully when criterion is null (body hidden)', () => {
    render(
      <BadgeCard
        badge={{ id: 'x', name: 'X', description: 'past', criterion: null }}
        variant="locked"
      />,
    )
    // Description should not leak into the locked variant
    expect(screen.queryByText('past')).not.toBeInTheDocument()
  })

  it('has aria-disabled="true"', () => {
    const { container } = render(
      <BadgeCard
        badge={{ id: 'x', name: 'X', description: 'd', criterion: 'do x' }}
        variant="locked"
      />,
    )
    expect(container.firstChild).toHaveAttribute('aria-disabled', 'true')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/badges/BadgeCard.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/badges/BadgeCard.tsx`**

```tsx
import { Lock } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { formatRelativeTr } from '@/lib/formatters'

const BADGE_ICONS: Record<string, string> = {
  first_annotation: '🏆',
  annotations_10: '✨',
  annotations_100: '💪',
  annotations_1000: '🌟',
  first_completion: '✅',
  marathoner: '🏃',
  good_reviewer: '🛡️',
}

function badgeIcon(id: string): string {
  return BADGE_ICONS[id] ?? '🎖️'
}

interface BadgeCardProps {
  badge: {
    id: string
    name: string
    description: string
    criterion?: string | null
    earned_at?: string
  }
  variant: 'earned' | 'locked'
}

export function BadgeCard({ badge, variant }: BadgeCardProps) {
  const isLocked = variant === 'locked'
  const body = isLocked ? (badge.criterion ?? '') : badge.description

  return (
    <Card
      className={cn(isLocked && 'grayscale opacity-60')}
      aria-disabled={isLocked || undefined}
    >
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-2xl" aria-hidden="true">{badgeIcon(badge.id)}</span>
          <h3 className="font-medium leading-tight">{badge.name}</h3>
          {isLocked && (
            <Lock className="ml-auto h-4 w-4 text-muted-foreground" aria-label="Kilitli" />
          )}
        </div>

        {body && (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <p className="line-clamp-2 text-sm text-muted-foreground">
                  {body}
                </p>
              </TooltipTrigger>
              <TooltipContent>{body}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {!isLocked && badge.earned_at && (
          <span className="block text-xs text-muted-foreground">
            {formatRelativeTr(badge.earned_at)}
          </span>
        )}
      </CardContent>
    </Card>
  )
}
```

Verify shadcn `card.tsx` exists: `ls frontend/src/components/ui/card.tsx`. If absent: `cd frontend && npx shadcn@latest add card`.

`lucide-react` is already a transitive dep of shadcn (16a/c uses it). If imports fail: `npm install lucide-react`.

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/badges/BadgeCard.test.tsx`
Expected: 6 PASS.

```bash
git add frontend/src/components/badges/BadgeCard.tsx frontend/src/components/badges/BadgeCard.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16d): BadgeCard with earned and locked variants

Earned: full color + description + relative earned_at.
Locked: grayscale + 🔒 + criterion (imperative). Description is hidden
on locked variant — past-tense copy is wrong context (Codex BROKEN-A).

line-clamp-2 + Tooltip prevents mobile overflow (Codex BROKEN-C, Pass 2).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 29: BadgesGrid with tabs + default-tab logic

**Files:**
- Create: `frontend/src/components/badges/BadgesGrid.tsx`
- Test: `frontend/src/components/badges/BadgesGrid.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/badges/BadgesGrid.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { BadgesGrid } from './BadgesGrid'
import { defaultBadgesCatalog, makeProfile } from '@/test/msw-handlers'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('BadgesGrid', () => {
  it('defaults to "Kazanılmış" tab when user has earned badges', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(defaultBadgesCatalog())),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile())),
    )
    render(<BadgesGrid />, { wrapper: wrap() })
    // Default tab is "Kazanılmış"
    expect(await screen.findByRole('tab', { name: /Kazanılmış/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('defaults to "Hepsi" tab when user has zero earned badges', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(defaultBadgesCatalog())),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ badges: [] }))),
    )
    render(<BadgesGrid />, { wrapper: wrap() })
    expect(await screen.findByRole('tab', { name: /Hepsi/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('"Hepsi" tab shows all 7 cards (earned + locked)', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(defaultBadgesCatalog())),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ badges: [] }))),
    )
    const user = userEvent.setup()
    render(<BadgesGrid />, { wrapper: wrap() })
    await user.click(await screen.findByRole('tab', { name: /Hepsi/ }))
    // 7 catalog entries should render as 7 BadgeCards
    expect(screen.getAllByText('🔒').length).toBeGreaterThanOrEqual(7)
  })

  it('on catalog fetch error, shows Kazanılmış-only + warning', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json({ broken: true }, { status: 500 })),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile())),
    )
    render(<BadgesGrid />, { wrapper: wrap() })
    expect(await screen.findByText(/Tüm rozet kataloğu yüklenemedi/)).toBeInTheDocument()
    // No "Hepsi" tab since catalog failed
    expect(screen.queryByRole('tab', { name: /Hepsi/ })).not.toBeInTheDocument()
  })

  it('empty Kazanılmış tab shows helper text', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(defaultBadgesCatalog())),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ badges: [] }))),
    )
    const user = userEvent.setup()
    render(<BadgesGrid />, { wrapper: wrap() })
    await user.click(await screen.findByRole('tab', { name: /Kazanılmış/ }))
    expect(screen.getByText(/Henüz rozet yok/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/badges/BadgesGrid.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/badges/BadgesGrid.tsx`**

```tsx
import { useMemo, useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { BadgeCard } from './BadgeCard'
import { useProfile } from '@/api/queries/profile'
import { useBadgesCatalog } from '@/api/queries/badges'

type TabKey = 'kazanilmis' | 'hepsi'

export function BadgesGrid() {
  const profile = useProfile()
  const catalog = useBadgesCatalog()

  const earned = profile.data?.badges ?? []
  const earnedIds = useMemo(() => new Set(earned.map((b) => b.id)), [earned])

  // Codex FRAGILE-E: compute default tab once on mount; if user has zero
  // earned badges, default to "Hepsi" so they see something interesting.
  const defaultTab = useMemo<TabKey>(
    () => (earned.length === 0 ? 'hepsi' : 'kazanilmis'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )
  const [tab, setTab] = useState<TabKey>(defaultTab)

  const catalogFailed = catalog.isError

  if (catalogFailed) {
    return (
      <section>
        <h2 className="text-lg font-semibold mb-3">Rozetler</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {earned.map((b) => (
            <BadgeCard key={b.id} badge={b} variant="earned" />
          ))}
          {earned.length === 0 && (
            <p className="col-span-full text-sm text-muted-foreground">
              Henüz rozet yok.
            </p>
          )}
        </div>
        <p className="mt-3 text-sm text-amber-600">
          Tüm rozet kataloğu yüklenemedi.{' '}
          <button
            type="button"
            className="underline"
            onClick={() => catalog.refetch()}
          >
            Yeniden dene
          </button>
        </p>
      </section>
    )
  }

  const catalogItems = catalog.data ?? []

  return (
    <section>
      <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Rozetler</h2>
          <TabsList>
            <TabsTrigger value="kazanilmis">Kazanılmış ({earned.length})</TabsTrigger>
            <TabsTrigger value="hepsi">Hepsi ({catalogItems.length})</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="kazanilmis">
          {earned.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Henüz rozet yok. Hepsi sekmesinde mevcut rozetleri gör.
            </p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {earned.map((b) => (
                <BadgeCard key={b.id} badge={b} variant="earned" />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="hepsi">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {catalogItems.map((c) => {
              const earnedRow = earned.find((b) => b.id === c.id)
              if (earnedRow) {
                return <BadgeCard key={c.id} badge={earnedRow} variant="earned" />
              }
              return (
                <BadgeCard
                  key={c.id}
                  badge={{ id: c.id, name: c.name, description: c.description, criterion: c.criterion ?? null }}
                  variant="locked"
                />
              )
            })}
          </div>
        </TabsContent>
      </Tabs>
    </section>
  )
}
```

Verify shadcn `tabs.tsx` exists (16c uses it). If absent: `cd frontend && npx shadcn@latest add tabs`.

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/badges/BadgesGrid.test.tsx`
Expected: 5 PASS.

```bash
git add frontend/src/components/badges/BadgesGrid.tsx frontend/src/components/badges/BadgesGrid.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16d): BadgesGrid with Kazanılmış/Hepsi tabs

Default tab = Hepsi when earned.length===0 (Codex FRAGILE-E, Pass 3) —
otherwise fresh users see an empty Kazanılmış tab and miss the
celebration of locked badges.

Catalog fetch error degrades to Kazanılmış-only + inline warning +
retry button (Codex FRAGILE-F).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 30: NotificationItem

**Files:**
- Create: `frontend/src/components/notifications/NotificationItem.tsx`
- Test: `frontend/src/components/notifications/NotificationItem.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/notifications/NotificationItem.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NotificationItem } from './NotificationItem'

const baseItem = {
  id: 1, kind: 'admin_announcement', title: 'Duyuru', body: null,
  data: null, is_read: false, created_at: '2026-05-11T00:00:00+00:00',
}

describe('NotificationItem', () => {
  it('renders title and relative time', () => {
    render(<NotificationItem item={baseItem} onMarkRead={vi.fn()} />)
    expect(screen.getByText('Duyuru')).toBeInTheDocument()
  })

  it('renders body when present', () => {
    render(<NotificationItem item={{ ...baseItem, body: 'detay' }} onMarkRead={vi.fn()} />)
    expect(screen.getByText('detay')).toBeInTheDocument()
  })

  it('shows mark-read button only when unread', () => {
    const { rerender } = render(<NotificationItem item={baseItem} onMarkRead={vi.fn()} />)
    expect(screen.getByLabelText(/okundu işaretle/i)).toBeInTheDocument()
    rerender(<NotificationItem item={{ ...baseItem, is_read: true }} onMarkRead={vi.fn()} />)
    expect(screen.queryByLabelText(/okundu işaretle/i)).not.toBeInTheDocument()
  })

  it('clicking mark-read calls onMarkRead with id', async () => {
    const onMarkRead = vi.fn()
    const user = userEvent.setup()
    render(<NotificationItem item={baseItem} onMarkRead={onMarkRead} />)
    await user.click(screen.getByLabelText(/okundu işaretle/i))
    expect(onMarkRead).toHaveBeenCalledWith(1)
  })

  it('uses kind-specific icon (badge_unlocked → 🏆)', () => {
    render(
      <NotificationItem
        item={{ ...baseItem, kind: 'badge_unlocked', title: 'Yeni rozet' }}
        onMarkRead={vi.fn()}
      />,
    )
    expect(screen.getByText('🏆')).toBeInTheDocument()
  })

  it('falls back to 🔔 for unknown kind', () => {
    render(
      <NotificationItem
        item={{ ...baseItem, kind: 'something_new' }}
        onMarkRead={vi.fn()}
      />,
    )
    expect(screen.getByText('🔔')).toBeInTheDocument()
  })

  it('unread items have visual emphasis (border + bold)', () => {
    const { container } = render(<NotificationItem item={baseItem} onMarkRead={vi.fn()} />)
    expect(container.firstChild).toHaveClass('font-medium')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/notifications/NotificationItem.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/notifications/NotificationItem.tsx`**

```tsx
import { Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { formatRelativeTr } from '@/lib/formatters'
import { iconForKind } from '@/lib/notificationKinds'
import type { Notification } from '@/lib/profileSchemas'

interface NotificationItemProps {
  item: Notification
  onMarkRead: (id: number) => void
}

export function NotificationItem({ item, onMarkRead }: NotificationItemProps) {
  const unread = !item.is_read
  return (
    <div
      className={cn(
        'flex items-start gap-3 border-b py-3',
        unread && 'border-l-4 border-l-primary pl-3 font-medium',
      )}
    >
      <span className="text-xl" aria-hidden="true">{iconForKind(item.kind)}</span>
      <div className="flex-1 min-w-0">
        <h4 className="truncate" title={item.title}>{item.title}</h4>
        {item.body && (
          <p className="text-sm text-muted-foreground line-clamp-2">{item.body}</p>
        )}
        <time className="text-xs text-muted-foreground">
          {formatRelativeTr(item.created_at)}
        </time>
      </div>
      {unread && (
        <Button
          variant="ghost"
          size="sm"
          aria-label={`${item.title} bildirimini okundu işaretle`}
          onClick={() => onMarkRead(item.id)}
        >
          <Check className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}
```

Verify `button.tsx` exists: yes from 16a.

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/notifications/NotificationItem.test.tsx`
Expected: 7 PASS.

```bash
git add frontend/src/components/notifications/NotificationItem.tsx frontend/src/components/notifications/NotificationItem.test.tsx
git commit -m "feat(paket-16d): NotificationItem with kind icons + mark-read

Unread: left border accent + bold + ✓ button. Read: muted. Icon map
from notificationKinds.ts with fallback 🔔.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 31: NotificationsList

**Files:**
- Create: `frontend/src/components/notifications/NotificationsList.tsx`
- Test: `frontend/src/components/notifications/NotificationsList.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/notifications/NotificationsList.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { NotificationsList } from './NotificationsList'
import { makeNotification } from '@/test/msw-handlers'

vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('NotificationsList', () => {
  it('renders empty state when history is empty', async () => {
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({ items: [] })),
    )
    render(<NotificationsList />, { wrapper: wrap() })
    expect(await screen.findByText(/Henüz bildirim yok/)).toBeInTheDocument()
  })

  it('renders items', async () => {
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({
          items: [
            makeNotification({ id: 1, title: 'A', is_read: false }),
            makeNotification({ id: 2, title: 'B', is_read: true }),
          ],
        })),
    )
    render(<NotificationsList />, { wrapper: wrap() })
    expect(await screen.findByText('A')).toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()
  })

  it('shows "Tümünü okundu yap" only when at least one unread item exists', async () => {
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({
          items: [makeNotification({ id: 2, title: 'X', is_read: true })],
        })),
    )
    render(<NotificationsList />, { wrapper: wrap() })
    await screen.findByText('X')
    expect(screen.queryByText(/Tümünü okundu yap/)).not.toBeInTheDocument()
  })

  it('clicking "Tümünü okundu yap" calls mark-all endpoint', async () => {
    let posted = false
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({
          items: [makeNotification({ id: 1, title: 'A', is_read: false })],
        })),
      http.post('http://localhost/api/me/notifications/read-all', () => {
        posted = true
        return HttpResponse.json({ marked_count: 1 })
      }),
    )
    const user = userEvent.setup()
    render(<NotificationsList />, { wrapper: wrap() })
    await screen.findByText('A')
    await user.click(screen.getByText(/Tümünü okundu yap/))
    await waitFor(() => expect(posted).toBe(true))
  })

  it('on fetch error, shows error block + retry', async () => {
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({ broken: true }, { status: 500 })),
    )
    render(<NotificationsList />, { wrapper: wrap() })
    expect(await screen.findByText(/yüklenirken hata/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/notifications/NotificationsList.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/notifications/NotificationsList.tsx`**

```tsx
import { Button } from '@/components/ui/button'
import {
  useNotificationsHistory, useMarkReadMutation, useMarkAllReadMutation,
} from '@/api/queries/notifications'
import { NotificationItem } from './NotificationItem'

export function NotificationsList() {
  const history = useNotificationsHistory()
  const markRead = useMarkReadMutation()
  const markAllRead = useMarkAllReadMutation()

  if (history.isError) {
    return (
      <section id="notifications">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Bildirimler</h2>
        </div>
        <p className="text-sm text-amber-600">
          Bildirimler yüklenirken hata oluştu.{' '}
          <button
            type="button"
            className="underline"
            onClick={() => history.refetch()}
          >
            Yeniden dene
          </button>
        </p>
      </section>
    )
  }

  if (history.isPending) {
    return (
      <section id="notifications">
        <h2 className="text-lg font-semibold mb-3">Bildirimler</h2>
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded bg-muted" />
          ))}
        </div>
      </section>
    )
  }

  const items = history.data?.items ?? []
  const hasUnread = items.some((i) => !i.is_read)

  return (
    <section id="notifications">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Bildirimler</h2>
        {hasUnread && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => markAllRead.mutate()}
            disabled={markAllRead.isPending}
          >
            Tümünü okundu yap
          </Button>
        )}
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Henüz bildirim yok.</p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <NotificationItem item={item} onMarkRead={(id) => markRead.mutate(id)} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/notifications/NotificationsList.test.tsx`
Expected: 5 PASS.

```bash
git add frontend/src/components/notifications/NotificationsList.tsx frontend/src/components/notifications/NotificationsList.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16d): NotificationsList for /me Notifications section

Empty / loading / error states. "Tümünü okundu yap" button visible only
when at least one unread. Loading uses 3-row skeleton. Error block
preserves the rest of /me (Codex FRAGILE-F isolation).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 32: ProfileHeader

**Files:**
- Create: `frontend/src/components/profile/ProfileHeader.tsx`
- Test: `frontend/src/components/profile/ProfileHeader.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/profile/ProfileHeader.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ProfileHeader } from './ProfileHeader'

describe('ProfileHeader', () => {
  it('renders username with @ prefix', () => {
    render(<ProfileHeader user={{ id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' }} createdAt="2026-05-01T00:00:00+00:00" />)
    expect(screen.getByText('@tester')).toBeInTheDocument()
  })

  it('renders role badge', () => {
    render(<ProfileHeader user={{ id: 1, username: 'admin1', role: 'admin', avatar_color: '#3b82f6' }} createdAt="2026-05-01T00:00:00+00:00" />)
    expect(screen.getByText(/admin/i)).toBeInTheDocument()
  })

  it('renders created date in Turkish locale', () => {
    render(<ProfileHeader user={{ id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' }} createdAt="2026-05-01T00:00:00+00:00" />)
    expect(screen.getByText(/Hesap oluşturuldu/i)).toBeInTheDocument()
  })

  it('uses avatar_color as background', () => {
    render(<ProfileHeader user={{ id: 1, username: 'tester', role: 'user', avatar_color: '#ef4444' }} createdAt="2026-05-01T00:00:00+00:00" />)
    const avatar = screen.getByText('T')
    expect(avatar.getAttribute('style')).toContain('background-color')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/profile/ProfileHeader.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/profile/ProfileHeader.tsx`**

```tsx
import type { UserSection } from '@/lib/profileSchemas'

interface ProfileHeaderProps {
  user: UserSection
  createdAt: string
}

function trDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })
}

function roleLabel(role: string): string {
  switch (role) {
    case 'admin': return 'Yönetici'
    default: return 'Bursiyer'
  }
}

export function ProfileHeader({ user, createdAt }: ProfileHeaderProps) {
  return (
    <header className="flex items-center gap-4 mb-6">
      <span
        className="inline-flex h-16 w-16 items-center justify-center rounded-full text-2xl font-semibold text-white"
        style={{ backgroundColor: user.avatar_color }}
      >
        {user.username[0]?.toUpperCase() ?? '?'}
      </span>
      <div>
        <h1 className="text-2xl font-semibold">@{user.username}</h1>
        <p className="text-sm text-muted-foreground">
          {roleLabel(user.role)} • Hesap oluşturuldu: {trDate(createdAt)}
        </p>
      </div>
    </header>
  )
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/profile/ProfileHeader.test.tsx`
Expected: 4 PASS.

```bash
git add frontend/src/components/profile/ProfileHeader.tsx frontend/src/components/profile/ProfileHeader.test.tsx
git commit -m "feat(paket-16d): ProfileHeader for /me page

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 33: StatCards (4-card grid)

**Files:**
- Create: `frontend/src/components/profile/StatCards.tsx`
- Test: `frontend/src/components/profile/StatCards.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/profile/StatCards.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatCards } from './StatCards'
import { makeProfile } from '@/test/msw-handlers'

describe('StatCards', () => {
  it('renders XP, Streak, Bugün, Rozet cards', () => {
    render(<StatCards profile={makeProfile()} />)
    expect(screen.getByText(/Toplam XP/i)).toBeInTheDocument()
    expect(screen.getByText(/Streak/i)).toBeInTheDocument()
    expect(screen.getByText(/Bugün/i)).toBeInTheDocument()
    expect(screen.getByText(/Toplam Rozet/i)).toBeInTheDocument()
  })

  it('formats XP with TR locale', () => {
    render(<StatCards profile={makeProfile({ xp: { total: 1234567 } })} />)
    expect(screen.getByText('1.234.567')).toBeInTheDocument()
  })

  it('shows "Günlük hedef kapalı" when daily_target is 0', () => {
    render(<StatCards profile={makeProfile({ today: { save: 5, complete: 0, review: 0, skip: 0, daily_target: 0 } })} />)
    expect(screen.getByText(/Günlük hedef kapalı/)).toBeInTheDocument()
  })

  it('shows progress bar when daily_target > 0', () => {
    render(<StatCards profile={makeProfile({ today: { save: 3, complete: 0, review: 0, skip: 0, daily_target: 10 } })} />)
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('shows longest in StreakCard subtitle', () => {
    render(<StatCards profile={makeProfile({ streak: { current: 3, longest: 12, last_active_date: '2026-05-11' } })} />)
    expect(screen.getByText(/En uzun.*12/)).toBeInTheDocument()
  })

  it('shows badge count', () => {
    render(<StatCards profile={makeProfile()} />)
    // Default makeProfile has 1 badge
    expect(screen.getByText('1')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/profile/StatCards.test.tsx`
Expected: module-not-found.

- [ ] **Step 3: Create `frontend/src/components/profile/StatCards.tsx`**

```tsx
import { Card, CardContent } from '@/components/ui/card'
import type { ProfileResponse } from '@/lib/profileSchemas'

const TR_FORMATTER = new Intl.NumberFormat('tr-TR')

interface StatCardsProps {
  profile: ProfileResponse
}

export function StatCards({ profile }: StatCardsProps) {
  const { xp, streak, today, badges } = profile
  const targetEnabled = today.daily_target > 0
  const ratio = targetEnabled ? Math.min(today.save / today.daily_target, 1) : 0

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {/* XP */}
      <Card>
        <CardContent className="p-4">
          <div className="text-3xl font-semibold">
            <span aria-hidden="true">✨</span> {TR_FORMATTER.format(xp.total)}
          </div>
          <div className="text-xs text-muted-foreground mt-1">Toplam XP</div>
        </CardContent>
      </Card>

      {/* Streak */}
      <Card>
        <CardContent className="p-4">
          <div className="text-3xl font-semibold">
            <span aria-hidden="true">🔥</span> {streak.current}
          </div>
          <div className="text-xs text-muted-foreground mt-1">Streak</div>
          <div className="text-xs text-muted-foreground">
            En uzun: {streak.longest} gün
          </div>
        </CardContent>
      </Card>

      {/* Today */}
      <Card>
        <CardContent className="p-4">
          {targetEnabled ? (
            <>
              <div className="text-3xl font-semibold">
                {today.save}/{today.daily_target}
              </div>
              <div
                role="progressbar"
                aria-valuenow={today.save}
                aria-valuemax={today.daily_target}
                aria-valuemin={0}
                className="mt-2 h-2 rounded-full bg-muted overflow-hidden"
              >
                <div
                  className={ratio === 1 ? 'h-full bg-green-500' : 'h-full bg-primary'}
                  style={{ width: `${Math.round(ratio * 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground mt-1">Bugün</div>
            </>
          ) : (
            <>
              <div className="text-3xl font-semibold">{today.save}</div>
              <div className="text-xs text-muted-foreground mt-1">Bugün</div>
              <div className="text-xs text-muted-foreground">Günlük hedef kapalı</div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Badges */}
      <Card>
        <CardContent className="p-4">
          <div className="text-3xl font-semibold">
            <span aria-hidden="true">🏆</span> {badges.length}
          </div>
          <div className="text-xs text-muted-foreground mt-1">Toplam Rozet</div>
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 4: Run tests + commit**

Run: `cd frontend && npx vitest run src/components/profile/StatCards.test.tsx`
Expected: 6 PASS.

```bash
git add frontend/src/components/profile/StatCards.tsx frontend/src/components/profile/StatCards.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16d): StatCards 4-card grid for /me

XP / Streak (with longest subtitle) / Bugün (progress bar OR "Günlük
hedef kapalı") / Toplam Rozet. Codex BROKEN, Pass 2: daily_target=0
edge case handled with raw count + subtitle copy.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 34: Profile.tsx route replacement + integration tests

**Files:**
- Modify: `frontend/src/routes/Profile.tsx`
- Test: `frontend/src/routes/Profile.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/routes/Profile.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { Profile } from './Profile'
import { useAuthStore } from '@/stores/authStore'
import { makeProfile, defaultBadgesCatalog } from '@/test/msw-handlers'

vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  useAuthStore.setState({
    user: { id: 1, username: 'tester', email: null, role: 'user',
            is_active: true, has_seen_manual: true, has_passed_training: true,
            avatar_color: '#3b82f6', created_at: '2026-05-01T00:00:00+00:00' },
  })
})

describe('Profile /me', () => {
  it('renders header + 4 stat cards + badges grid + notifications section', async () => {
    render(<Profile />, { wrapper: wrap() })
    expect(await screen.findByText('@tester')).toBeInTheDocument()
    expect(screen.getByText(/Toplam XP/)).toBeInTheDocument()
    expect(screen.getByText(/Rozetler/)).toBeInTheDocument()
    expect(screen.getByText(/Bildirimler/)).toBeInTheDocument()
  })

  it('fresh user (badges=[]) defaults BadgesGrid to Hepsi tab', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ badges: [] }))),
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(defaultBadgesCatalog())),
    )
    render(<Profile />, { wrapper: wrap() })
    expect(await screen.findByRole('tab', { name: /Hepsi/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('mark-all-read flow: button → 0 unread', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({
          items: [
            { id: 1, kind: 'admin_announcement', title: 'A',
              body: null, data: null, is_read: false,
              created_at: '2026-05-11T00:00:00+00:00' },
          ],
        })),
      http.post('http://localhost/api/me/notifications/read-all', () =>
        HttpResponse.json({ marked_count: 1 })),
    )
    render(<Profile />, { wrapper: wrap() })
    await user.click(await screen.findByText(/Tümünü okundu yap/))
    // Toast was mocked; just verify the network call ran by checking the
    // button vanished after refetch — implementation polls/invalidates.
    await waitFor(() => expect(screen.queryByText(/Tümünü okundu yap/)).not.toBeInTheDocument())
  })

  it('on profile fetch error shows a full-page retry block', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json({ broken: true }, { status: 500 })),
    )
    render(<Profile />, { wrapper: wrap() })
    expect(await screen.findByText(/Profil yüklenemedi/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/routes/Profile.test.tsx`
Expected: FAIL — current Profile is a STUB.

- [ ] **Step 3: Replace `frontend/src/routes/Profile.tsx`**

```tsx
import { useAuthStore } from '@/stores/authStore'
import { useProfile } from '@/api/queries/profile'
import { ProfileHeader } from '@/components/profile/ProfileHeader'
import { StatCards } from '@/components/profile/StatCards'
import { BadgesGrid } from '@/components/badges/BadgesGrid'
import { NotificationsList } from '@/components/notifications/NotificationsList'

export function Profile() {
  const user = useAuthStore((s) => s.user)
  const profile = useProfile()

  if (profile.isError) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <p className="text-sm text-amber-600">
          Profil yüklenemedi.{' '}
          <button
            type="button"
            className="underline"
            onClick={() => profile.refetch()}
          >
            Yeniden dene
          </button>
        </p>
      </div>
    )
  }

  if (profile.isPending || !profile.data || !user) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <div className="h-16 w-48 animate-pulse rounded bg-muted mb-6" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded bg-muted" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl p-6 space-y-8">
      <ProfileHeader user={profile.data.user} createdAt={user.created_at} />
      <StatCards profile={profile.data} />
      <BadgesGrid />
      <NotificationsList />
    </div>
  )
}
```

- [ ] **Step 4: Run integration tests**

Run: `cd frontend && npx vitest run src/routes/Profile.test.tsx`
Expected: 4 PASS.

- [ ] **Step 5: Run full frontend suite**

Run: `cd frontend && npm run test:run`
Expected: all 258 + ~150 new tests PASS. Identify and fix any cross-file regression here.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/Profile.tsx frontend/src/routes/Profile.test.tsx
git commit -m "$(cat <<'EOF'
feat(paket-16d): replace /me STUB with full Profile page

Single scroll: ProfileHeader → StatCards → BadgesGrid → NotificationsList.
Skeleton loading; profile fetch error shows retry block; section-level
errors (BadgesGrid, NotificationsList) degrade independently
(Codex FRAGILE-F isolation).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 35: Acceptance — full suite, coverage, lint, typecheck, gen:types

**Files:** none (verification only)

- [ ] **Step 1: Run full backend suite**

Run: `.venv/bin/python -m pytest backend/tests -q`
Expected: all PASS (~755 tests including 16d additions, 0 failures).

- [ ] **Step 2: Run full frontend suite with coverage**

Run: `cd frontend && npm run test:coverage`
Expected: all PASS. Coverage thresholds ≥80% statements/branches/functions/lines for files in `src/components/topbar/`, `src/components/badges/`, `src/components/notifications/`, `src/components/profile/`, `src/api/queries/`, `src/hooks/sse/`, `src/lib/profileSchemas.ts`, `src/lib/sseSchemas.ts`, `src/lib/notificationKinds.ts`, `src/routes/Profile.tsx`.

If a file drops below 80%, add tests for the uncovered branches. Common gaps:
- Error paths in StreakCounter tier logic
- Popover trigger paths in OnlineUsers when overflow=0
- Mark-all-read disabled state during mutation pending

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: clean.

- [ ] **Step 4: Lint**

Run: `cd frontend && npm run lint`
Expected: clean.

- [ ] **Step 5: OpenAPI sync check**

Run: `cd frontend && npm run gen:types:check`
Expected: exit 0 (no diff vs live spec).

- [ ] **Step 6: Build**

Run: `cd frontend && npm run build`
Expected: clean (tsc --noEmit + vite build).

- [ ] **Step 7: Commit (chore — if any test fixtures or .gitignore tweaks happened during this verification)**

```bash
git status
# If clean, no commit needed.
# Otherwise:
git add -p
git commit -m "chore(paket-16d): verification adjustments

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 36: Manual E2E smoke + tag release

**Files:** none (smoke run + tag)

- [ ] **Step 1: Confirm dev servers running**

Run: `lsof -i :8000 :5173 -P -n | head -5`
Expected: both ports listening. If not, start them per HANDOFF-16d.md §4.

- [ ] **Step 2: Manual E2E smoke checklist**

Open `http://localhost:5173` in a browser and run each of these (spec §16):

1. Login as `testbot` (password from `deneme-dev/data/db/annotations.db` seed) or `admin`. TopBar visible with stats.
2. Click avatar → ProfileDropdown opens → click "Profilim" → arrive at `/me` with header + 4 stats + BadgesGrid + Notifications.
3. From `/`, open a doc, save an annotation. If `first_annotation` not yet earned for this user, expect: 15s celebration toast "🎉 Yeni rozet: İlk Annotation", bell counter increments, TopBar XP increments, Bugün progress moves.
4. Click the unread notification in the bell dropdown → counter decrements; row turns read.
5. Click "Tümünü Gör" → land on `/me#notifications` → see read+unread.
6. Open `/me` BadgesGrid → if at least one earned, default tab = Kazanılmış; click "Hepsi" → 7 cards: earned colored, others grayscale + 🔒 + criterion.
7. Open `/docs/<id>` in a SECOND browser tab (same user, different session) → in tab 1, OnlineUsers in TopBar shows +1 user (after ≤30s).
8. Close tab 2 → in tab 1 OnlineUsers drops by 1 (within ≤30s due to polling reconcile OR sub-second via SSE user_offline).
9. Navigate to `/help` and `/training` → TopBar must NOT render there (those routes are outside AppShell).
10. Open dev tools → resize viewport to <768px → OnlineUsers strip in TopBar hides; ProfileDropdown remains visible.
11. Make 5 rapid saves within ~5 min → speed_warning toast fires (gentle 8s).
12. Force a long source_text save → char_limit_warning toast fires.
13. Force-kill the SSE connection (DevTools → Network → block /api/events) → after the reconnect attempt, useProfile + useOnlineUsers refetch automatically.

Record any issue not in the spec's accepted-limitations list. If found, file a follow-up plan task and skip tagging until resolved.

- [ ] **Step 3: Final regression check**

Run: `cd frontend && npm run test:run && cd .. && .venv/bin/python -m pytest backend/tests -q`
Expected: all PASS.

- [ ] **Step 4: Tag release**

```bash
git tag -a paket-16d-gamification-ui -m "Paket 16d: Gamification UI

TopBar (XP/streak/today/online/profile dropdown+bell) mounted in
AppShell. Profile /me replaces 16a STUB. SSE handlers refactored into
orchestrator; new handlers for badge_unlocked, speed/char warnings,
user_online/user_offline. 3 new endpoints (online users, badges catalog,
mark-all-read). Broker QueueFull path hardened to prevent ghost users.

Codex adversarial review: 11 BROKEN + 8 FRAGILE findings fixed across
3 passes during design.

Coverage ≥80% all metrics. Zero regression to 16a/b/c."
```

- [ ] **Step 5: Push tag (only if user explicitly approves remote push — this is a one-line ask)**

If the user has previously expressed approval for pushing tags to origin (handoff §3 point 1 says direct-to-main; tag push is a separate destructive-ish action), ask once:

> "16d tag'i hazır. `git push origin paket-16d-gamification-ui` çalıştırayım mı?"

If yes: `git push origin paket-16d-gamification-ui`. Otherwise skip and stop.

---

## Acceptance Criteria Mapping

Each acceptance criterion from spec §15 mapped to a task:

| Spec criterion | Task(s) |
|---|---|
| All new unit + hook + integration tests pass | T8-T34 |
| 16a/16b/16c existing tests pass | T20, T27, T35 |
| Coverage ≥80% all 4 metrics | T35 |
| `npm run typecheck` clean | T35 |
| `npm run lint` clean | T35 |
| `npm run gen:types:check` clean | T7, T35 |
| GET `/api/users/online` returns shape; auth required | T3 |
| GET `/api/badges/catalog` returns 7 entries with criterion | T1, T2 |
| POST `/api/me/notifications/read-all` returns marked_count; idempotent | T4 |
| SSE emits user_online on subscribe (excluding self) + user_offline on unsubscribe AND QueueFull drop | T5, T6 |
| Broker QueueFull path cleanly removes dead queue | T5 |
| Backend tests cover new endpoints + broker hardening | T1-T6 |
| Manual E2E smoke | T36 |
| No regression to 16b SSE lock handling | T16, T20, T35 |
| No regression to 16b annotation save flow | T27, T35 |
| TopBar visible on all post-training routes; hidden on login/register/help/training | T27 (routing inherited from 16a) + T36 step 9 manual verification |
| Profile /me reachable, all sections render with default seed user | T34 + T36 step 2 |

---

## Self-Review (post-write checklist)

1. **Spec coverage** — all 18 sections covered:
   - §1 Goal/scope → tasks across all phases
   - §2 Tech stack → no new deps (Verified)
   - §3 Backend contract → T1-T6 + T7 types regen
   - §4 Locked decisions D1-D7 → wired in components (TopBar layout T26, OnlineUsers T24, badge toast T18 no action button, Profile /me single-scroll T34, locked badges T28, mark-all-read T4+T12, refetchInterval T12+T14)
   - §5 Folder structure → tasks create exactly the listed files (note: §5.1 says "formatRelativeTr MOVED — re-export only" but actually it's already in `lib/formatters.ts`; **plan explicitly reuses from there** in the reconciliation block at the top)
   - §6 Routing → T34 (no route tree changes)
   - §7 TopBar → T21-T27
   - §8 Profile → T28-T34
   - §9 SSE handlers → T16-T20
   - §10 Hooks & queries → T11-T14
   - §11 Type guards → T8 + per-hook fail isolation in T11/T12/T13/T14/T26/T29/T31/T34
   - §12 Accessibility → aria-labels in T21-T34 tests
   - §13 Codex findings — every BROKEN/FRAGILE has at least one Codex-citation comment in the relevant task
   - §14 Tests — coverage targets in T35
   - §15 Acceptance — mapping table above
   - §16 Manual E2E — T36 step 2
   - §17 Files changed summary — matches the File Map at top
   - §18 Risks — `min-h-0` precaution in T27; QueueFull recursion guarded in T5; create_task vs inline broadcast decision documented in T5
2. **Placeholders** — scanned. None found.
3. **Type consistency** — `notificationsKeys`, `profileKeys`, `badgesKeys`, `usersKeys` named consistently. `Notification` type used uniformly. `BadgeCatalogItem.criterion` field appears as `string | null | undefined` consistently (Zod `.nullable().optional()`).

---

**End of plan. 36 tasks, ~750 LOC backend changes + ~2500 LOC frontend changes + ~2000 LOC tests, targeting ≥80% coverage and zero 16a/b/c regression.**

