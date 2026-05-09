import json
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared import audit


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    # Seed a test user (FK target)
    conn.execute(
        "INSERT INTO users(id, username, password_hash, created_at, updated_at) VALUES (1, 'tester', 'x', datetime('now'), datetime('now'))"
    )
    yield conn
    conn.close()


def test_log_activity_inserts_row(db):
    audit.log_activity(db, user_id=1, event_type="save", document_id="doc_001", duration_ms=4500)
    rows = db.execute("SELECT * FROM activity_events").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "save"
    assert rows[0]["user_id"] == 1
    assert rows[0]["document_id"] == "doc_001"
    assert rows[0]["duration_ms"] == 4500


def test_log_activity_with_extra(db):
    audit.log_activity(db, user_id=1, event_type="open_doc",
                       document_id="doc_001", extra={"from": "review_tab"})
    row = db.execute("SELECT extra_json FROM activity_events").fetchone()
    assert json.loads(row["extra_json"]) == {"from": "review_tab"}


def test_log_behavioral_inserts(db):
    audit.log_behavioral(db, user_id=1, detector="speed_warning",
                          threshold_value=5.0, actual_value=7.0,
                          context={"recent": 7})
    row = db.execute("SELECT * FROM behavioral_events").fetchone()
    assert row["detector"] == "speed_warning"
    assert row["threshold_value"] == 5.0
    assert row["actual_value"] == 7.0


def test_log_admin_action_inserts(db):
    audit.log_admin_action(db, admin_user_id=1, action_type="promote_admin",
                           target_kind="user", target_id="42",
                           metadata={"reason": "trust"})
    row = db.execute("SELECT * FROM admin_audit_log").fetchone()
    assert row["action_type"] == "promote_admin"
    assert row["target_id"] == "42"


def test_log_system_event_inserts(db):
    audit.log_system_event(db, event_type="backup_complete",
                            severity="info", message="OK")
    row = db.execute("SELECT * FROM system_events").fetchone()
    assert row["event_type"] == "backup_complete"
    assert row["severity"] == "info"


def test_log_system_event_invalid_severity(db):
    with pytest.raises(ValueError):
        audit.log_system_event(db, event_type="x", severity="bogus")


def test_gen_trace_id_format():
    """16-char lowercase hex token (64 bits of entropy)."""
    from backend.shared.audit import gen_trace_id
    tid = gen_trace_id()
    assert isinstance(tid, str)
    assert len(tid) == 16
    assert all(c in "0123456789abcdef" for c in tid)


def test_gen_trace_id_is_unique_in_practice():
    """1000 calls produce 1000 distinct values (uniqueness sanity)."""
    from backend.shared.audit import gen_trace_id
    values = {gen_trace_id() for _ in range(1000)}
    assert len(values) == 1000


def test_log_admin_action_writes_trace_id(db):
    audit.log_admin_action(
        db, admin_user_id=1, action_type="settings_update",
        trace_id="abc123def4567890",
    )
    row = db.execute("SELECT trace_id FROM admin_audit_log").fetchone()
    assert row["trace_id"] == "abc123def4567890"


def test_log_admin_action_default_trace_id_is_null(db):
    audit.log_admin_action(db, admin_user_id=1, action_type="something")
    row = db.execute("SELECT trace_id FROM admin_audit_log").fetchone()
    assert row["trace_id"] is None


def test_log_system_event_writes_trace_id(db):
    audit.log_system_event(
        db, event_type="backup_started", severity="info",
        trace_id="0fedcba987654321",
    )
    row = db.execute("SELECT trace_id FROM system_events").fetchone()
    assert row["trace_id"] == "0fedcba987654321"


def test_log_system_event_default_trace_id_is_null(db):
    audit.log_system_event(db, event_type="boot", severity="info")
    row = db.execute("SELECT trace_id FROM system_events").fetchone()
    assert row["trace_id"] is None
