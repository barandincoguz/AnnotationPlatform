"""Tests for v0014 — move backup cadence default to 24 hours."""
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


def test_v0014_sets_backup_interval_default_to_24h(fresh_db):
    row = fresh_db.execute(
        "SELECT value FROM site_settings WHERE key='backup.interval_seconds'"
    ).fetchone()
    assert row["value"] == "86400"


def test_v0014_preserves_operator_tuned_backup_interval(fresh_db):
    from backend.migrations.v0014_backup_interval_24h import up

    fresh_db.execute(
        "UPDATE site_settings SET value=? WHERE key='backup.interval_seconds'",
        ("43200",),
    )
    fresh_db.commit()

    up(fresh_db)

    row = fresh_db.execute(
        "SELECT value FROM site_settings WHERE key='backup.interval_seconds'"
    ).fetchone()
    assert row["value"] == "43200"
