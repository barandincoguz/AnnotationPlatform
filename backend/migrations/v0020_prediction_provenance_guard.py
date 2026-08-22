"""v0020 — enforce real-agent provenance for every prediction write."""

import sqlite3

from backend.quality.provenance import TRUSTED_G0_MODEL_FINGERPRINTS


TRIGGER_NAMES = (
    "protect_model_prediction_provenance_insert",
    "protect_model_prediction_provenance_update",
)

def install_prediction_provenance_guards(conn: sqlite3.Connection) -> None:
    trusted_fingerprints_sql = ", ".join(
        f"'{fingerprint}'" for fingerprint in sorted(TRUSTED_G0_MODEL_FINGERPRINTS)
    )
    predicate = f"""
        NEW.generation <> 'G0'
        OR NEW.source <> 'dqcheck_agent'
        OR json_valid(NEW.operational_json) = 0
        OR COALESCE(json_extract(NEW.operational_json, '$.backend'), '') <> 'mlx-g0'
        OR length(NEW.model_fingerprint) <> 64
        OR NEW.model_fingerprint GLOB '*[^0-9a-f]*'
        OR NEW.model_fingerprint NOT IN ({trusted_fingerprints_sql})
        OR length(NEW.text_sha256) <> 64
        OR NEW.text_sha256 GLOB '*[^0-9a-f]*'
    """
    for operation, name in zip(("INSERT", "UPDATE"), TRIGGER_NAMES, strict=True):
        conn.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS {name}
            BEFORE {operation} ON model_predictions
            WHEN {predicate}
            BEGIN
                SELECT RAISE(ABORT, 'untrusted model prediction provenance');
            END
            """
        )


def up(conn: sqlite3.Connection) -> None:
    install_prediction_provenance_guards(conn)
