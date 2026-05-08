# Paket 11 — Admin Panel (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the backend admin surface so the future frontend admin panel (Paket 16) can manage users, training data, locks, and audit/system event visibility. Adds 7 new admin endpoints (locks force-release, training reset, gold-doc CRUD, quiz CRUD, system-events viewer) plus an in-place enhancement of `/api/admin/audit-log` (pagination + filters). Adds one schema migration (`v0002`) for `training_quiz_overrides`. Backend-only paket; no UI work.

**Architecture:** Domain-distributed: force-release goes into `backend/locks/routes.py` (next to acquire/release); training reset + gold-doc CRUD + quiz CRUD go into `backend/training/routes.py` (next to start/quiz/annotate); audit-log + system-events viewers go into the existing `backend/admin/routes.py` (which already houses `/api/admin/settings`). Service helpers live in their respective domain `service.py` files; new `backend/admin/service.py` for system-events listing. Reuses Paket 5/8 inline-audit pattern, Paket 9 per-step fault isolation, Paket 10 hybrid resolver pattern.

**Tech Stack:** Existing FastAPI + SQLite. No new third-party deps. Reuses `backend.shared.audit.log_admin_action`, `backend.notifications.service.create`, `backend.shared.sse.broker`, `backend.users.deps.require_admin`.

---

## Mimari Kararlar (Locked from spec 2026-05-08-paket-11-admin-panel-design.md, commit e63d21e)

- **Module layout:**
  - `backend/migrations/v0002_admin_panel.py` — adds `training_quiz_overrides` table.
  - `backend/locks/routes.py` — adds `POST /{document_id}/admin/force-release`. Existing 3 `lock_released` publish sites (route release, sweep release, force release) all gain `reason` field.
  - `backend/training/routes.py` — adds reset + gold-doc CRUD + quiz CRUD (7 endpoints).
  - `backend/training/service.py` — adds `reset_user_training`, `upsert_gold_doc_override`, `soft_delete_gold_doc`, `upsert_quiz_override`, `soft_delete_quiz_override`. `start_attempt` and `submit_quiz` migrate from `quiz_data.QUIZ_QUESTIONS` import to `quiz_data.get_active_quiz_questions(db)`.
  - `backend/training/quiz_data.py` — adds `get_active_quiz_questions(db)` hybrid resolver (mirrors `service.get_active_gold_docs`).
  - `backend/training/models.py` — Pydantic schemas for the 7 new endpoints.
  - `backend/admin/routes.py` — adds `GET /audit-log` (replaces in-place) + `GET /system-events`.
  - `backend/admin/service.py` — NEW. `list_system_events`. (`list_admin_audit` lives in `users/service.py` to stay close to Paket 2 admin user mgmt.)
  - `backend/users/service.py` — adds `list_admin_audit`.
- **Auth:** All new endpoints `Depends(require_admin)` → 404 existence-hide for non-admins.
- **Quiz override storage** is symmetric with `training_gold_doc_overrides`. Schema:
  ```sql
  CREATE TABLE training_quiz_overrides (
      question_id          TEXT    PRIMARY KEY,
      is_deleted           INTEGER NOT NULL DEFAULT 0,
      text                 TEXT,
      choices_json         TEXT,
      correct_choice_idx   INTEGER,
      source               TEXT    NOT NULL CHECK(source IN ('override','custom')),
      created_by_admin_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
      created_at           TIMESTAMP NOT NULL,
      updated_at           TIMESTAMP NOT NULL
  );
  CREATE INDEX idx_quiz_overrides_active
      ON training_quiz_overrides(question_id) WHERE is_deleted=0;
  ```
- **Hybrid quiz resolver** mirrors gold-doc resolver:
  ```python
  def get_active_quiz_questions(db) -> list[dict]:
      rows = db.execute("SELECT * FROM training_quiz_overrides").fetchall()
      overrides = {r["question_id"]: r for r in rows}
      out = []
      seen = set()
      for code in QUIZ_QUESTIONS:
          qid = code["id"]
          ov = overrides.get(qid)
          if ov is not None and ov["is_deleted"]:
              continue
          if ov is not None:
              text = ov["text"] if ov["text"] is not None else code["text"]
              choices = json.loads(ov["choices_json"]) if ov["choices_json"] is not None else code["choices"]
              cci = ov["correct_choice_idx"] if ov["correct_choice_idx"] is not None else code["correct_choice_idx"]
              out.append({"id": qid, "text": text, "choices": choices, "correct_choice_idx": cci})
          else:
              out.append(dict(code))
          seen.add(qid)
      for qid, ov in overrides.items():
          if ov["source"] == "custom" and not ov["is_deleted"] and qid not in seen:
              out.append({
                  "id": qid,
                  "text": ov["text"],
                  "choices": json.loads(ov["choices_json"]) if ov["choices_json"] else [],
                  "correct_choice_idx": ov["correct_choice_idx"] if ov["correct_choice_idx"] is not None else 0,
              })
      return out
  ```
- **Training reset** is soft-only: `DELETE FROM training_attempts WHERE user_id=?` + `UPDATE users SET has_passed_training=0`. XP, badges, ledger rows retained. Notification `kind='training_reset'` is created for the affected user.
- **Force-release SSE:** existing `lock_released` event gains a `reason` field at all 3 publish sites:
  - `backend/locks/routes.py:97` (user release) → `reason='user_release'`
  - `backend/locks/sweep.py:35` (expired sweep) → `reason='sweep_expired'`
  - new admin force-release → `reason='admin_force'`
- **Audit-log shape:** existing `GET /api/admin/audit-log` returns `{events: [...]}` today; Paket 11 changes to `{items, total, has_more}`. Per-item field names preserved.
- **Pagination convention:** `limit` (default 50, max 200), `offset` (default 0). Response: `{items, total, has_more}`.
- **system_events table** has no `user_id` column. Filter set: `event_type`, `severity` ∈ {info,warn,error}, `date_from`, `date_to`.
- **Audit row writing:** every new admin route inline-writes via `audit.log_admin_action(...)` (Paket 5/8 pattern, NOT a new helper). `force_release` gets `action_type='lock_force_release'`; reset → `'reset_training'`; gold-doc upsert → `'upsert_gold_doc'`; gold-doc delete → `'delete_gold_doc'`; quiz upsert → `'upsert_quiz_question'`; quiz delete → `'delete_quiz_question'`.
- **`force_release` service signature** (Paket 5) is `force_release(db, *, document_id) -> None`. No admin_id param. Audit row writing happens in the route handler with `admin["id"]`.
- **Type hints on `db`:** `db: sqlite3.Connection` (Paket 7+ convention).
- **Idempotent reset:** re-resetting an already-reset user is a no-op success. Re-tombstoning an already-tombstoned override is allowed (just bumps updated_at).

## Dosya Yapısı

```
backend/migrations/v0002_admin_panel.py    # NEW — training_quiz_overrides table
backend/locks/routes.py                    # MODIFIED — add force-release + reason field on 2 existing publishes
backend/locks/sweep.py                     # MODIFIED — add reason='sweep_expired'
backend/training/quiz_data.py              # MODIFIED — add get_active_quiz_questions(db)
backend/training/service.py                # MODIFIED — add reset/upsert/delete helpers; switch start_attempt + submit_quiz to resolver
backend/training/models.py                 # MODIFIED — add 6 new Pydantic schemas (4 request, 2 response wrappers)
backend/training/routes.py                 # MODIFIED — add 7 admin endpoints
backend/admin/routes.py                    # MODIFIED — add audit-log (replaces) + system-events GETs
backend/admin/service.py                   # NEW — list_system_events
backend/users/service.py                   # MODIFIED — add list_admin_audit
backend/users/routes.py                    # MODIFIED — REMOVE existing /admin/audit-log handler (moved to admin/routes.py)
backend/main.py                            # NO CHANGE (admin_router already mounted from Paket 8)

tests/test_migrations_v0002.py             # NEW — schema applied cleanly
tests/test_training_quiz_resolver.py       # NEW — hybrid quiz resolver
tests/test_training_admin_reset.py         # NEW — reset_user_training + endpoint
tests/test_locks_admin_force_release.py    # NEW — force-release endpoint + SSE reason
tests/test_training_admin_gold_docs.py     # NEW — gold-doc CRUD endpoints
tests/test_training_admin_quiz.py          # NEW — quiz CRUD endpoints + start_attempt now uses resolver
tests/test_admin_audit_log_filtered.py     # NEW — pagination + filters
tests/test_admin_system_events.py          # NEW — system-events viewer
tests/test_locks_routes.py                 # MODIFIED — assert reason='user_release' on existing lock_released test
tests/test_locks_sweep.py                  # MODIFIED — assert reason='sweep_expired' on existing test
tests/test_admin_routes.py                 # MODIFIED — replace existing audit-log assertion (was {events: ...})
```

---

## Test Helpers (Shared Across All New Test Files)

Existing test files (`tests/test_admin_routes.py`, `tests/test_training_routes.py`, etc.) each define their own `_bootstrap_admin` and `_seen_manual_user` helpers — they are NOT in `conftest.py`. The pattern is local-per-file duplication.

For Paket 11 we follow the same pattern but extend the helpers to **return IDs** (existing versions don't). **Copy this block verbatim into each new test file's top:**

```python
def _bootstrap_admin(client, username="root", password="rootpass1"):
    """Register a user, promote to admin via direct DB, login.
    Returns: admin user_id (int)."""
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("BURSIYER-2026",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": username, "password": password, "invite_code": "BURSIYER-2026",
    })
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE users SET role='admin' WHERE username=?", (username,))
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        admin_id = row["id"]
    finally:
        conn.close()
    client.post("/api/auth/login", json={"username": username, "password": password})
    return admin_id


def _seen_manual_user(client, username, invite_code, password="test123"):
    """Register a new user with the given invite code; mark has_seen_manual=1
    so they pass the require_seen_manual gate. Logs them in.
    Returns: user_id (int).
    Note: deactivates the existing active invite first to avoid
    idx_invite_active uniqueness conflict."""
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE invite_codes SET is_active=0")
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            (invite_code,),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": username, "password": password, "invite_code": invite_code,
    })
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE users SET has_seen_manual=1 WHERE username=?", (username,))
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        user_id = row["id"]
    finally:
        conn.close()
    client.post("/api/auth/login", json={"username": username, "password": password})
    return user_id
```

**`client` fixture** comes from the existing `tests/conftest.py` (already provides a TestClient with isolated DATA_DIR per-test). New tests `import` it implicitly via pytest discovery — no explicit import needed in test files; just take `client` as a function parameter.

**Where this matters:** every test code block in Tasks 3, 4, 5, 6, 7, 8 references these helpers. Drop the `from tests.conftest import client, _bootstrap_admin, _seen_manual_user` import line shown in those task code blocks (it doesn't work) and instead copy the helper definitions into the top of each new test file.

---

## Task 1: v0002 Migration — `training_quiz_overrides` Table

**Goal:** Ship the new table so the resolver in Task 2 has somewhere to read overrides from. Migration runner auto-discovers `v0002_*.py`; no runner changes needed.

**Files:**
- Create: `backend/migrations/v0002_admin_panel.py`
- Create: `tests/test_migrations_v0002.py`

- [ ] **Step 1: Write `tests/test_migrations_v0002.py`**

```python
"""Verify v0002 migration creates training_quiz_overrides cleanly."""
import sqlite3

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect


@pytest.fixture
def fresh_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = connect(db_path)
    yield conn
    conn.close()


def test_v0002_creates_quiz_overrides_table(fresh_db):
    apply_migrations(fresh_db, discover_migrations())
    rows = fresh_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='training_quiz_overrides'"
    ).fetchall()
    assert len(rows) == 1


def test_v0002_quiz_overrides_columns(fresh_db):
    apply_migrations(fresh_db, discover_migrations())
    cols = {r[1]: r for r in fresh_db.execute("PRAGMA table_info(training_quiz_overrides)").fetchall()}
    assert "question_id" in cols
    assert "is_deleted" in cols
    assert "text" in cols
    assert "choices_json" in cols
    assert "correct_choice_idx" in cols
    assert "source" in cols
    assert "created_by_admin_id" in cols
    assert "created_at" in cols
    assert "updated_at" in cols
    # question_id is PK
    pk_cols = [r[1] for r in cols.values() if r[5] > 0]
    assert pk_cols == ["question_id"]


def test_v0002_quiz_overrides_source_check(fresh_db):
    apply_migrations(fresh_db, discover_migrations())
    fresh_db.execute(
        "INSERT INTO training_quiz_overrides(question_id, source, created_at, updated_at) "
        "VALUES (?, 'override', ?, ?)", ("q01", "2026-05-08T00:00:00+00:00", "2026-05-08T00:00:00+00:00"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        fresh_db.execute(
            "INSERT INTO training_quiz_overrides(question_id, source, created_at, updated_at) "
            "VALUES (?, 'invalid', ?, ?)", ("q02", "2026-05-08T00:00:00+00:00", "2026-05-08T00:00:00+00:00"),
        )


def test_v0002_idempotent(fresh_db):
    """Running discover+apply twice should be a no-op the second time."""
    apply_migrations(fresh_db, discover_migrations())
    second = apply_migrations(fresh_db, discover_migrations())
    assert second == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_migrations_v0002.py -v`
Expected: FAIL — `table training_quiz_overrides has no rows` or `no such table`.

- [ ] **Step 3: Implement `backend/migrations/v0002_admin_panel.py`**

```python
"""v0002 — Admin Panel: training_quiz_overrides table.

Adds a single new table symmetric with training_gold_doc_overrides (v0001).
Quiz override storage allows admins (Paket 11) to edit, replace, or
soft-delete training quiz questions without code changes. NULL fields
fall back to baseline `quiz_data.QUIZ_QUESTIONS` per the hybrid resolver.
"""
import sqlite3


SCHEMA_SQL = """
CREATE TABLE training_quiz_overrides (
    question_id          TEXT    PRIMARY KEY,
    is_deleted           INTEGER NOT NULL DEFAULT 0,
    text                 TEXT,
    choices_json         TEXT,
    correct_choice_idx   INTEGER,
    source               TEXT    NOT NULL CHECK(source IN ('override','custom')),
    created_by_admin_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at           TIMESTAMP NOT NULL,
    updated_at           TIMESTAMP NOT NULL
);

CREATE INDEX idx_quiz_overrides_active
    ON training_quiz_overrides(question_id) WHERE is_deleted=0;
"""


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_migrations_v0002.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 461 prior + 4 new = 465 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/migrations/v0002_admin_panel.py tests/test_migrations_v0002.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket11): v0002 migration — training_quiz_overrides table

Symmetric with training_gold_doc_overrides; NULL fallback to baseline
quiz_data.QUIZ_QUESTIONS via the hybrid resolver added in Task 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Hybrid Quiz Resolver

**Goal:** Add `get_active_quiz_questions(db)` to `backend/training/quiz_data.py` mirroring the gold-doc resolver pattern. Tested in isolation; consumed by `start_attempt` and `submit_quiz` in Task 6.

**Files:**
- Modify: `backend/training/quiz_data.py` (add function at bottom)
- Create: `tests/test_training_quiz_resolver.py`

- [ ] **Step 1: Write `tests/test_training_quiz_resolver.py`**

```python
"""Hybrid resolver: code baseline + DB overrides for quiz questions."""
import json
import sqlite3
from datetime import datetime, timezone

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect
from backend.training.quiz_data import QUIZ_QUESTIONS, get_active_quiz_questions


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "t.db")
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_resolver_returns_baseline_when_no_overrides(db):
    out = get_active_quiz_questions(db)
    assert len(out) == len(QUIZ_QUESTIONS)
    assert {q["id"] for q in out} == {q["id"] for q in QUIZ_QUESTIONS}


def test_override_replaces_baseline_text(db):
    db.execute(
        """INSERT INTO training_quiz_overrides(question_id, is_deleted, text, choices_json, correct_choice_idx, source, created_at, updated_at)
           VALUES (?, 0, ?, ?, ?, 'override', ?, ?)""",
        ("q01", "Yeni soru metni", json.dumps(["A", "B", "C", "D"]), 2, _now(), _now()),
    )
    out = get_active_quiz_questions(db)
    q01 = next(q for q in out if q["id"] == "q01")
    assert q01["text"] == "Yeni soru metni"
    assert q01["choices"] == ["A", "B", "C", "D"]
    assert q01["correct_choice_idx"] == 2


def test_override_with_null_fields_falls_back_to_baseline(db):
    db.execute(
        """INSERT INTO training_quiz_overrides(question_id, is_deleted, text, choices_json, correct_choice_idx, source, created_at, updated_at)
           VALUES (?, 0, NULL, NULL, NULL, 'override', ?, ?)""",
        ("q01", _now(), _now()),
    )
    out = get_active_quiz_questions(db)
    q01_baseline = next(q for q in QUIZ_QUESTIONS if q["id"] == "q01")
    q01_resolved = next(q for q in out if q["id"] == "q01")
    assert q01_resolved["text"] == q01_baseline["text"]
    assert q01_resolved["choices"] == q01_baseline["choices"]
    assert q01_resolved["correct_choice_idx"] == q01_baseline["correct_choice_idx"]


def test_tombstone_excludes_baseline_question(db):
    db.execute(
        """INSERT INTO training_quiz_overrides(question_id, is_deleted, source, created_at, updated_at)
           VALUES (?, 1, 'override', ?, ?)""",
        ("q01", _now(), _now()),
    )
    out = get_active_quiz_questions(db)
    assert "q01" not in {q["id"] for q in out}
    assert len(out) == len(QUIZ_QUESTIONS) - 1


def test_custom_question_appended(db):
    db.execute(
        """INSERT INTO training_quiz_overrides(question_id, is_deleted, text, choices_json, correct_choice_idx, source, created_at, updated_at)
           VALUES (?, 0, ?, ?, ?, 'custom', ?, ?)""",
        ("custom_q01", "Yeni özel soru", json.dumps(["X", "Y", "Z", "W"]), 1, _now(), _now()),
    )
    out = get_active_quiz_questions(db)
    assert len(out) == len(QUIZ_QUESTIONS) + 1
    custom = next(q for q in out if q["id"] == "custom_q01")
    assert custom["text"] == "Yeni özel soru"
    assert custom["correct_choice_idx"] == 1


def test_tombstone_blocks_custom_too(db):
    db.execute(
        """INSERT INTO training_quiz_overrides(question_id, is_deleted, text, choices_json, correct_choice_idx, source, created_at, updated_at)
           VALUES (?, 1, ?, ?, ?, 'custom', ?, ?)""",
        ("custom_q01", "Will not appear", json.dumps(["A", "B", "C", "D"]), 0, _now(), _now()),
    )
    out = get_active_quiz_questions(db)
    assert "custom_q01" not in {q["id"] for q in out}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_training_quiz_resolver.py -v`
Expected: FAIL — `cannot import name 'get_active_quiz_questions'`.

- [ ] **Step 3: Implement `get_active_quiz_questions` at bottom of `backend/training/quiz_data.py`**

Append after the `QUIZ_QUESTIONS = [...]` list:

```python
import json
import sqlite3


def get_active_quiz_questions(db: sqlite3.Connection) -> list[dict]:
    """Hybrid resolver: code baseline (QUIZ_QUESTIONS) + DB overrides
    (training_quiz_overrides). Symmetric with
    backend.training.service.get_active_gold_docs.

    Resolution rules:
      - For every code-baseline entry:
          * Override row with is_deleted=1 → exclude.
          * Override row present → merge (override fields win; NULL means
            fall back to code).
          * Otherwise → use code entry as-is.
      - For every override row with source='custom' AND is_deleted=0 AND
        question_id NOT in code baseline → append.
    """
    rows = db.execute(
        "SELECT question_id, is_deleted, text, choices_json, "
        "correct_choice_idx, source FROM training_quiz_overrides"
    ).fetchall()
    overrides = {r["question_id"]: r for r in rows}

    out: list[dict] = []
    seen: set[str] = set()
    for code in QUIZ_QUESTIONS:
        qid = code["id"]
        ov = overrides.get(qid)
        if ov is not None and ov["is_deleted"]:
            continue
        if ov is not None:
            text = ov["text"] if ov["text"] is not None else code["text"]
            choices = (
                json.loads(ov["choices_json"]) if ov["choices_json"] is not None
                else code["choices"]
            )
            cci = (
                ov["correct_choice_idx"] if ov["correct_choice_idx"] is not None
                else code["correct_choice_idx"]
            )
            out.append({
                "id": qid, "text": text,
                "choices": choices, "correct_choice_idx": cci,
            })
        else:
            out.append(dict(code))
        seen.add(qid)

    for qid, ov in overrides.items():
        if ov["source"] == "custom" and not ov["is_deleted"] and qid not in seen:
            out.append({
                "id": qid,
                "text": ov["text"],
                "choices": json.loads(ov["choices_json"]) if ov["choices_json"] else [],
                "correct_choice_idx": (
                    ov["correct_choice_idx"] if ov["correct_choice_idx"] is not None else 0
                ),
            })

    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_training_quiz_resolver.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 465 prior + 6 new = 471 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/training/quiz_data.py tests/test_training_quiz_resolver.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket11): hybrid quiz resolver

Mirror of get_active_gold_docs for quiz questions: code baseline +
training_quiz_overrides merge with NULL-fallback. Consumed by start_attempt
and submit_quiz in Task 6.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Training Reset Endpoint

**Goal:** `POST /api/admin/training/users/{user_id}/reset` — soft reset: clear `training_attempts` rows, set `users.has_passed_training=0`, write notification, write audit row. Idempotent.

**Files:**
- Modify: `backend/training/service.py` (add `reset_user_training`)
- Modify: `backend/training/routes.py` (add admin reset route)
- Modify: `backend/training/models.py` (add `OkAdminResponse`)
- Create: `tests/test_training_admin_reset.py`

- [ ] **Step 1: Write `tests/test_training_admin_reset.py`**

(Copy the `_bootstrap_admin` + `_seen_manual_user` helpers from the "Test Helpers" section above into the top of this file.)

```python
"""Admin reset endpoint: soft reset (clear attempts + has_passed_training=0)."""


def test_reset_clears_attempts_and_flips_passed(client):
    admin_id = _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")

    # Simulate: user has passed training
    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    db.execute(
        "INSERT INTO training_attempts(id, user_id, started_at, finished_at, quiz_score, quiz_total, annotation_pass_count, annotation_total, passed) VALUES (1, ?, '2026-05-01T00:00:00+00:00', '2026-05-01T00:01:00+00:00', 5, 5, 3, 3, 1)",
        (user_id,),
    )
    db.execute("UPDATE users SET has_passed_training=1 WHERE id=?", (user_id,))
    db.commit()
    db.close()

    r = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    db = connect(DB_PATH)
    rows = db.execute("SELECT id FROM training_attempts WHERE user_id=?", (user_id,)).fetchall()
    assert rows == []
    user = db.execute("SELECT has_passed_training FROM users WHERE id=?", (user_id,)).fetchone()
    assert user["has_passed_training"] == 0
    db.close()


def test_reset_writes_audit_row(client):
    admin_id = _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    r = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='reset_training' AND target_id=?",
        (str(user_id),),
    ).fetchone()
    assert row is not None
    assert row["admin_user_id"] == admin_id
    db.close()


def test_reset_creates_notification(client):
    admin_id = _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    r = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM notifications WHERE user_id=? AND kind='training_reset'", (user_id,),
    ).fetchone()
    assert row is not None
    db.close()


def test_reset_unknown_user_returns_404(client):
    _bootstrap_admin(client)
    r = client.post("/api/admin/training/users/9999/reset")
    assert r.status_code == 404


def test_reset_is_idempotent(client):
    _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    r1 = client.post(f"/api/admin/training/users/{user_id}/reset")
    r2 = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r1.status_code == 200
    assert r2.status_code == 200


def test_reset_requires_admin(client):
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    # No admin bootstrap → user is not admin
    r = client.post(f"/api/admin/training/users/{user_id}/reset")
    assert r.status_code == 404  # existence-hide
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_training_admin_reset.py -v`
Expected: FAIL — 404 for unknown route.

- [ ] **Step 3: Add `reset_user_training` in `backend/training/service.py`**

Append after the existing `finalize_if_complete`:

```python
def reset_user_training(
    db: sqlite3.Connection, *, user_id: int, admin_id: int
) -> bool:
    """Soft reset: delete training_attempts rows, flip has_passed_training=0,
    create training_reset notification, write admin audit row.

    Returns True if user existed (operation completed), False if user not found.
    Idempotent: running on an already-reset user is a no-op success.

    Per-step fault isolation pattern from Paket 9: notification + audit
    failures are logged and swallowed; the core state change (DELETE +
    UPDATE) is the source of truth.
    """
    user_row = db.execute(
        "SELECT id, username FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if user_row is None:
        return False

    db.execute("DELETE FROM training_attempts WHERE user_id=?", (user_id,))
    db.execute("UPDATE users SET has_passed_training=0 WHERE id=?", (user_id,))

    try:
        from backend.notifications import service as notif_service
        notif_service.create(
            db,
            user_id=user_id,
            kind="training_reset",
            title="Eğitiminiz sıfırlandı",
            body="Bir admin eğitim ilerlemenizi sıfırladı. Yeniden başlayabilirsiniz.",
            data={"admin_id": admin_id},
        )
    except Exception:
        log.exception("create training_reset notification failed for user_id=%s", user_id)

    try:
        from backend.shared import audit
        audit.log_admin_action(
            db, admin_user_id=admin_id, action_type="reset_training",
            target_kind="user", target_id=str(user_id),
            metadata={"username": user_row["username"]},
        )
    except Exception:
        log.exception("log_admin_action reset_training failed for user_id=%s", user_id)

    return True
```

- [ ] **Step 4: Update imports + add admin_router in `backend/training/routes.py`**

The training_router prefix is `/api/training` (used by the public 3 endpoints). For admin endpoints we want `/api/admin/training/...` per spec — that needs a separate sub-router. Update the imports and add the new router declaration at the top.

**Replace the existing import block at the top of `backend/training/routes.py`:**

```python
from backend.training.models import (
    StartResponse, QuizSubmitRequest, QuizSubmitResponse,
    AnnotateSubmitRequest, AnnotateSubmitResponse,
    OkResponse,
)
from backend.users.deps import get_db, require_seen_manual, require_admin
```

**Add the admin_router below the existing `router = APIRouter(...)` line:**

```python
router = APIRouter(prefix="/api/training", tags=["training"])
admin_router = APIRouter(prefix="/api/admin/training", tags=["admin-training"])
```

**Append at the bottom of the file:**

```python
@admin_router.post("/users/{user_id}/reset", response_model=OkResponse)
def admin_reset_user_training(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Admin endpoint — soft reset of a user's training. Clears attempts,
    sets has_passed_training=0, creates training_reset notification,
    writes audit row. Idempotent."""
    ok = service.reset_user_training(
        db, user_id=user_id, admin_id=admin["id"],
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"user {user_id} not found")
    return {"ok": True}
```

**Mount `admin_router` in `backend/main.py`.** Find the line that mounts training routes and update it (split the import + add a second include):

Before:
```python
from backend.training.routes import router as training_router
# ...
app.include_router(training_router)
```

After:
```python
from backend.training.routes import router as training_router, admin_router as training_admin_router
# ...
app.include_router(training_router)
app.include_router(training_admin_router)
```

Confirm `OkResponse` already exists in `backend/training/models.py` (it does — at line 46, used by the existing public endpoints).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_training_admin_reset.py -v`
Expected: 6 PASS.

- [ ] **Step 6: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 471 prior + 6 new = 477 PASS.

- [ ] **Step 7: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/training/service.py backend/training/routes.py backend/main.py tests/test_training_admin_reset.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket11): admin training reset endpoint

POST /api/admin/training/users/{user_id}/reset — soft reset clears
training_attempts and sets has_passed_training=0. Per-step fault isolation
on notification + audit writes. Idempotent.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Locks Force-Release Endpoint + SSE `reason` Field

**Goal:** `POST /api/locks/{document_id}/admin/force-release`. Adds `reason` field to all 3 `lock_released` SSE publishes (`user_release`, `sweep_expired`, `admin_force`). Updates existing tests asserting on `lock_released` payload shape.

**Files:**
- Modify: `backend/locks/routes.py` (add force-release; add `reason` to existing publish)
- Modify: `backend/locks/sweep.py` (add `reason='sweep_expired'`)
- Create: `tests/test_locks_admin_force_release.py`
- Modify: `tests/test_locks_routes.py` (assert reason on existing test)
- Modify: `tests/test_locks_sweep.py` (assert reason on existing test)

- [ ] **Step 1: Find existing lock_released test assertions to update**

Run: `grep -rn "lock_released" tests/`
Expected: at minimum `tests/test_locks_routes.py` and `tests/test_locks_sweep.py`. Note line numbers for Step 7.

- [ ] **Step 2: Write `tests/test_locks_admin_force_release.py`**

(Copy the `_bootstrap_admin` + `_seen_manual_user` helpers from the "Test Helpers" section above into the top of this file.)

```python
"""Admin force-release endpoint + SSE reason='admin_force' field."""


def test_force_release_deletes_lock(client):
    admin_id = _bootstrap_admin(client)
    other_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")

    # bursiyer1 acquires a lock first
    client.post("/api/auth/login", json={"username": "bursiyer1", "password": "test123"})
    client.post("/api/locks/doc-A/acquire")

    # Switch back to admin via login
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})
    r = client.post("/api/locks/doc-A/admin/force-release")
    assert r.status_code == 200

    # Lock row is gone
    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute("SELECT * FROM document_locks WHERE document_id='doc-A'").fetchone()
    assert row is None
    db.close()


def test_force_release_writes_audit(client):
    admin_id = _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")

    client.post("/api/auth/login", json={"username": "bursiyer1", "password": "test123"})
    client.post("/api/locks/doc-B/acquire")
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    client.post("/api/locks/doc-B/admin/force-release")

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='lock_force_release' AND target_id='doc-B'"
    ).fetchone()
    assert row is not None
    assert row["admin_user_id"] == admin_id
    db.close()


def test_force_release_no_lock_returns_404(client):
    _bootstrap_admin(client)
    r = client.post("/api/locks/doc-doesnotexist/admin/force-release")
    assert r.status_code == 404


def test_force_release_publishes_lock_released_with_reason(client):
    """Direct SSE event capture by patching the broker."""
    admin_id = _bootstrap_admin(client)
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")

    client.post("/api/auth/login", json={"username": "bursiyer1", "password": "test123"})
    client.post("/api/locks/doc-C/acquire")
    client.post("/api/auth/login", json={"username": "root", "password": "rootpass1"})

    captured = []

    from backend.shared.sse import broker as sse_broker

    orig_publish = sse_broker.publish_broadcast

    async def capture(event_type: str, data: dict):
        captured.append((event_type, data))
        await orig_publish(event_type, data)

    sse_broker.publish_broadcast = capture
    try:
        r = client.post("/api/locks/doc-C/admin/force-release")
        assert r.status_code == 200
    finally:
        sse_broker.publish_broadcast = orig_publish

    released = [(t, d) for t, d in captured if t == "lock_released"]
    assert len(released) == 1
    assert released[0][1]["reason"] == "admin_force"
    assert released[0][1]["document_id"] == "doc-C"


def test_force_release_requires_admin(client):
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    # bursiyer1 is logged in (not admin)
    r = client.post("/api/locks/doc-X/admin/force-release")
    assert r.status_code == 404  # existence-hide


def test_user_release_publishes_reason_user_release(client):
    """Regression: existing user-driven release now carries reason='user_release'."""
    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    client.post("/api/locks/doc-D/acquire")

    captured = []
    from backend.shared.sse import broker as sse_broker
    orig_publish = sse_broker.publish_broadcast

    async def capture(event_type, data):
        captured.append((event_type, data))
        await orig_publish(event_type, data)

    sse_broker.publish_broadcast = capture
    try:
        r = client.post("/api/locks/doc-D/release")
        assert r.status_code == 200
    finally:
        sse_broker.publish_broadcast = orig_publish

    released = [(t, d) for t, d in captured if t == "lock_released"]
    assert len(released) == 1
    assert released[0][1]["reason"] == "user_release"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_locks_admin_force_release.py -v`
Expected: FAIL — 404 for unknown route + assertion failures on `reason` key (because user-release publish doesn't include it yet).

- [ ] **Step 4: Add force-release route in `backend/locks/routes.py`**

```python
# At top of file, ensure import exists:
from backend.users.deps import get_db, require_passed_training, require_admin
from backend.shared import audit


# At bottom of file, add:
@router.post("/{document_id}/admin/force-release", response_model=OkResponse)
async def admin_force_release(
    document_id: str,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    """Admin override — unconditional release. 404 if no lock currently held.
    Broadcasts lock_released with reason='admin_force'. Writes admin audit."""
    held = service.get_lock(db, document_id)
    if held is None:
        raise HTTPException(status_code=404, detail=f"no lock on {document_id}")

    prior_user_id = held["user_id"]
    service.force_release(db, document_id=document_id)

    try:
        await sse_broker.publish_broadcast(
            "lock_released",
            {
                "document_id": document_id,
                "by_user_id": prior_user_id,
                "reason": "admin_force",
            },
        )
    except Exception:
        log.exception("publish lock_released admin_force failed for %s", document_id)

    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="lock_force_release",
            target_kind="document", target_id=document_id,
            metadata={"prior_holder_user_id": prior_user_id},
        )
    except Exception:
        log.exception("log_admin_action lock_force_release failed for %s", document_id)

    return {"ok": True}
```

- [ ] **Step 5: Add `reason='user_release'` to the existing release publish in `backend/locks/routes.py`**

Update the existing `release()` handler payload (around line 100):

```python
        try:
            await sse_broker.publish_broadcast(
                "lock_released",
                {
                    "document_id": document_id,
                    "by_user_id": holder_user_id,
                    "reason": "user_release",
                },
            )
        except Exception:
            log.exception("publish lock_released failed for %s", document_id)
```

- [ ] **Step 6: Add `reason='sweep_expired'` to the sweep publish in `backend/locks/sweep.py`**

Update the existing publish call (around line 35):

```python
        try:
            await sse_broker.publish_broadcast(
                "lock_released",
                {
                    "document_id": document_id,
                    "by_user_id": None,
                    "reason": "sweep_expired",
                },
            )
        except Exception:
            log.exception("publish lock_released failed for %s", document_id)
```

- [ ] **Step 7: Update existing tests asserting on `lock_released` payload**

Search and update:

Run: `grep -rn "lock_released" tests/test_locks_routes.py tests/test_locks_sweep.py tests/test_sse_routes.py 2>&1`

For each test that captures or asserts on the `lock_released` event, add the appropriate `reason` field assertion:
- If the test triggers `release()` → assert `reason == "user_release"`
- If the test triggers `sweep_expired()` → assert `reason == "sweep_expired"`

If a test asserts payload equality (e.g. `assert data == {"document_id": ..., "by_user_id": ...}`), update to include the new `reason` field. Tests that ignore the payload (only check event_type) need no change.

- [ ] **Step 8: Run target tests + full suite**

Run: `.venv/bin/python -m pytest tests/test_locks_admin_force_release.py tests/test_locks_routes.py tests/test_locks_sweep.py -v`
Expected: all PASS (target file 6/6 + existing tests with updated assertions).

Run: `.venv/bin/python -m pytest -x -q`
Expected: 477 prior + 6 new = 483 PASS (some existing tests updated in place; test count unchanged for them).

- [ ] **Step 9: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/locks/routes.py backend/locks/sweep.py tests/test_locks_admin_force_release.py tests/test_locks_routes.py tests/test_locks_sweep.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket11): admin lock force-release endpoint + SSE reason field

POST /api/locks/{id}/admin/force-release — unconditional release with
admin audit. lock_released event payload gains a `reason` field at all
three publish sites: user_release, sweep_expired, admin_force.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Gold-Doc Admin CRUD Endpoints

**Goal:** `GET/PUT/DELETE /api/admin/training/gold-docs[/{gold_id}]`. Service helpers `upsert_gold_doc_override` + `soft_delete_gold_doc`. All write ops audit-logged.

**Files:**
- Modify: `backend/training/service.py` (add upsert + soft-delete)
- Modify: `backend/training/models.py` (add request schemas)
- Modify: `backend/training/routes.py` (add 3 endpoints to `admin_router`)
- Create: `tests/test_training_admin_gold_docs.py`

- [ ] **Step 1: Write `tests/test_training_admin_gold_docs.py`**

(Copy the `_bootstrap_admin` + `_seen_manual_user` helpers from the "Test Helpers" section above into the top of this file.)

```python
"""Admin gold-doc CRUD: list, upsert (override + custom), tombstone."""


def test_list_gold_docs_returns_resolved_and_overrides(client):
    _bootstrap_admin(client)
    r = client.get("/api/admin/training/gold-docs")
    assert r.status_code == 200
    body = r.json()
    assert "resolved" in body
    assert "overrides" in body
    # Baseline has 3 placeholder docs; no overrides yet
    assert len(body["resolved"]) == 3
    assert body["overrides"] == []


def test_upsert_baseline_id_writes_source_override(client):
    admin_id = _bootstrap_admin(client)
    payload = {
        "content": "Modified placeholder content",
        "expected_concepts": [{"kanun_no": "5520", "madde": "5"}],
        "min_concept_count": 1,
    }
    r = client.put("/api/admin/training/gold-docs/sample_kvk_5", json=payload)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM training_gold_doc_overrides WHERE gold_id='sample_kvk_5'"
    ).fetchone()
    assert row is not None
    assert row["source"] == "override"
    assert row["is_deleted"] == 0
    assert row["created_by_admin_id"] == admin_id
    db.close()


def test_upsert_new_id_writes_source_custom(client):
    admin_id = _bootstrap_admin(client)
    payload = {
        "content": "Yeni özelge metni",
        "expected_concepts": [{"kanun_no": "193", "madde": "37"}],
        "min_concept_count": 1,
    }
    r = client.put("/api/admin/training/gold-docs/my_new_gold_001", json=payload)
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM training_gold_doc_overrides WHERE gold_id='my_new_gold_001'"
    ).fetchone()
    assert row["source"] == "custom"
    db.close()


def test_delete_writes_tombstone(client):
    _bootstrap_admin(client)
    r = client.delete("/api/admin/training/gold-docs/sample_kvk_5")
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM training_gold_doc_overrides WHERE gold_id='sample_kvk_5'"
    ).fetchone()
    assert row["is_deleted"] == 1
    db.close()

    # Resolver should now exclude it
    r = client.get("/api/admin/training/gold-docs")
    resolved_ids = [d["gold_id"] for d in r.json()["resolved"]]
    assert "sample_kvk_5" not in resolved_ids


def test_upsert_writes_audit_row(client):
    admin_id = _bootstrap_admin(client)
    client.put(
        "/api/admin/training/gold-docs/x_new",
        json={"content": "X", "expected_concepts": [], "min_concept_count": 0},
    )

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='upsert_gold_doc' AND target_id='x_new'"
    ).fetchone()
    assert row is not None
    db.close()


def test_delete_writes_audit_row(client):
    admin_id = _bootstrap_admin(client)
    client.delete("/api/admin/training/gold-docs/sample_kvk_5")

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='delete_gold_doc' AND target_id='sample_kvk_5'"
    ).fetchone()
    assert row is not None
    db.close()


def test_endpoints_require_admin(client):
    _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    r = client.get("/api/admin/training/gold-docs")
    assert r.status_code == 404
    r = client.put("/api/admin/training/gold-docs/x", json={"content": "", "expected_concepts": [], "min_concept_count": 0})
    assert r.status_code == 404
    r = client.delete("/api/admin/training/gold-docs/x")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_training_admin_gold_docs.py -v`
Expected: FAIL — routes don't exist.

- [ ] **Step 3: Add Pydantic models in `backend/training/models.py`**

```python
# At bottom of file:

class ConceptInput(BaseModel):
    kanun_no: str
    kanun_ad: str | None = None
    madde: str | None = None
    fikra: str | None = None
    bent: str | None = None


class GoldDocUpsertRequest(BaseModel):
    content: str
    expected_concepts: list[ConceptInput]
    min_concept_count: int


class GoldDocsListResponse(BaseModel):
    resolved: list[dict]
    overrides: list[dict]
```

- [ ] **Step 4: Add service helpers in `backend/training/service.py`**

```python
# Add at bottom:

def upsert_gold_doc_override(
    db: sqlite3.Connection, *, gold_id: str, content: str,
    expected_concepts: list[dict], min_concept_count: int, admin_id: int,
) -> None:
    """Upsert a gold-doc override row. source='override' if gold_id exists in
    code baseline, else 'custom'."""
    baseline_ids = {d["gold_id"] for d in code_gold.GOLD_DOCS}
    source = "override" if gold_id in baseline_ids else "custom"
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT OR REPLACE INTO training_gold_doc_overrides(
            gold_id, is_deleted, content, expected_concepts,
            min_concept_count, source, created_by_admin_id,
            created_at, updated_at
        ) VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gold_id, content, json.dumps(expected_concepts),
            min_concept_count, source, admin_id, now, now,
        ),
    )


def soft_delete_gold_doc(
    db: sqlite3.Connection, *, gold_id: str, admin_id: int,
) -> None:
    """Tombstone via is_deleted=1. Idempotent."""
    baseline_ids = {d["gold_id"] for d in code_gold.GOLD_DOCS}
    source = "override" if gold_id in baseline_ids else "custom"
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT OR REPLACE INTO training_gold_doc_overrides(
            gold_id, is_deleted, content, expected_concepts,
            min_concept_count, source, created_by_admin_id,
            created_at, updated_at
        ) VALUES (?, 1, NULL, NULL, NULL, ?, ?, ?, ?)
        """,
        (gold_id, source, admin_id, now, now),
    )
```

Ensure `from datetime import datetime, timezone` is imported at the top of service.py (already imported in Paket 10).

- [ ] **Step 5: Add 3 routes to `admin_router` in `backend/training/routes.py`**

```python
from backend.training.models import (
    StartResponse, QuizSubmitRequest, QuizSubmitResponse,
    AnnotateSubmitRequest, AnnotateSubmitResponse,
    OkResponse,
    GoldDocUpsertRequest, GoldDocsListResponse,  # NEW
)
from backend.shared import audit


@admin_router.get("/gold-docs", response_model=GoldDocsListResponse)
def admin_list_gold_docs(
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    resolved = service.get_active_gold_docs(db)
    rows = db.execute(
        "SELECT gold_id, is_deleted, content, expected_concepts, "
        "min_concept_count, source, created_by_admin_id, created_at, updated_at "
        "FROM training_gold_doc_overrides ORDER BY gold_id"
    ).fetchall()
    overrides = [dict(r) for r in rows]
    return {"resolved": resolved, "overrides": overrides}


@admin_router.put("/gold-docs/{gold_id}", response_model=OkResponse)
def admin_upsert_gold_doc(
    gold_id: str,
    payload: GoldDocUpsertRequest,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    concepts = [c.model_dump(exclude_none=False) for c in payload.expected_concepts]
    service.upsert_gold_doc_override(
        db, gold_id=gold_id, content=payload.content,
        expected_concepts=concepts,
        min_concept_count=payload.min_concept_count,
        admin_id=admin["id"],
    )
    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="upsert_gold_doc",
            target_kind="gold_doc", target_id=gold_id,
            metadata={"min_concept_count": payload.min_concept_count, "concept_count": len(concepts)},
        )
    except Exception:
        log.exception("audit upsert_gold_doc failed for %s", gold_id)
    return {"ok": True}


@admin_router.delete("/gold-docs/{gold_id}", response_model=OkResponse)
def admin_delete_gold_doc(
    gold_id: str,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    service.soft_delete_gold_doc(db, gold_id=gold_id, admin_id=admin["id"])
    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="delete_gold_doc",
            target_kind="gold_doc", target_id=gold_id,
        )
    except Exception:
        log.exception("audit delete_gold_doc failed for %s", gold_id)
    return {"ok": True}
```

Ensure `import logging` and `log = logging.getLogger(__name__)` exist at top of routes.py (add if missing).

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_training_admin_gold_docs.py -v`
Expected: 7 PASS.

- [ ] **Step 7: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 483 prior + 7 new = 490 PASS.

- [ ] **Step 8: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/training/service.py backend/training/models.py backend/training/routes.py tests/test_training_admin_gold_docs.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket11): admin gold-doc CRUD endpoints

GET/PUT/DELETE /api/admin/training/gold-docs[/{gold_id}] with audit
on every write. Source resolved from baseline membership: 'override'
for known IDs, 'custom' for new. Soft-delete via tombstone.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Quiz Admin CRUD + Resolver Migration in `start_attempt` / `submit_quiz`

**Goal:** Symmetric quiz CRUD; AND switch `start_attempt` and `submit_quiz` to `get_active_quiz_questions(db)` so admin overrides take effect immediately.

**Files:**
- Modify: `backend/training/service.py` (upsert_quiz_override + soft_delete_quiz_override; resolver migration in start_attempt + submit_quiz)
- Modify: `backend/training/models.py` (add `QuizUpsertRequest`, `QuizListResponse`)
- Modify: `backend/training/routes.py` (add 3 quiz CRUD routes)
- Create: `tests/test_training_admin_quiz.py`

- [ ] **Step 1: Audit existing test references to `QUIZ_QUESTIONS`**

Run: `grep -rn "QUIZ_QUESTIONS\|quiz_data\.QUIZ" tests/`
Expected: at most a few references — note the file:line for review in Step 7. The resolver migration may break those if they assume static `QUIZ_QUESTIONS` is the source of truth used at runtime. They should still pass because resolver returns baseline when no overrides exist.

- [ ] **Step 2: Write `tests/test_training_admin_quiz.py`**

(Copy the `_bootstrap_admin` + `_seen_manual_user` helpers from the "Test Helpers" section above into the top of this file.)

```python
"""Admin quiz CRUD + resolver integration in start_attempt."""


def test_list_quiz_returns_resolved_and_overrides(client):
    _bootstrap_admin(client)
    r = client.get("/api/admin/training/quiz")
    assert r.status_code == 200
    body = r.json()
    assert "resolved" in body
    assert "overrides" in body
    # Baseline has 8 placeholder questions
    assert len(body["resolved"]) == 8
    assert body["overrides"] == []


def test_upsert_baseline_id_writes_source_override(client):
    admin_id = _bootstrap_admin(client)
    payload = {
        "text": "Yeni soru?",
        "choices": ["A", "B", "C", "D"],
        "correct_choice_idx": 2,
    }
    r = client.put("/api/admin/training/quiz/q01", json=payload)
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM training_quiz_overrides WHERE question_id='q01'"
    ).fetchone()
    assert row["source"] == "override"
    assert row["text"] == "Yeni soru?"
    assert row["correct_choice_idx"] == 2
    db.close()


def test_upsert_new_id_writes_source_custom(client):
    _bootstrap_admin(client)
    r = client.put(
        "/api/admin/training/quiz/custom_q99",
        json={"text": "X", "choices": ["a", "b", "c", "d"], "correct_choice_idx": 0},
    )
    assert r.status_code == 200

    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT source FROM training_quiz_overrides WHERE question_id='custom_q99'"
    ).fetchone()
    assert row["source"] == "custom"
    db.close()


def test_delete_writes_tombstone(client):
    _bootstrap_admin(client)
    r = client.delete("/api/admin/training/quiz/q01")
    assert r.status_code == 200

    r = client.get("/api/admin/training/quiz")
    resolved_ids = [q["id"] for q in r.json()["resolved"]]
    assert "q01" not in resolved_ids


def test_start_attempt_uses_resolver_with_admin_override(client):
    """Regression — start_attempt now reads from resolver, not direct import."""
    admin_id = _bootstrap_admin(client)
    # Override q01 with new text
    client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "Override question text", "choices": ["A", "B", "C", "D"], "correct_choice_idx": 0},
    )

    user_id = _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    r = client.get("/api/training/start")
    assert r.status_code == 200
    questions = r.json()["quiz_questions"]
    # If q01 is among the 5 sampled, it should have the override text
    q01 = next((q for q in questions if q["id"] == "q01"), None)
    if q01 is not None:
        assert q01["text"] == "Override question text"


def test_quiz_endpoints_require_admin(client):
    _seen_manual_user(client, "bursiyer1", "INVITE-2026")
    assert client.get("/api/admin/training/quiz").status_code == 404
    assert client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "X", "choices": ["a", "b", "c", "d"], "correct_choice_idx": 0},
    ).status_code == 404
    assert client.delete("/api/admin/training/quiz/q01").status_code == 404


def test_upsert_writes_audit_row(client):
    _bootstrap_admin(client)
    client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "X", "choices": ["a", "b", "c", "d"], "correct_choice_idx": 0},
    )
    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    row = db.execute(
        "SELECT * FROM admin_audit_log WHERE action_type='upsert_quiz_question' AND target_id='q01'"
    ).fetchone()
    assert row is not None
    db.close()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_training_admin_quiz.py -v`
Expected: FAIL — routes don't exist.

- [ ] **Step 4: Add Pydantic models in `backend/training/models.py`**

```python
# At bottom:

class QuizUpsertRequest(BaseModel):
    text: str
    choices: list[str]
    correct_choice_idx: int


class QuizListResponse(BaseModel):
    resolved: list[dict]
    overrides: list[dict]
```

- [ ] **Step 5: Add service helpers in `backend/training/service.py`**

```python
def upsert_quiz_override(
    db: sqlite3.Connection, *, question_id: str, text: str,
    choices: list[str], correct_choice_idx: int, admin_id: int,
) -> None:
    """Upsert a quiz override row. source='override' if question_id is in
    code baseline (QUIZ_QUESTIONS), else 'custom'."""
    from backend.training.quiz_data import QUIZ_QUESTIONS
    baseline_ids = {q["id"] for q in QUIZ_QUESTIONS}
    source = "override" if question_id in baseline_ids else "custom"
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT OR REPLACE INTO training_quiz_overrides(
            question_id, is_deleted, text, choices_json, correct_choice_idx,
            source, created_by_admin_id, created_at, updated_at
        ) VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            question_id, text, json.dumps(choices), correct_choice_idx,
            source, admin_id, now, now,
        ),
    )


def soft_delete_quiz_override(
    db: sqlite3.Connection, *, question_id: str, admin_id: int,
) -> None:
    """Tombstone via is_deleted=1."""
    from backend.training.quiz_data import QUIZ_QUESTIONS
    baseline_ids = {q["id"] for q in QUIZ_QUESTIONS}
    source = "override" if question_id in baseline_ids else "custom"
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """
        INSERT OR REPLACE INTO training_quiz_overrides(
            question_id, is_deleted, text, choices_json, correct_choice_idx,
            source, created_by_admin_id, created_at, updated_at
        ) VALUES (?, 1, NULL, NULL, NULL, ?, ?, ?, ?)
        """,
        (question_id, source, admin_id, now, now),
    )
```

- [ ] **Step 6: Migrate `start_attempt` and `submit_quiz` to resolver**

In `backend/training/service.py`, find `start_attempt` and replace any direct reference to `QUIZ_QUESTIONS` with `get_active_quiz_questions(db)`:

```python
# At top of file, ensure import:
from backend.training.quiz_data import QUIZ_QUESTIONS, get_active_quiz_questions

# In start_attempt(), where the current code imports/uses QUIZ_QUESTIONS:
def start_attempt(db: sqlite3.Connection, *, user_id: int) -> dict:
    # ... existing checks (already_passed, lockout) ...

    # Insert the attempt row first (id is the seed)
    # ... existing INSERT ...

    # CHANGED: use resolver instead of static list
    quiz_pool = get_active_quiz_questions(db)
    rng = random.Random(attempt_id)
    quiz_sample = rng.sample(quiz_pool, k=min(5, len(quiz_pool)))

    # ... existing gold-doc selection unchanged (already uses get_active_gold_docs) ...

    # Strip correct_choice_idx before returning to user
    quiz_for_user = [
        {"id": q["id"], "text": q["text"], "choices": q["choices"]}
        for q in quiz_sample
    ]
    # ... return as before ...
```

In `submit_quiz`:

```python
def submit_quiz(...):
    # ... existing idempotency check ...
    quiz_pool = get_active_quiz_questions(db)
    rng = random.Random(attempt_id)
    quiz_sample = rng.sample(quiz_pool, k=min(5, len(quiz_pool)))
    # Use quiz_sample for scoring instead of static QUIZ_QUESTIONS
    # ... rest of scoring logic unchanged ...
```

**Tip:** Read the existing `start_attempt` and `submit_quiz` first to find exactly where `QUIZ_QUESTIONS` is referenced. The migration is mechanical; don't change scoring logic.

- [ ] **Step 7: Add 3 quiz CRUD routes to `admin_router` in `backend/training/routes.py`**

```python
from backend.training.models import (
    # existing imports ...
    QuizUpsertRequest, QuizListResponse,
)
from backend.training.quiz_data import get_active_quiz_questions


@admin_router.get("/quiz", response_model=QuizListResponse)
def admin_list_quiz(
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    resolved = get_active_quiz_questions(db)
    rows = db.execute(
        "SELECT question_id, is_deleted, text, choices_json, correct_choice_idx, "
        "source, created_by_admin_id, created_at, updated_at "
        "FROM training_quiz_overrides ORDER BY question_id"
    ).fetchall()
    overrides = [dict(r) for r in rows]
    return {"resolved": resolved, "overrides": overrides}


@admin_router.put("/quiz/{question_id}", response_model=OkResponse)
def admin_upsert_quiz(
    question_id: str,
    payload: QuizUpsertRequest,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    service.upsert_quiz_override(
        db, question_id=question_id, text=payload.text,
        choices=payload.choices, correct_choice_idx=payload.correct_choice_idx,
        admin_id=admin["id"],
    )
    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="upsert_quiz_question",
            target_kind="quiz_question", target_id=question_id,
        )
    except Exception:
        log.exception("audit upsert_quiz_question failed for %s", question_id)
    return {"ok": True}


@admin_router.delete("/quiz/{question_id}", response_model=OkResponse)
def admin_delete_quiz(
    question_id: str,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    service.soft_delete_quiz_override(db, question_id=question_id, admin_id=admin["id"])
    try:
        audit.log_admin_action(
            db, admin_user_id=admin["id"], action_type="delete_quiz_question",
            target_kind="quiz_question", target_id=question_id,
        )
    except Exception:
        log.exception("audit delete_quiz_question failed for %s", question_id)
    return {"ok": True}
```

- [ ] **Step 8: Run target tests + full suite**

Run: `.venv/bin/python -m pytest tests/test_training_admin_quiz.py tests/test_training_routes.py tests/test_training_pass_integration.py -v`
Expected: 7 new PASS + existing training tests still green.

Run: `.venv/bin/python -m pytest -x -q`
Expected: 490 prior + 7 new = 497 PASS.

- [ ] **Step 9: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/training/service.py backend/training/models.py backend/training/routes.py tests/test_training_admin_quiz.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket11): admin quiz CRUD + start_attempt resolver migration

GET/PUT/DELETE /api/admin/training/quiz[/{question_id}] symmetric with
gold-doc CRUD. start_attempt and submit_quiz now read from
get_active_quiz_questions(db) so admin overrides take effect on next attempt.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Audit-Log Pagination + Filters

**Goal:** Replace `users/routes.py:/admin/audit-log` with a paginated, filterable version mounted under `backend/admin/routes.py`. Update existing test (`test_admin_routes.py::test_admin_audit_log_endpoint_returns_actions`).

**Files:**
- Modify: `backend/users/routes.py` (REMOVE existing /admin/audit-log handler, lines ~231-252)
- Modify: `backend/users/service.py` (add `list_admin_audit`)
- Modify: `backend/admin/routes.py` (add new GET /audit-log)
- Modify: `tests/test_admin_routes.py` (update existing assertion)
- Create: `tests/test_admin_audit_log_filtered.py`

- [ ] **Step 1: Write `tests/test_admin_audit_log_filtered.py`**

(Copy the `_bootstrap_admin` helper from the "Test Helpers" section above into the top of this file.)

```python
"""Audit-log endpoint with pagination + filters."""
from datetime import datetime, timedelta, timezone


def test_audit_log_returns_paginated_shape(client):
    _bootstrap_admin(client)
    # Create some audit entries
    for i in range(5):
        client.post("/api/admin/invite/rotate", json={"new_code": f"CODE-{i}"})

    r = client.get("/api/admin/audit-log")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "has_more" in body
    assert isinstance(body["items"], list)
    assert isinstance(body["total"], int)
    assert isinstance(body["has_more"], bool)


def test_audit_log_default_limit_50(client):
    _bootstrap_admin(client)
    for i in range(60):
        client.post("/api/admin/invite/rotate", json={"new_code": f"CODE-{i}"})

    r = client.get("/api/admin/audit-log")
    body = r.json()
    assert len(body["items"]) == 50
    assert body["has_more"] is True


def test_audit_log_offset_and_limit(client):
    _bootstrap_admin(client)
    for i in range(10):
        client.post("/api/admin/invite/rotate", json={"new_code": f"CODE-{i}"})

    r = client.get("/api/admin/audit-log?limit=3&offset=2")
    body = r.json()
    assert len(body["items"]) == 3
    assert body["total"] >= 10
    assert body["has_more"] is True


def test_audit_log_max_limit_clamped_to_200(client):
    _bootstrap_admin(client)
    r = client.get("/api/admin/audit-log?limit=999")
    # Either 400 or clamps silently — pick clamp + ok per spec
    body = r.json()
    assert len(body["items"]) <= 200


def test_audit_log_filter_by_action(client):
    admin_id = _bootstrap_admin(client)
    client.post("/api/admin/invite/rotate", json={"new_code": "CODE-A"})
    # Bootstrap admin already wrote a promote_admin row

    r = client.get("/api/admin/audit-log?action=rotate_invite_code")
    body = r.json()
    assert all(item["action_type"] == "rotate_invite_code" for item in body["items"])


def test_audit_log_filter_by_admin_id(client):
    admin_id = _bootstrap_admin(client)
    client.post("/api/admin/invite/rotate", json={"new_code": "CODE-A"})

    r = client.get(f"/api/admin/audit-log?admin_id={admin_id}")
    body = r.json()
    assert all(item["admin_user_id"] == admin_id for item in body["items"])


def test_audit_log_filter_date_range(client):
    _bootstrap_admin(client)
    client.post("/api/admin/invite/rotate", json={"new_code": "TODAY-1"})

    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()

    r = client.get(f"/api/admin/audit-log?date_from={yesterday}&date_to={tomorrow}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1


def test_audit_log_requires_admin(client):
    r = client.get("/api/admin/audit-log")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_admin_audit_log_filtered.py -v`
Expected: FAIL — old endpoint returns `{events:...}` shape.

- [ ] **Step 3: Add `list_admin_audit` in `backend/users/service.py`**

```python
def list_admin_audit(
    db: sqlite3.Connection, *,
    limit: int, offset: int,
    admin_id: int | None = None,
    action: str | None = None,
    date_from: str | None = None,  # ISO date "2026-05-08"
    date_to: str | None = None,
) -> dict:
    """Paginated + filtered admin_audit_log query.
    Returns {items, total, has_more}."""
    where = []
    params: list = []
    if admin_id is not None:
        where.append("admin_user_id = ?")
        params.append(admin_id)
    if action is not None:
        where.append("action_type = ?")
        params.append(action)
    if date_from is not None:
        where.append("created_at >= ?")
        params.append(f"{date_from}T00:00:00+00:00")
    if date_to is not None:
        where.append("created_at <= ?")
        params.append(f"{date_to}T23:59:59+00:00")
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = db.execute(
        f"SELECT COUNT(*) AS c FROM admin_audit_log {where_clause}", params
    ).fetchone()["c"]

    rows = db.execute(
        f"""SELECT id, admin_user_id, action_type, target_kind, target_id,
                   metadata_json, created_at
            FROM admin_audit_log {where_clause}
            ORDER BY id DESC LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()

    items = [
        {
            "id": r["id"],
            "admin_user_id": r["admin_user_id"],
            "action_type": r["action_type"],
            "target_kind": r["target_kind"],
            "target_id": r["target_id"],
            "metadata": r["metadata_json"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": total,
        "has_more": offset + len(items) < total,
    }
```

- [ ] **Step 4: Add new audit-log route in `backend/admin/routes.py`**

```python
# At top — add imports if missing:
from typing import Optional
from fastapi import Query
from backend.users import service as users_service


@router.get("/audit-log")
def admin_audit_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_id: Optional[int] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    """Paginated + filtered admin audit log."""
    return users_service.list_admin_audit(
        db, limit=limit, offset=offset,
        admin_id=admin_id, action=action,
        date_from=date_from, date_to=date_to,
    )
```

- [ ] **Step 5: Remove old handler from `backend/users/routes.py`**

Delete the lines in `backend/users/routes.py` (around lines 231-252) covering the old `@router.get("/admin/audit-log")` handler. The new one in admin/routes.py replaces it.

- [ ] **Step 6: Update existing test `tests/test_admin_routes.py::test_admin_audit_log_endpoint_returns_actions`**

Find:

```python
def test_admin_audit_log_endpoint_returns_actions(client):
    _bootstrap_admin(client)
    client.post("/api/admin/invite/rotate", json={"new_code": "X-2026"})
    r = client.get("/api/admin/audit-log")
    assert r.status_code == 200
    body = r.json()
    assert any(e["action_type"] == "rotate_invite_code" for e in body["events"])
```

Replace with:

```python
def test_admin_audit_log_endpoint_returns_actions(client):
    _bootstrap_admin(client)
    client.post("/api/admin/invite/rotate", json={"new_code": "X-2026"})
    r = client.get("/api/admin/audit-log")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "has_more" in body
    assert any(e["action_type"] == "rotate_invite_code" for e in body["items"])
```

- [ ] **Step 7: Run target tests + full suite**

Run: `.venv/bin/python -m pytest tests/test_admin_audit_log_filtered.py tests/test_admin_routes.py -v`
Expected: 8 new + 1 updated = 9 PASS.

Run: `.venv/bin/python -m pytest -x -q`
Expected: 497 prior + 8 new = 505 PASS.

- [ ] **Step 8: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/users/routes.py backend/users/service.py backend/admin/routes.py tests/test_admin_audit_log_filtered.py tests/test_admin_routes.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket11): audit-log pagination + filters

GET /api/admin/audit-log moves from users/ to admin/ router with
{items,total,has_more} shape. Filter set: admin_id, action, date_from,
date_to. Updates the one existing test asserting on body['events'].

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: System-Events Viewer

**Goal:** `GET /api/admin/system-events` — paginated + filtered (event_type, severity, date_from, date_to).

**Files:**
- Create: `backend/admin/service.py`
- Modify: `backend/admin/routes.py` (add system-events GET)
- Create: `tests/test_admin_system_events.py`

- [ ] **Step 1: Write `tests/test_admin_system_events.py`**

(Copy the `_bootstrap_admin` helper from the "Test Helpers" section above into the top of this file.)

```python
"""GET /api/admin/system-events — pagination + filters."""
from datetime import datetime, timezone


def _seed_event(client, event_type: str, severity: str = "info", message: str = "test"):
    from backend.shared.db import connect
    from backend.config import DB_PATH
    db = connect(DB_PATH)
    db.execute(
        "INSERT INTO system_events(event_type, severity, message, created_at) "
        "VALUES (?, ?, ?, ?)",
        (event_type, severity, message, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    db.close()


def test_system_events_returns_paginated_shape(client):
    _bootstrap_admin(client)
    for i in range(5):
        _seed_event(client, f"event_{i}", "info")

    r = client.get("/api/admin/system-events")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "has_more" in body


def test_filter_by_event_type(client):
    _bootstrap_admin(client)
    _seed_event(client, "training_pass", "info")
    _seed_event(client, "lock_force_release", "warn")

    r = client.get("/api/admin/system-events?event_type=training_pass")
    body = r.json()
    assert all(item["event_type"] == "training_pass" for item in body["items"])


def test_filter_by_severity(client):
    _bootstrap_admin(client)
    _seed_event(client, "ev_a", "info")
    _seed_event(client, "ev_b", "warn")
    _seed_event(client, "ev_c", "error")

    r = client.get("/api/admin/system-events?severity=error")
    body = r.json()
    assert all(item["severity"] == "error" for item in body["items"])


def test_default_limit_50(client):
    _bootstrap_admin(client)
    for i in range(60):
        _seed_event(client, f"e_{i}")

    r = client.get("/api/admin/system-events")
    body = r.json()
    assert len(body["items"]) == 50
    assert body["has_more"] is True


def test_system_events_requires_admin(client):
    r = client.get("/api/admin/system-events")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_admin_system_events.py -v`
Expected: FAIL — route doesn't exist.

- [ ] **Step 3: Create `backend/admin/service.py`**

```python
"""Admin-side service helpers for cross-cutting features."""
import sqlite3


def list_system_events(
    db: sqlite3.Connection, *,
    limit: int, offset: int,
    event_type: str | None = None,
    severity: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Paginated + filtered system_events query.
    Returns {items, total, has_more}."""
    where = []
    params: list = []
    if event_type is not None:
        where.append("event_type = ?")
        params.append(event_type)
    if severity is not None:
        where.append("severity = ?")
        params.append(severity)
    if date_from is not None:
        where.append("created_at >= ?")
        params.append(f"{date_from}T00:00:00+00:00")
    if date_to is not None:
        where.append("created_at <= ?")
        params.append(f"{date_to}T23:59:59+00:00")
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = db.execute(
        f"SELECT COUNT(*) AS c FROM system_events {where_clause}", params
    ).fetchone()["c"]

    rows = db.execute(
        f"""SELECT id, event_type, severity, message, extra_json, created_at
            FROM system_events {where_clause}
            ORDER BY id DESC LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()

    items = [
        {
            "id": r["id"],
            "event_type": r["event_type"],
            "severity": r["severity"],
            "message": r["message"],
            "extra": r["extra_json"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": total,
        "has_more": offset + len(items) < total,
    }
```

- [ ] **Step 4: Add system-events route in `backend/admin/routes.py`**

```python
from backend.admin import service as admin_service


@router.get("/system-events")
def admin_system_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    """Paginated + filtered system events log."""
    return admin_service.list_system_events(
        db, limit=limit, offset=offset,
        event_type=event_type, severity=severity,
        date_from=date_from, date_to=date_to,
    )
```

- [ ] **Step 5: Run tests + full suite**

Run: `.venv/bin/python -m pytest tests/test_admin_system_events.py -v`
Expected: 5 PASS.

Run: `.venv/bin/python -m pytest -x -q`
Expected: 505 prior + 5 new = 510 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/admin/service.py backend/admin/routes.py tests/test_admin_system_events.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(paket11): admin system-events viewer

GET /api/admin/system-events — paginated + filterable view of the
system_events table. Filter set: event_type, severity, date_from/to.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Polish + Tag

**Goal:** Cleanup pass; ensure dead imports removed, full suite green, tag the paket.

- [ ] **Step 1: Run full suite, check expected count**

Run: `.venv/bin/python -m pytest -q`
Expected: 510 PASS (461 baseline + 49 new = 510).

- [ ] **Step 2: Run pyright (cosmetic, but flag any real type errors)**

Run: `.venv/bin/python -m pyright backend/ 2>&1 | grep -E "error" | head -30`
Expected: no errors beyond pre-existing import-resolution warnings.

- [ ] **Step 3: Quick dead-import scan**

Run: `grep -rn "^import\|^from " backend/admin/ backend/training/ backend/locks/ | head -50`
Look for: imports that this paket added but no longer references after the route reorg (e.g. if `audit` is imported but unused after removing the old handler in users/routes.py).

If found, remove with a small follow-up commit.

- [ ] **Step 4: Read your own diff**

Run: `git log --oneline paket-10-training-gate..HEAD`
Confirm: 8 commits (Tasks 1-8), each focused; messages match conventions.

Run: `git diff paket-10-training-gate..HEAD --stat`
Expected: ~12-15 files changed; net ~+1500 lines (test + impl).

- [ ] **Step 5: Polish commit (if anything found in step 3)**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add <files>
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
chore(paket11): polish — dead imports, pyright cleanup

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Tag the paket**

```bash
git tag paket-11-admin-panel
```

- [ ] **Step 7: Final summary**

Run: `git log --oneline paket-10-training-gate..paket-11-admin-panel`
Expected: a clean linear sequence of feat/chore commits, all signed-off by Co-Authored-By footer.

---

## Verification Checklist (post-completion)

- [ ] All 9 tasks committed with the prescribed messages
- [ ] `paket-11-admin-panel` tag created
- [ ] `.venv/bin/python -m pytest -q` reports 510 PASS, 0 FAIL
- [ ] `DATA_DIR=/tmp/p11-fresh .venv/bin/python -m backend.cli migrate` applies v0001 + v0002 cleanly on a fresh data dir
- [ ] Manual curl walkthrough (admin user → each new endpoint → spot-check `admin_audit_log` rows). See spec §"Verification" for command list.
- [ ] No regressions in Paket 7 SSE tests (`lock_released` payload now carries `reason`)
- [ ] No regressions in Paket 10 training tests (`start_attempt` now uses resolver but baseline is unchanged so behavior is identical)
