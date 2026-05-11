# Paket 9 — Gamification + Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an XP ledger, streak counter, badge unlocks, daily-target counters, and an in-app notifications inbox. Hooks into the annotations save/skip/complete paths to award XP, update streaks, fire badge checks, persist notifications, and publish personal SSE events (`badge_unlocked`, `notification`). Expose `GET /api/me/profile`, `GET /api/me/notifications`, `POST /api/me/notifications/{id}/read`.

**Architecture:** Two new modules — `backend/gamification/` (XP, streak, badges, orchestrator) and `backend/notifications/` (inbox CRUD + routes). Both follow the Paket 8 pattern: pure service functions plus an async orchestrator wired into `backend/annotations/routes.py` AFTER the existing publish + behavioral blocks. Each side-effect is fault-isolated — a gamification or notification failure never rolls back the save and never 500s the request.

**Tech Stack:** Existing schema tables (`gamification_state`, `gamification_ledger`, `badges_earned`, `notifications`) seeded in `v0001`. Existing `backend.shared.audit`, `backend.shared.settings`, `backend.shared.sse.broker`. Existing `require_passed_training` / `get_current_user` deps. No new third-party deps.

---

## Mimari Kararlar (Locked)

- **Module layout:**
  - `backend/gamification/` — `service.py` (XP, streak, counters, orchestrator), `badges.py` (static metadata + `check_badges` detector), `models.py` (Pydantic for `/api/me/profile`).
  - `backend/notifications/` — `service.py` (CRUD), `models.py`, `routes.py` mounted at `/api/me/notifications/...`.
  - `/api/me/profile` lives on the existing `backend/users/routes.py` (alongside `/api/auth/*`) — it's a "me" endpoint, not a domain-prefix one. We don't create a new `me/` module.
- **Trigger points (mirror Paket 8 fault-isolation pattern):**
  - `annotations.routes.save` (already async; already has behavioral hook) → adds a third try/except: `await gamification_service.run_after_save(db, user_id, username, action, is_diff_zero, document_id)`.
  - `annotations.routes.complete` (already async) → adds a try/except: `await gamification_service.run_after_complete(db, user_id, username, completed, document_id)`.
  - `annotations.routes.skip` (sync) → adds a sync `gamification_service.record_skip(db, user_id)` call. Skip yields 0 XP, no badges, no SSE — only increments `today_skip_count`. Stays sync.
- **XP rules (read from `site_settings` so admin can tune):**
  - Save create → `gamification.xp_save` (default 1, reason=`save`)
  - Save edit → `gamification.xp_review` (default 2, reason=`review`)
  - Complete (false→true toggle only) → `gamification.xp_complete` (default 5, reason=`complete`)
  - Uncomplete (true→false) → 0 XP (decrements today_complete_count toward floor 0)
  - Skip → 0 XP
  - Training pass → `gamification.xp_training_pass` (default 50, reason=`training_pass`) — out of scope (Paket 10 wires this)
  - Review kept (post-hoc) → `gamification.xp_review_kept` (default 3, reason=`review_kept`) — fires inside `run_after_save` when `action='edit'` AND `is_diff_zero=true` AND prior version's user_id is a different user; awards that prior user +3, re-checks their badges, publishes SSE to them. Post-hoc multi-user side effect is the design.
- **Streak semantics:**
  - Day boundary = UTC+3 calendar date. Helper `_today_tr() -> str` returns `"YYYY-MM-DD"` in UTC+3.
  - Transition rules (on every successful save):
    - `last_active_date is None` → first activity ever: set to today, streak=1, longest=max(1, prior).
    - `last_active_date == today` → no change to streak (multiple saves same day = same streak).
    - `last_active_date == yesterday` (today-1) → streak += 1, longest = max(streak, longest).
    - `last_active_date < yesterday` → streak = 1, longest unchanged.
  - Streak only updates on `save` actions. complete/skip do not touch streak. (Spec: "Her gün en az 1 save → streak += 1".)
- **today_* counter reset (lazy):**
  - Every state write checks `last_active_date`. If `last_active_date != today`, reset all `today_save_count`, `today_complete_count`, `today_review_count`, `today_skip_count` to 0 first, then increment the relevant counter for the current action.
  - No daily midnight job needed for counters — the lazy reset does it.
- **Badge definitions:**

  | ID | name | criterion |
  |---|---|---|
  | `first_annotation` | İlk Annotation | total save count (ledger reasons in {save, review}) ≥ 1 |
  | `annotations_10` | 10 Annotation | total save count ≥ 10 |
  | `annotations_100` | 100 Annotation | total save count ≥ 100 |
  | `annotations_1000` | 1000 Annotation | total save count ≥ 1000 |
  | `first_completion` | İlk Tamamlama | total complete count (ledger reason='complete') ≥ 1 |
  | `marathoner` | Maratoncu | current_streak_days ≥ 7 |
  | `good_reviewer` | Good Reviewer | review count ≥ `gamification.good_reviewer.min_reviews` AND review_kept count ≥ `gamification.good_reviewer.min_kept` |

  - "Save count" = ledger rows where reason in (`save`, `review`).
  - "Complete count" = ledger rows where reason = `complete`.
  - "Review count" = ledger rows where reason = `review`.
  - "Review_kept count" = ledger rows where reason = `review_kept`.
  - Idempotency: `badges_earned` has PK `(user_id, badge_id)`. `check_badges` queries the criteria, deducts already-earned badges, returns the list of NEWLY-earned. The orchestrator inserts each newly-earned row and only then publishes the unlock event.
- **SSE events (personal):**
  - `badge_unlocked` `{badge_id, name, description, earned_at}` — published per newly-earned badge inside the orchestrator.
  - `notification` `{notification_id, kind, title, body, data}` — published every time `notifications.service.create()` writes a row.
  - `streak_at_risk` `{current_streak, hours_left}` — DEFERRED. Requires a midnight scheduler that the project doesn't have yet. Out of scope. Flagged as follow-up.
- **Notification creation policy:**
  - Every newly-earned badge → ALSO creates a notification row (so an offline user sees it in their inbox on next login). The notification's `kind='badge_unlocked'`, `data_json={badge_id, name, description, earned_at}`. The notification creation triggers a `notification` SSE event automatically. The badge unlock SSE event is published separately so the live UI can pop a "shiny" toast that's distinct from inbox-style "you have a new notification" UI.
  - Result: when a badge unlocks while user is online, they receive BOTH `badge_unlocked` and `notification` SSE events for that one unlock. Frontend dedupes via the badge_id in both payloads.
  - This is the explicit, documented design — not a bug to dedup later.
- **Atomicity:**
  - The save itself has already committed before `run_after_save` runs (Paket 8 pattern). Gamification's own writes (ledger row + state update + badge row + notification row) live inside one inner BEGIN/COMMIT. If any of them fail, we roll back the gamification side-effect and the save still stands.
  - SSE publishes happen AFTER the gamification commit (so a broker bug can't poison the gamification DB write).
- **Profile endpoint scope:**
  - `GET /api/me/profile` is gated by `get_current_user` only — NOT `require_passed_training`. Pre-training users can see their (zero-XP) profile.
  - Response shape:
    ```json
    {
      "user": {"id": int, "username": str, "role": str, "avatar_color": str},
      "xp": {"total": int},
      "streak": {"current": int, "longest": int, "last_active_date": str | null},
      "today": {"save": int, "complete": int, "review": int, "skip": int, "daily_target": int},
      "badges": [{"id": str, "name": str, "description": str, "earned_at": str}, ...]
    }
    ```
  - Lazy state row creation: if no row exists for the user (first profile fetch before any save), return zeros without inserting a row.
- **Notifications endpoint scope:**
  - `GET /api/me/notifications?unread_only=true&limit=50` — default returns unread; `unread_only=false` returns all (most-recent-first). Limit defaults to 50, max 200.
  - `POST /api/me/notifications/{id}/read` — marks single notification as read. 404 if not the calling user's notification (existence-hide style — don't leak that someone else's id exists). 200 if already read (idempotent).
  - Both gated by `get_current_user`.
- **Settings keys consumed (already seeded in v0001):**
  - `gamification.xp_save` (1), `xp_complete` (5), `xp_review` (2), `xp_review_kept` (3), `xp_training_pass` (50)
  - `gamification.daily_target_docs` (20)
  - `gamification.good_reviewer.min_reviews` (20), `min_kept` (15)
- **Type hints on `db`:** Per Paket 7/8 reviewer convention, use `db: sqlite3.Connection` annotations on new service functions.

## Dosya Yapısı

```
backend/gamification/                   # NEW package
├── __init__.py                         # empty
├── badges.py                           # BADGE_DEFS dict + check_badges(db, user_id) detector
├── models.py                           # Pydantic for /api/me/profile response
└── service.py                          # award_xp, update_streak_and_counters,
                                        #   record_skip, run_after_save, run_after_complete,
                                        #   get_profile_state

backend/notifications/                  # NEW package
├── __init__.py                         # empty
├── models.py                           # NotificationOut, NotificationListResponse
├── routes.py                           # GET /api/me/notifications, POST .../{id}/read
└── service.py                          # create, list_for_user, mark_read

backend/users/routes.py                 # MODIFY: add GET /api/me/profile
backend/annotations/routes.py           # MODIFY: invoke gamification orchestrators
backend/main.py                         # MODIFY: mount notifications_router

tests/test_notifications_service.py     # NEW — CRUD unit tests
tests/test_notifications_routes.py      # NEW — HTTP integration
tests/test_gamification_xp.py           # NEW — award_xp + ledger + state
tests/test_gamification_streak.py       # NEW — streak transitions + counter reset
tests/test_gamification_badges.py       # NEW — check_badges per badge type
tests/test_gamification_orchestrator.py # NEW — run_after_save/run_after_complete unit tests
tests/test_gamification_integration.py  # NEW — through POST /api/annotations + /complete
tests/test_me_profile_route.py          # NEW — GET /api/me/profile
tests/test_sse_publish_gamification.py  # NEW — personal-only invariant for badge/notification
```

---

## Task 1: Notifications Service (CRUD)

**Goal:** Pure service for notifications table operations. No SSE yet — that wires up in Task 6.

**Files:**
- Create: `backend/notifications/__init__.py`
- Create: `backend/notifications/service.py`
- Create: `tests/test_notifications_service.py`

- [ ] **Step 1: Create empty package**

Run:
```bash
mkdir -p /Users/barandincoguz/Desktop/deneme/backend/notifications
touch /Users/barandincoguz/Desktop/deneme/backend/notifications/__init__.py
```

- [ ] **Step 2: Write `tests/test_notifications_service.py`**

```python
"""Unit tests for notifications.service CRUD."""
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.notifications import service as notif


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (2, 'bob', 'x', 'user', ?, ?)",
        (now, now),
    )
    yield conn
    conn.close()


def test_create_returns_id_and_persists(db):
    nid = notif.create(
        db, user_id=1, kind="badge_unlocked",
        title="Yeni rozet!", body="İlk Annotation rozetini kazandın.",
        data={"badge_id": "first_annotation"},
    )
    assert isinstance(nid, int) and nid > 0

    rows = db.execute("SELECT user_id, kind, title, is_read FROM notifications").fetchall()
    assert len(rows) == 1
    assert rows[0]["user_id"] == 1
    assert rows[0]["kind"] == "badge_unlocked"
    assert rows[0]["title"] == "Yeni rozet!"
    assert rows[0]["is_read"] == 0


def test_list_for_user_unread_only(db):
    notif.create(db, user_id=1, kind="badge_unlocked", title="N1")
    nid_read = notif.create(db, user_id=1, kind="info", title="N2")
    notif.mark_read(db, notification_id=nid_read, user_id=1)
    notif.create(db, user_id=2, kind="info", title="N-bob")

    out = notif.list_for_user(db, user_id=1, unread_only=True)
    assert len(out) == 1
    assert out[0]["title"] == "N1"


def test_list_for_user_all_returns_read_too(db):
    n1 = notif.create(db, user_id=1, kind="a", title="N1")
    n2 = notif.create(db, user_id=1, kind="b", title="N2")
    notif.mark_read(db, notification_id=n1, user_id=1)

    out = notif.list_for_user(db, user_id=1, unread_only=False)
    titles = sorted(o["title"] for o in out)
    assert titles == ["N1", "N2"]


def test_list_for_user_other_users_excluded(db):
    notif.create(db, user_id=1, kind="x", title="alice")
    notif.create(db, user_id=2, kind="x", title="bob")

    alice = notif.list_for_user(db, user_id=1)
    bob = notif.list_for_user(db, user_id=2)
    assert [n["title"] for n in alice] == ["alice"]
    assert [n["title"] for n in bob] == ["bob"]


def test_list_orders_newest_first(db):
    n1 = notif.create(db, user_id=1, kind="a", title="first")
    n2 = notif.create(db, user_id=1, kind="b", title="second")
    out = notif.list_for_user(db, user_id=1)
    assert [o["id"] for o in out] == [n2, n1]


def test_list_respects_limit(db):
    for i in range(15):
        notif.create(db, user_id=1, kind="x", title=f"N{i}")
    out = notif.list_for_user(db, user_id=1, limit=5)
    assert len(out) == 5


def test_mark_read_idempotent(db):
    nid = notif.create(db, user_id=1, kind="x", title="N")
    notif.mark_read(db, notification_id=nid, user_id=1)
    notif.mark_read(db, notification_id=nid, user_id=1)  # second time: no error
    row = db.execute("SELECT is_read FROM notifications WHERE id=?", (nid,)).fetchone()
    assert row["is_read"] == 1


def test_mark_read_wrong_user_raises_not_found(db):
    nid = notif.create(db, user_id=1, kind="x", title="N")
    with pytest.raises(notif.NotificationNotFound):
        notif.mark_read(db, notification_id=nid, user_id=2)


def test_mark_read_unknown_id_raises_not_found(db):
    with pytest.raises(notif.NotificationNotFound):
        notif.mark_read(db, notification_id=99999, user_id=1)


def test_data_json_roundtrips(db):
    nid = notif.create(
        db, user_id=1, kind="x", title="N",
        data={"badge_id": "annotations_10", "earned_at": "2026-05-07T10:00:00+00:00"},
    )
    out = notif.list_for_user(db, user_id=1)
    assert out[0]["data"] == {"badge_id": "annotations_10", "earned_at": "2026-05-07T10:00:00+00:00"}


def test_create_with_no_data_returns_none_data_in_list(db):
    nid = notif.create(db, user_id=1, kind="x", title="N")
    out = notif.list_for_user(db, user_id=1)
    assert out[0]["data"] is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_notifications_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.notifications.service'`.

- [ ] **Step 4: Implement `backend/notifications/service.py`**

```python
"""Notifications inbox CRUD.

Public API:
  create(db, *, user_id, kind, title, body=None, data=None) -> int (new id)
  list_for_user(db, *, user_id, unread_only=True, limit=50) -> list[dict]
  mark_read(db, *, notification_id, user_id) -> None
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional


class NotificationNotFound(Exception):
    """Either id doesn't exist or it's not this user's notification."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create(
    db: sqlite3.Connection,
    *,
    user_id: int,
    kind: str,
    title: str,
    body: Optional[str] = None,
    data: Optional[dict] = None,
) -> int:
    cur = db.execute(
        """
        INSERT INTO notifications(user_id, kind, title, body, data_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, kind, title, body, json.dumps(data) if data is not None else None, _now()),
    )
    return cur.lastrowid


def list_for_user(
    db: sqlite3.Connection,
    *,
    user_id: int,
    unread_only: bool = True,
    limit: int = 50,
) -> list[dict]:
    if limit > 200:
        limit = 200
    if limit < 1:
        limit = 1
    if unread_only:
        sql = (
            "SELECT id, kind, title, body, data_json, is_read, created_at "
            "FROM notifications WHERE user_id=? AND is_read=0 "
            "ORDER BY id DESC LIMIT ?"
        )
    else:
        sql = (
            "SELECT id, kind, title, body, data_json, is_read, created_at "
            "FROM notifications WHERE user_id=? "
            "ORDER BY id DESC LIMIT ?"
        )
    rows = db.execute(sql, (user_id, limit)).fetchall()
    out: list[dict] = []
    for r in rows:
        out.append({
            "id": r["id"],
            "kind": r["kind"],
            "title": r["title"],
            "body": r["body"],
            "data": json.loads(r["data_json"]) if r["data_json"] else None,
            "is_read": bool(r["is_read"]),
            "created_at": r["created_at"],
        })
    return out


def mark_read(
    db: sqlite3.Connection,
    *,
    notification_id: int,
    user_id: int,
) -> None:
    row = db.execute(
        "SELECT user_id FROM notifications WHERE id=?", (notification_id,)
    ).fetchone()
    if row is None or row["user_id"] != user_id:
        raise NotificationNotFound(notification_id)
    db.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notification_id,))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_notifications_service.py -v`
Expected: 11 PASS.

- [ ] **Step 6: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 328 prior + 11 new = 339 PASS.

- [ ] **Step 7: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/notifications/__init__.py backend/notifications/service.py tests/test_notifications_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(notifications): add inbox CRUD service

Pure service over the notifications table: create, list_for_user with
unread filter and limit cap, mark_read with cross-user existence-hiding.
No SSE delivery yet — the orchestrator in Paket 9 Task 6 wires that up.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Notifications HTTP Routes

**Goal:** `GET /api/me/notifications` and `POST /api/me/notifications/{id}/read`.

**Files:**
- Create: `backend/notifications/models.py`
- Create: `backend/notifications/routes.py`
- Modify: `backend/main.py`
- Create: `tests/test_notifications_routes.py`

- [ ] **Step 1: Write `tests/test_notifications_routes.py`**

```python
"""HTTP tests for /api/me/notifications endpoints."""
from backend.shared.db import connect
from backend import config


def test_list_requires_auth(client):
    r = client.get("/api/me/notifications")
    assert r.status_code == 401


def test_list_returns_user_notifications_unread_default(passed_user):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    conn = connect(config.DB_PATH)
    try:
        from backend.notifications import service as notif
        notif.create(conn, user_id=user_id, kind="info", title="N1")
        notif.create(conn, user_id=user_id, kind="info", title="N2")
    finally:
        conn.close()

    r = c.get("/api/me/notifications")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert len(data["items"]) == 2
    titles = sorted(n["title"] for n in data["items"])
    assert titles == ["N1", "N2"]
    assert all(n["is_read"] is False for n in data["items"])


def test_list_unread_only_false_includes_read(passed_user):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    conn = connect(config.DB_PATH)
    try:
        from backend.notifications import service as notif
        n1 = notif.create(conn, user_id=user_id, kind="info", title="N1")
        notif.create(conn, user_id=user_id, kind="info", title="N2")
        notif.mark_read(conn, notification_id=n1, user_id=user_id)
    finally:
        conn.close()

    r = c.get("/api/me/notifications?unread_only=false")
    assert r.status_code == 200
    titles = sorted(n["title"] for n in r.json()["items"])
    assert titles == ["N1", "N2"]


def test_mark_read_persists(passed_user):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    conn = connect(config.DB_PATH)
    try:
        from backend.notifications import service as notif
        nid = notif.create(conn, user_id=user_id, kind="info", title="N")
    finally:
        conn.close()

    r = c.post(f"/api/me/notifications/{nid}/read")
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        row = conn.execute("SELECT is_read FROM notifications WHERE id=?", (nid,)).fetchone()
    finally:
        conn.close()
    assert row["is_read"] == 1


def test_mark_read_other_users_notification_404(second_passed_user):
    ctx = second_passed_user
    c = ctx["client"]
    bob_id = ctx["bob"]["id"]
    conn = connect(config.DB_PATH)
    try:
        from backend.notifications import service as notif
        bobs_id = notif.create(conn, user_id=bob_id, kind="info", title="bob's")
    finally:
        conn.close()

    ctx["login"]("alice")
    r = c.post(f"/api/me/notifications/{bobs_id}/read")
    assert r.status_code == 404


def test_mark_read_unknown_id_404(passed_user):
    r = passed_user["client"].post("/api/me/notifications/99999/read")
    assert r.status_code == 404


def test_list_pre_training_user_can_see_inbox(client):
    """Notification inbox doesn't require training pass — pre-training users
    might receive admin announcements."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("INV-NO-TRAIN",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": "u_pretrain", "password": "password123",
        "invite_code": "INV-NO-TRAIN",
    })
    assert r.status_code == 201
    r = client.post("/api/auth/login", json={
        "username": "u_pretrain", "password": "password123",
    })
    assert r.status_code == 200

    r = client.get("/api/me/notifications")
    assert r.status_code == 200  # NOT 409 (training_not_passed)
    assert r.json()["items"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_notifications_routes.py -v`
Expected: FAIL — 404 for /api/me/notifications.

- [ ] **Step 3: Write `backend/notifications/models.py`**

```python
"""Pydantic schemas for notifications endpoints."""
from typing import Any, Optional

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    is_read: bool
    created_at: str


class NotificationListResponse(BaseModel):
    items: list[NotificationOut]


class OkResponse(BaseModel):
    ok: bool = True
```

- [ ] **Step 4: Write `backend/notifications/routes.py`**

```python
"""HTTP endpoints for the notifications inbox.

Auth: get_current_user (NOT require_passed_training — even pre-training
users may receive admin announcements).
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.notifications import service
from backend.notifications.models import (
    NotificationListResponse, OkResponse,
)
from backend.users.deps import get_current_user, get_db


router = APIRouter(prefix="/api/me/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(get_current_user),
    unread_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
):
    items = service.list_for_user(
        db, user_id=user["id"], unread_only=unread_only, limit=limit,
    )
    return {"items": items}


@router.post("/{notification_id}/read", response_model=OkResponse)
def mark_read(
    notification_id: int,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(get_current_user),
):
    try:
        service.mark_read(db, notification_id=notification_id, user_id=user["id"])
    except service.NotificationNotFound:
        raise HTTPException(status_code=404, detail="notification not found")
    return {"ok": True}
```

- [ ] **Step 5: Mount the router in `backend/main.py`**

Add the import (alphabetical, near the other domain imports):

```python
from backend.notifications.routes import router as notifications_router
```

And below the other `app.include_router(...)` lines:

```python
app.include_router(notifications_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_notifications_routes.py -v`
Expected: 7 PASS.

- [ ] **Step 7: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 339 prior + 7 new = 346 PASS.

- [ ] **Step 8: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/notifications/models.py backend/notifications/routes.py backend/main.py tests/test_notifications_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(notifications): add GET and POST mark-read HTTP endpoints

GET /api/me/notifications with unread_only filter and limit cap (1..200).
POST /api/me/notifications/{id}/read with cross-user 404. Both gated by
get_current_user only — pre-training users see their inbox.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Gamification XP Service

**Goal:** `award_xp(db, user_id, delta_xp, reason, related_doc_id=None)` writes a ledger row and updates `gamification_state.total_xp`. Handles lazy state-row creation. Pure DB operation; no SSE.

**Files:**
- Create: `backend/gamification/__init__.py`
- Create: `backend/gamification/service.py`
- Create: `tests/test_gamification_xp.py`

- [ ] **Step 1: Create empty package**

Run:
```bash
mkdir -p /Users/barandincoguz/Desktop/deneme/backend/gamification
touch /Users/barandincoguz/Desktop/deneme/backend/gamification/__init__.py
```

- [ ] **Step 2: Write `tests/test_gamification_xp.py`**

```python
"""Unit tests for gamification.service.award_xp."""
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.gamification import service as gam


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', ?, ?)",
        (now, now),
    )
    yield conn
    conn.close()


def test_first_award_creates_state_row_and_writes_ledger(db):
    gam.award_xp(db, user_id=1, delta_xp=5, reason="complete", related_doc_id="doc_a")
    state = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=1").fetchone()
    assert state is not None
    assert state["total_xp"] == 5

    ledger = db.execute(
        "SELECT user_id, delta_xp, reason, related_doc_id FROM gamification_ledger"
    ).fetchall()
    assert len(ledger) == 1
    assert ledger[0]["user_id"] == 1
    assert ledger[0]["delta_xp"] == 5
    assert ledger[0]["reason"] == "complete"
    assert ledger[0]["related_doc_id"] == "doc_a"


def test_multiple_awards_accumulate_total_xp(db):
    gam.award_xp(db, user_id=1, delta_xp=1, reason="save")
    gam.award_xp(db, user_id=1, delta_xp=5, reason="complete")
    gam.award_xp(db, user_id=1, delta_xp=2, reason="review")
    total = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=1").fetchone()
    assert total["total_xp"] == 8


def test_zero_delta_still_writes_ledger(db):
    """Defensive: zero-XP events (e.g. skip) still benefit from a ledger
    breadcrumb. But the orchestrator decides whether to call award_xp
    for zero-XP cases; this just shows award_xp doesn't no-op."""
    gam.award_xp(db, user_id=1, delta_xp=0, reason="probe")
    rows = db.execute("SELECT delta_xp FROM gamification_ledger").fetchall()
    assert len(rows) == 1
    assert rows[0]["delta_xp"] == 0


def test_negative_delta_decrements(db):
    """Defensive: future undo flows might subtract XP. Make sure the math
    handles it without going below zero (clamp at 0)."""
    gam.award_xp(db, user_id=1, delta_xp=10, reason="x")
    gam.award_xp(db, user_id=1, delta_xp=-3, reason="undo")
    total = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=1").fetchone()
    assert total["total_xp"] == 7


def test_negative_delta_clamps_at_zero(db):
    gam.award_xp(db, user_id=1, delta_xp=2, reason="x")
    gam.award_xp(db, user_id=1, delta_xp=-10, reason="undo")
    total = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=1").fetchone()
    assert total["total_xp"] == 0


def test_ensure_state_idempotent(db):
    gam.ensure_state(db, user_id=1)
    gam.ensure_state(db, user_id=1)
    rows = db.execute("SELECT COUNT(*) AS c FROM gamification_state WHERE user_id=1").fetchall()
    assert rows[0]["c"] == 1


def test_get_xp_total_returns_zero_for_unknown_user(db):
    assert gam.get_xp_total(db, user_id=999) == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_gamification_xp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.gamification.service'`.

- [ ] **Step 4: Implement `backend/gamification/service.py` (XP portion only)**

```python
"""Gamification — XP, streak, counters, badges, orchestrator.

Public API (filled progressively across Paket 9 tasks):
  ensure_state(db, *, user_id)
  award_xp(db, *, user_id, delta_xp, reason, related_doc_id=None)
  get_xp_total(db, *, user_id) -> int
  update_streak_and_counters(db, *, user_id, action)  # Task 4
  record_skip(db, *, user_id)                         # Task 4
  run_after_save(db, *, user_id, username, action,    # Task 6
                 is_diff_zero, document_id)
  run_after_complete(db, *, user_id, username,        # Task 6
                     completed, document_id)
  get_profile_state(db, *, user_id) -> dict           # Task 8

Pure DB ops in this module; SSE publishes happen only inside the
orchestrator (Task 6).
"""
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional


log = logging.getLogger(__name__)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# State row management + XP
# ---------------------------------------------------------------------------

def ensure_state(db: sqlite3.Connection, *, user_id: int) -> None:
    """Insert a zero-state gamification_state row for the user if missing.
    Idempotent. Used by every write path that touches state."""
    db.execute(
        """
        INSERT OR IGNORE INTO gamification_state(
            user_id, total_xp, current_streak_days, longest_streak_days,
            last_active_date,
            today_save_count, today_complete_count,
            today_review_count, today_skip_count,
            updated_at
        ) VALUES (?, 0, 0, 0, NULL, 0, 0, 0, 0, ?)
        """,
        (user_id, _now_utc_iso()),
    )


def award_xp(
    db: sqlite3.Connection,
    *,
    user_id: int,
    delta_xp: int,
    reason: str,
    related_doc_id: Optional[str] = None,
) -> None:
    """Append a ledger row and update total_xp. Total clamps at 0 floor."""
    ensure_state(db, user_id=user_id)
    now = _now_utc_iso()
    db.execute(
        """
        INSERT INTO gamification_ledger(user_id, delta_xp, reason, related_doc_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, delta_xp, reason, related_doc_id, now),
    )
    db.execute(
        """
        UPDATE gamification_state
           SET total_xp = MAX(0, total_xp + ?),
               updated_at = ?
         WHERE user_id = ?
        """,
        (delta_xp, now, user_id),
    )


def get_xp_total(db: sqlite3.Connection, *, user_id: int) -> int:
    row = db.execute(
        "SELECT total_xp FROM gamification_state WHERE user_id=?", (user_id,)
    ).fetchone()
    return row["total_xp"] if row else 0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_gamification_xp.py -v`
Expected: 7 PASS.

- [ ] **Step 6: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 346 prior + 7 new = 353 PASS.

- [ ] **Step 7: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/gamification/__init__.py backend/gamification/service.py tests/test_gamification_xp.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(gamification): add award_xp + ledger row + state row management

ensure_state idempotently materializes a zero-state row. award_xp appends
a ledger entry and bumps total_xp with a 0-floor clamp so future undo
flows don't go negative. get_xp_total returns 0 for unseeded users.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Streak + Today-Counters

**Goal:** `update_streak_and_counters(db, user_id, action)` handles streak transitions in UTC+3 and lazy resets of today_*_count fields. `record_skip(db, user_id)` is the sync entry point used by `annotations.routes.skip`.

**Files:**
- Modify: `backend/gamification/service.py`
- Create: `tests/test_gamification_streak.py`

- [ ] **Step 1: Write `tests/test_gamification_streak.py`**

```python
"""Unit tests for streak transitions and today_* counter resets.

Day boundary = UTC+3 calendar date. Tests directly seed last_active_date
to control transitions deterministically.
"""
from datetime import datetime, timezone, timedelta

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.gamification import service as gam


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', ?, ?)",
        (now, now),
    )
    yield conn
    conn.close()


def _seed_state(conn, *, last_active_date, current_streak=0, longest_streak=0,
                today_save=0, today_complete=0, today_review=0, today_skip=0):
    conn.execute("DELETE FROM gamification_state WHERE user_id=1")
    conn.execute(
        """
        INSERT INTO gamification_state(
            user_id, total_xp, current_streak_days, longest_streak_days,
            last_active_date, today_save_count, today_complete_count,
            today_review_count, today_skip_count, updated_at
        ) VALUES (1, 0, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (current_streak, longest_streak, last_active_date,
         today_save, today_complete, today_review, today_skip,
         datetime.now(timezone.utc).isoformat()),
    )


def _read_state(conn):
    return dict(conn.execute("SELECT * FROM gamification_state WHERE user_id=1").fetchone())


def test_first_save_ever_starts_streak_at_one(db):
    """No state row at all: first save creates row, streak=1, longest=1."""
    today = gam._today_tr()
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["last_active_date"] == today
    assert s["current_streak_days"] == 1
    assert s["longest_streak_days"] == 1
    assert s["today_save_count"] == 1


def test_multiple_saves_same_day_no_streak_change(db):
    today = gam._today_tr()
    _seed_state(db, last_active_date=today, current_streak=3, longest_streak=5,
                today_save=2)
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["current_streak_days"] == 3  # unchanged
    assert s["longest_streak_days"] == 5
    assert s["today_save_count"] == 3


def test_consecutive_day_increments_streak(db):
    today = gam._today_tr()
    yesterday_dt = datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)
    yesterday = yesterday_dt.strftime("%Y-%m-%d")
    _seed_state(db, last_active_date=yesterday, current_streak=4, longest_streak=4)
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["last_active_date"] == today
    assert s["current_streak_days"] == 5
    assert s["longest_streak_days"] == 5  # caught up


def test_consecutive_day_can_extend_longest(db):
    today = gam._today_tr()
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    _seed_state(db, last_active_date=yesterday, current_streak=7, longest_streak=7)
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["current_streak_days"] == 8
    assert s["longest_streak_days"] == 8


def test_gap_resets_current_streak_preserves_longest(db):
    today = gam._today_tr()
    two_days_ago = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=2)).strftime("%Y-%m-%d")
    _seed_state(db, last_active_date=two_days_ago, current_streak=10, longest_streak=10)
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["current_streak_days"] == 1
    assert s["longest_streak_days"] == 10


def test_today_counters_reset_on_day_change(db):
    today = gam._today_tr()
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    _seed_state(db, last_active_date=yesterday, current_streak=2, longest_streak=2,
                today_save=8, today_complete=3, today_review=2, today_skip=1)
    gam.update_streak_and_counters(db, user_id=1, action="save_create")
    s = _read_state(db)
    assert s["today_save_count"] == 1     # reset to 0 then +1
    assert s["today_complete_count"] == 0  # reset
    assert s["today_review_count"] == 0
    assert s["today_skip_count"] == 0


def test_save_edit_increments_review_counter(db):
    gam.update_streak_and_counters(db, user_id=1, action="save_edit")
    s = _read_state(db)
    assert s["today_save_count"] == 1
    assert s["today_review_count"] == 1


def test_complete_increments_complete_counter_only_streak_unchanged(db):
    today = gam._today_tr()
    _seed_state(db, last_active_date=today, current_streak=3, longest_streak=3,
                today_save=5)
    gam.update_streak_and_counters(db, user_id=1, action="complete")
    s = _read_state(db)
    assert s["today_save_count"] == 5         # unchanged
    assert s["today_complete_count"] == 1
    assert s["current_streak_days"] == 3       # complete does NOT extend streak


def test_complete_on_first_ever_activity_does_not_seed_streak(db):
    """Spec: streak only updates on save events. A user who only completes
    has no streak. Their last_active_date stays None until they save."""
    gam.update_streak_and_counters(db, user_id=1, action="complete")
    s = _read_state(db)
    assert s["current_streak_days"] == 0
    assert s["last_active_date"] is None
    assert s["today_complete_count"] == 1


def test_record_skip_increments_skip_counter_only(db):
    """Skip path: sync function, just bumps the counter. No streak, no XP."""
    gam.record_skip(db, user_id=1)
    s = _read_state(db)
    assert s["today_skip_count"] == 1
    assert s["current_streak_days"] == 0
    assert s["last_active_date"] is None


def test_record_skip_resets_today_counters_on_day_change(db):
    today = gam._today_tr()
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    _seed_state(db, last_active_date=yesterday, today_save=4, today_skip=1)
    gam.record_skip(db, user_id=1)
    s = _read_state(db)
    # skip is NOT a save action, so last_active_date stays at yesterday
    assert s["last_active_date"] == yesterday
    # but today counters DID reset on read because we crossed the day boundary
    assert s["today_save_count"] == 0
    assert s["today_skip_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_gamification_streak.py -v`
Expected: FAIL — `_today_tr` / `update_streak_and_counters` / `record_skip` not defined.

- [ ] **Step 3: Append streak + counter helpers to `backend/gamification/service.py`**

Insert below the XP block (after `get_xp_total`):

```python
# ---------------------------------------------------------------------------
# Streak + today-counter management
# ---------------------------------------------------------------------------

from datetime import timedelta

VALID_ACTIONS = ("save_create", "save_edit", "complete", "uncomplete", "skip")
_TR_TZ = timezone(timedelta(hours=3))


def _today_tr() -> str:
    """Today in Turkey time (UTC+3) as YYYY-MM-DD."""
    return datetime.now(_TR_TZ).date().isoformat()


def _is_yesterday_tr(d: str) -> bool:
    """Is the YYYY-MM-DD string exactly one Turkey-time day before today?"""
    today = datetime.strptime(_today_tr(), "%Y-%m-%d").date()
    try:
        d_date = datetime.strptime(d, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    return (today - d_date).days == 1


def _maybe_reset_today_counters(state_row: dict) -> dict:
    """If the row's last_active_date is older than today (TR), zero the
    today_* counters in the returned dict. Caller writes the dict back."""
    today = _today_tr()
    out = dict(state_row)
    last = out.get("last_active_date")
    if last != today:
        out["today_save_count"] = 0
        out["today_complete_count"] = 0
        out["today_review_count"] = 0
        out["today_skip_count"] = 0
    return out


def _next_streak(last_active_date, current, longest):
    """Compute (new_last_active_date, new_current, new_longest) for a save
    action firing today (TR). Only call this when the action is a save."""
    today = _today_tr()
    if last_active_date == today:
        return today, current, longest
    if _is_yesterday_tr(last_active_date or ""):
        new_current = current + 1
        return today, new_current, max(new_current, longest)
    # gap or first ever
    return today, 1, max(1, longest)


_COUNTER_BUMP = {
    "save_create": ("today_save_count", 1),
    "save_edit": ("today_save_count", 1),  # save_edit increments BOTH counters
    "complete": ("today_complete_count", 1),
    "uncomplete": ("today_complete_count", 0),
    "skip": ("today_skip_count", 1),
}


def update_streak_and_counters(
    db: sqlite3.Connection,
    *,
    user_id: int,
    action: str,
) -> None:
    """Single state-write entry point covering streak transition and the
    today_* counter bumps for save/complete/skip events. Lazily resets all
    today_* counters when the day rolls over.

    `action` is one of:
      - 'save_create'  → save count +1, streak transition
      - 'save_edit'    → save count +1 AND review count +1, streak transition
      - 'complete'     → complete count +1, no streak change
      - 'uncomplete'   → no counter changes (clamp behavior — symmetric undo
                          would require a delta but spec doesn't mandate it)
      - 'skip'         → use record_skip() instead; this raises if used here
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"unknown action: {action!r}")
    if action == "skip":
        # Skip path is intentionally split — keep the routing explicit.
        raise ValueError("use record_skip() for skip events")

    ensure_state(db, user_id=user_id)
    row = db.execute(
        "SELECT * FROM gamification_state WHERE user_id=?", (user_id,)
    ).fetchone()
    state = _maybe_reset_today_counters(dict(row))

    # Streak transition only on save actions.
    if action in ("save_create", "save_edit"):
        new_last, new_streak, new_longest = _next_streak(
            state.get("last_active_date"),
            state.get("current_streak_days", 0),
            state.get("longest_streak_days", 0),
        )
        state["last_active_date"] = new_last
        state["current_streak_days"] = new_streak
        state["longest_streak_days"] = new_longest

    # Counter bump.
    if action == "save_create":
        state["today_save_count"] += 1
    elif action == "save_edit":
        state["today_save_count"] += 1
        state["today_review_count"] += 1
    elif action == "complete":
        state["today_complete_count"] += 1
    # uncomplete / skip handled separately

    db.execute(
        """
        UPDATE gamification_state SET
            last_active_date=?,
            current_streak_days=?,
            longest_streak_days=?,
            today_save_count=?,
            today_complete_count=?,
            today_review_count=?,
            today_skip_count=?,
            updated_at=?
         WHERE user_id=?
        """,
        (
            state["last_active_date"],
            state["current_streak_days"],
            state["longest_streak_days"],
            state["today_save_count"],
            state["today_complete_count"],
            state["today_review_count"],
            state["today_skip_count"],
            _now_utc_iso(),
            user_id,
        ),
    )


def record_skip(db: sqlite3.Connection, *, user_id: int) -> None:
    """Sync entry point for the skip route. Bumps today_skip_count, runs
    the lazy day-rollover reset, but does NOT touch streak or last_active_date
    (skip is not a 'save')."""
    ensure_state(db, user_id=user_id)
    row = db.execute(
        "SELECT * FROM gamification_state WHERE user_id=?", (user_id,)
    ).fetchone()
    state = _maybe_reset_today_counters(dict(row))
    state["today_skip_count"] += 1
    db.execute(
        """
        UPDATE gamification_state SET
            today_save_count=?,
            today_complete_count=?,
            today_review_count=?,
            today_skip_count=?,
            updated_at=?
         WHERE user_id=?
        """,
        (
            state["today_save_count"],
            state["today_complete_count"],
            state["today_review_count"],
            state["today_skip_count"],
            _now_utc_iso(),
            user_id,
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_gamification_streak.py -v`
Expected: 11 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 353 prior + 11 new = 364 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/gamification/service.py tests/test_gamification_streak.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(gamification): add streak + today-counter management

UTC+3 day boundary; consecutive-day extends streak, gap resets to 1.
Lazy today_* counter reset every state write covers the day-rollover
without a midnight job. record_skip is the sync entry point for the
skip route — bumps skip count without touching streak.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Badge Definitions + check_badges Detector

**Goal:** Static `BADGE_DEFS` dict + `check_badges(db, user_id)` returning the list of newly-earned badge IDs (idempotent — already-earned badges excluded).

**Files:**
- Create: `backend/gamification/badges.py`
- Create: `tests/test_gamification_badges.py`

- [ ] **Step 1: Write `tests/test_gamification_badges.py`**

```python
"""Unit tests for badge unlock detection."""
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.gamification import badges, service as gam


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', ?, ?)",
        (now, now),
    )
    yield conn
    conn.close()


def _ledger(conn, user_id, reason, n):
    """Plant N ledger rows of the given reason for the user."""
    now = datetime.now(timezone.utc).isoformat()
    for _ in range(n):
        conn.execute(
            "INSERT INTO gamification_ledger(user_id, delta_xp, reason, created_at) "
            "VALUES (?, 1, ?, ?)",
            (user_id, reason, now),
        )


def test_first_annotation_unlocks_at_1_save(db):
    _ledger(db, 1, "save", 1)
    out = badges.check_badges(db, user_id=1)
    assert "first_annotation" in out


def test_first_annotation_does_not_unlock_at_zero(db):
    out = badges.check_badges(db, user_id=1)
    assert "first_annotation" not in out


def test_annotations_10_unlocks_at_10_saves(db):
    _ledger(db, 1, "save", 10)
    out = badges.check_badges(db, user_id=1)
    assert {"first_annotation", "annotations_10"}.issubset(set(out))


def test_review_count_counts_toward_save_thresholds(db):
    """save and review are both 'productive' actions for the cumulative thresholds."""
    _ledger(db, 1, "save", 5)
    _ledger(db, 1, "review", 5)  # 5+5 = 10 total
    out = badges.check_badges(db, user_id=1)
    assert "annotations_10" in out


def test_first_completion_unlocks_at_first_complete(db):
    _ledger(db, 1, "complete", 1)
    out = badges.check_badges(db, user_id=1)
    assert "first_completion" in out


def test_marathoner_unlocks_at_streak_7(db):
    gam.ensure_state(db, user_id=1)
    db.execute(
        "UPDATE gamification_state SET current_streak_days=7 WHERE user_id=1"
    )
    out = badges.check_badges(db, user_id=1)
    assert "marathoner" in out


def test_marathoner_does_not_unlock_at_streak_6(db):
    gam.ensure_state(db, user_id=1)
    db.execute(
        "UPDATE gamification_state SET current_streak_days=6 WHERE user_id=1"
    )
    out = badges.check_badges(db, user_id=1)
    assert "marathoner" not in out


def test_good_reviewer_requires_both_min_reviews_and_min_kept(db):
    """20 reviews + 15 kept by default. With 19 reviews + 15 kept: no unlock.
    With 20 reviews + 14 kept: no unlock. With both met: unlock."""
    _ledger(db, 1, "review", 19)
    _ledger(db, 1, "review_kept", 15)
    assert "good_reviewer" not in badges.check_badges(db, user_id=1)

    _ledger(db, 1, "review", 1)  # now 20 reviews + 15 kept
    out = badges.check_badges(db, user_id=1)
    assert "good_reviewer" in out


def test_idempotent_already_earned_excluded(db):
    """A badge already in badges_earned is NOT re-emitted."""
    _ledger(db, 1, "save", 1)
    earned_at = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO badges_earned(user_id, badge_id, earned_at) VALUES (1, 'first_annotation', ?)",
        (earned_at,),
    )
    out = badges.check_badges(db, user_id=1)
    assert "first_annotation" not in out


def test_badge_defs_metadata_complete(db):
    """Every badge_id check_badges can return must have a name + description in BADGE_DEFS."""
    _ledger(db, 1, "save", 1000)
    _ledger(db, 1, "complete", 1)
    _ledger(db, 1, "review_kept", 15)
    _ledger(db, 1, "review", 20)
    gam.ensure_state(db, user_id=1)
    db.execute("UPDATE gamification_state SET current_streak_days=7 WHERE user_id=1")

    out = badges.check_badges(db, user_id=1)
    for bid in out:
        assert bid in badges.BADGE_DEFS
        assert "name" in badges.BADGE_DEFS[bid]
        assert "description" in badges.BADGE_DEFS[bid]


def test_check_badges_settings_overrides(db):
    """Admin tunes good_reviewer min_reviews=3, min_kept=2 → unlocks earlier."""
    from backend.shared import settings as S
    S.set_value(db, "gamification.good_reviewer.min_reviews", 3, updated_by_user_id=None)
    S.set_value(db, "gamification.good_reviewer.min_kept", 2, updated_by_user_id=None)
    _ledger(db, 1, "review", 3)
    _ledger(db, 1, "review_kept", 2)
    out = badges.check_badges(db, user_id=1)
    assert "good_reviewer" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_gamification_badges.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.gamification.badges'`.

- [ ] **Step 3: Implement `backend/gamification/badges.py`**

```python
"""Badge definitions + check_badges detector.

`BADGE_DEFS` maps badge_id → {name, description}.
`check_badges(db, user_id)` returns the list of newly-unlocked badge IDs
(already-earned ones excluded). The orchestrator handles inserting the
badges_earned rows + creating notifications + publishing SSE.
"""
import sqlite3

from backend.shared import settings as S


BADGE_DEFS: dict[str, dict[str, str]] = {
    "first_annotation": {
        "name": "İlk Annotation",
        "description": "İlk kayıt başarıyla yapıldı.",
    },
    "annotations_10": {
        "name": "10 Annotation",
        "description": "10 kayıt biriktirdin.",
    },
    "annotations_100": {
        "name": "100 Annotation",
        "description": "100 kayıt — istikrarlı çalışıyorsun.",
    },
    "annotations_1000": {
        "name": "1000 Annotation",
        "description": "Bin kayıt: ekibin omurgası oldun.",
    },
    "first_completion": {
        "name": "İlk Tamamlama",
        "description": "İlk dokümanı tamamlandı olarak işaretledin.",
    },
    "marathoner": {
        "name": "Maratoncu",
        "description": "7 gün üst üste çalıştın.",
    },
    "good_reviewer": {
        "name": "Good Reviewer",
        "description": "Yaptığın review'lerin çoğu sonraki kullanıcılar tarafından korundu.",
    },
}


def _save_total(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS c FROM gamification_ledger "
        "WHERE user_id=? AND reason IN ('save','review')",
        (user_id,),
    ).fetchone()
    return row["c"]


def _complete_total(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS c FROM gamification_ledger "
        "WHERE user_id=? AND reason='complete'",
        (user_id,),
    ).fetchone()
    return row["c"]


def _review_total(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS c FROM gamification_ledger "
        "WHERE user_id=? AND reason='review'",
        (user_id,),
    ).fetchone()
    return row["c"]


def _review_kept_total(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS c FROM gamification_ledger "
        "WHERE user_id=? AND reason='review_kept'",
        (user_id,),
    ).fetchone()
    return row["c"]


def _current_streak(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT current_streak_days FROM gamification_state WHERE user_id=?",
        (user_id,),
    ).fetchone()
    return row["current_streak_days"] if row else 0


def _already_earned(db: sqlite3.Connection, user_id: int) -> set[str]:
    rows = db.execute(
        "SELECT badge_id FROM badges_earned WHERE user_id=?", (user_id,)
    ).fetchall()
    return {r["badge_id"] for r in rows}


def check_badges(db: sqlite3.Connection, *, user_id: int) -> list[str]:
    """Return the list of badge_ids the user newly qualifies for, excluding
    those already in badges_earned. Order is stable per insertion."""
    saves = _save_total(db, user_id)
    completes = _complete_total(db, user_id)
    streak = _current_streak(db, user_id)
    reviews = _review_total(db, user_id)
    kept = _review_kept_total(db, user_id)
    min_reviews = S.get_int(db, "gamification.good_reviewer.min_reviews", default=20)
    min_kept = S.get_int(db, "gamification.good_reviewer.min_kept", default=15)

    candidates: list[str] = []
    if saves >= 1:
        candidates.append("first_annotation")
    if saves >= 10:
        candidates.append("annotations_10")
    if saves >= 100:
        candidates.append("annotations_100")
    if saves >= 1000:
        candidates.append("annotations_1000")
    if completes >= 1:
        candidates.append("first_completion")
    if streak >= 7:
        candidates.append("marathoner")
    if reviews >= min_reviews and kept >= min_kept:
        candidates.append("good_reviewer")

    earned = _already_earned(db, user_id)
    return [b for b in candidates if b not in earned]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_gamification_badges.py -v`
Expected: 11 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 364 prior + 11 new = 375 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/gamification/badges.py tests/test_gamification_badges.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(gamification): add 7 badge definitions + check_badges detector

Pure ledger-and-state query that returns newly-qualifying badge IDs,
excluding already-earned ones. Cumulative count thresholds, current
streak, and the good_reviewer compound rule (min_reviews AND min_kept
read from site_settings so admins can tune).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Orchestrator (`run_after_save`, `run_after_complete`)

**Goal:** Async orchestrator that ties together XP award + streak update + badge check + notification creation + SSE publish. Handles the post-hoc `review_kept` award to a previous editor when `is_diff_zero=True`.

**Files:**
- Modify: `backend/gamification/service.py`
- Create: `tests/test_gamification_orchestrator.py`

- [ ] **Step 1: Write `tests/test_gamification_orchestrator.py`**

```python
"""Unit tests for gamification.service.run_after_save / run_after_complete.

Drives the full orchestrator: XP award, streak update, badge check, notification
create, SSE publish to the saving user (and to a prior editor on review_kept).
"""
import asyncio
import json
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.shared.sse import broker as sse_broker
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.gamification import service as gam


@pytest.fixture(autouse=True)
def _reset_broker():
    sse_broker._subscribers.clear()
    yield
    sse_broker._subscribers.clear()


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (2, 'bob', 'x', 'user', ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
        "sentence_count, text_density, estimated_difficulty, created_at) "
        "VALUES ('doc_1', 'x.json', 'text', 1, 1, 1.0, 'Kolay', ?)",
        (now,),
    )
    yield conn
    conn.close()


def _seed_prior_version(conn, doc_id, user_id, refs_json="[]"):
    """Plant an annotation_versions row so run_after_save can find a prior editor."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO annotation_versions(document_id, user_id, references_json, "
        "diff_from_previous, is_diff_zero, action, created_at) "
        "VALUES (?, ?, ?, ?, 0, 'create', ?)",
        (doc_id, user_id, refs_json, json.dumps({"added": [], "removed": []}), now),
    )


def test_save_create_awards_xp_and_increments_counters(db):
    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="create", is_diff_zero=False, document_id="doc_1",
    ))

    state = db.execute("SELECT total_xp, today_save_count, current_streak_days FROM gamification_state WHERE user_id=1").fetchone()
    assert state["total_xp"] == 1            # xp_save default
    assert state["today_save_count"] == 1
    assert state["current_streak_days"] == 1

    ledger = db.execute("SELECT reason, delta_xp FROM gamification_ledger").fetchall()
    assert len(ledger) == 1
    assert ledger[0]["reason"] == "save"
    assert ledger[0]["delta_xp"] == 1


def test_save_edit_awards_review_xp(db):
    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="edit", is_diff_zero=False, document_id="doc_1",
    ))
    state = db.execute("SELECT total_xp, today_review_count FROM gamification_state WHERE user_id=1").fetchone()
    assert state["total_xp"] == 2            # xp_review default
    assert state["today_review_count"] == 1


def test_save_create_unlocks_first_annotation_badge(db):
    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="create", is_diff_zero=False, document_id="doc_1",
    ))

    # badges_earned has the row
    rows = db.execute("SELECT badge_id FROM badges_earned WHERE user_id=1").fetchall()
    assert {r["badge_id"] for r in rows} == {"first_annotation"}

    # SSE: badge_unlocked + notification both published
    received = []
    async def _drain():
        for _ in range(2):
            received.append(await asyncio.wait_for(queue.get(), timeout=2.0))
    asyncio.run(_drain())
    types = sorted(e.event_type for e in received)
    assert types == ["badge_unlocked", "notification"]

    # notification row also persisted
    nrow = db.execute("SELECT kind, title FROM notifications WHERE user_id=1").fetchone()
    assert nrow["kind"] == "badge_unlocked"


def test_complete_awards_xp_publishes_no_extra_event_if_no_badge(db):
    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(gam.run_after_complete(
        db, user_id=1, username="alice",
        completed=True, document_id="doc_1",
    ))
    state = db.execute("SELECT total_xp, today_complete_count FROM gamification_state WHERE user_id=1").fetchone()
    assert state["total_xp"] == 5
    assert state["today_complete_count"] == 1

    # First complete unlocks first_completion → 2 events
    received = []
    async def _drain():
        for _ in range(2):
            received.append(await asyncio.wait_for(queue.get(), timeout=2.0))
    asyncio.run(_drain())
    types = sorted(e.event_type for e in received)
    assert types == ["badge_unlocked", "notification"]


def test_uncomplete_awards_zero_xp_no_events(db):
    asyncio.run(gam.run_after_complete(
        db, user_id=1, username="alice",
        completed=True, document_id="doc_1",
    ))
    queue = sse_broker.subscribe(user_id=1)

    asyncio.run(gam.run_after_complete(
        db, user_id=1, username="alice",
        completed=False, document_id="doc_1",
    ))
    # No new XP awarded
    total = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=1").fetchone()["total_xp"]
    assert total == 5  # unchanged

    # No new event delivered
    async def _wait():
        return await asyncio.wait_for(queue.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_wait())


def test_review_kept_awards_prior_user_xp(db):
    """alice edits doc_1 with diff_zero against bob's prior version → bob gets +3.

    Note: the orchestrator queries the last 2 annotation_versions and treats
    the second-most-recent as the prior editor. So we plant TWO rows: bob's
    older version, then alice's just-inserted current version. (In a real
    save through annotations.service, the new version row is already
    committed before run_after_save fires.)"""
    _seed_prior_version(db, "doc_1", user_id=2)  # bob's prior version
    _seed_prior_version(db, "doc_1", user_id=1)  # alice's just-inserted current
    bob_q = sse_broker.subscribe(user_id=2)

    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="edit", is_diff_zero=True, document_id="doc_1",
    ))

    # bob got +3 (xp_review_kept default)
    bob_total = db.execute("SELECT total_xp FROM gamification_state WHERE user_id=2").fetchone()
    assert bob_total["total_xp"] == 3
    bob_ledger = db.execute(
        "SELECT reason FROM gamification_ledger WHERE user_id=2"
    ).fetchall()
    assert any(r["reason"] == "review_kept" for r in bob_ledger)


def test_review_kept_does_not_self_award(db):
    """If the prior version's editor is the same user, NO review_kept award.
    Plant TWO alice-versions so _prior_version_user_id resolves to alice
    (not None), then assert the same-user-skip branch fires."""
    _seed_prior_version(db, "doc_1", user_id=1)  # alice's older version
    _seed_prior_version(db, "doc_1", user_id=1)  # alice's current version

    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="edit", is_diff_zero=True, document_id="doc_1",
    ))
    rows = db.execute(
        "SELECT reason FROM gamification_ledger WHERE user_id=1 AND reason='review_kept'"
    ).fetchall()
    assert rows == []  # no self-kept


def test_personal_scope_other_users_dont_see_alice_badge(db):
    """Bob is online; alice unlocks first_annotation. Bob's queue stays empty."""
    bob_q = sse_broker.subscribe(user_id=2)
    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="create", is_diff_zero=False, document_id="doc_1",
    ))
    async def _wait():
        return await asyncio.wait_for(bob_q.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_wait())


def test_xp_award_failure_does_not_block_streak_or_badges(db, monkeypatch):
    """If award_xp raises, the rest of the orchestrator (streak + badges)
    must still run. Each step is independently fault-isolated."""
    original_award = gam.award_xp
    call_count = {"n": 0}
    def boom_award(*a, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("award_xp boom")
        return original_award(*a, **kw)
    monkeypatch.setattr(gam, "award_xp", boom_award)

    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="create", is_diff_zero=False, document_id="doc_1",
    ))
    # Streak still updated
    state = db.execute("SELECT current_streak_days FROM gamification_state WHERE user_id=1").fetchone()
    assert state["current_streak_days"] == 1


def test_run_after_complete_uncomplete_does_not_touch_streak(db):
    asyncio.run(gam.run_after_save(
        db, user_id=1, username="alice",
        action="create", is_diff_zero=False, document_id="doc_1",
    ))
    streak_before = db.execute(
        "SELECT current_streak_days FROM gamification_state WHERE user_id=1"
    ).fetchone()["current_streak_days"]

    asyncio.run(gam.run_after_complete(
        db, user_id=1, username="alice",
        completed=True, document_id="doc_1",
    ))
    asyncio.run(gam.run_after_complete(
        db, user_id=1, username="alice",
        completed=False, document_id="doc_1",
    ))
    streak_after = db.execute(
        "SELECT current_streak_days FROM gamification_state WHERE user_id=1"
    ).fetchone()["current_streak_days"]
    assert streak_after == streak_before
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_gamification_orchestrator.py -v`
Expected: FAIL — `run_after_save` / `run_after_complete` not defined.

- [ ] **Step 3: Append the orchestrator to `backend/gamification/service.py`**

Insert below the streak block (after `record_skip`):

```python
# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

from backend.shared import settings as S
from backend.shared.sse import broker as sse_broker
from backend.gamification import badges as badges_module
from backend.notifications import service as notif_service


def _xp_for_save_action(db: sqlite3.Connection, action: str) -> int:
    if action == "create":
        return S.get_int(db, "gamification.xp_save", default=1)
    if action == "edit":
        return S.get_int(db, "gamification.xp_review", default=2)
    return 0


def _award_badges_and_notify(
    db: sqlite3.Connection, *, user_id: int, username: str,
) -> list[dict]:
    """Insert each newly-earned badge row and return the list of unlock
    payloads for SSE publishing. Caller does the publishes."""
    earned: list[dict] = []
    for badge_id in badges_module.check_badges(db, user_id=user_id):
        meta = badges_module.BADGE_DEFS.get(badge_id, {"name": badge_id, "description": ""})
        now = _now_utc_iso()
        db.execute(
            "INSERT OR IGNORE INTO badges_earned(user_id, badge_id, earned_at) "
            "VALUES (?, ?, ?)",
            (user_id, badge_id, now),
        )
        # Persist a notification row (also publishes 'notification' SSE event below)
        notif_service.create(
            db, user_id=user_id, kind="badge_unlocked",
            title=f"Yeni rozet: {meta['name']}",
            body=meta["description"],
            data={"badge_id": badge_id, "name": meta["name"],
                  "description": meta["description"], "earned_at": now},
        )
        earned.append({
            "badge_id": badge_id,
            "name": meta["name"],
            "description": meta["description"],
            "earned_at": now,
        })
    return earned


async def _publish_unlock_events(user_id: int, earned: list[dict]) -> None:
    for payload in earned:
        await sse_broker.publish_to([user_id], "badge_unlocked", payload)
        # Also publish a generic 'notification' event so the inbox indicator updates
        await sse_broker.publish_to(
            [user_id], "notification",
            {"kind": "badge_unlocked", "data": payload},
        )


async def run_after_save(
    db: sqlite3.Connection,
    *,
    user_id: int,
    username: str,
    action: str,            # 'create' | 'edit'
    is_diff_zero: bool,
    document_id: str,
) -> None:
    """Run after annotations.service.save_annotation has committed.

    Awards XP (xp_save or xp_review), updates streak/today-counters, checks
    for badge unlocks, persists a notification per unlock, and publishes
    personal SSE events. If `action='edit'` and `is_diff_zero=True`, also
    awards the prior version's editor +3 (xp_review_kept) — except when
    that prior editor is the same user.

    Each step is independently fault-isolated. Caller must invoke AFTER
    the save commits."""
    # --- 1. XP award (own action) ---
    try:
        delta = _xp_for_save_action(db, action)
        if delta > 0:
            reason = "save" if action == "create" else "review"
            award_xp(db, user_id=user_id, delta_xp=delta, reason=reason,
                     related_doc_id=document_id)
    except Exception:
        log.exception("award_xp failed for user %s on %s", user_id, document_id)

    # --- 2. Streak + counter update ---
    try:
        sub_action = "save_create" if action == "create" else "save_edit"
        update_streak_and_counters(db, user_id=user_id, action=sub_action)
    except Exception:
        log.exception("streak update failed for user %s", user_id)

    # --- 3. Badge check + notify (own user) ---
    own_earned: list[dict] = []
    try:
        own_earned = _award_badges_and_notify(db, user_id=user_id, username=username)
    except Exception:
        log.exception("badge check failed for user %s", user_id)

    # --- 4. Post-hoc review_kept for prior editor (if applicable) ---
    prior_earned: list[dict] = []
    prior_user_id: Optional[int] = None
    if action == "edit" and is_diff_zero:
        try:
            prior_user_id = _prior_version_user_id(
                db, document_id=document_id, current_user_id=user_id,
            )
            if prior_user_id is not None:
                kept_xp = S.get_int(db, "gamification.xp_review_kept", default=3)
                award_xp(db, user_id=prior_user_id, delta_xp=kept_xp,
                         reason="review_kept", related_doc_id=document_id)
                prior_earned = _award_badges_and_notify(
                    db, user_id=prior_user_id, username="",
                )
        except Exception:
            log.exception(
                "review_kept post-hoc award failed for prior editor %s on %s",
                prior_user_id, document_id,
            )

    # --- 5. SSE publishes ---
    try:
        await _publish_unlock_events(user_id, own_earned)
        if prior_user_id is not None:
            await _publish_unlock_events(prior_user_id, prior_earned)
    except Exception:
        log.exception("badge_unlocked publish failed")


async def run_after_complete(
    db: sqlite3.Connection,
    *,
    user_id: int,
    username: str,
    completed: bool,
    document_id: str,
) -> None:
    """Run after annotations.service.set_complete has committed for a real
    state change (caller has already filtered out same-state no-ops).

    On `completed=True`: awards xp_complete (default 5), bumps today_complete_count,
    checks for first_completion badge.
    On `completed=False`: no XP, no counter bump (clamp), no badge check."""
    if not completed:
        return

    try:
        delta = S.get_int(db, "gamification.xp_complete", default=5)
        if delta > 0:
            award_xp(db, user_id=user_id, delta_xp=delta, reason="complete",
                     related_doc_id=document_id)
    except Exception:
        log.exception("complete xp award failed for user %s", user_id)

    try:
        update_streak_and_counters(db, user_id=user_id, action="complete")
    except Exception:
        log.exception("complete counter update failed for user %s", user_id)

    own_earned: list[dict] = []
    try:
        own_earned = _award_badges_and_notify(db, user_id=user_id, username=username)
    except Exception:
        log.exception("badge check failed for user %s on complete", user_id)

    try:
        await _publish_unlock_events(user_id, own_earned)
    except Exception:
        log.exception("badge_unlocked publish failed (complete path)")


def _prior_version_user_id(
    db: sqlite3.Connection, *, document_id: str, current_user_id: int,
) -> Optional[int]:
    """Return the second-most-recent annotation_versions.user_id for the doc
    (the version BEFORE the one the current save just inserted), if it
    belongs to a different user. None otherwise."""
    rows = db.execute(
        """
        SELECT user_id FROM annotation_versions
         WHERE document_id=?
         ORDER BY id DESC LIMIT 2
        """,
        (document_id,),
    ).fetchall()
    if len(rows) < 2:
        return None
    prior_user_id = rows[1]["user_id"]
    if prior_user_id == current_user_id:
        return None
    return prior_user_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_gamification_orchestrator.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 375 prior + 10 new = 385 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/gamification/service.py tests/test_gamification_orchestrator.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(gamification): add run_after_save/run_after_complete orchestrators

Each orchestrator runs XP award + streak/counter update + badge check +
notification create + SSE publish, with each step fault-isolated. The
save orchestrator also awards review_kept (+3) to the prior editor when
the current save is action=edit AND is_diff_zero — multi-user side
effect by design. Same-user prior versions don't self-award.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Wire Orchestrator into `annotations/routes.py`

**Goal:** Hook `gamification.run_after_save`, `run_after_complete`, and `record_skip` into the three annotation routes. Same fault-isolation pattern as Paket 8's behavioral wiring.

**Files:**
- Modify: `backend/annotations/routes.py`
- Create: `tests/test_gamification_integration.py`

- [ ] **Step 1: Write `tests/test_gamification_integration.py`**

```python
"""Integration tests: gamification fires through annotation HTTP routes."""
import asyncio
from datetime import datetime, timezone

import pytest
from backend.shared.sse import broker as sse_broker
from backend.shared.db import connect
from backend import config


@pytest.fixture(autouse=True)
def _reset_broker():
    sse_broker._subscribers.clear()
    yield
    sse_broker._subscribers.clear()


def _ref(**overrides):
    base = {
        "kanun_no": "5520", "kanun_ad": "KVK", "madde": "5",
        "fikra": "1", "bent": "a", "source_text": "kısa",
    }
    base.update(overrides)
    return base


def test_first_save_awards_xp_and_unlocks_first_annotation(passed_user, ingest_doc):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_g1")

    queue = sse_broker.subscribe(user_id=user_id)
    r = c.post("/api/annotations", json={
        "document_id": "doc_g1", "references": [_ref()],
    })
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        state = conn.execute(
            "SELECT total_xp, today_save_count, current_streak_days "
            "FROM gamification_state WHERE user_id=?", (user_id,),
        ).fetchone()
        badges = conn.execute(
            "SELECT badge_id FROM badges_earned WHERE user_id=?", (user_id,),
        ).fetchall()
    finally:
        conn.close()
    assert state["total_xp"] == 1
    assert state["today_save_count"] == 1
    assert state["current_streak_days"] == 1
    assert {b["badge_id"] for b in badges} == {"first_annotation"}


def test_skip_increments_skip_count_no_xp(passed_user, ingest_doc):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_g_skip")
    r = c.post("/api/annotations/doc_g_skip/skip")
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        state = conn.execute(
            "SELECT total_xp, today_skip_count FROM gamification_state WHERE user_id=?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    assert state["total_xp"] == 0
    assert state["today_skip_count"] == 1


def test_complete_awards_xp_and_unlocks_first_completion(passed_user, ingest_doc):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_g_complete")
    # Need an annotation row before complete works
    r = c.post("/api/annotations", json={
        "document_id": "doc_g_complete", "references": [_ref()],
    })
    assert r.status_code == 200

    queue = sse_broker.subscribe(user_id=user_id)
    r = c.post("/api/annotations/doc_g_complete/complete", json={"completed": True})
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        total = conn.execute(
            "SELECT total_xp FROM gamification_state WHERE user_id=?", (user_id,),
        ).fetchone()["total_xp"]
        badges = conn.execute(
            "SELECT badge_id FROM badges_earned WHERE user_id=?", (user_id,),
        ).fetchall()
    finally:
        conn.close()
    # 1 (save) + 5 (complete) = 6
    assert total == 6
    assert "first_completion" in {b["badge_id"] for b in badges}


def test_uncomplete_does_not_decrement_xp(passed_user, ingest_doc):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_g_uc")
    c.post("/api/annotations", json={"document_id": "doc_g_uc", "references": [_ref()]})
    c.post("/api/annotations/doc_g_uc/complete", json={"completed": True})
    c.post("/api/annotations/doc_g_uc/complete", json={"completed": False})
    conn = connect(config.DB_PATH)
    try:
        total = conn.execute(
            "SELECT total_xp FROM gamification_state WHERE user_id=?", (user_id,),
        ).fetchone()["total_xp"]
    finally:
        conn.close()
    # 1 (save) + 5 (complete) + 0 (uncomplete) = 6 — no decrement
    assert total == 6


def test_orchestrator_failure_does_not_500_save(passed_user, ingest_doc, monkeypatch):
    """If gamification.run_after_save explodes, the save still returns 200."""
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_g_isolate")

    async def boom(*args, **kwargs):
        raise RuntimeError("orchestrator exploded")
    monkeypatch.setattr(
        "backend.annotations.routes.gamification_service.run_after_save", boom
    )
    r = c.post("/api/annotations", json={
        "document_id": "doc_g_isolate", "references": [_ref()],
    })
    assert r.status_code == 200


def test_review_kept_post_hoc_award_through_http(second_passed_user, ingest_doc):
    """bob saves doc_x → alice edits doc_x with the same references (diff_zero)
    → bob gets +3 xp_review_kept."""
    ctx = second_passed_user
    c = ctx["client"]
    bob_id = ctx["bob"]["id"]
    ingest_doc("doc_g_kept")

    ctx["login"]("bob")
    r = c.post("/api/annotations", json={
        "document_id": "doc_g_kept", "references": [_ref()],
    })
    assert r.status_code == 200

    ctx["login"]("alice")
    r = c.post("/api/annotations", json={
        "document_id": "doc_g_kept", "references": [_ref()],  # identical → diff_zero
    })
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        bob_total = conn.execute(
            "SELECT total_xp FROM gamification_state WHERE user_id=?", (bob_id,),
        ).fetchone()["total_xp"]
    finally:
        conn.close()
    # bob: 1 (save) + 3 (review_kept) = 4
    assert bob_total == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_gamification_integration.py -v`
Expected: FAIL — gamification module not wired into routes; first save → no badge row, no XP.

- [ ] **Step 3: Modify `backend/annotations/routes.py`**

Add the import (alphabetical, near `from backend.behavioral import service as behavioral_service`):

```python
from backend.gamification import service as gamification_service
```

Append a third try/except inside `save` (AFTER the existing behavioral try/except, BEFORE `return result`):

```python
    try:
        action = "create" if result["is_new"] else "edit"
        await gamification_service.run_after_save(
            db,
            user_id=user["id"],
            username=user["username"],
            action=action,
            is_diff_zero=result["is_diff_zero"],
            document_id=payload.document_id,
        )
    except Exception:
        log.exception("gamification.run_after_save failed for %s", payload.document_id)
```

Add a try/except inside `complete` (AFTER the `if will_change:` publish_broadcast block, BEFORE `return {"ok": True}`):

```python
    if will_change:
        try:
            await gamification_service.run_after_complete(
                db,
                user_id=user["id"],
                username=user["username"],
                completed=payload.completed,
                document_id=document_id,
            )
        except Exception:
            log.exception("gamification.run_after_complete failed for %s", document_id)
```

Add a sync call inside `skip` (AFTER `service.skip_annotation`, BEFORE `return {"ok": True}`):

```python
    try:
        gamification_service.record_skip(db, user_id=user["id"])
    except Exception:
        log.exception("gamification.record_skip failed for %s", document_id)
```

Update the three docstrings to reflect the new responsibility (one-line additions naming gamification — keep them concise).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_gamification_integration.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 385 prior + 6 new = 391 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/annotations/routes.py tests/test_gamification_integration.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(annotations): wire gamification orchestrators into save/skip/complete

save: third try/except after behavioral hook → run_after_save with
action+is_diff_zero. complete: orchestrator only on real state changes.
skip: sync record_skip — bumps today_skip_count, no XP. All three
fault-isolated; orchestrator failure cannot 500 the request.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `GET /api/me/profile`

**Goal:** Return user XP, streak, today counters, and earned badges in one fetch. Auth: `get_current_user` (no training gate).

**Files:**
- Create: `backend/gamification/models.py`
- Modify: `backend/users/routes.py` (add the endpoint)
- Modify: `backend/gamification/service.py` (add `get_profile_state`)
- Create: `tests/test_me_profile_route.py`

- [ ] **Step 1: Write `tests/test_me_profile_route.py`**

```python
"""HTTP tests for GET /api/me/profile."""
from backend.shared.db import connect
from backend import config


def _ref(**overrides):
    base = {
        "kanun_no": "5520", "kanun_ad": "KVK", "madde": "5",
        "fikra": "1", "bent": "a", "source_text": "kısa",
    }
    base.update(overrides)
    return base


def test_profile_requires_auth(client):
    r = client.get("/api/me/profile")
    assert r.status_code == 401


def test_profile_pre_training_user_returns_zero_state(client):
    """Pre-training user can fetch profile — sees zeroed state, no badges."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("INV-PROF",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": "u_prof", "password": "password123", "invite_code": "INV-PROF",
    })
    assert r.status_code == 201
    r = client.post("/api/auth/login", json={
        "username": "u_prof", "password": "password123",
    })
    assert r.status_code == 200

    r = client.get("/api/me/profile")
    assert r.status_code == 200  # NOT 409
    data = r.json()
    assert data["user"]["username"] == "u_prof"
    assert data["xp"]["total"] == 0
    assert data["streak"]["current"] == 0
    assert data["streak"]["last_active_date"] is None
    assert data["today"]["save"] == 0
    assert data["today"]["daily_target"] == 20  # default from settings
    assert data["badges"] == []


def test_profile_after_save_reflects_xp_and_badge(passed_user, ingest_doc):
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_prof")

    r = c.post("/api/annotations", json={
        "document_id": "doc_prof", "references": [_ref()],
    })
    assert r.status_code == 200

    r = c.get("/api/me/profile")
    assert r.status_code == 200
    data = r.json()
    assert data["xp"]["total"] == 1
    assert data["streak"]["current"] == 1
    assert data["today"]["save"] == 1
    assert any(b["id"] == "first_annotation" for b in data["badges"])


def test_profile_user_section_has_avatar_color(passed_user):
    r = passed_user["client"].get("/api/me/profile")
    assert r.status_code == 200
    user = r.json()["user"]
    assert "avatar_color" in user
    assert user["avatar_color"].startswith("#")


def test_profile_today_daily_target_reflects_settings(passed_user):
    """Admin-tunable daily target shows up in the response."""
    conn = connect(config.DB_PATH)
    try:
        from backend.shared import settings as S
        S.set_value(conn, "gamification.daily_target_docs", 35, updated_by_user_id=None)
    finally:
        conn.close()
    r = passed_user["client"].get("/api/me/profile")
    assert r.status_code == 200
    assert r.json()["today"]["daily_target"] == 35
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_me_profile_route.py -v`
Expected: FAIL — `/api/me/profile` not registered.

- [ ] **Step 3: Write `backend/gamification/models.py`**

```python
"""Pydantic schemas for gamification endpoints."""
from typing import Optional

from pydantic import BaseModel


class UserSection(BaseModel):
    id: int
    username: str
    role: str
    avatar_color: str


class XpSection(BaseModel):
    total: int


class StreakSection(BaseModel):
    current: int
    longest: int
    last_active_date: Optional[str]


class TodaySection(BaseModel):
    save: int
    complete: int
    review: int
    skip: int
    daily_target: int


class BadgeOut(BaseModel):
    id: str
    name: str
    description: str
    earned_at: str


class ProfileResponse(BaseModel):
    user: UserSection
    xp: XpSection
    streak: StreakSection
    today: TodaySection
    badges: list[BadgeOut]
```

- [ ] **Step 4: Append `get_profile_state` to `backend/gamification/service.py`**

Below the orchestrator block, add:

```python
# ---------------------------------------------------------------------------
# Profile aggregator
# ---------------------------------------------------------------------------

def get_profile_state(db: sqlite3.Connection, *, user_id: int) -> dict:
    """Aggregate the gamification slice of a user's profile. Returns zeros
    if no state row exists (pre-save user)."""
    state = db.execute(
        "SELECT total_xp, current_streak_days, longest_streak_days, "
        "last_active_date, today_save_count, today_complete_count, "
        "today_review_count, today_skip_count "
        "FROM gamification_state WHERE user_id=?",
        (user_id,),
    ).fetchone()
    daily_target = S.get_int(db, "gamification.daily_target_docs", default=20)

    if state is None:
        xp_total = 0
        current = longest = 0
        last_active = None
        save = complete = review = skip = 0
    else:
        # Lazy day-rollover: if last_active < today_tr, the today_* counters
        # the user sees should be zero (mirroring how the next save would reset).
        today = _today_tr()
        if state["last_active_date"] != today:
            save = complete = review = skip = 0
        else:
            save = state["today_save_count"]
            complete = state["today_complete_count"]
            review = state["today_review_count"]
            skip = state["today_skip_count"]
        xp_total = state["total_xp"]
        current = state["current_streak_days"]
        longest = state["longest_streak_days"]
        last_active = state["last_active_date"]

    badge_rows = db.execute(
        "SELECT badge_id, earned_at FROM badges_earned WHERE user_id=? "
        "ORDER BY earned_at ASC",
        (user_id,),
    ).fetchall()
    badges_out: list[dict] = []
    for r in badge_rows:
        meta = badges_module.BADGE_DEFS.get(
            r["badge_id"], {"name": r["badge_id"], "description": ""},
        )
        badges_out.append({
            "id": r["badge_id"],
            "name": meta["name"],
            "description": meta["description"],
            "earned_at": r["earned_at"],
        })

    return {
        "xp": {"total": xp_total},
        "streak": {
            "current": current, "longest": longest,
            "last_active_date": last_active,
        },
        "today": {
            "save": save, "complete": complete, "review": review,
            "skip": skip, "daily_target": daily_target,
        },
        "badges": badges_out,
    }
```

- [ ] **Step 5: Add the `/api/me/profile` route to `backend/users/routes.py`**

Add the import at the top:

```python
from backend.gamification import service as gamification_service
from backend.gamification.models import ProfileResponse
```

Add the route below the existing user routes (e.g. after the `/auth/me` endpoint or wherever fits the file's grouping):

```python
@router.get("/me/profile", response_model=ProfileResponse)
def get_my_profile(
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(get_current_user),
):
    """Aggregated profile: identity + XP + streak + today counters + badges.
    Gated by get_current_user only (pre-training users see their zeroed state)."""
    state = gamification_service.get_profile_state(db, user_id=user["id"])
    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "avatar_color": user["avatar_color"],
        },
        **state,
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_me_profile_route.py -v`
Expected: 5 PASS.

- [ ] **Step 7: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 391 prior + 5 new = 396 PASS.

- [ ] **Step 8: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/gamification/models.py backend/gamification/service.py backend/users/routes.py tests/test_me_profile_route.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(profile): add GET /api/me/profile aggregating xp/streak/today/badges

Single fetch returns identity + XP total + streak + today counters
(with lazy day-rollover) + earned badges with full metadata. Gated
by get_current_user only — pre-training users see zeroed state.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: SSE Personal-Only Invariant Tests

**Goal:** Defense-in-depth like Paket 8 Task 7 — pin that `badge_unlocked` and `notification` are personal events, never broadcast. A future refactor that misuses `publish_broadcast` is caught here.

**Files:**
- Create: `tests/test_sse_publish_gamification.py`

- [ ] **Step 1: Write `tests/test_sse_publish_gamification.py`**

```python
"""Verify gamification publishes personal SSE events to the saving user
only — never as broadcast.

annotation_saved is broadcast (Paket 7) and reaches all online users; the
gamification events (badge_unlocked, notification) must reach only the
user who triggered them. A subscribed second user should never receive
the personal events generated by another user's actions.
"""
import asyncio

import pytest
from backend.shared.sse import broker as sse_broker


@pytest.fixture(autouse=True)
def _reset_broker():
    sse_broker._subscribers.clear()
    yield
    sse_broker._subscribers.clear()


def _ref(**overrides):
    base = {
        "kanun_no": "5520", "kanun_ad": "KVK", "madde": "5",
        "fikra": "1", "bent": "a", "source_text": "kısa",
    }
    base.update(overrides)
    return base


def test_first_save_badge_only_to_saving_user(second_passed_user, ingest_doc):
    """alice's first save unlocks first_annotation. Bob (online) sees the
    annotation_saved broadcast but NOT badge_unlocked or notification."""
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_gam_publ")
    alice_id = ctx["alice"]["id"]
    bob_id = ctx["bob"]["id"]

    bob_q = sse_broker.subscribe(user_id=bob_id)
    alice_q = sse_broker.subscribe(user_id=alice_id)

    ctx["login"]("alice")
    r = c.post("/api/annotations", json={
        "document_id": "doc_gam_publ", "references": [_ref()],
    })
    assert r.status_code == 200

    async def _drain(q, n, timeout=2.0):
        out = []
        for _ in range(n):
            out.append(await asyncio.wait_for(q.get(), timeout=timeout))
        return out

    # alice's queue: annotation_saved (broadcast) + badge_unlocked + notification
    alice_events = asyncio.run(_drain(alice_q, 3))
    types = sorted(e.event_type for e in alice_events)
    assert types == ["annotation_saved", "badge_unlocked", "notification"]

    # bob's queue: only annotation_saved
    bob_events = asyncio.run(_drain(bob_q, 1))
    assert bob_events[0].event_type == "annotation_saved"

    # bob's queue must be empty (no badge or notification leaked)
    async def _empty():
        return await asyncio.wait_for(bob_q.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_empty())


def test_review_kept_publishes_only_to_prior_editor(second_passed_user, ingest_doc):
    """bob saves doc; alice edits with same refs (diff_zero) → bob gets the
    review_kept-driven badge events, alice does NOT get bob's badge events
    (alice gets her own first_annotation from her own save)."""
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_gam_kept")
    alice_id = ctx["alice"]["id"]
    bob_id = ctx["bob"]["id"]

    ctx["login"]("bob")
    c.post("/api/annotations", json={
        "document_id": "doc_gam_kept", "references": [_ref()],
    })

    bob_q = sse_broker.subscribe(user_id=bob_id)
    alice_q = sse_broker.subscribe(user_id=alice_id)

    ctx["login"]("alice")
    r = c.post("/api/annotations", json={
        "document_id": "doc_gam_kept", "references": [_ref()],  # diff_zero
    })
    assert r.status_code == 200

    # alice receives: annotation_saved (broadcast) + her own first_annotation
    # badge_unlocked + notification
    # bob receives: annotation_saved (broadcast); review_kept does NOT unlock
    # any new badge by itself for bob (bob's first_annotation already unlocked
    # on his earlier save), but the orchestrator may emit zero new events for him.
    # The hard invariant: bob's queue must NOT contain alice's first_annotation
    # badge_unlocked event.
    async def _collect(q, timeout=0.5):
        out = []
        try:
            while True:
                out.append(await asyncio.wait_for(q.get(), timeout=timeout))
        except asyncio.TimeoutError:
            pass
        return out

    alice_events = asyncio.run(_collect(alice_q, 1.0))
    bob_events = asyncio.run(_collect(bob_q, 0.5))

    # bob's annotation_saved is from alice's broadcast; nothing else
    bob_types = [e.event_type for e in bob_events]
    assert bob_types == ["annotation_saved"]

    # alice has her own badge events (first_annotation from her save's ledger row),
    # but we only assert: she sees 'badge_unlocked' and 'notification' — and they
    # describe HER badge, not bob's
    alice_unlock = next((e for e in alice_events if e.event_type == "badge_unlocked"), None)
    assert alice_unlock is not None
    assert alice_unlock.data["badge_id"] == "first_annotation"
```

- [ ] **Step 2: Run tests to verify they pass (Task 6+7's wiring already correct)**

Run: `.venv/bin/python -m pytest tests/test_sse_publish_gamification.py -v`
Expected: 2 PASS.

- [ ] **Step 3: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 396 prior + 2 new = 398 PASS.

- [ ] **Step 4: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add tests/test_sse_publish_gamification.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
test(sse): pin personal-only invariant for gamification events

Two-user tests confirm badge_unlocked and notification are delivered to
the user whose action triggered them — never broadcast. Bob (online and
subscribed) sees only the annotation_saved broadcast when alice saves;
alice's first_annotation badge does not leak.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Polish + Tag

**Goal:** Final cleanup pass and `paket-9-gamification-notifications` tag.

- [ ] **Step 1: Inspect for dead code / drift**

Run:
```bash
.venv/bin/python -m pytest -q
git diff main --stat   # sanity-check the surface
```

Look for and clean up:
- Unused imports in `backend/gamification/service.py` (the file grew a lot — check that mid-file imports added in Tasks 4/6/8 are all used).
- Unused `username` parameters on `run_after_save` / `run_after_complete`. The plan keeps these for caller-contract symmetry with Paket 8's `behavioral_service.run_after_save`. If they're genuinely unused everywhere, they can be dropped — but check that no future Paket 10 code anticipates them. Default: leave them.
- Any leftover `print(...)` statements.
- Docstring rot: did `annotations/routes.py` save/skip/complete docstrings get updated to mention gamification? If not, fix.

- [ ] **Step 2: Verify OpenAPI surface**

Run:
```bash
.venv/bin/python -c "
from backend.main import app
paths = sorted(p for p in app.openapi()['paths'])
for p in paths:
    if 'me' in p or 'notifications' in p:
        print(p)
"
```
Expected output includes:
```
/api/me/notifications
/api/me/notifications/{notification_id}/read
/api/me/profile
```

- [ ] **Step 3: Run full suite one final time**

Run: `.venv/bin/python -m pytest -q`
Expected: 398 PASS (or whatever count after polish; should be at least 398).

- [ ] **Step 4: Commit any polish + tag**

If polish changes were made:
```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add -A
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
chore(paket9): polish — drop unused imports, docstrings

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Note: do NOT add the untracked planning markdown files in `docs/superpowers/plans/` — they are tracked separately. Use targeted `git add` for source files only.

Tag:
```bash
git tag paket-9-gamification-notifications
git log --oneline -12
git tag --list 'paket-*'
```

Expected: `paket-9-gamification-notifications` appears alongside paket-1 through paket-8.

---

## Out of Scope / Follow-ups

- **`streak_at_risk` SSE event:** Spec lists this as a personal event with `{current_streak, hours_left}`. It requires a midnight scheduler that the project doesn't have yet. Out of scope for Paket 9 — flag for a later pass once a scheduled-task harness exists (likely bundled with Paket 12 backup loop or a dedicated cron module).
- **Daily streak rollover job (UTC+3 midnight):** Spec mentions "Hesaplama günlük midnight job ile (UTC+3)". The lazy-reset approach in Paket 9 covers today_* counters and streak transitions on the next save, but it does NOT proactively zero a user's streak when they miss a day if they don't open the app. This means a user who comes back after a 3-day gap will see their old streak in their profile until they save once. Acceptable for now (the streak displayed is technically the streak-as-of-last-activity, which is honest); add a true midnight job later if UI feedback demands it.
- **`POST /api/me/notifications/read-all`:** YAGNI — frontend can call mark-read in a loop. If batch UX is needed in Paket 16, add then.
- **XP undo flow:** `award_xp` accepts negative deltas with a 0-floor clamp, but no caller produces negative deltas yet. Reserved for future moderation flows.
- **Frontend toasts (TopBar XP, BadgeUnlockedToast):** Paket 16's job. Backend wire is ready.
- **Notification kinds beyond `badge_unlocked`:** Admin announcement notifications (`kind="admin_announce"`) belong to Paket 11 (admin panel).
- **good_reviewer badge in practice:** Will only unlock after `review_kept` ledger rows accumulate. The post-hoc award in `run_after_save` is the only emitter today; if the project grows other "kept" detectors (e.g. on annotation completion by a third user), those would also write `review_kept` ledger rows and contribute to the same compound check.
