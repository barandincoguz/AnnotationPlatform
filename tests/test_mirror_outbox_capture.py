"""End-to-end capture tests for the Phase 4 outbox triggers (Task 5).

Asserts that committed writes against project tables produce exactly one
`_outbox` row each, with the correct shape (table_name, op, pk_value,
payload_json, delivered_at=NULL, retry_count=0).

Phase 4 Task 13 will append the FastAPI end-to-end smoke test to this file;
Phase 4 Task 7 / Task 8 (config defaults / dispatcher unit) also reuse the
fresh-conn fixture pattern below.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


def _migrated_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    apply_migrations(conn, discover_migrations())
    return conn


def _seed_user(conn: sqlite3.Connection, **overrides) -> int:
    """Insert a minimal users row; returns the new id."""
    fields = {
        "username": "u1",
        "email": None,
        "password_hash": "x",
        "role": "user",
        "is_active": 1,
        "has_passed_training": 0,
        "has_seen_manual": 0,
        "avatar_color": None,
        "created_at": "2026-05-18T00:00:00Z",
        "updated_at": "2026-05-18T00:00:00Z",
    }
    fields.update(overrides)
    cur = conn.execute(
        "INSERT INTO users(username, email, password_hash, role, is_active, "
        "has_passed_training, has_seen_manual, avatar_color, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        tuple(fields[k] for k in (
            "username", "email", "password_hash", "role", "is_active",
            "has_passed_training", "has_seen_manual", "avatar_color",
            "created_at", "updated_at",
        )),
    )
    return cur.lastrowid


# === Task 5: end-to-end trigger capture ===


def test_66_triggers_installed_after_migrations():
    conn = _migrated_conn()
    row = conn.execute(
        "SELECT count(*) AS c FROM sqlite_master "
        "WHERE type='trigger' AND name LIKE '_outbox_%'"
    ).fetchone()
    assert row["c"] == 66
    conn.close()


def test_insert_users_writes_one_outbox_row():
    conn = _migrated_conn()
    user_id = _seed_user(conn, username="alice")
    rows = conn.execute(
        "SELECT * FROM _outbox WHERE table_name='users'"
    ).fetchall()
    assert len(rows) == 1, f"expected exactly 1 outbox row, got {len(rows)}"
    row = rows[0]
    assert row["op"] == "INSERT"
    assert row["pk_value"] == str(user_id)
    assert row["delivered_at"] is None
    assert row["retry_count"] == 0
    payload = json.loads(row["payload_json"])
    assert payload["id"] == user_id
    assert payload["username"] == "alice"
    # Every users column is represented in the payload
    for col in ("password_hash", "role", "is_active", "created_at"):
        assert col in payload
    conn.close()


def test_update_users_writes_outbox_update_row():
    conn = _migrated_conn()
    user_id = _seed_user(conn, username="bob")
    # Clear the INSERT outbox row for isolation.
    conn.execute("DELETE FROM _outbox")
    conn.execute("UPDATE users SET role='admin' WHERE id=?", (user_id,))
    rows = conn.execute("SELECT * FROM _outbox WHERE table_name='users'").fetchall()
    assert len(rows) == 1
    assert rows[0]["op"] == "UPDATE"
    assert rows[0]["pk_value"] == str(user_id)
    payload = json.loads(rows[0]["payload_json"])
    assert payload["role"] == "admin"
    conn.close()


def test_delete_users_writes_outbox_delete_row():
    conn = _migrated_conn()
    user_id = _seed_user(conn, username="carol")
    conn.execute("DELETE FROM _outbox")
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    rows = conn.execute("SELECT * FROM _outbox WHERE table_name='users'").fetchall()
    assert len(rows) == 1
    assert rows[0]["op"] == "DELETE"
    assert rows[0]["pk_value"] == str(user_id)
    # DELETE payload captures the OLD row.
    payload = json.loads(rows[0]["payload_json"])
    assert payload["username"] == "carol"
    conn.close()


def test_composite_pk_capture_for_drafts():
    """`drafts (document_id, user_id)` → pk_value = '<doc_id>::<user_id>'."""
    conn = _migrated_conn()
    # Seed parent rows first (FK constraint).
    user_id = _seed_user(conn, username="dave")
    conn.execute(
        "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
        "sentence_count, text_density, estimated_difficulty, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ("doc-A", "/tmp/a.json", "pdf body", 2, 1, 0.5, "Kolay", "2026-05-18T00:00:00Z"),
    )
    conn.execute("DELETE FROM _outbox")
    conn.execute(
        "INSERT INTO drafts(document_id, user_id, references_json, updated_at) "
        "VALUES (?,?,?,?)",
        ("doc-A", user_id, "[]", "2026-05-18T00:00:00Z"),
    )
    rows = conn.execute("SELECT * FROM _outbox WHERE table_name='drafts'").fetchall()
    assert len(rows) == 1
    assert rows[0]["pk_value"] == f"doc-A::{user_id}", rows[0]["pk_value"]
    conn.close()


def test_migration_v0006_is_idempotent():
    """Re-running v0006 against an already-installed DB does not raise."""
    from backend.migrations.v0006_install_outbox_triggers import up as v0006_up
    conn = _migrated_conn()
    v0006_up(conn)
    v0006_up(conn)
    row = conn.execute(
        "SELECT count(*) AS c FROM sqlite_master "
        "WHERE type='trigger' AND name LIKE '_outbox_%'"
    ).fetchone()
    assert row["c"] == 66
    conn.close()


def test_user_sessions_never_write_bearer_tokens_to_outbox():
    conn = _migrated_conn()
    user_id = _seed_user(conn, username="session-owner")
    conn.execute("DELETE FROM _outbox")
    conn.execute(
        "INSERT INTO user_sessions("
        "user_id, session_token, started_at, last_activity_at"
        ") VALUES (?, ?, ?, ?)",
        (user_id, "plaintext-bearer-token", "2026-05-18T00:00:00Z", "2026-05-18T00:00:00Z"),
    )
    conn.execute(
        "UPDATE user_sessions SET last_activity_at=? WHERE session_token=?",
        ("2026-05-18T00:01:00Z", "plaintext-bearer-token"),
    )
    conn.execute(
        "DELETE FROM user_sessions WHERE session_token=?",
        ("plaintext-bearer-token",),
    )
    leaked = conn.execute(
        "SELECT COUNT(*) AS c FROM _outbox WHERE table_name='user_sessions'"
    ).fetchone()["c"]
    assert leaked == 0
    conn.close()


def test_activity_event_outbox_payload_does_not_export_session_id():
    conn = _migrated_conn()
    user_id = _seed_user(conn, username="activity-owner")
    session_id = conn.execute(
        "INSERT INTO user_sessions("
        "user_id, session_token, started_at, last_activity_at"
        ") VALUES (?, ?, ?, ?)",
        (user_id, "local-only", "2026-05-18T00:00:00Z", "2026-05-18T00:00:00Z"),
    ).lastrowid
    conn.execute("DELETE FROM _outbox")
    conn.execute(
        "INSERT INTO activity_events("
        "user_id, session_id, event_type, created_at"
        ") VALUES (?, ?, 'login', ?)",
        (user_id, session_id, "2026-05-18T00:00:00Z"),
    )

    row = conn.execute(
        "SELECT payload_json FROM _outbox WHERE table_name='activity_events'"
    ).fetchone()
    assert json.loads(row["payload_json"])["session_id"] is None
    assert conn.execute(
        "SELECT session_id FROM activity_events"
    ).fetchone()["session_id"] == session_id
    conn.close()


def test_outbox_table_not_self_mirrored():
    """Inserting into _outbox does not produce a recursive _outbox row.
    (D-06: _outbox itself is never mirrored.)
    """
    conn = _migrated_conn()
    conn.execute(
        "INSERT INTO _outbox(table_name, op, pk_value, payload_json, created_at) "
        "VALUES (?,?,?,?,?)",
        ("ghost", "INSERT", "1", "{}", "2026-05-18T00:00:00Z"),
    )
    rows = conn.execute(
        "SELECT count(*) AS c FROM _outbox WHERE table_name='_outbox'"
    ).fetchone()
    assert rows["c"] == 0  # no recursion
    conn.close()


# === Task 7: mirror config defaults ===


def test_config_defaults(monkeypatch):
    """Config module exposes the documented defaults when no env vars are set."""
    for name in (
        "NEON_MIRROR_URL", "NEON_MIRROR_BATCH_SIZE", "NEON_MIRROR_MAX_RETRIES",
        "NEON_MIRROR_EMPTY_SLEEP", "NEON_MIRROR_BATCH_SLEEP",
    ):
        monkeypatch.delenv(name, raising=False)
    from backend.mirror import config as cfg
    cfg.reload_from_env()
    assert cfg.NEON_MIRROR_URL is None
    assert cfg.NEON_MIRROR_BATCH_SIZE == 100
    assert cfg.MAX_RETRIES == 5
    assert cfg.EMPTY_QUEUE_SLEEP == 5.0
    assert cfg.INTER_BATCH_SLEEP == 0.1
    assert cfg.BACKOFF_SECONDS == (1.0, 2.0, 4.0, 8.0, 16.0)


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("NEON_MIRROR_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("NEON_MIRROR_BATCH_SIZE", "50")
    monkeypatch.setenv("NEON_MIRROR_EMPTY_SLEEP", "2.5")
    from backend.mirror import config as cfg
    cfg.reload_from_env()
    assert cfg.NEON_MIRROR_URL == "postgresql://u:p@h/db"
    assert cfg.NEON_MIRROR_BATCH_SIZE == 50
    assert cfg.EMPTY_QUEUE_SLEEP == 2.5
    # Restore defaults for downstream tests.
    monkeypatch.delenv("NEON_MIRROR_URL", raising=False)
    monkeypatch.delenv("NEON_MIRROR_BATCH_SIZE", raising=False)
    monkeypatch.delenv("NEON_MIRROR_EMPTY_SLEEP", raising=False)
    cfg.reload_from_env()


def test_neon_client_lazy_connect_with_no_dsn():
    """NeonClient(None).connect() returns False; no exception."""
    from backend.mirror.neon_client import NeonClient
    client = NeonClient(None)
    assert client.connect() is False
    assert client._conn is None
    # apply() should raise NeonTransient since connect failed.
    from backend.mirror.neon_client import NeonTransient
    with pytest.raises(NeonTransient):
        client.apply("INSERT", "users", "1", {"id": 1, "username": "x"})


def test_neon_client_upsert_sql_shape():
    """Confirm the upsert builder produces the expected SQL for both single and composite PKs."""
    from psycopg.sql import Composed
    from backend.mirror.neon_client import _build_upsert
    # Single-column PK (users.id).
    query, args = _build_upsert("baran_users", ["id"], {"id": 1, "username": "a"})
    assert isinstance(query, Composed)
    rendered = query.as_string(None)
    assert 'INSERT INTO "baran_users"' in rendered
    assert 'ON CONFLICT ("id") DO UPDATE' in rendered
    assert '"username" = EXCLUDED."username"' in rendered
    assert args == [1, "a"]
    # Composite PK (drafts).
    query2, args2 = _build_upsert(
        "baran_drafts", ["document_id", "user_id"],
        {"document_id": "doc1", "user_id": 42, "references_json": "[]"},
    )
    assert isinstance(query2, Composed)
    rendered2 = query2.as_string(None)
    assert 'ON CONFLICT ("document_id", "user_id") DO UPDATE' in rendered2
    assert '"references_json" = EXCLUDED."references_json"' in rendered2


def test_neon_client_delete_sql_shape():
    from psycopg.sql import Composed
    from backend.mirror.neon_client import _build_delete
    # Single PK.
    query, args = _build_delete("baran_users", ["id"], "42")
    assert isinstance(query, Composed)
    rendered = query.as_string(None)
    assert '"baran_users"' in rendered
    assert '"id" = %s' in rendered
    assert args == ["42"]
    # Composite PK split on '::'.
    query2, args2 = _build_delete("baran_drafts", ["document_id", "user_id"], "doc-1::99")
    assert isinstance(query2, Composed)
    rendered2 = query2.as_string(None)
    assert '"document_id" = %s' in rendered2
    assert '"user_id" = %s' in rendered2
    assert args2 == ["doc-1", "99"]


# === Task 13: end-to-end smoke + latency regression guard ===
#
# Wires the live FastAPI app (via TestClient) to the trigger-capture
# layer and verifies the full round-trip: HTTP write → SQLite row +
# _outbox row → dispatcher drain → mark delivered. The latency check
# is a SOFT 50ms p95 regression bound, NOT the MIRROR-07 5ms target
# (that one is verified out-of-process via wrk/hey and recorded in
# 4-SUMMARY.md; see <output> of 4-PLAN.md).


def test_http_write_creates_one_outbox_row(client):
    """POST /api/auth/register writes a users row; the _outbox trigger
    captures the INSERT exactly once with the right shape."""
    # Seed an invite code first (registration needs one).
    from backend.shared.db import connect
    from backend import config as app_config
    conn = connect(app_config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) "
            "VALUES (?,1,datetime('now'))",
            ("E2E-INV-13",),
        )
        conn.commit()
        # Snapshot _outbox BEFORE the HTTP write so we can isolate
        # rows produced by the register endpoint specifically.
        before = conn.execute(
            "SELECT COUNT(*) AS c FROM _outbox WHERE table_name=? AND op=?",
            ("users", "INSERT"),
        ).fetchone()["c"]
    finally:
        conn.close()

    r = client.post("/api/auth/register", json={
        "username": "e2e_user_13",
        "password": "password123",
        "invite_code": "E2E-INV-13",
        "email": "e2e13@example.com",
    })
    assert r.status_code == 201, r.text

    conn = connect(app_config.DB_PATH)
    try:
        after = conn.execute(
            "SELECT COUNT(*) AS c FROM _outbox WHERE table_name=? AND op=?",
            ("users", "INSERT"),
        ).fetchone()["c"]
        # Exactly one new users INSERT outbox row from the register endpoint.
        assert after - before == 1
        row = conn.execute(
            "SELECT table_name, op, pk_value, payload_json, delivered_at, retry_count "
            "FROM _outbox WHERE table_name=? AND op=? ORDER BY id DESC LIMIT 1",
            ("users", "INSERT"),
        ).fetchone()
        assert row["table_name"] == "users"
        assert row["op"] == "INSERT"
        assert row["delivered_at"] is None  # not yet drained
        assert row["retry_count"] == 0
        payload = json.loads(row["payload_json"])
        assert payload["username"] == "e2e_user_13"
        # pk_value reflects the row's PK (users.id is INTEGER, surfaces as str).
        assert row["pk_value"] == str(payload["id"])
    finally:
        conn.close()


async def test_dispatcher_drains_http_originated_outbox_rows(client):
    """End-to-end Task 13 contract: an HTTP write produces an _outbox
    row, then the dispatcher (with a FakeNeon stand-in) drains the
    row and marks it delivered."""
    import asyncio
    from backend.shared.db import connect
    from backend import config as app_config
    from backend.mirror.dispatcher import run_dispatcher

    # Seed invite + register (HTTP write → trigger → outbox row).
    conn = connect(app_config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) "
            "VALUES (?,1,datetime('now'))",
            ("E2E-INV-13B",),
        )
        conn.commit()
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": "e2e_user_13b",
        "password": "password123",
        "invite_code": "E2E-INV-13B",
        "email": "e2e13b@example.com",
    })
    assert r.status_code == 201, r.text

    # Spin up the dispatcher with a FakeNeon that always succeeds.
    class _FakeNeon:
        def __init__(self):
            self.applied = []
            self.last_status = None
            self.has_connected_once = False
        def connect(self):
            self.has_connected_once = True
            return True
        def close(self):
            pass
        def apply(self, op, table, pk_value, payload):
            self.applied.append((op, table, pk_value, payload))
            self.last_status = True

    neon = _FakeNeon()
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_dispatcher(
            conn_factory=lambda: connect(app_config.DB_PATH),
            neon_client=neon,
            batch_size=100,
            sleep_empty=0.0,
            sleep_batch=0.0,
            max_retries=5,
            stop_event=stop,
        )
    )
    # Let the dispatcher drain at least once.
    for _ in range(20):
        await asyncio.sleep(0.01)
        # Stop as soon as the new users INSERT shows up in the applied log.
        if any(a[1] == "users" and a[0] == "INSERT" for a in neon.applied):
            break
    stop.set()
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except asyncio.TimeoutError:
        task.cancel()
        raise

    # The dispatcher applied at least one users INSERT (the one we just made).
    user_inserts = [a for a in neon.applied if a[1] == "users" and a[0] == "INSERT"]
    assert len(user_inserts) >= 1
    # And the _outbox row for that insert is now marked delivered.
    conn = connect(app_config.DB_PATH)
    try:
        delivered = conn.execute(
            "SELECT COUNT(*) AS c FROM _outbox "
            "WHERE table_name='users' AND op='INSERT' "
            "  AND delivered_at IS NOT NULL"
        ).fetchone()["c"]
        assert delivered >= 1
    finally:
        conn.close()


def test_http_latency_regression_guard_under_dispatcher(client):
    """Soft 50ms p95 regression bound on a lightweight GET while the
    dispatcher is NOT running vs. running. The strict MIRROR-07 5ms p95
    budget is verified out-of-process via wrk/hey and recorded in
    `4-SUMMARY.md`; this in-process check is a coarse regression guard
    only — do NOT tighten to 5ms (CI jitter + GIL noise make a tight
    in-process assertion flaky)."""
    import time
    import asyncio
    from backend.shared.db import connect
    from backend import config as app_config
    from backend.mirror.dispatcher import run_dispatcher

    def _measure_p95():
        samples = []
        for _ in range(100):
            t0 = time.perf_counter()
            r = client.get("/api/health")
            assert r.status_code == 200
            samples.append((time.perf_counter() - t0) * 1000.0)  # ms
        samples.sort()
        return samples[int(len(samples) * 0.95)]

    # Baseline: no dispatcher.
    p95_no_dispatcher = _measure_p95()

    # Now start a dispatcher in the background and re-measure.
    class _IdleNeon:
        def __init__(self):
            self.last_status = None
            self.has_connected_once = False
        def connect(self):
            self.has_connected_once = True
            return True
        def close(self):
            pass
        def apply(self, op, table, pk_value, payload):
            self.last_status = True

    async def _with_dispatcher():
        neon = _IdleNeon()
        stop = asyncio.Event()
        task = asyncio.create_task(
            run_dispatcher(
                conn_factory=lambda: connect(app_config.DB_PATH),
                neon_client=neon,
                batch_size=100,
                sleep_empty=0.05,
                sleep_batch=0.0,
                max_retries=5,
                stop_event=stop,
            )
        )
        await asyncio.sleep(0.05)  # let it spin up
        p95 = await asyncio.to_thread(_measure_p95)
        stop.set()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except asyncio.TimeoutError:
            task.cancel()
        return p95

    p95_with_dispatcher = asyncio.run(_with_dispatcher())

    delta_ms = p95_with_dispatcher - p95_no_dispatcher
    # Soft 50ms p95 regression bound. DO NOT TIGHTEN.
    assert delta_ms <= 50.0, (
        f"p95 latency regression {delta_ms:.2f}ms exceeded the 50ms soft "
        f"guard (no-dispatcher={p95_no_dispatcher:.2f}ms, "
        f"with-dispatcher={p95_with_dispatcher:.2f}ms). The strict 5ms "
        f"MIRROR-07 budget is verified out-of-process via wrk/hey; this "
        f"in-process check is a coarse regression guard only."
    )
