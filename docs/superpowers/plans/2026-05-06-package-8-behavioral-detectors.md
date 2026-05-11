# Paket 8 — Behavioral Detectors + Site Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two behavioral detectors that fire after a successful annotation save (`speed_warning`, `char_limit_warning`), log to `behavioral_events`, and publish personal SSE events to the saving user. Add admin endpoints to read/write the runtime-tunable thresholds in `site_settings`.

**Architecture:** New `backend/behavioral/` module with pure detector functions + an async orchestrator. The orchestrator is invoked from `backend/annotations/routes.py:save` after the annotation has been written and the broadcast `annotation_saved` has been published. Detector failures are isolated — they never roll back the save. New `backend/admin/` module exposes `GET/PUT /api/admin/settings` (allowlisted to keys that already exist in `site_settings` to prevent arbitrary key creation).

**Tech Stack:** Existing `backend.shared.audit.log_behavioral`, `backend.shared.settings` typed accessors, `backend.shared.sse.broker.publish_to`, `backend.users.deps.require_admin`. No new third-party deps.

---

## Mimari Kararlar (Locked)

- **Module layout:** `backend/behavioral/` is service-only (no routes — invoked from `annotations/routes.py`). `backend/admin/` is route-only (delegates to `shared/settings.py`).
- **Trigger point:** `behavioral.service.run_after_save(...)` is called from `annotations/routes.py:save` AFTER both `service.save_annotation` and the `annotation_saved` broadcast publish. Detector failures are caught and logged; they never propagate as 500 to the client and never roll back the DB write (the save has already committed).
- **What triggers detectors:** Only `POST /api/annotations` (save). Skip and complete do NOT trigger detectors. Speed velocity is a save-rate metric; char-limit only makes sense on payloads that carry references.
- **Detector function shape:** Pure-ish — each takes `(db, ...)` and returns either `None` (no event) or a `dict` describing the verdict. The orchestrator is the only place that performs side effects (`log_behavioral` + `publish_to`).
- **speed_warning semantics:**
  - Window = `speed_warning.window_seconds` setting (default 300s).
  - Threshold = `speed_warning.max_saves_in_window` setting (default 5).
  - Counts `activity_events` rows with `event_type='annotation_save'` for the user in the last `window_seconds`.
  - **Dedup:** Suppress firing if user already has a `speed_warning` row in `behavioral_events` within the last `window_seconds`. This prevents spamming the user every save while they're hot — they get warned once per window. Without dedup, a user at 6 saves in 5 minutes would receive a warning on saves 6, 7, 8, 9, …
- **char_limit_warning semantics:**
  - `warn_threshold` (default 300) and `alert_threshold` (default 600) read from `site_settings`.
  - Scans every reference's `kanun_ad` and `source_text` length.
  - Aggregates per save: returns `level='alert'` if any field hits alert; else `level='warn'` if any hits warn; else `None`.
  - Payload includes `fields: [{ref_index, field, length, level}, ...]` so the frontend can highlight specific cells.
  - **No dedup** — each save evaluates independently. If the user's draft was edited down between saves, the warning naturally goes away.
- **`min_seconds_per_doc` (DEFERRED):** The setting `speed_warning.min_seconds_per_doc=30` exists in v0001 seeds, but Paket 4 does not yet log `document_open` activity events. Implementing this rule requires upstream document_open instrumentation. Out of scope for Paket 8 — explicitly tagged as a follow-up item in this plan.
- **SSE events (personal, never broadcast):**
  - `speed_warning`: `{message, recent_save_count, window_seconds, threshold}`. Sent via `broker.publish_to([user_id], ...)`.
  - `char_limit_warning`: `{level: 'warn'|'alert', fields: [...], warn_threshold, alert_threshold}`. Personal.
- **Behavioral event payload:** `behavioral_events.detector` = `'speed_warning'` or `'char_limit_warning'`. `actual_value` = the count or max length. `threshold_value` = the configured threshold. `context_json` = the SSE payload (so an admin reading the table later sees what the user saw).
- **Atomicity & error isolation:** Each detector runs in `try/except Exception: log.exception(...)` so one failing detector doesn't block the other. The save itself has already committed — there's no rollback to consider.
- **Admin settings allowlist:** `PUT /api/admin/settings/{key}` only accepts keys that already exist in `site_settings`. This prevents arbitrary keys from being created via the API (those should be added via migrations). 404 on unknown key.
- **Admin settings type guard:** PUT enforces that the new value's Python type matches the existing value's type (int↔int, dict↔dict, str↔str). Float/int are NOT considered compatible — the typed accessor `get_int` would silently truncate a float and the spec values are integers throughout. 422 on mismatch.
- **Audit:** Every successful PUT writes an `admin_audit_log` row with `action_type='settings_update'`, `target_kind='setting'`, `target_id=key`, `metadata={'old_value': ..., 'new_value': ...}`. GET is not audited (read access is not sensitive enough).
- **Settings caching:** Detectors read settings on every save. SQLite + WAL + a single `SELECT value FROM site_settings WHERE key=?` is well under a millisecond — no cache layer needed for Paket 8 scale.

## Dosya Yapısı

```
backend/behavioral/                     # NEW package
├── __init__.py                         # empty
└── service.py                          # detect_speed_warning, detect_char_limit_warning, run_after_save

backend/admin/                          # NEW package
├── __init__.py                         # empty
├── models.py                           # Pydantic schemas for settings GET/PUT
└── routes.py                           # GET /api/admin/settings, PUT /api/admin/settings/{key}

backend/annotations/routes.py           # MODIFIED: save() invokes behavioral.run_after_save
backend/main.py                         # MODIFIED: mount admin_router

tests/test_behavioral_speed.py          # NEW — speed_warning unit tests
tests/test_behavioral_char_limit.py     # NEW — char_limit_warning unit tests
tests/test_behavioral_orchestrator.py   # NEW — run_after_save orchestrator tests
tests/test_behavioral_integration.py    # NEW — through POST /api/annotations
tests/test_admin_settings_routes.py     # NEW — GET/PUT settings, allowlist, type guard, audit
tests/test_sse_publish_behavioral.py    # NEW — verify SSE events delivered to the saving user only
```

---

## Task 1: `behavioral.service.detect_speed_warning` (TDD)

**Goal:** Pure function that counts the user's recent `annotation_save` events; returns a verdict dict if the user is over threshold AND has no recent `speed_warning` behavioral_event in the same window. Returns `None` otherwise.

**Files:**
- Create: `backend/behavioral/__init__.py`
- Create: `backend/behavioral/service.py`
- Create: `tests/test_behavioral_speed.py`

- [ ] **Step 1: Create empty package**

Run:
```bash
mkdir -p /Users/barandincoguz/Desktop/deneme/backend/behavioral
touch /Users/barandincoguz/Desktop/deneme/backend/behavioral/__init__.py
```

- [ ] **Step 2: Write `tests/test_behavioral_speed.py`**

```python
"""Unit tests for behavioral.service.detect_speed_warning.

Speed warning fires when a user has more saves in the configured window than
the configured threshold AND has not already been warned within that window.
"""
from datetime import datetime, timezone, timedelta

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared import audit, settings as S
from backend.behavioral import service as behavioral


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    # Insert a user
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', ?, ?)",
        (now, now),
    )
    yield conn
    conn.close()


def _insert_save(conn, user_id, ts):
    conn.execute(
        "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
        (user_id, "annotation_save", ts),
    )


def test_under_threshold_returns_none(db):
    """4 saves in 5min, threshold=5 → no warning."""
    now = datetime.now(timezone.utc)
    for i in range(4):
        _insert_save(db, 1, (now - timedelta(seconds=10 * i)).isoformat())
    assert behavioral.detect_speed_warning(db, user_id=1) is None


def test_over_threshold_returns_verdict(db):
    """6 saves in 5min, threshold=5 → warning verdict with payload."""
    now = datetime.now(timezone.utc)
    for i in range(6):
        _insert_save(db, 1, (now - timedelta(seconds=10 * i)).isoformat())
    verdict = behavioral.detect_speed_warning(db, user_id=1)
    assert verdict is not None
    assert verdict["recent_save_count"] == 6
    assert verdict["window_seconds"] == 300
    assert verdict["threshold"] == 5
    assert "message" in verdict


def test_old_saves_outside_window_are_ignored(db):
    """6 saves but spread over 1 hour → only those inside 5min window count."""
    now = datetime.now(timezone.utc)
    # 2 inside the window
    _insert_save(db, 1, (now - timedelta(seconds=30)).isoformat())
    _insert_save(db, 1, (now - timedelta(seconds=60)).isoformat())
    # 4 outside the window
    for i in range(4):
        _insert_save(db, 1, (now - timedelta(seconds=600 + i * 60)).isoformat())
    assert behavioral.detect_speed_warning(db, user_id=1) is None


def test_other_users_saves_do_not_count(db):
    """Bob's 10 saves don't affect Alice's count."""
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (2, 'bob', 'x', 'user', ?, ?)",
        (now.isoformat(), now.isoformat()),
    )
    for i in range(10):
        _insert_save(db, 2, (now - timedelta(seconds=10 * i)).isoformat())
    # alice has zero saves
    assert behavioral.detect_speed_warning(db, user_id=1) is None


def test_other_event_types_do_not_count(db):
    """document_open or annotation_skip don't count as saves."""
    now = datetime.now(timezone.utc)
    for i in range(10):
        db.execute(
            "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
            (1, "annotation_skip", (now - timedelta(seconds=10 * i)).isoformat()),
        )
    assert behavioral.detect_speed_warning(db, user_id=1) is None


def test_recent_warning_suppresses_re_fire(db):
    """If user already has a speed_warning behavioral_event in the window, suppress."""
    now = datetime.now(timezone.utc)
    for i in range(8):
        _insert_save(db, 1, (now - timedelta(seconds=10 * i)).isoformat())
    # Plant a recent warning (60s ago)
    audit.log_behavioral(
        db, user_id=1, detector="speed_warning",
        threshold_value=5, actual_value=7, context={"recent_save_count": 7},
    )
    assert behavioral.detect_speed_warning(db, user_id=1) is None


def test_old_warning_outside_window_does_not_suppress(db):
    """A warning older than window_seconds is no longer relevant — re-fire allowed."""
    now = datetime.now(timezone.utc)
    for i in range(7):
        _insert_save(db, 1, (now - timedelta(seconds=10 * i)).isoformat())
    # Plant an old warning (10 minutes ago — outside 5min window)
    old = (now - timedelta(seconds=700)).isoformat()
    db.execute(
        "INSERT INTO behavioral_events(user_id, detector, threshold_value, actual_value, context_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, "speed_warning", 5, 6, '{"recent_save_count":6}', old),
    )
    verdict = behavioral.detect_speed_warning(db, user_id=1)
    assert verdict is not None


def test_uses_settings_overrides(db):
    """Threshold and window are read from site_settings — admin can tune them."""
    S.set_value(db, "speed_warning.window_seconds", 60, updated_by_user_id=None)
    S.set_value(db, "speed_warning.max_saves_in_window", 2, updated_by_user_id=None)
    now = datetime.now(timezone.utc)
    for i in range(3):
        _insert_save(db, 1, (now - timedelta(seconds=5 * i)).isoformat())
    verdict = behavioral.detect_speed_warning(db, user_id=1)
    assert verdict is not None
    assert verdict["window_seconds"] == 60
    assert verdict["threshold"] == 2
    assert verdict["recent_save_count"] == 3
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_behavioral_speed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.behavioral.service'`.

- [ ] **Step 4: Implement `backend/behavioral/service.py` (speed only)**

```python
"""Behavioral detectors that fire after a successful annotation save.

Public API:
  detect_speed_warning(db, *, user_id) -> Optional[dict]
  detect_char_limit_warning(references) -> Optional[dict]
  run_after_save(db, *, user_id, username, references) -> None  (async, side-effecting)

Pure detectors return either None or a verdict dict. The orchestrator is the
only place that calls log_behavioral + broker.publish_to.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.shared import settings as S


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# speed_warning
# ---------------------------------------------------------------------------

def detect_speed_warning(db, *, user_id: int) -> Optional[dict]:
    """Return a verdict dict if the user has crossed the saves-per-window
    threshold AND has not been warned within the same window. None otherwise.
    """
    window_seconds = S.get_int(db, "speed_warning.window_seconds", default=300)
    threshold = S.get_int(db, "speed_warning.max_saves_in_window", default=5)

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_seconds)).isoformat()

    save_count_row = db.execute(
        """
        SELECT COUNT(*) AS c FROM activity_events
        WHERE user_id=? AND event_type='annotation_save' AND created_at >= ?
        """,
        (user_id, cutoff),
    ).fetchone()
    save_count = save_count_row["c"]
    if save_count <= threshold:
        return None

    # Dedup: skip if a speed_warning was already logged within the window
    recent_warning_row = db.execute(
        """
        SELECT 1 FROM behavioral_events
        WHERE user_id=? AND detector='speed_warning' AND created_at >= ?
        LIMIT 1
        """,
        (user_id, cutoff),
    ).fetchone()
    if recent_warning_row is not None:
        return None

    return {
        "message": (
            f"Son {window_seconds // 60} dakikada {save_count} kayıt yaptın. "
            "Yavaşlayıp her dokümana dikkatlice bakman annotation kalitesini yükseltir."
        ),
        "recent_save_count": save_count,
        "window_seconds": window_seconds,
        "threshold": threshold,
    }


# ---------------------------------------------------------------------------
# char_limit_warning  (Task 2 implements)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Orchestrator  (Task 3 implements)
# ---------------------------------------------------------------------------
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_behavioral_speed.py -v`
Expected: 8 PASS.

- [ ] **Step 6: Run full test suite (smoke)**

Run: `.venv/bin/python -m pytest -x -q`
Expected: all tests pass (288 prior + 8 new = 296).

- [ ] **Step 7: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/behavioral/__init__.py backend/behavioral/service.py tests/test_behavioral_speed.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(behavioral): add speed_warning detector with window-based dedup

Counts annotation_save activity_events in the configured window; suppresses
firing if a speed_warning was already logged within the same window so the
user gets warned once per hot-streak rather than every save.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `behavioral.service.detect_char_limit_warning` (TDD)

**Goal:** Pure function that scans the references payload of a save, returns the worst-severity verdict (`alert` > `warn` > `None`).

**Files:**
- Modify: `backend/behavioral/service.py`
- Create: `tests/test_behavioral_char_limit.py`

- [ ] **Step 1: Write `tests/test_behavioral_char_limit.py`**

```python
"""Unit tests for behavioral.service.detect_char_limit_warning.

Returns None / warn / alert based on per-reference field lengths.
"""
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared import settings as S
from backend.behavioral import service as behavioral


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def _ref(kanun_ad="Kurumlar Vergisi Kanunu", source_text="kısa atıf", **overrides):
    base = {
        "kanun_no": "5520",
        "kanun_ad": kanun_ad,
        "madde": "5",
        "fikra": "1",
        "bent": "a",
        "source_text": source_text,
    }
    base.update(overrides)
    return base


def test_all_short_returns_none(db):
    """No field exceeds either threshold → None."""
    refs = [_ref(), _ref(kanun_ad="Gelir Vergisi", source_text="atıf metni")]
    assert behavioral.detect_char_limit_warning(db, references=refs) is None


def test_warn_threshold_hit_only(db):
    """A single source_text crosses warn (300) but not alert (600)."""
    refs = [_ref(source_text="x" * 301)]
    verdict = behavioral.detect_char_limit_warning(db, references=refs)
    assert verdict is not None
    assert verdict["level"] == "warn"
    assert verdict["warn_threshold"] == 300
    assert verdict["alert_threshold"] == 600
    assert len(verdict["fields"]) == 1
    f = verdict["fields"][0]
    assert f["ref_index"] == 0
    assert f["field"] == "source_text"
    assert f["length"] == 301
    assert f["level"] == "warn"


def test_alert_threshold_dominates(db):
    """If any field crosses alert, verdict.level=alert even when others only warn."""
    refs = [
        _ref(source_text="x" * 350),    # warn
        _ref(source_text="y" * 700),    # alert
    ]
    verdict = behavioral.detect_char_limit_warning(db, references=refs)
    assert verdict["level"] == "alert"
    # Both offending fields are reported
    assert len(verdict["fields"]) == 2
    levels = sorted(f["level"] for f in verdict["fields"])
    assert levels == ["alert", "warn"]


def test_kanun_ad_field_is_checked(db):
    """kanun_ad over warn threshold also triggers."""
    refs = [_ref(kanun_ad="Y" * 305, source_text="kısa")]
    verdict = behavioral.detect_char_limit_warning(db, references=refs)
    assert verdict["level"] == "warn"
    assert verdict["fields"][0]["field"] == "kanun_ad"


def test_other_fields_not_checked(db):
    """kanun_no/madde/fikra/bent are not checked even if long (they're short by domain)."""
    refs = [_ref(kanun_no="x" * 1000, madde="y" * 1000)]
    assert behavioral.detect_char_limit_warning(db, references=refs) is None


def test_empty_references_returns_none(db):
    """0 refs → no warning (a doc may have no legal references)."""
    assert behavioral.detect_char_limit_warning(db, references=[]) is None


def test_uses_settings_overrides(db):
    """Admin tunes warn=50, alert=100 → very short text now triggers."""
    S.set_value(db, "char_limit.warn_threshold", 50, updated_by_user_id=None)
    S.set_value(db, "char_limit.alert_threshold", 100, updated_by_user_id=None)
    refs = [_ref(source_text="x" * 60)]
    verdict = behavioral.detect_char_limit_warning(db, references=refs)
    assert verdict["level"] == "warn"
    assert verdict["warn_threshold"] == 50
    assert verdict["alert_threshold"] == 100


def test_threshold_boundary_not_inclusive(db):
    """Length == threshold is NOT a hit; length > threshold is. (Spec ambiguous; pick strict >.)"""
    refs = [_ref(source_text="x" * 300)]   # exactly == warn → no hit
    assert behavioral.detect_char_limit_warning(db, references=refs) is None
    refs = [_ref(source_text="x" * 301)]
    assert behavioral.detect_char_limit_warning(db, references=refs)["level"] == "warn"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_behavioral_char_limit.py -v`
Expected: FAIL — `AttributeError: module 'backend.behavioral.service' has no attribute 'detect_char_limit_warning'`.

- [ ] **Step 3: Add `detect_char_limit_warning` to `backend/behavioral/service.py`**

Replace the `# char_limit_warning  (Task 2 implements)` placeholder block with:

```python
# ---------------------------------------------------------------------------
# char_limit_warning
# ---------------------------------------------------------------------------

_CHECKED_FIELDS = ("kanun_ad", "source_text")


def detect_char_limit_warning(db, *, references: list[dict]) -> Optional[dict]:
    """Return a verdict if any reference's `kanun_ad` or `source_text` exceeds
    the warn or alert threshold. Returns the worst severity across all hits.
    None if every field is below warn.
    """
    if not references:
        return None

    warn = S.get_int(db, "char_limit.warn_threshold", default=300)
    alert = S.get_int(db, "char_limit.alert_threshold", default=600)

    hits: list[dict] = []
    for idx, ref in enumerate(references):
        for field in _CHECKED_FIELDS:
            value = ref.get(field) or ""
            length = len(value)
            if length > alert:
                hits.append({"ref_index": idx, "field": field, "length": length, "level": "alert"})
            elif length > warn:
                hits.append({"ref_index": idx, "field": field, "length": length, "level": "warn"})

    if not hits:
        return None

    worst = "alert" if any(h["level"] == "alert" for h in hits) else "warn"
    return {
        "level": worst,
        "fields": hits,
        "warn_threshold": warn,
        "alert_threshold": alert,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_behavioral_char_limit.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/behavioral/service.py tests/test_behavioral_char_limit.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(behavioral): add char_limit_warning detector with warn/alert levels

Scans kanun_ad and source_text on every reference; aggregates per save with
worst severity wins. Returns offender list so the frontend can highlight
specific cells. Boundary is strict-greater-than (length > threshold).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `behavioral.service.run_after_save` orchestrator (TDD)

**Goal:** Async function that runs both detectors, logs each hit to `behavioral_events`, and publishes the corresponding personal SSE event. Detector failures are isolated.

**Files:**
- Modify: `backend/behavioral/service.py`
- Create: `tests/test_behavioral_orchestrator.py`

- [ ] **Step 1: Write `tests/test_behavioral_orchestrator.py`**

```python
"""Unit tests for behavioral.service.run_after_save orchestrator.

Verifies that both detectors are evaluated, hits are logged to
behavioral_events with full context, and personal SSE events are published.
A failure in one detector must not block the other.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from backend.shared.db import connect
from backend.shared.sse import broker as sse_broker
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.behavioral import service as behavioral


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
    yield conn
    conn.close()


def _ref(**overrides):
    base = {
        "kanun_no": "5520", "kanun_ad": "KVK", "madde": "5",
        "fikra": "1", "bent": "a", "source_text": "kısa",
    }
    base.update(overrides)
    return base


def test_no_hits_no_events_no_logs(db):
    """Quiet save with short refs → no SSE events, no behavioral rows."""
    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice", references=[_ref()],
    ))
    rows = db.execute("SELECT * FROM behavioral_events").fetchall()
    assert rows == []
    # No events delivered
    async def _wait():
        return await asyncio.wait_for(queue.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_wait())


def test_speed_warning_logs_and_publishes(db):
    """6 saves in 5min → speed_warning logged + SSE personal event."""
    now = datetime.now(timezone.utc)
    for i in range(6):
        db.execute(
            "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
            (1, "annotation_save", (now - timedelta(seconds=10 * i)).isoformat()),
        )

    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice", references=[_ref()],
    ))

    rows = db.execute(
        "SELECT detector, threshold_value, actual_value, context_json FROM behavioral_events"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["detector"] == "speed_warning"
    assert rows[0]["threshold_value"] == 5
    assert rows[0]["actual_value"] == 6
    ctx = json.loads(rows[0]["context_json"])
    assert ctx["recent_save_count"] == 6

    async def _wait():
        return await asyncio.wait_for(queue.get(), timeout=2.0)
    event = asyncio.run(_wait())
    assert event.event_type == "speed_warning"
    assert event.data["recent_save_count"] == 6
    assert event.data["window_seconds"] == 300
    assert "message" in event.data


def test_char_limit_warning_logs_and_publishes(db):
    """Long source_text → char_limit_warning logged + SSE personal event."""
    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice",
        references=[_ref(source_text="x" * 700)],
    ))

    rows = db.execute(
        "SELECT detector, actual_value FROM behavioral_events WHERE detector='char_limit_warning'"
    ).fetchall()
    assert len(rows) == 1
    # actual_value carries the worst length seen
    assert rows[0]["actual_value"] == 700

    async def _wait():
        return await asyncio.wait_for(queue.get(), timeout=2.0)
    event = asyncio.run(_wait())
    assert event.event_type == "char_limit_warning"
    assert event.data["level"] == "alert"
    assert event.data["warn_threshold"] == 300
    assert event.data["alert_threshold"] == 600


def test_both_detectors_fire_independently(db):
    """If both fire, both rows logged + both SSE events delivered."""
    now = datetime.now(timezone.utc)
    for i in range(7):
        db.execute(
            "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
            (1, "annotation_save", (now - timedelta(seconds=10 * i)).isoformat()),
        )

    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice",
        references=[_ref(source_text="y" * 400)],
    ))

    detectors = sorted(
        r["detector"] for r in db.execute(
            "SELECT detector FROM behavioral_events ORDER BY id"
        ).fetchall()
    )
    assert detectors == ["char_limit_warning", "speed_warning"]

    received = []
    async def _drain():
        for _ in range(2):
            received.append(await asyncio.wait_for(queue.get(), timeout=2.0))
    asyncio.run(_drain())
    types = sorted(e.event_type for e in received)
    assert types == ["char_limit_warning", "speed_warning"]


def test_only_publishes_to_saving_user_not_broadcast(db, monkeypatch):
    """Personal events: bob (online) must NOT see alice's speed_warning."""
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO users(id, username, password_hash, role, created_at, updated_at) "
        "VALUES (2, 'bob', 'x', 'user', ?, ?)",
        (now.isoformat(), now.isoformat()),
    )
    for i in range(7):
        db.execute(
            "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
            (1, "annotation_save", (now - timedelta(seconds=10 * i)).isoformat()),
        )

    alice_q = sse_broker.subscribe(user_id=1)
    bob_q = sse_broker.subscribe(user_id=2)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice", references=[_ref()],
    ))

    # alice receives
    async def _alice():
        return await asyncio.wait_for(alice_q.get(), timeout=2.0)
    ev = asyncio.run(_alice())
    assert ev.event_type == "speed_warning"

    # bob does not
    async def _bob():
        return await asyncio.wait_for(bob_q.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_bob())


def test_speed_detector_failure_does_not_block_char_limit(db, monkeypatch):
    """If speed detector raises, char_limit still fires."""
    def boom(*a, **kw):
        raise RuntimeError("speed detector exploded")
    monkeypatch.setattr(behavioral, "detect_speed_warning", boom)

    queue = sse_broker.subscribe(user_id=1)
    asyncio.run(behavioral.run_after_save(
        db, user_id=1, username="alice",
        references=[_ref(source_text="z" * 400)],
    ))

    detectors = [r["detector"] for r in db.execute(
        "SELECT detector FROM behavioral_events"
    ).fetchall()]
    assert detectors == ["char_limit_warning"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_behavioral_orchestrator.py -v`
Expected: FAIL — `AttributeError: module 'backend.behavioral.service' has no attribute 'run_after_save'`.

- [ ] **Step 3: Implement `run_after_save` in `backend/behavioral/service.py`**

Replace the `# Orchestrator  (Task 3 implements)` placeholder block with:

```python
# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

from backend.shared import audit
from backend.shared.sse import broker as _broker


async def run_after_save(
    db,
    *,
    user_id: int,
    username: str,
    references: list[dict],
) -> None:
    """Run all behavioral detectors after a successful save and publish
    personal SSE events for any verdicts. Each detector is isolated — a
    failure in one does not block the others, and no failure rolls back
    the already-committed save (callers should call this AFTER commit).
    """
    # ---- speed_warning --------------------------------------------------
    try:
        verdict = detect_speed_warning(db, user_id=user_id)
        if verdict is not None:
            audit.log_behavioral(
                db, user_id=user_id, detector="speed_warning",
                threshold_value=float(verdict["threshold"]),
                actual_value=float(verdict["recent_save_count"]),
                context=verdict,
            )
            await _broker.publish_to([user_id], "speed_warning", verdict)
    except Exception:
        log.exception("speed_warning detector failed for user %s", user_id)

    # ---- char_limit_warning --------------------------------------------
    try:
        verdict = detect_char_limit_warning(db, references=references)
        if verdict is not None:
            worst_length = max((f["length"] for f in verdict["fields"]), default=0)
            threshold_for_log = (
                verdict["alert_threshold"]
                if verdict["level"] == "alert"
                else verdict["warn_threshold"]
            )
            audit.log_behavioral(
                db, user_id=user_id, detector="char_limit_warning",
                threshold_value=float(threshold_for_log),
                actual_value=float(worst_length),
                context=verdict,
            )
            await _broker.publish_to([user_id], "char_limit_warning", verdict)
    except Exception:
        log.exception("char_limit_warning detector failed for user %s", user_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_behavioral_orchestrator.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/behavioral/service.py tests/test_behavioral_orchestrator.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(behavioral): add run_after_save orchestrator with detector isolation

Runs both detectors, logs verdicts to behavioral_events, publishes personal
SSE events. Each detector wrapped in try/except so a failure in one cannot
suppress the other. Caller must invoke AFTER the save commits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Wire orchestrator into `annotations/routes.py:save` (TDD via integration test)

**Goal:** Hook `behavioral.run_after_save` into the annotation save HTTP path so end-to-end behavior matches the unit tests.

**Files:**
- Modify: `backend/annotations/routes.py`
- Create: `tests/test_behavioral_integration.py`

- [ ] **Step 1: Write `tests/test_behavioral_integration.py`**

```python
"""Integration tests: behavioral detectors fire through POST /api/annotations.

Drives the full HTTP path so a regression in routes.py wiring is caught.
"""
import asyncio
from datetime import datetime, timedelta, timezone

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
        "fikra": "1", "bent": "a", "source_text": "kısa atıf",
    }
    base.update(overrides)
    return base


def test_save_triggers_speed_warning_after_threshold(passed_user, ingest_doc):
    """5 prior saves planted, 6th save through HTTP triggers speed_warning."""
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_speed_x")

    # Plant 5 prior annotation_save activity_events (just under threshold)
    conn = connect(config.DB_PATH)
    try:
        now = datetime.now(timezone.utc)
        for i in range(5):
            conn.execute(
                "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
                (user_id, "annotation_save", (now - timedelta(seconds=10 * (i + 1))).isoformat()),
            )
    finally:
        conn.close()

    queue = sse_broker.subscribe(user_id=user_id)

    r = c.post("/api/annotations", json={
        "document_id": "doc_speed_x", "references": [_ref()],
    })
    assert r.status_code == 200

    # We should see TWO events on the queue: annotation_saved (broadcast) + speed_warning (personal).
    received_types = []
    async def _drain():
        for _ in range(2):
            received_types.append(
                (await asyncio.wait_for(queue.get(), timeout=2.0)).event_type
            )
    asyncio.run(_drain())
    assert "speed_warning" in received_types

    # And the behavioral row exists
    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT detector, actual_value FROM behavioral_events WHERE user_id=?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    assert any(r["detector"] == "speed_warning" for r in rows)


def test_save_with_long_source_text_triggers_char_limit(passed_user, ingest_doc):
    """Single save with source_text > alert threshold triggers char_limit_warning."""
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_chars_x")

    queue = sse_broker.subscribe(user_id=user_id)

    r = c.post("/api/annotations", json={
        "document_id": "doc_chars_x",
        "references": [_ref(source_text="x" * 700)],
    })
    assert r.status_code == 200

    received_types = []
    async def _drain():
        for _ in range(2):
            received_types.append(
                (await asyncio.wait_for(queue.get(), timeout=2.0)).event_type
            )
    asyncio.run(_drain())
    assert "char_limit_warning" in received_types

    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute(
            "SELECT detector FROM behavioral_events WHERE user_id=?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    assert any(r["detector"] == "char_limit_warning" for r in rows)


def test_save_with_short_payload_no_behavioral_events(passed_user, ingest_doc):
    """Quiet save → no behavioral rows, no personal SSE events (annotation_saved still
    broadcasts but that's separate)."""
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_quiet_x")

    r = c.post("/api/annotations", json={
        "document_id": "doc_quiet_x", "references": [_ref()],
    })
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        rows = conn.execute("SELECT * FROM behavioral_events WHERE user_id=?", (user_id,)).fetchall()
    finally:
        conn.close()
    assert rows == []


def test_detector_failure_does_not_500_the_save(passed_user, ingest_doc, monkeypatch):
    """If run_after_save explodes, the save still returns 200 — detectors are best-effort."""
    user_id = passed_user["user"]["id"]
    c = passed_user["client"]
    ingest_doc("doc_isolate_x")

    async def boom(*args, **kwargs):
        raise RuntimeError("orchestrator exploded")
    monkeypatch.setattr(
        "backend.annotations.routes.behavioral_service.run_after_save", boom
    )

    r = c.post("/api/annotations", json={
        "document_id": "doc_isolate_x", "references": [_ref()],
    })
    assert r.status_code == 200

    # And the actual annotation row is persisted
    conn = connect(config.DB_PATH)
    try:
        row = conn.execute(
            "SELECT 1 FROM annotations WHERE document_id=?", ("doc_isolate_x",)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_behavioral_integration.py -v`
Expected: FAIL — `speed_warning` event not delivered (no wiring yet) or `behavioral_service` import fails inside monkeypatch.

- [ ] **Step 3: Wire `behavioral.run_after_save` into `backend/annotations/routes.py:save`**

Modify the imports section to add (note the alias keeps the monkeypatch path stable):

```python
from backend.behavioral import service as behavioral_service
```

Then replace the publish-block-end-of-`save` (currently ends at line ~67 after the `try/except` around `publish_broadcast`). The new tail of `save` should be:

```python
    try:
        action = "create" if result["is_new"] else "edit"
        await sse_broker.publish_broadcast(
            "annotation_saved",
            {
                "document_id": payload.document_id,
                "user_id": user["id"],
                "username": user["username"],
                "action": action,
                "is_diff_zero": result["is_diff_zero"],
                "ref_count": len(result["current_references"]),
            },
        )
    except Exception:
        log.exception("publish annotation_saved failed for %s", payload.document_id)

    try:
        await behavioral_service.run_after_save(
            db,
            user_id=user["id"],
            username=user["username"],
            references=result["current_references"],
        )
    except Exception:
        log.exception("run_after_save failed for %s", payload.document_id)
    return result
```

Update the docstring at the top of `save` to reflect the new responsibility:

```python
    """Save reference list (atomic version + denorm rebuild). Broadcasts
    annotation_saved on success, then runs behavioral detectors which may
    publish personal speed_warning / char_limit_warning events back to the
    saving user. 422 on duplicate/invalid refs; 404 on unknown document.
    Publish errors and detector errors are logged and swallowed."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_behavioral_integration.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/annotations/routes.py tests/test_behavioral_integration.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(annotations): invoke behavioral detectors after annotation_saved publish

run_after_save runs after the broadcast; both calls share the same fault-
isolation pattern: failures are logged and swallowed so a detector bug or
broker bug cannot 500 a successful save.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Admin settings — `GET /api/admin/settings` (TDD)

**Goal:** Return the full key→value map of `site_settings`. Admin-only.

**Files:**
- Create: `backend/admin/__init__.py`
- Create: `backend/admin/models.py`
- Create: `backend/admin/routes.py`
- Modify: `backend/main.py`
- Create: `tests/test_admin_settings_routes.py`

- [ ] **Step 1: Create empty package**

Run:
```bash
mkdir -p /Users/barandincoguz/Desktop/deneme/backend/admin
touch /Users/barandincoguz/Desktop/deneme/backend/admin/__init__.py
```

- [ ] **Step 2: Write `tests/test_admin_settings_routes.py` (GET portion only — PUT comes in Task 6)**

```python
"""HTTP tests for admin settings endpoints."""
from backend.shared.db import connect
from backend import config


def _make_admin(client):
    """Register a user, promote to admin, log them in, return the user dict."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("ADMIN-INV",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": "boss", "password": "password123",
        "invite_code": "ADMIN-INV", "email": "boss@example.com",
    })
    assert r.status_code == 201
    user = r.json()
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET role='admin', has_seen_manual=1, has_passed_training=1 WHERE id=?",
            (user["id"],),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/login", json={
        "username": "boss", "password": "password123",
    })
    assert r.status_code == 200
    return user


def test_get_settings_requires_auth(client):
    r = client.get("/api/admin/settings")
    assert r.status_code == 401


def test_get_settings_non_admin_404(passed_user):
    r = passed_user["client"].get("/api/admin/settings")
    # require_admin returns 404 to hide existence (per backend/users/deps.py:52)
    assert r.status_code == 404


def test_get_settings_returns_seeded_keys(client):
    _make_admin(client)
    r = client.get("/api/admin/settings")
    assert r.status_code == 200
    data = r.json()
    # Some seeded keys present
    assert "speed_warning.window_seconds" in data
    assert data["speed_warning.window_seconds"] == 300
    assert data["char_limit.warn_threshold"] == 300
    assert data["char_limit.alert_threshold"] == 600
```

- [ ] **Step 3: Write `backend/admin/models.py`**

```python
"""Pydantic schemas for admin endpoints."""
from typing import Any

from pydantic import BaseModel


class SettingUpdateRequest(BaseModel):
    value: Any


class SettingUpdateResponse(BaseModel):
    key: str
    value: Any


class OkResponse(BaseModel):
    ok: bool = True
```

- [ ] **Step 4: Write `backend/admin/routes.py` (GET only — PUT in Task 6)**

```python
"""Admin-only HTTP endpoints. Currently: site_settings read/write."""
import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.admin.models import SettingUpdateRequest, SettingUpdateResponse, OkResponse
from backend.shared import audit, settings as S
from backend.users.deps import get_db, require_admin


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/settings")
def list_settings(
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    """Return the full key→value map of site_settings."""
    return S.get_all(db)
```

- [ ] **Step 5: Mount the admin router in `backend/main.py`**

Add the import (alphabetical with the other domain imports):

```python
from backend.admin.routes import router as admin_router
```

And below the other `app.include_router(...)` lines:

```python
app.include_router(admin_router)
```

- [ ] **Step 6: Run tests to verify GET-portion passes**

Run: `.venv/bin/python -m pytest tests/test_admin_settings_routes.py -v -k "get_settings"`
Expected: 3 PASS.

- [ ] **Step 7: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/admin/__init__.py backend/admin/models.py backend/admin/routes.py backend/main.py tests/test_admin_settings_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(admin): add GET /api/admin/settings (admin-only key→value map)

require_admin gates the route; non-admin gets 404 (existence-hiding semantic
inherited from users.deps). Returns the full seeded key→value dict so the
admin UI can render every tunable in one fetch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Admin settings — `PUT /api/admin/settings/{key}` (TDD)

**Goal:** Update a single key with allowlist (must already exist) + type guard (new value's Python type must match existing). Audit-logged.

**Files:**
- Modify: `backend/admin/routes.py`
- Modify: `tests/test_admin_settings_routes.py`

- [ ] **Step 1: Append PUT tests to `tests/test_admin_settings_routes.py`**

```python
import json


def test_put_settings_requires_auth(client):
    r = client.put("/api/admin/settings/speed_warning.window_seconds", json={"value": 600})
    assert r.status_code == 401


def test_put_settings_non_admin_404(passed_user):
    r = passed_user["client"].put(
        "/api/admin/settings/speed_warning.window_seconds", json={"value": 600},
    )
    assert r.status_code == 404


def test_put_unknown_key_404(client):
    _make_admin(client)
    r = client.put("/api/admin/settings/no.such.key", json={"value": 1})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_setting_key"


def test_put_persists_int_value(client):
    _make_admin(client)
    r = client.put(
        "/api/admin/settings/speed_warning.window_seconds", json={"value": 600},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["key"] == "speed_warning.window_seconds"
    assert data["value"] == 600

    # Round-trip: GET sees the new value
    r = client.get("/api/admin/settings")
    assert r.json()["speed_warning.window_seconds"] == 600


def test_put_type_mismatch_int_to_string_422(client):
    _make_admin(client)
    r = client.put(
        "/api/admin/settings/speed_warning.window_seconds", json={"value": "abc"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "type_mismatch"


def test_put_type_mismatch_int_to_dict_422(client):
    _make_admin(client)
    r = client.put(
        "/api/admin/settings/char_limit.warn_threshold",
        json={"value": {"foo": "bar"}},
    )
    assert r.status_code == 422


def test_put_audit_log_written(client):
    admin = _make_admin(client)
    r = client.put(
        "/api/admin/settings/speed_warning.window_seconds", json={"value": 1200},
    )
    assert r.status_code == 200

    conn = connect(config.DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT admin_user_id, action_type, target_kind, target_id, metadata_json
            FROM admin_audit_log
            WHERE action_type='settings_update'
            ORDER BY id DESC LIMIT 1
            """,
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["admin_user_id"] == admin["id"]
    assert row["target_kind"] == "setting"
    assert row["target_id"] == "speed_warning.window_seconds"
    metadata = json.loads(row["metadata_json"])
    assert metadata["old_value"] == 300
    assert metadata["new_value"] == 1200


def test_put_same_value_still_audited(client):
    """Idempotent PUT (no-op write) is still recorded in admin_audit_log so the
    audit trail captures every admin attempt, not just behaviorally distinct ones."""
    _make_admin(client)
    r = client.put(
        "/api/admin/settings/speed_warning.window_seconds", json={"value": 300},
    )
    assert r.status_code == 200
    conn = connect(config.DB_PATH)
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM admin_audit_log WHERE action_type='settings_update'"
        ).fetchone()["c"]
    finally:
        conn.close()
    assert count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_admin_settings_routes.py -v -k "put"`
Expected: FAIL — `405 Method Not Allowed` because PUT route doesn't exist yet.

- [ ] **Step 3: Append the PUT route to `backend/admin/routes.py`**

```python
def _python_type_label(value) -> str:
    """Human-readable type label for type-mismatch errors."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def _types_compatible(old, new) -> bool:
    """int↔int, str↔str, dict↔dict, list↔list, bool↔bool, float↔float.
    int and float are NOT considered compatible (the typed accessors are strict
    and the seeded values are integers throughout — silent truncation would be
    a footgun)."""
    return _python_type_label(old) == _python_type_label(new)


@router.put("/settings/{key}", response_model=SettingUpdateResponse)
def update_setting(
    key: str,
    payload: SettingUpdateRequest,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Update an existing site_settings entry. Allowlist: 404 if the key isn't
    already in the table (use migrations to add new keys). Type guard: 422 if
    the new value's Python type does not match the existing value's type.
    Successful writes are audited."""
    all_settings = S.get_all(db)
    if key not in all_settings:
        raise HTTPException(
            status_code=404,
            detail={"error": "unknown_setting_key", "key": key},
        )
    old_value = all_settings[key]
    new_value = payload.value
    if not _types_compatible(old_value, new_value):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "type_mismatch",
                "expected": _python_type_label(old_value),
                "got": _python_type_label(new_value),
            },
        )

    S.set_value(db, key, new_value, updated_by_user_id=admin["id"])
    audit.log_admin_action(
        db, admin_user_id=admin["id"], action_type="settings_update",
        target_kind="setting", target_id=key,
        metadata={"old_value": old_value, "new_value": new_value},
    )
    return {"key": key, "value": new_value}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_admin_settings_routes.py -v`
Expected: all (3 GET + 7 PUT) PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/admin/routes.py tests/test_admin_settings_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(admin): add PUT /api/admin/settings/{key} with allowlist + type guard

Allowlist prevents arbitrary key creation through the API (use migrations
for new keys). Strict-type guard rejects int→str etc. with 422 since the
typed settings accessors would otherwise silently corrupt downstream
detectors. Every write is recorded in admin_audit_log with old/new values.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: SSE-publish smoke for behavioral events (TDD)

**Goal:** Defense-in-depth: a dedicated test file pinning the personal-only invariant for the two behavioral SSE event types — same style as `test_sse_publish_locks.py` and `test_sse_publish_annotations.py`.

**Files:**
- Create: `tests/test_sse_publish_behavioral.py`

- [ ] **Step 1: Write `tests/test_sse_publish_behavioral.py`**

```python
"""Verify behavioral detectors publish personal SSE events to the saving
user only — never as broadcast. Covers the same ground as the integration
tests but pins the personal-vs-broadcast invariant explicitly so a future
refactor that switches to publish_broadcast would be caught here."""
import asyncio
from datetime import datetime, timedelta, timezone

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


def test_speed_warning_only_to_saving_user(second_passed_user, ingest_doc):
    """Bob is online; alice trips the speed_warning. Bob must NOT see it."""
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_publ_speed")
    alice_id = ctx["alice"]["id"]
    bob_id = ctx["bob"]["id"]

    # Plant 5 prior saves for alice
    conn = connect(config.DB_PATH)
    try:
        now = datetime.now(timezone.utc)
        for i in range(5):
            conn.execute(
                "INSERT INTO activity_events(user_id, event_type, created_at) VALUES (?, ?, ?)",
                (alice_id, "annotation_save", (now - timedelta(seconds=10 * (i + 1))).isoformat()),
            )
    finally:
        conn.close()

    bob_q = sse_broker.subscribe(user_id=bob_id)
    alice_q = sse_broker.subscribe(user_id=alice_id)

    ctx["login"]("alice")
    r = c.post("/api/annotations", json={
        "document_id": "doc_publ_speed", "references": [_ref()],
    })
    assert r.status_code == 200

    # alice receives speed_warning (plus annotation_saved broadcast). bob only sees broadcast.
    async def _drain(q, n, timeout=2.0):
        out = []
        for _ in range(n):
            out.append(await asyncio.wait_for(q.get(), timeout=timeout))
        return out

    # alice's queue: 2 events expected (annotation_saved + speed_warning)
    alice_events = asyncio.run(_drain(alice_q, 2))
    types = sorted(e.event_type for e in alice_events)
    assert types == ["annotation_saved", "speed_warning"]

    # bob's queue: 1 event expected (annotation_saved only)
    bob_events = asyncio.run(_drain(bob_q, 1))
    assert bob_events[0].event_type == "annotation_saved"

    # bob's queue must be empty now (no extra speed_warning leaked)
    async def _empty():
        return await asyncio.wait_for(bob_q.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_empty())


def test_char_limit_warning_only_to_saving_user(second_passed_user, ingest_doc):
    """Long source_text → char_limit_warning to alice only."""
    ctx = second_passed_user
    c = ctx["client"]
    ingest_doc("doc_publ_chars")
    alice_id = ctx["alice"]["id"]
    bob_id = ctx["bob"]["id"]

    bob_q = sse_broker.subscribe(user_id=bob_id)
    alice_q = sse_broker.subscribe(user_id=alice_id)

    ctx["login"]("alice")
    r = c.post("/api/annotations", json={
        "document_id": "doc_publ_chars",
        "references": [_ref(source_text="x" * 700)],
    })
    assert r.status_code == 200

    async def _drain(q, n, timeout=2.0):
        out = []
        for _ in range(n):
            out.append(await asyncio.wait_for(q.get(), timeout=timeout))
        return out

    alice_events = asyncio.run(_drain(alice_q, 2))
    types = sorted(e.event_type for e in alice_events)
    assert types == ["annotation_saved", "char_limit_warning"]

    bob_events = asyncio.run(_drain(bob_q, 1))
    assert bob_events[0].event_type == "annotation_saved"

    async def _empty():
        return await asyncio.wait_for(bob_q.get(), timeout=0.3)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(_empty())
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sse_publish_behavioral.py -v`
Expected: 2 PASS.

- [ ] **Step 3: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add tests/test_sse_publish_behavioral.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
test(sse): pin personal-only invariant for behavioral SSE events

Two-user test confirms speed_warning and char_limit_warning are delivered to
the saving user only — bob (online) sees the annotation_saved broadcast but
not the personal warning. A future refactor that switched to
publish_broadcast would be caught here.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Polish + tag

**Goal:** Final cleanup pass and release tag.

- [ ] **Step 1: Inspect final state and tidy any rough edges**

Run:
```bash
.venv/bin/python -m pytest -q
git diff main --stat   # sanity-check the surface area touched
```

Look for:
- Unused imports anywhere in `backend/behavioral/`, `backend/admin/`, the new tests.
- Missing or misleading docstrings on the public detectors / orchestrator / admin route handlers.
- Lingering `# TODO` markers (there should be none).

If anything needs touching, fix in place.

- [ ] **Step 2: Verify OpenAPI surface includes the new admin endpoints**

Run:
```bash
.venv/bin/python -c "
from backend.main import app
paths = sorted(p for p in app.openapi()['paths'])
for p in paths:
    if 'admin' in p:
        print(p)
"
```
Expected output includes:
```
/api/admin/audit-log
/api/admin/invite/rotate
/api/admin/settings
/api/admin/settings/{key}
/api/admin/users
...
```

- [ ] **Step 3: Run the full suite one final time**

Run: `.venv/bin/python -m pytest -q`
Expected: all green (288 prior + ~30 new).

- [ ] **Step 4: Commit any polish + tag**

If polish changes were made:
```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add -A
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
chore(paket8): polish — docstrings, drop unused imports

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Then:
```bash
git tag paket-8-behavioral-detectors
git log --oneline -5
git tag --list 'paket-*'
```

Expected: tag list includes `paket-8-behavioral-detectors` and the previous seven tags.

---

## Out of Scope / Follow-ups

- **`speed_warning.min_seconds_per_doc` / `min_words_for_min_seconds`:** The seeded settings exist (30s, 100 words) but Paket 4 does not log a `document_open` activity event we can compare against. Adding this rule requires upstream instrumentation and is left for a later pass — likely bundled with Paket 11 admin work or after Paket 16 frontend opens documents and emits the `document_open` ping.
- **Frontend toasts:** Personal SSE events `speed_warning` and `char_limit_warning` are now flowing on the wire. Surfacing them as orange/red toasts is Paket 16 (`SpeedWarningToast.tsx`).
- **Settings GET 304/cache:** Currently un-cached; admin reload is fine for the 30-user scale. If the admin panel begins polling, add an `If-Modified-Since` strategy keyed on the max `updated_at` in `site_settings`.
- **PUT validation per-key:** A future task could add per-key min/max bounds (e.g., `speed_warning.window_seconds` must be ≥ 60). For now the type guard is the only check.
