"""Backfill idempotency tests (Phase 4 Task 11).

Uses a FakeNeonAccumulator (in-process) that captures every (sql, values)
pair the backfill would have executed against Neon. Asserts:
  - first run writes exactly N rows per table,
  - second run still writes (upserts), but the resulting state is identical
    (the SQL emitted is upsert, so a second run is a no-op semantically),
  - FK topological order (parents before children),
  - --dry-run reports counts without firing pg_apply,
  - --table filter restricts to a subset,
  - composite-PK tables include both PK columns in ON CONFLICT.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared.db import connect
from scripts.neon_backfill import run_backfill


class FakeNeonAccumulator:
    """Records every (sql, values) tuple the backfill would have executed."""

    def __init__(self):
        self.calls: list[tuple[str, list]] = []

    def apply(self, sql: str, values: list) -> None:
        self.calls.append((sql, list(values)))


def _bootstrap_db_with_seed(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    conn = connect(db)
    try:
        apply_migrations(conn, discover_migrations())
        # Seed 2 users.
        for u in ("alice", "bob"):
            conn.execute(
                "INSERT INTO users(username, password_hash, role, is_active, "
                "has_passed_training, has_seen_manual, created_at, updated_at) "
                "VALUES (?, ?, 'user', 1, 0, 0, '2026-05-18T00:00:00Z', '2026-05-18T00:00:00Z')",
                (u, "x"),
            )
        # Seed 1 documents_meta.
        conn.execute(
            "INSERT INTO documents_meta(document_id, file_path, pdf_text, word_count, "
            "sentence_count, text_density, estimated_difficulty, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("doc-X", "/tmp/x.json", "body", 2, 1, 0.5, "Kolay", "2026-05-18T00:00:00Z"),
        )
        # Seed 1 annotation with a non-trivial references_json payload.
        conn.execute(
            "INSERT INTO annotations(document_id, references_json, is_completed, "
            "edit_count, unique_users_count, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            ("doc-X",
             '[{"kanun_no":"193","madde":"37","source_text":"GVK m.37"}]',
             0, 1, 1, "2026-05-18T00:00:00Z", "2026-05-18T00:00:00Z"),
        )
        # Seed 1 draft (composite PK).
        user_id = conn.execute(
            "SELECT id FROM users WHERE username='alice'"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO drafts(document_id, user_id, references_json, updated_at) "
            "VALUES (?,?,?,?)",
            ("doc-X", user_id, "[]", "2026-05-18T00:00:00Z"),
        )
    finally:
        conn.close()
    return db


def test_full_backfill_emits_one_upsert_per_seeded_row(tmp_path):
    db = _bootstrap_db_with_seed(tmp_path)
    sqlite_conn = connect(db)
    try:
        acc = FakeNeonAccumulator()
        counts = run_backfill(sqlite_conn, acc.apply, log=lambda s: None)
    finally:
        sqlite_conn.close()
    # users → 2 rows
    assert counts["users"] == 2
    # documents_meta → 1 row
    assert counts["documents_meta"] == 1
    # annotations → 1 row
    assert counts["annotations"] == 1
    # drafts → 1 row
    assert counts["drafts"] == 1
    # Calls equal sum of row counts.
    assert len(acc.calls) == sum(counts.values())


def test_idempotency_second_run_produces_same_upsert_shape(tmp_path):
    db = _bootstrap_db_with_seed(tmp_path)
    sqlite_conn = connect(db)
    try:
        a, b = FakeNeonAccumulator(), FakeNeonAccumulator()
        run_backfill(sqlite_conn, a.apply, log=lambda _: None)
        run_backfill(sqlite_conn, b.apply, log=lambda _: None)
    finally:
        sqlite_conn.close()
    # Both runs hit the same set of (sql, values) tuples.
    assert a.calls == b.calls


def test_fk_topological_order_users_before_annotations(tmp_path):
    db = _bootstrap_db_with_seed(tmp_path)
    sqlite_conn = connect(db)
    try:
        acc = FakeNeonAccumulator()
        run_backfill(sqlite_conn, acc.apply, log=lambda _: None)
    finally:
        sqlite_conn.close()
    sql_strs = [c[0] for c in acc.calls]
    # Locate the first call into baran_users vs baran_annotations.
    pos_users = next((i for i, s in enumerate(sql_strs) if "INTO baran_users " in s), -1)
    pos_anno = next((i for i, s in enumerate(sql_strs) if "INTO baran_annotations " in s), -1)
    pos_meta = next((i for i, s in enumerate(sql_strs) if "INTO baran_documents_meta " in s), -1)
    assert 0 <= pos_users < pos_anno
    assert 0 <= pos_meta < pos_anno


def test_dry_run_does_not_call_pg_apply(tmp_path):
    db = _bootstrap_db_with_seed(tmp_path)
    sqlite_conn = connect(db)
    try:
        acc = FakeNeonAccumulator()
        counts = run_backfill(sqlite_conn, acc.apply, dry_run=True, log=lambda _: None)
    finally:
        sqlite_conn.close()
    # No real writes occurred.
    assert acc.calls == []
    # But counts still reflect rows that WOULD be upserted.
    assert counts["users"] == 2
    assert counts["annotations"] == 1


def test_single_table_filter_only_touches_users(tmp_path):
    db = _bootstrap_db_with_seed(tmp_path)
    sqlite_conn = connect(db)
    try:
        acc = FakeNeonAccumulator()
        counts = run_backfill(sqlite_conn, acc.apply,
                              tables_filter=["users"], log=lambda _: None)
    finally:
        sqlite_conn.close()
    assert list(counts.keys()) == ["users"]
    assert all("INTO baran_users " in c[0] for c in acc.calls)


def test_drafts_on_conflict_uses_composite_pk(tmp_path):
    db = _bootstrap_db_with_seed(tmp_path)
    sqlite_conn = connect(db)
    try:
        acc = FakeNeonAccumulator()
        run_backfill(sqlite_conn, acc.apply,
                     tables_filter=["drafts"], log=lambda _: None)
    finally:
        sqlite_conn.close()
    drafts_calls = [c for c in acc.calls if "INTO baran_drafts " in c[0]]
    assert len(drafts_calls) == 1
    sql = drafts_calls[0][0]
    assert "ON CONFLICT (document_id, user_id) DO UPDATE" in sql, sql
    # Non-PK column appears in SET clause.
    assert "references_json = EXCLUDED.references_json" in sql


def test_references_json_payload_is_serialized_as_text_for_jsonb(tmp_path):
    """The captured SQL values must carry a JSON-text payload for jsonb columns."""
    db = _bootstrap_db_with_seed(tmp_path)
    sqlite_conn = connect(db)
    try:
        acc = FakeNeonAccumulator()
        run_backfill(sqlite_conn, acc.apply,
                     tables_filter=["annotations"], log=lambda _: None)
    finally:
        sqlite_conn.close()
    anno_calls = [c for c in acc.calls if "INTO baran_annotations " in c[0]]
    assert len(anno_calls) == 1
    sql, values = anno_calls[0]
    # The references_json position in the placeholder list — find the value
    # that's a JSON string.
    json_strings = [v for v in values if isinstance(v, str) and v.startswith("[")]
    assert json_strings, f"no json-text value found in {values}"
    parsed = json.loads(json_strings[0])
    assert isinstance(parsed, list)
    assert parsed[0]["kanun_no"] == "193"
