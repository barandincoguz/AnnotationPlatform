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


# ---------------------------------------------------------------------------
# Orchestrator  (Task 3 implements)
# ---------------------------------------------------------------------------
