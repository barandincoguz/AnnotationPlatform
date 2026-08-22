"""v0017 — pre-submit quality audit: prediction cache + audit decision log.

The original v0017 rollout mirrored only `annotation_audit_logs`. Later mirror
migrations deliberately added `model_predictions` so an ephemeral Space can
restore its prediction cache from Neon. Current production provenance guards
are installed by v0020 and the generated Postgres DDL.
"""
import sqlite3

from backend.migrations.helpers.schema_introspect import introspect_table
from backend.migrations.helpers.trigger_generator import build_triggers_for_table

SCHEMA_SQL = """
CREATE TABLE model_predictions (
    document_id            TEXT PRIMARY KEY
                           REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    generation             TEXT NOT NULL,
    status                 TEXT NOT NULL CHECK(status IN ('success','error')),
    references_json        TEXT NOT NULL DEFAULT '[]',
    truncated              INTEGER NOT NULL DEFAULT 0 CHECK(truncated IN (0,1)),
    model_fingerprint      TEXT NOT NULL,
    prediction_fingerprint TEXT NOT NULL,
    text_sha256            TEXT NOT NULL,
    source                 TEXT NOT NULL,
    error                  TEXT,
    operational_json       TEXT NOT NULL DEFAULT '{}',
    created_at             TIMESTAMP NOT NULL,
    updated_at             TIMESTAMP NOT NULL
);
CREATE INDEX idx_pred_generation ON model_predictions(generation);

CREATE TABLE annotation_audit_logs (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id            TEXT NOT NULL
                           REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    user_id                INTEGER REFERENCES users(id) ON DELETE SET NULL,
    bucket                 TEXT,
    decision               TEXT NOT NULL CHECK(decision IN (
                               'no_discrepancy','accepted_model',
                               'human_override','model_unavailable')),
    reason                 TEXT,
    reasons_json           TEXT NOT NULL DEFAULT '[]',
    similarity             REAL,
    model_only_json        TEXT NOT NULL DEFAULT '[]',
    human_only_json        TEXT NOT NULL DEFAULT '[]',
    prediction_fingerprint TEXT,
    policy_id              TEXT NOT NULL,
    model_generation       TEXT,
    created_at             TIMESTAMP NOT NULL
);
CREATE INDEX idx_audit_doc_time ON annotation_audit_logs(document_id, created_at DESC);
CREATE INDEX idx_audit_decision ON annotation_audit_logs(decision);
CREATE INDEX idx_audit_bucket ON annotation_audit_logs(bucket);
"""


def up(conn: sqlite3.Connection) -> None:
    for raw in SCHEMA_SQL.split(";"):
        stmt = raw.strip()
        if stmt:
            conn.execute(stmt)
    schema = introspect_table(conn, "annotation_audit_logs")
    for stmt in build_triggers_for_table(schema):
        conn.execute(stmt)
