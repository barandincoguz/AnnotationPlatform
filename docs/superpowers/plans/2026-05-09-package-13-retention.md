# Paket 13 — Retention Purge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily background job that hard-purges old rows from six high-churn tables (`behavioral_events`, `activity_events`, `system_events`, `user_sessions`, `notifications`, `drafts`), with configurable per-table retention windows, plus admin endpoints for dry-run preview and manual run-now trigger.

**Architecture:** New `backend/retention/` package with: a pure-function service layer (`service.py` — policy + compute_cutoffs + run_purge + preview_purge), an async loop (`loop.py`) mirroring `backend/backup/loop.py`, an admin HTTP layer (`routes.py` + `models.py`). Single migration `v0003` inserts default config rows into `site_settings` via INSERT OR IGNORE. Single transaction with all-or-nothing semantics; per-cycle observability via `system_events`; manual triggers logged to `admin_audit_log`. Lifespan task added alongside existing `locks_sweep` and `backup_loop`.

**Tech Stack:** Existing FastAPI + SQLite + Pydantic. Reuses `backend.shared.audit.log_system_event`, `backend.shared.audit.log_admin_action`, `backend.shared.settings.get_int`, `backend.users.deps.require_admin`. No new third-party deps.

---

## Mimari Kararlar (Locked from spec 2026-05-09-paket-13-retention-design.md, commit `1ca7059`)

- **Module layout:**
  - `backend/retention/__init__.py` — empty
  - `backend/retention/service.py` — `PURGE_POLICY` list, `compute_cutoffs`, `purge_single_table`, `run_purge`, `preview_purge`
  - `backend/retention/loop.py` — `retention_once`, `retention_loop`, `_read_interval`, `start`, `stop` (mirrors `backend/backup/loop.py`)
  - `backend/retention/models.py` — Pydantic schemas for the two endpoints
  - `backend/retention/routes.py` — `POST /api/admin/retention/run-now`, `GET /api/admin/retention/preview`
  - `backend/main.py` — extend lifespan + include router (NO refactor of existing tasks)
  - `backend/migrations/v0003_retention_settings.py` — INSERT OR IGNORE site_settings rows
- **PURGE_POLICY (code-baseline, immutable list):**
  - `behavioral_events.created_at < cutoff` — default 30 days
  - `activity_events.created_at < cutoff` — default 90 days
  - `system_events.created_at < cutoff` — default 180 days
  - `user_sessions.ended_at < cutoff WHERE ended_at IS NOT NULL` — default 30 days
  - `notifications.created_at < cutoff WHERE is_read=1` — default 30 days
  - `drafts.updated_at < cutoff` — default 14 days
- **Resolver pattern (Paket 10 reuse):** `code default → DB override`. For each policy entry the code default applies unless `site_settings` has key `retention.<table>.days` with an int value ≥ 0. Value 0 = kill switch (skip table). Negative values raise `ValueError` at read time.
- **Cycle interval:** `retention.cycle_interval_seconds`, default 86400 (24 hours), live-tunable from `site_settings`. Re-read each iteration.
- **Trigger surface:** scheduled (lifespan asyncio task) AND manual `POST /api/admin/retention/run-now`. Both call same `run_purge` orchestrator.
- **Preview endpoint:** `GET /api/admin/retention/preview` runs `SELECT COUNT(*)` per entry inside `BEGIN DEFERRED` (read-only). No DELETE, no commit.
- **Atomicity:** `run_purge` runs all DELETEs inside ONE `BEGIN IMMEDIATE` → `COMMIT`. Single fail rolls back all changes. Per-table fault isolation rejected (would leave DB incoherent).
- **Auth:** Both new HTTP routes use `Depends(require_admin)` → 404 existence-hide if not admin.
- **Audit + system events:**
  - Manual trigger writes `admin_audit_log` row: `action_type='retention_run_now', target_kind='retention', target_id=None, metadata={'total': N, 'by_table': {...}}`.
  - Every cycle (manual or scheduled) writes `system_events` row: `event_type='retention_success'` (or `'retention_failed'`) with severity `'info'` / `'error'`, `extra_json={'purged': {...}}` or `{'step': 'purge', 'error': '...'}`.
- **Loop pattern (mirrors `backend/backup/loop.py`):** sleep-first ordering — sleep then run, so the first cycle is one interval after server start. Cancellation (`asyncio.CancelledError`) returns cleanly. All other exceptions are caught with `log.exception` so the loop never dies.
- **No SSE:** purge is silent. Admins consult `system_events` viewer (Paket 11) to see history.
- **No new tables, no archive tables, no VACUUM, no per-table fault isolation.**

---

## Files Created/Modified

| File | Action | Purpose |
|------|--------|---------|
| `backend/migrations/v0003_retention_settings.py` | Create | Insert 7 default site_settings rows |
| `backend/retention/__init__.py` | Create | Empty package marker |
| `backend/retention/service.py` | Create | PURGE_POLICY + compute_cutoffs + purge_single_table + run_purge + preview_purge |
| `backend/retention/loop.py` | Create | Async lifespan task |
| `backend/retention/models.py` | Create | Pydantic request/response schemas |
| `backend/retention/routes.py` | Create | Two admin endpoints |
| `backend/main.py` | Modify (3 small edits) | Import retention modules + lifespan start/stop + include_router |
| `tests/test_v0003_retention_migration.py` | Create | 2 tests |
| `tests/test_retention_service.py` | Create | 11 tests (4 cutoffs + 4 single-table + 3 run_purge) |
| `tests/test_retention_preview.py` | Create | 3 tests |
| `tests/test_retention_loop.py` | Create | 3 tests |
| `tests/test_retention_admin_routes.py` | Create | 6 tests |
| `tests/test_retention_lifespan.py` | Create | 1 test |

**Test budget:** 26 new tests. Suite size 574 → 600.

---

## Task 1: v0003 migration

**Files:**
- Create: `backend/migrations/v0003_retention_settings.py`
- Test: `tests/test_v0003_retention_migration.py`

The migration runner discovers any `v*.py` module in `backend/migrations/` automatically (`backend/migrations/__init__.py:discover_migrations`), so we only need to drop a new module — no list to update.

- [ ] **Step 1: Write the failing test**

Create `tests/test_v0003_retention_migration.py`:

```python
"""Tests for v0003 — retention default settings migration."""
import sqlite3
from pathlib import Path

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


EXPECTED_KEYS = {
    "retention.cycle_interval_seconds": "86400",
    "retention.behavioral_events.days": "30",
    "retention.activity_events.days":   "90",
    "retention.system_events.days":     "180",
    "retention.user_sessions.days":     "30",
    "retention.notifications.days":     "30",
    "retention.drafts.days":            "14",
}


def test_v0003_inserts_default_retention_keys(fresh_db):
    rows = fresh_db.execute(
        "SELECT key, value FROM site_settings WHERE key LIKE 'retention.%'"
    ).fetchall()
    actual = {r["key"]: r["value"] for r in rows}
    assert actual == EXPECTED_KEYS


def test_v0003_is_idempotent_via_insert_or_ignore(fresh_db):
    """Operator-tuned override survives re-running v0003. Simulates the
    re-apply path that happens after a restore (operator may have set
    retention.system_events.days=60 before backup; restore must not clobber)."""
    fresh_db.execute(
        "UPDATE site_settings SET value=? WHERE key=?",
        ("60", "retention.system_events.days"),
    )
    fresh_db.commit()

    # Re-run v0003 specifically
    from backend.migrations.v0003_retention_settings import up
    up(fresh_db)

    row = fresh_db.execute(
        "SELECT value FROM site_settings WHERE key=?",
        ("retention.system_events.days",),
    ).fetchone()
    assert row["value"] == "60"  # operator override preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_v0003_retention_migration.py -v`
Expected: FAIL with `ImportError: cannot import name 'v0003_retention_settings'` (module not yet created).

- [ ] **Step 3: Write minimal implementation**

Create `backend/migrations/v0003_retention_settings.py`:

```python
"""v0003 — retention default settings.

Inserts 7 rows into site_settings: cycle_interval_seconds + one days
key per PURGE_POLICY entry (behavioral_events, activity_events,
system_events, user_sessions, notifications, drafts).

INSERT OR IGNORE so re-applying after a restore preserves operator
overrides written between v0003 application and the restore point.
"""
import sqlite3


SETTINGS_SQL = """
INSERT OR IGNORE INTO site_settings (key, value, updated_at) VALUES
  ('retention.cycle_interval_seconds', '86400',  datetime('now')),
  ('retention.behavioral_events.days', '30',     datetime('now')),
  ('retention.activity_events.days',   '90',     datetime('now')),
  ('retention.system_events.days',     '180',    datetime('now')),
  ('retention.user_sessions.days',     '30',     datetime('now')),
  ('retention.notifications.days',     '30',     datetime('now')),
  ('retention.drafts.days',            '14',     datetime('now'));
"""


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(SETTINGS_SQL)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_v0003_retention_migration.py -v`
Expected: 2 passed.

Also run full suite to check no regression:
Run: `.venv/bin/python -m pytest -x`
Expected: 576 passed (574 baseline + 2 new).

- [ ] **Step 5: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/migrations/v0003_retention_settings.py \
  tests/test_v0003_retention_migration.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket13-T1): v0003 migration — retention default settings

Inserts 7 site_settings rows via INSERT OR IGNORE (idempotent so
operator-tuned overrides survive restore). One cycle_interval_seconds
key plus one .days key per PURGE_POLICY entry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: PURGE_POLICY + compute_cutoffs

**Files:**
- Create: `backend/retention/__init__.py`
- Create: `backend/retention/service.py`
- Test: `tests/test_retention_service.py`

This task introduces the policy data structure and the resolver function. No DELETEs yet — pure read of `site_settings` plus arithmetic.

- [ ] **Step 1: Write the failing test (compute_cutoffs sub-tests)**

Create `tests/test_retention_service.py`:

```python
"""Tests for backend/retention/service.py — compute_cutoffs (Task 2),
purge_single_table (Task 3), run_purge (Task 4)."""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


# ---------------- compute_cutoffs ----------------


def test_compute_cutoffs_uses_code_default_when_no_db_override(fresh_db):
    """If site_settings has no retention.<table>.days override, the
    PolicyEntry's default_days is used."""
    from backend.retention.service import compute_cutoffs, PURGE_POLICY

    # Wipe defaults inserted by v0003 so the resolver falls through to code.
    fresh_db.execute("DELETE FROM site_settings WHERE key LIKE 'retention.%'")
    fresh_db.commit()

    cutoffs = compute_cutoffs(fresh_db)
    now = datetime.now(timezone.utc)
    for entry in PURGE_POLICY:
        expected = now - timedelta(days=entry.default_days)
        actual = cutoffs[entry.table]
        # Allow 5-second wiggle for clock skew between compute and assertion.
        assert abs((actual - expected).total_seconds()) < 5, (
            f"cutoff for {entry.table}: expected {expected}, got {actual}"
        )


def test_compute_cutoffs_prefers_db_override(fresh_db):
    """If site_settings has retention.<table>.days, that value wins over default."""
    from backend.retention.service import compute_cutoffs

    # v0003 sets 30 by default; override to 60.
    fresh_db.execute(
        "UPDATE site_settings SET value=? WHERE key=?",
        ("60", "retention.behavioral_events.days"),
    )
    fresh_db.commit()

    cutoffs = compute_cutoffs(fresh_db)
    now = datetime.now(timezone.utc)
    expected = now - timedelta(days=60)
    assert abs((cutoffs["behavioral_events"] - expected).total_seconds()) < 5


def test_compute_cutoffs_treats_zero_days_as_kill_switch(fresh_db):
    """retention.<table>.days = 0 → entry is omitted from the cutoff dict
    entirely. Caller must skip the table for this cycle."""
    from backend.retention.service import compute_cutoffs

    fresh_db.execute(
        "UPDATE site_settings SET value='0' WHERE key='retention.drafts.days'"
    )
    fresh_db.commit()

    cutoffs = compute_cutoffs(fresh_db)
    assert "drafts" not in cutoffs


def test_compute_cutoffs_raises_on_negative_days(fresh_db):
    """Negative days is operator error; raise ValueError so the cycle fails
    fast and the system_events row records the misconfiguration."""
    from backend.retention.service import compute_cutoffs

    fresh_db.execute(
        "UPDATE site_settings SET value='-1' WHERE key='retention.notifications.days'"
    )
    fresh_db.commit()

    with pytest.raises(ValueError) as exc:
        compute_cutoffs(fresh_db)
    assert "negative" in str(exc.value).lower() or "-1" in str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_retention_service.py -v`
Expected: 4 FAILS — `ImportError: cannot import name 'compute_cutoffs' from 'backend.retention.service'` (module not yet created).

- [ ] **Step 3: Write minimal implementation**

Create `backend/retention/__init__.py`:

```python
```

(Empty file — package marker.)

Create `backend/retention/service.py`:

```python
"""Retention purge — core service layer.

Architecture mirrors backend/backup/service.py: a pure-function layer
the loop and HTTP routes both call into. No async, no SQLite session
state; callers manage connections.

The PURGE_POLICY list is the source of truth for which tables get
retention applied. site_settings provides per-deployment overrides.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import sqlite3

from backend.shared import settings


@dataclass(frozen=True)
class PurgePolicyEntry:
    table: str
    cutoff_column: str
    default_days: int
    extra_where: Optional[str]


PURGE_POLICY: list[PurgePolicyEntry] = [
    PurgePolicyEntry("behavioral_events", "created_at", 30,  None),
    PurgePolicyEntry("activity_events",   "created_at", 90,  None),
    PurgePolicyEntry("system_events",     "created_at", 180, None),
    PurgePolicyEntry("user_sessions",     "ended_at",   30,  "ended_at IS NOT NULL"),
    PurgePolicyEntry("notifications",     "created_at", 30,  "is_read=1"),
    PurgePolicyEntry("drafts",            "updated_at", 14,  None),
]


def _resolve_days(db: sqlite3.Connection, entry: PurgePolicyEntry) -> int:
    """Return effective retention days for `entry`. Reads
    site_settings retention.<table>.days; falls back to entry.default_days
    if missing. Raises ValueError on negative values (operator error)."""
    key = f"retention.{entry.table}.days"
    days = settings.get_int(db, key, default=entry.default_days)
    if days < 0:
        raise ValueError(
            f"site_settings {key}={days} is negative; retention windows "
            f"must be >= 0 (0 = kill switch, table not purged)"
        )
    return days


def compute_cutoffs(db: sqlite3.Connection) -> dict[str, datetime]:
    """For each PURGE_POLICY entry, compute cutoff = now() - days(N).
    Skips entries whose effective days is 0 (kill switch) — the result
    dict will not contain those tables, signaling to the caller that
    they must be omitted from this cycle.

    Raises ValueError if any entry has negative days configured.
    """
    now = datetime.now(timezone.utc)
    cutoffs: dict[str, datetime] = {}
    for entry in PURGE_POLICY:
        days = _resolve_days(db, entry)
        if days == 0:
            continue  # kill switch
        cutoffs[entry.table] = now - timedelta(days=days)
    return cutoffs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_retention_service.py -v`
Expected: 4 passed.

Also confirm full suite still green:
Run: `.venv/bin/python -m pytest -x`
Expected: 580 passed (576 + 4 new).

- [ ] **Step 5: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/retention/__init__.py \
  backend/retention/service.py \
  tests/test_retention_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket13-T2): PURGE_POLICY and compute_cutoffs resolver

Defines six PurgePolicyEntry rows (behavioral_events, activity_events,
system_events, user_sessions, notifications, drafts) and a resolver
that reads site_settings retention.<table>.days with code-default
fallback. Days=0 acts as kill switch (entry omitted from cutoff dict);
negative days raises ValueError.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: purge_single_table primitive

**Files:**
- Modify: `backend/retention/service.py` (add `purge_single_table`)
- Test: `tests/test_retention_service.py` (add 4 tests)

Given a connection, an entry, and a cutoff datetime, run a single DELETE and return the rowcount. Caller is responsible for opening/closing the transaction.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_retention_service.py`:

```python
# ---------------- purge_single_table ----------------


def _seed_behavioral_event(db, *, days_ago: int) -> int:
    """Insert a behavioral_events row dated `days_ago` days in the past."""
    cur = db.execute(
        """
        INSERT INTO behavioral_events
            (user_id, detector, threshold_value, actual_value, context_json, created_at)
        VALUES (1, 'test', 1.0, 1.0, '{}', datetime('now', ?))
        """,
        (f"-{days_ago} days",),
    )
    db.commit()
    return cur.lastrowid


def _seed_user(db, user_id: int = 1):
    """Insert a row into users so behavioral_events FK is satisfied."""
    db.execute(
        """
        INSERT INTO users (id, username, password_hash, role, is_active,
                           has_seen_manual, has_passed_training,
                           avatar_color, created_at, updated_at)
        VALUES (?, 'u', 'x', 'user', 1, 1, 1, '#000', datetime('now'), datetime('now'))
        """,
        (user_id,),
    )
    db.commit()


def test_purge_single_table_deletes_rows_older_than_cutoff(fresh_db):
    """A row dated 31 days ago is deleted when retention is 30 days."""
    from backend.retention.service import (
        purge_single_table, PURGE_POLICY,
    )
    from datetime import datetime, timedelta, timezone

    _seed_user(fresh_db)
    old_id = _seed_behavioral_event(fresh_db, days_ago=31)

    entry = next(p for p in PURGE_POLICY if p.table == "behavioral_events")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    fresh_db.execute("BEGIN IMMEDIATE")
    count = purge_single_table(fresh_db, entry, cutoff)
    fresh_db.execute("COMMIT")

    assert count == 1
    row = fresh_db.execute(
        "SELECT id FROM behavioral_events WHERE id=?", (old_id,)
    ).fetchone()
    assert row is None


def test_purge_single_table_keeps_rows_younger_than_cutoff(fresh_db):
    """A row dated 5 days ago is preserved when retention is 30 days."""
    from backend.retention.service import (
        purge_single_table, PURGE_POLICY,
    )
    from datetime import datetime, timedelta, timezone

    _seed_user(fresh_db)
    young_id = _seed_behavioral_event(fresh_db, days_ago=5)

    entry = next(p for p in PURGE_POLICY if p.table == "behavioral_events")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    fresh_db.execute("BEGIN IMMEDIATE")
    count = purge_single_table(fresh_db, entry, cutoff)
    fresh_db.execute("COMMIT")

    assert count == 0
    row = fresh_db.execute(
        "SELECT id FROM behavioral_events WHERE id=?", (young_id,)
    ).fetchone()
    assert row is not None


def test_purge_single_table_respects_extra_where(fresh_db):
    """notifications has extra_where='is_read=1' so unread rows are NEVER
    purged regardless of age."""
    from backend.retention.service import (
        purge_single_table, PURGE_POLICY,
    )
    from datetime import datetime, timedelta, timezone

    _seed_user(fresh_db)
    # Insert two old (60-day) notifications: one read, one unread.
    fresh_db.execute(
        """INSERT INTO notifications (user_id, kind, title, body, data_json,
           is_read, created_at)
           VALUES (1, 't', 'old read', 'b', '{}', 1, datetime('now', '-60 days'))""",
    )
    fresh_db.execute(
        """INSERT INTO notifications (user_id, kind, title, body, data_json,
           is_read, created_at)
           VALUES (1, 't', 'old unread', 'b', '{}', 0, datetime('now', '-60 days'))""",
    )
    fresh_db.commit()

    entry = next(p for p in PURGE_POLICY if p.table == "notifications")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    fresh_db.execute("BEGIN IMMEDIATE")
    count = purge_single_table(fresh_db, entry, cutoff)
    fresh_db.execute("COMMIT")

    assert count == 1  # only the read one
    rows = fresh_db.execute(
        "SELECT title, is_read FROM notifications ORDER BY title"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["title"] == "old unread"
    assert rows[0]["is_read"] == 0


def test_purge_single_table_uses_correct_cutoff_column(fresh_db):
    """user_sessions uses ended_at (not created_at). Verify by inserting
    an old started_at + recent ended_at row — it must NOT be purged."""
    from backend.retention.service import (
        purge_single_table, PURGE_POLICY,
    )
    from datetime import datetime, timedelta, timezone

    _seed_user(fresh_db)
    # Old started_at, recent ended_at → should be kept.
    fresh_db.execute(
        """INSERT INTO user_sessions
           (user_id, session_token, ip_hash, user_agent,
            started_at, ended_at, last_activity_at)
           VALUES (1, 'tok-recent', '', '',
                   datetime('now', '-60 days'),
                   datetime('now', '-1 days'),
                   datetime('now', '-1 days'))""",
    )
    # Old started_at AND old ended_at → should be purged.
    fresh_db.execute(
        """INSERT INTO user_sessions
           (user_id, session_token, ip_hash, user_agent,
            started_at, ended_at, last_activity_at)
           VALUES (1, 'tok-old', '', '',
                   datetime('now', '-90 days'),
                   datetime('now', '-60 days'),
                   datetime('now', '-60 days'))""",
    )
    fresh_db.commit()

    entry = next(p for p in PURGE_POLICY if p.table == "user_sessions")
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    fresh_db.execute("BEGIN IMMEDIATE")
    count = purge_single_table(fresh_db, entry, cutoff)
    fresh_db.execute("COMMIT")

    assert count == 1
    rows = fresh_db.execute(
        "SELECT session_token FROM user_sessions ORDER BY session_token"
    ).fetchall()
    assert [r["session_token"] for r in rows] == ["tok-recent"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_retention_service.py -v -k "purge_single_table"`
Expected: 4 FAILS — `ImportError: cannot import name 'purge_single_table'`.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/retention/service.py`:

```python
def purge_single_table(
    db: sqlite3.Connection,
    entry: PurgePolicyEntry,
    cutoff: datetime,
) -> int:
    """Delete rows where entry.cutoff_column < cutoff (and extra_where if any).
    Caller manages the transaction (typically a multi-table BEGIN IMMEDIATE).
    Returns the rowcount of the DELETE statement.

    The cutoff is bound as an ISO timestamp string; SQLite's text-comparison
    on ISO-8601 produces correct chronological ordering."""
    cutoff_iso = cutoff.isoformat()
    sql = f"DELETE FROM {entry.table} WHERE {entry.cutoff_column} < ?"
    if entry.extra_where:
        sql += f" AND {entry.extra_where}"
    cur = db.execute(sql, (cutoff_iso,))
    return cur.rowcount
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_retention_service.py -v`
Expected: 8 passed (4 from T2 + 4 from T3).

Run full suite: `.venv/bin/python -m pytest -x`
Expected: 584 passed.

- [ ] **Step 5: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/retention/service.py \
  tests/test_retention_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket13-T3): purge_single_table primitive

DELETE FROM <table> WHERE <cutoff_column> < ? [AND extra_where].
Caller manages the transaction. Returns cursor rowcount. Uses ISO-8601
timestamp binding so SQLite text-comparison yields correct chronology.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: run_purge orchestrator

**Files:**
- Modify: `backend/retention/service.py` (add `run_purge`)
- Test: `tests/test_retention_service.py` (add 3 tests)

Wraps `compute_cutoffs` + multi-table DELETE in a single `BEGIN IMMEDIATE` transaction. Writes `system_events` row for success/failure. Returns `{ok, purged, total}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_retention_service.py`:

```python
# ---------------- run_purge ----------------


def test_run_purge_writes_retention_success_event_with_counts(fresh_db):
    """Successful cycle writes one system_events row with event_type=
    'retention_success', severity='info', extra_json containing per-table
    purge counts."""
    from backend.retention.service import run_purge

    _seed_user(fresh_db)
    _seed_behavioral_event(fresh_db, days_ago=31)
    _seed_behavioral_event(fresh_db, days_ago=5)  # young, must survive

    out = run_purge(fresh_db)

    assert out["ok"] is True
    assert out["purged"]["behavioral_events"] == 1
    assert out["total"] >= 1

    row = fresh_db.execute(
        """SELECT event_type, severity, extra_json FROM system_events
           WHERE event_type='retention_success' ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    assert row is not None
    assert row["severity"] == "info"
    import json
    extra = json.loads(row["extra_json"])
    assert extra["purged"]["behavioral_events"] == 1


def test_run_purge_atomic_rollback_on_mid_cycle_failure(fresh_db, monkeypatch):
    """If purge_single_table raises mid-cycle, all DELETEs roll back,
    a retention_failed event is recorded, and the exception propagates."""
    from backend.retention import service as svc

    _seed_user(fresh_db)
    old_id = _seed_behavioral_event(fresh_db, days_ago=60)

    call_count = [0]
    real_purge = svc.purge_single_table

    def flaky(db, entry, cutoff):
        call_count[0] += 1
        if call_count[0] == 2:
            raise sqlite3.OperationalError("simulated mid-cycle failure")
        return real_purge(db, entry, cutoff)

    monkeypatch.setattr(svc, "purge_single_table", flaky)

    with pytest.raises(sqlite3.OperationalError):
        svc.run_purge(fresh_db)

    # First entry's DELETE was rolled back; old_id must still exist.
    row = fresh_db.execute(
        "SELECT id FROM behavioral_events WHERE id=?", (old_id,)
    ).fetchone()
    assert row is not None  # rolled back

    # retention_failed event recorded with step + error in extra_json.
    fail = fresh_db.execute(
        """SELECT event_type, severity, extra_json FROM system_events
           WHERE event_type='retention_failed' ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    assert fail is not None
    assert fail["severity"] == "error"
    import json
    extra = json.loads(fail["extra_json"])
    assert extra["step"] == "purge"
    assert "simulated mid-cycle failure" in extra["error"]


def test_run_purge_skips_table_when_kill_switch_set(fresh_db):
    """retention.behavioral_events.days=0 means that table is skipped
    entirely; count is reported as 0 (not absent), so admin UI shows
    'this table not purged this cycle'."""
    from backend.retention.service import run_purge

    fresh_db.execute(
        "UPDATE site_settings SET value='0' WHERE key='retention.behavioral_events.days'"
    )
    fresh_db.commit()

    _seed_user(fresh_db)
    old_id = _seed_behavioral_event(fresh_db, days_ago=60)

    out = run_purge(fresh_db)

    assert out["purged"]["behavioral_events"] == 0
    row = fresh_db.execute(
        "SELECT id FROM behavioral_events WHERE id=?", (old_id,)
    ).fetchone()
    assert row is not None  # kill switch preserved it
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_retention_service.py -v -k "run_purge"`
Expected: 3 FAILS — `ImportError: cannot import name 'run_purge'`.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/retention/service.py`:

```python
import logging

from backend.shared import audit


log = logging.getLogger(__name__)


def run_purge(db: sqlite3.Connection) -> dict:
    """Run a single retention cycle. Resolves cutoffs, opens a
    BEGIN IMMEDIATE transaction, runs purge_single_table for each
    PURGE_POLICY entry that has a cutoff (kill-switched entries are
    omitted from the dict). On any failure rolls back, records a
    retention_failed system_event, and re-raises. On success commits
    and records retention_success.

    Returns {ok: True, purged: {table: count}, total: N}.
    """
    cutoffs = compute_cutoffs(db)

    db.execute("BEGIN IMMEDIATE")
    try:
        purged: dict[str, int] = {}
        for entry in PURGE_POLICY:
            if entry.table not in cutoffs:
                purged[entry.table] = 0  # kill switch — report 0, not absent
                continue
            count = purge_single_table(db, entry, cutoffs[entry.table])
            purged[entry.table] = count
        db.execute("COMMIT")
    except Exception as e:
        db.execute("ROLLBACK")
        audit.log_system_event(
            db, "retention_failed", "error",
            message="retention cycle failed",
            extra={"step": "purge", "error": str(e)},
        )
        raise

    total = sum(purged.values())
    audit.log_system_event(
        db, "retention_success", "info",
        message=f"purged {total} rows across {len(purged)} tables",
        extra={"purged": purged},
    )
    return {"ok": True, "purged": purged, "total": total}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_retention_service.py -v`
Expected: 11 passed (4 + 4 + 3).

Full suite: `.venv/bin/python -m pytest -x`
Expected: 587 passed.

- [ ] **Step 5: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/retention/service.py \
  tests/test_retention_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket13-T4): run_purge orchestrator with atomic transaction

Single BEGIN IMMEDIATE wraps all purge_single_table calls; mid-cycle
failure rolls back all changes, writes retention_failed system_event
with step+error in extra_json, and re-raises. Success path COMMITs and
writes retention_success with per-table counts.

Kill-switched tables (days=0) report 0 in the purged dict rather than
being absent, so admin UI can distinguish 'no rows matched' from
'table not purged this cycle'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: preview_purge

**Files:**
- Modify: `backend/retention/service.py` (add `preview_purge`)
- Test: `tests/test_retention_preview.py` (3 tests)

Returns `{rows_to_purge: {table: count}, total, policy: [...]}`. No DELETE.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retention_preview.py`:

```python
"""Tests for backend.retention.service.preview_purge."""
import sqlite3
from pathlib import Path

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def _seed_user(db, user_id: int = 1):
    db.execute(
        """INSERT INTO users (id, username, password_hash, role, is_active,
                              has_seen_manual, has_passed_training,
                              avatar_color, created_at, updated_at)
           VALUES (?, 'u', 'x', 'user', 1, 1, 1, '#000',
                   datetime('now'), datetime('now'))""",
        (user_id,),
    )
    db.commit()


def test_preview_returns_count_per_table_without_deleting(fresh_db):
    """preview_purge counts rows that would be purged; does not delete."""
    from backend.retention.service import preview_purge

    _seed_user(fresh_db)
    fresh_db.execute(
        """INSERT INTO behavioral_events
           (user_id, detector, threshold_value, actual_value, context_json, created_at)
           VALUES (1, 't', 1.0, 1.0, '{}', datetime('now', '-31 days'))"""
    )
    fresh_db.execute(
        """INSERT INTO behavioral_events
           (user_id, detector, threshold_value, actual_value, context_json, created_at)
           VALUES (1, 't', 1.0, 1.0, '{}', datetime('now', '-5 days'))"""
    )
    fresh_db.commit()

    out = preview_purge(fresh_db)
    assert out["rows_to_purge"]["behavioral_events"] == 1
    # Both rows still exist after preview (no delete).
    n = fresh_db.execute(
        "SELECT COUNT(*) FROM behavioral_events"
    ).fetchone()[0]
    assert n == 2


def test_preview_includes_policy_snapshot(fresh_db):
    """The response includes a policy list with table, days, cutoff_iso so
    admin UI can render 'rows older than YYYY-MM-DD will be deleted'."""
    from backend.retention.service import preview_purge, PURGE_POLICY

    out = preview_purge(fresh_db)
    assert "policy" in out
    assert isinstance(out["policy"], list)
    tables_in_response = {p["table"] for p in out["policy"]}
    assert tables_in_response == {p.table for p in PURGE_POLICY}
    for entry in out["policy"]:
        assert "days" in entry
        assert "cutoff_iso" in entry
        assert isinstance(entry["days"], int)


def test_preview_uses_db_override_in_policy_snapshot(fresh_db):
    """Operator changes retention.drafts.days to 1 → preview shows 1, not 14."""
    from backend.retention.service import preview_purge

    fresh_db.execute(
        "UPDATE site_settings SET value='1' WHERE key='retention.drafts.days'"
    )
    fresh_db.commit()

    out = preview_purge(fresh_db)
    drafts_entry = next(p for p in out["policy"] if p["table"] == "drafts")
    assert drafts_entry["days"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_retention_preview.py -v`
Expected: 3 FAILS — `ImportError: cannot import name 'preview_purge'`.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/retention/service.py`:

```python
def preview_purge(db: sqlite3.Connection) -> dict:
    """Dry-run: COUNT(*) rows that would be deleted by run_purge, without
    deleting anything. Returns:
        {
            'rows_to_purge': {table: count},
            'total': N,
            'policy': [{'table', 'days', 'cutoff_iso'}, ...]
        }
    Kill-switched tables appear in 'policy' with days=0 and cutoff_iso=None;
    they are absent from 'rows_to_purge' so the count never includes them.
    """
    now_cutoffs = compute_cutoffs(db)  # only non-killed tables

    counts: dict[str, int] = {}
    policy: list[dict] = []
    for entry in PURGE_POLICY:
        days = _resolve_days(db, entry)
        cutoff_iso: Optional[str] = None
        if entry.table in now_cutoffs:
            cutoff = now_cutoffs[entry.table]
            cutoff_iso = cutoff.isoformat()
            sql = f"SELECT COUNT(*) FROM {entry.table} WHERE {entry.cutoff_column} < ?"
            if entry.extra_where:
                sql += f" AND {entry.extra_where}"
            counts[entry.table] = db.execute(sql, (cutoff_iso,)).fetchone()[0]
        policy.append({
            "table": entry.table,
            "days": days,
            "cutoff_iso": cutoff_iso,
        })

    return {
        "rows_to_purge": counts,
        "total": sum(counts.values()),
        "policy": policy,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_retention_preview.py -v`
Expected: 3 passed.

Full suite: `.venv/bin/python -m pytest -x`
Expected: 590 passed.

- [ ] **Step 5: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/retention/service.py \
  tests/test_retention_preview.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket13-T5): preview_purge dry-run

COUNT(*) per PURGE_POLICY entry without deleting; returns rows_to_purge,
total, and a policy snapshot (table, days, cutoff_iso) so admin UI can
render 'rows older than YYYY-MM-DD will be deleted'. Kill-switched
tables show days=0, cutoff_iso=null and are absent from rows_to_purge.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Async lifespan loop

**Files:**
- Create: `backend/retention/loop.py`
- Test: `tests/test_retention_loop.py`

Mirrors `backend/backup/loop.py` exactly. Sleep-first ordering. `_read_interval` re-reads `retention.cycle_interval_seconds` each iteration. Cancellation graceful. Exceptions swallowed (loop never dies).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retention_loop.py`:

```python
"""Tests for backend/retention/loop.py — async retention loop."""
import asyncio
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_retention_once_calls_run_purge_in_thread():
    """retention_once is a thin wrapper that opens a connection and
    calls run_purge in a worker thread (async-friendly)."""
    from backend.retention import loop as retention_loop

    with patch("backend.retention.loop.run_purge", return_value={"ok": True}) as mock_run:
        await retention_loop.retention_once()
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_loop_cancellation_is_graceful():
    """Cancelling the task returns cleanly without bubbling CancelledError."""
    from backend.retention import loop as retention_loop

    with patch("backend.retention.loop.retention_once") as mock_once, \
         patch("backend.retention.loop._read_interval", return_value=10):
        mock_once.return_value = None
        task = asyncio.create_task(retention_loop.retention_loop())
        await asyncio.sleep(0.01)  # let it enter sleep
        task.cancel()
        await asyncio.wait_for(task, timeout=1.0)
        assert task.done()
        assert not task.cancelled()
        assert task.exception() is None


@pytest.mark.asyncio
async def test_loop_swallows_cycle_exception_and_continues():
    """If retention_once raises, log + continue (don't kill the loop).
    Uses asyncio.Event for deterministic 2nd-call detection (Paket 12 polish pattern)."""
    from backend.retention import loop as retention_loop

    call_count = [0]
    second_call_done = asyncio.Event()

    async def cycle_then_raise():
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("boom")
        second_call_done.set()

    with patch("backend.retention.loop.retention_once", side_effect=cycle_then_raise), \
         patch("backend.retention.loop._read_interval", return_value=0):
        task = asyncio.create_task(retention_loop.retention_loop())
        await asyncio.wait_for(second_call_done.wait(), timeout=1.0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert call_count[0] >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_retention_loop.py -v`
Expected: 3 FAILS — `ImportError: cannot import name 'loop' from 'backend.retention'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/retention/loop.py`:

```python
"""Async retention loop. Mirrors backend/backup/loop.py: lifespan-driven
asyncio task, sleep-first ordering, settings live-tuned interval, never
dies on per-cycle exceptions.
"""
import asyncio
import logging
from typing import Optional

from backend import config
from backend.retention.service import run_purge
from backend.shared import settings as settings_mod
from backend.shared.db import connect


log = logging.getLogger(__name__)


DEFAULT_INTERVAL_SECONDS = 86400  # 24h


def _read_interval() -> int:
    """Re-read site_settings.retention.cycle_interval_seconds each cycle.
    Falls back to DEFAULT_INTERVAL_SECONDS if missing or unparseable.
    Uses its own short-lived connection (called from async context)."""
    try:
        conn = connect(config.DB_PATH)
        try:
            return settings_mod.get_int(
                conn,
                "retention.cycle_interval_seconds",
                default=DEFAULT_INTERVAL_SECONDS,
            )
        finally:
            conn.close()
    except Exception:
        log.exception("retention: failed to read interval, using default")
        return DEFAULT_INTERVAL_SECONDS


def _run_purge_blocking() -> None:
    """Open a connection, call run_purge, close. Synchronous wrapper for
    asyncio.to_thread — keeps blocking SQLite work off the event loop."""
    conn = connect(config.DB_PATH)
    try:
        run_purge(conn)
    finally:
        conn.close()


async def retention_once() -> None:
    """Run one retention cycle in a worker thread. Exposed for tests so
    they can call a single cycle without driving the loop."""
    await asyncio.to_thread(_run_purge_blocking)


async def retention_loop() -> None:
    """Async loop. Cancel via task.cancel().
    Sleep-first ordering: first cycle fires `interval` seconds AFTER start,
    matching backup_loop and locks_sweep so concurrent first-fire does not
    happen at boot.
    """
    while True:
        try:
            interval = _read_interval()
            await asyncio.sleep(interval)
            await retention_once()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("retention cycle failed")


_task: Optional[asyncio.Task] = None


def start() -> asyncio.Task:
    """Start the retention task; returns the handle for shutdown cancellation."""
    global _task
    _task = asyncio.create_task(retention_loop())
    return _task


def stop() -> None:
    """Cancel the running retention task (no-op if not started)."""
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
    _task = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_retention_loop.py -v`
Expected: 3 passed.

Full suite: `.venv/bin/python -m pytest -x`
Expected: 593 passed.

- [ ] **Step 5: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/retention/loop.py \
  tests/test_retention_loop.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket13-T6): async retention loop

Mirrors backend/backup/loop.py: sleep-first ordering, settings live-
tuned interval (retention.cycle_interval_seconds, 86400 default),
asyncio.to_thread for blocking SQLite work, CancelledError clean
return, all other exceptions logged-and-continued via log.exception.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Pydantic models + admin HTTP routes

**Files:**
- Create: `backend/retention/models.py`
- Create: `backend/retention/routes.py`
- Test: `tests/test_retention_admin_routes.py`

Two endpoints. Both `require_admin`. `run-now` writes `admin_audit_log`. Errors translate to HTTP 500 with PAT-style scrubbed message envelope (no PAT to scrub here, but the same `{detail: {error, message}}` shape from Paket 12 keeps API consistent).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_retention_admin_routes.py`:

```python
"""Tests for backend/retention/routes.py — admin retention HTTP endpoints."""
import json

import pytest


def test_run_now_admin_only(client, passed_user):
    """A non-admin gets 404 (existence-hide pattern)."""
    r = client.post("/api/admin/retention/run-now")
    assert r.status_code in (401, 404)


def test_run_now_returns_purged_counts(client, bootstrap_admin):
    """Admin sees {ok, purged: {table: count}, total} on success."""
    bootstrap_admin()
    r = client.post("/api/admin/retention/run-now")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert "purged" in body
    assert "total" in body
    # All six policy tables present in purged dict (kill-switched ones are 0).
    assert set(body["purged"].keys()) == {
        "behavioral_events", "activity_events", "system_events",
        "user_sessions", "notifications", "drafts",
    }


def test_run_now_writes_admin_audit_log_row(client, bootstrap_admin):
    """admin_audit_log captures the manual trigger."""
    bootstrap_admin()
    client.post("/api/admin/retention/run-now")

    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        row = conn.execute(
            "SELECT action_type, target_kind, metadata_json FROM admin_audit_log "
            "WHERE action_type='retention_run_now' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["target_kind"] == "retention"
    meta = json.loads(row["metadata_json"])
    assert "total" in meta
    assert "by_table" in meta


def test_run_now_returns_500_on_internal_failure(client, bootstrap_admin, monkeypatch):
    """If run_purge raises, return 500 with structured error detail."""
    bootstrap_admin()
    from backend.retention import routes as retention_routes
    monkeypatch.setattr(
        retention_routes, "run_purge",
        lambda db: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    r = client.post("/api/admin/retention/run-now")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"]["error"] == "retention_failed"
    assert "boom" in body["detail"]["message"]


def test_preview_admin_only(client, passed_user):
    r = client.get("/api/admin/retention/preview")
    assert r.status_code in (401, 404)


def test_preview_returns_dry_run_counts(client, bootstrap_admin):
    """Preview returns rows_to_purge, total, policy without modifying DB."""
    bootstrap_admin()
    r = client.get("/api/admin/retention/preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rows_to_purge" in body
    assert "total" in body
    assert "policy" in body
    assert isinstance(body["policy"], list)
    assert len(body["policy"]) == 6  # all six tables represented
    for p in body["policy"]:
        assert {"table", "days", "cutoff_iso"} <= set(p.keys())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_retention_admin_routes.py -v`
Expected: 6 FAILS — endpoints not registered (404) or import errors.

- [ ] **Step 3: Write minimal implementation**

Create `backend/retention/models.py`:

```python
"""Pydantic schemas for /api/admin/retention/{run-now,preview}."""
from typing import Optional

from pydantic import BaseModel, Field


class RetentionRunNowResponse(BaseModel):
    ok: bool = Field(..., description="True if cycle committed successfully")
    purged: dict[str, int] = Field(
        ...,
        description="Per-table row counts deleted in this cycle. "
                    "Kill-switched tables show 0.",
    )
    total: int = Field(..., description="Sum of purged values")


class RetentionPolicyEntry(BaseModel):
    table: str
    days: int = Field(
        ..., description="Effective retention window. 0 = kill switch."
    )
    cutoff_iso: Optional[str] = Field(
        None,
        description="ISO-8601 timestamp; rows older than this would be "
                    "purged. Null for kill-switched tables.",
    )


class RetentionPreviewResponse(BaseModel):
    rows_to_purge: dict[str, int] = Field(
        ...,
        description="Per-table row counts a run_purge would delete now. "
                    "Excludes kill-switched tables.",
    )
    total: int
    policy: list[RetentionPolicyEntry]
```

Create `backend/retention/routes.py`:

```python
"""Admin HTTP endpoints for retention purge and dry-run preview."""
import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.retention.models import (
    RetentionPreviewResponse,
    RetentionRunNowResponse,
)
from backend.retention.service import preview_purge, run_purge
from backend.shared import audit
from backend.users.deps import get_db, require_admin


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/retention", tags=["admin-retention"])


@router.post("/run-now", response_model=RetentionRunNowResponse)
def admin_retention_run_now(
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Trigger a retention cycle synchronously. Blocks until commit/rollback.
    Returns 500 on any failure (system_events row already written by
    run_purge's failure path)."""
    try:
        result = run_purge(db)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "retention_failed", "message": str(e)},
        )

    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="retention_run_now",
            target_kind="retention", target_id=None,
            metadata={
                "total": result["total"],
                "by_table": result["purged"],
            },
        )
    except Exception:
        log.exception("audit retention_run_now failed")

    return result


@router.get("/preview", response_model=RetentionPreviewResponse)
def admin_retention_preview(
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Read-only dry-run. Returns per-table count of rows that would be
    purged plus the active policy snapshot."""
    return preview_purge(db)
```

- [ ] **Step 4: Wire the router into the app**

Modify `backend/main.py`:
- Find existing `app.include_router(...)` calls (around line 80+).
- Add one new line to import + include the retention router.

Specifically, locate the import block at the top of `backend/main.py`:

```python
from backend.locks import sweep as locks_sweep
from backend.backup import loop as backup_loop
```

Add directly below:

```python
from backend.retention import loop as retention_loop
```

Then locate the `app.include_router(...)` block and add:

```python
from backend.retention.routes import router as retention_router
app.include_router(retention_router)
```

(Lifespan integration for start/stop comes in Task 8 — keep that scope contained.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_retention_admin_routes.py -v`
Expected: 6 passed.

Full suite: `.venv/bin/python -m pytest -x`
Expected: 599 passed.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/retention/models.py \
  backend/retention/routes.py \
  backend/main.py \
  tests/test_retention_admin_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket13-T7): admin endpoints for run-now and preview

POST /api/admin/retention/run-now and GET /api/admin/retention/preview,
both require_admin (404-on-non-admin existence hide). Run-now writes
admin_audit_log row with total + by_table metadata. Run-now translates
service exceptions to HTTP 500 with {detail: {error, message}} matching
Paket 12 backup endpoint envelope.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Lifespan integration + integration test

**Files:**
- Modify: `backend/main.py` (lifespan start/stop)
- Test: `tests/test_retention_lifespan.py`

Add 1 start call and 4 stop+await lines to `lifespan()`. The test verifies the task is started and stopped with the app, mirroring `tests/test_backup_lifespan.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_retention_lifespan.py` (mirrors `tests/test_backup_lifespan.py:6-39`):

```python
"""Smoke test verifying the retention task starts and stops cleanly with the server."""
from fastapi.testclient import TestClient
from unittest.mock import patch


def test_lifespan_starts_and_stops_retention_task(tmp_path, monkeypatch):
    """Server lifespan creates the retention task on startup and cancels it on
    shutdown without raising. Uses side_effect that calls the real start/stop
    so the task is properly created and cancelled inside the right event loop."""
    from backend import main, config
    from backend.retention import loop as retention_loop_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db" / "test.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr(config, "DB_DIR", tmp_path / "db")
    monkeypatch.setattr(config, "DOCUMENTS_DIR", tmp_path / "documents")
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path / "exports")

    started = []
    stopped = []
    real_start = retention_loop_mod.start
    real_stop = retention_loop_mod.stop

    def fake_start():
        started.append(True)
        return real_start()

    def fake_stop():
        stopped.append(True)
        return real_stop()

    # Patch target is `backend.main.retention_loop.start` because main.py
    # imports the module under that alias (`from backend.retention import
    # loop as retention_loop`).
    with patch("backend.main.retention_loop.start", side_effect=fake_start), \
         patch("backend.main.retention_loop.stop",  side_effect=fake_stop):
        with TestClient(main.app) as client:
            r = client.get("/api/health")
            assert r.status_code == 200
        # After exiting the with block, lifespan shutdown ran.
        assert started == [True]
        assert stopped == [True]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_retention_lifespan.py -v`
Expected: FAIL — `mock_start.call_count == 0` because `lifespan()` doesn't call it yet.

- [ ] **Step 3: Modify `backend/main.py` lifespan**

Locate the existing lifespan body in `backend/main.py` (around line 36-69). Find the section where `backup_loop.start()` is called:

```python
    sweep_task = locks_sweep.start(interval_seconds=60)
    backup_task = backup_loop.start()
    yield
```

Change to:

```python
    sweep_task     = locks_sweep.start(interval_seconds=60)
    backup_task    = backup_loop.start()
    retention_task = retention_loop.start()
    yield
```

Then locate the post-yield cleanup. Find:

```python
    backup_loop.stop()
    try:
        await backup_task
    except Exception:
        pass
```

Append directly after it:

```python
    retention_loop.stop()
    try:
        await retention_task
    except Exception:
        pass
```

(The `from backend.retention import loop as retention_loop` import was added in Task 7.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_retention_lifespan.py -v`
Expected: 1 passed.

Full suite: `.venv/bin/python -m pytest -x`
Expected: 600 passed (574 + 26 new).

- [ ] **Step 5: Smoke-test against the live dev server**

Confirm end-to-end with the actual server:

```bash
# Stop any running server first
lsof -ti:8000 | xargs -r kill 2>/dev/null; sleep 1

# Start with retention loop active
DATA_DIR=$(pwd)/deneme-dev/data \
  .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
sleep 2

# Login
curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"adminpass123"}' \
  -c /tmp/deneme-cookies.txt -b /tmp/deneme-cookies.txt

# Preview (read-only, shows policy + counts)
curl -s -b /tmp/deneme-cookies.txt http://127.0.0.1:8000/api/admin/retention/preview

# Run-now (actually purges)
curl -s -X POST -b /tmp/deneme-cookies.txt http://127.0.0.1:8000/api/admin/retention/run-now

# Verify system_events
.venv/bin/python -c "
import sqlite3
db = sqlite3.connect('deneme-dev/data/db/annotations.db')
db.row_factory = sqlite3.Row
for r in db.execute(
    \"SELECT id, event_type, severity, extra_json, created_at \"
    \"FROM system_events WHERE event_type LIKE 'retention_%' \"
    \"ORDER BY id DESC LIMIT 3\"
):
    print(dict(r))
"

# Tear down
lsof -ti:8000 | xargs -r kill 2>/dev/null
```

Expected:
- Preview returns 200 with policy list + zero/low row counts (fresh dev DB).
- Run-now returns 200 with `purged: {behavioral_events: 0, ...}` and `pushed: not relevant`.
- system_events shows one `retention_success` row with `extra_json={"purged": {...}}`.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add \
  backend/main.py \
  tests/test_retention_lifespan.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "feat(paket13-T8): lifespan integration for retention loop

Adds retention_loop.start() alongside locks_sweep.start and
backup_loop.start, plus the symmetric stop+await on shutdown. Test
verifies start/stop are each called exactly once across an app
lifecycle (mirrors tests/test_backup_lifespan.py).

End-to-end smoke verified against live dev server: preview returns
policy snapshot, run-now writes retention_success system_event with
per-table counts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 7: Tag the paket**

```bash
git tag paket-13-retention HEAD
git tag -l "paket-13-*" --format="%(refname:short)  %(objectname:short)  %(subject)"
```

Expected:
```
paket-13-retention  <new sha>  feat(paket13-T8): lifespan integration for retention loop
```

---

## Self-Review Checklist (run after writing the plan, fix inline)

✅ **Spec coverage:**
- D1 (retention only, no GDPR delete) — no task touches users; non-goals section in spec; correct.
- D2 (hard purge, no archival) — purge_single_table uses DELETE, no archive table created. ✓
- D3 (scheduled + manual) — Task 6 (loop) + Task 7 (run-now). ✓
- D4 (preview endpoint) — Task 5 + Task 7. ✓
- D5 (no VACUUM) — not implemented. ✓
- D6 (code PURGE_POLICY + DB override) — Task 2. ✓
- D7 (single transaction all-or-nothing) — run_purge in Task 4. ✓
- D8 (no SSE) — no sse_broker calls anywhere. ✓
- D9 (no new tables) — only v0003 INSERT OR IGNORE into site_settings. ✓

✅ **Placeholder scan:** No "TBD", "TODO", "fill in", "similar to". Every step has actual code or runnable command.

✅ **Type consistency:**
- `PurgePolicyEntry` defined Task 2, used in Tasks 3-7. Field names: `table`, `cutoff_column`, `default_days`, `extra_where`. Consistent.
- `compute_cutoffs` returns `dict[str, datetime]` everywhere.
- `run_purge` returns `{ok, purged: dict[str, int], total: int}` in Task 4, asserted in Task 7 routes test, consumed by routes implementation. Consistent.
- `preview_purge` returns `{rows_to_purge, total, policy}` in Task 5, consumed by routes in Task 7. Consistent.
- Audit metadata key is `by_table` (not `by_table_purged` etc.) — used in route impl + test. Consistent.

✅ **Test counts:**
- T1: 2 tests (migration)
- T2: 4 tests (compute_cutoffs)
- T3: 4 tests (purge_single_table)
- T4: 3 tests (run_purge)
- T5: 3 tests (preview_purge)
- T6: 3 tests (loop)
- T7: 6 tests (admin routes)
- T8: 1 test (lifespan)
- **Total: 26 new tests.** Suite size 574 → 600.

✅ **No backward-compatibility shims** introduced. No feature flags. Code matches spec.

✅ **Frequent commits:** 8 commits, one per task. Atomic, paket-tagged messages.
