"""Mirror configuration (env-driven; Phase 4, D-09 + D-10 + MIRROR-10).

All values resolve lazily from environment variables so tests can override
via `monkeypatch.setenv` between cases. Module import never raises.
"""
from __future__ import annotations

import os


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# Connection — None when unset (the "Neon unreachable" degraded mode, D-14).
NEON_MIRROR_URL: str | None = os.environ.get("NEON_MIRROR_URL") or None

# Batch + backoff knobs (D-09, D-10). The lists are tuples so they're hashable
# / sliceable; consumer code should treat them as read-only.
NEON_MIRROR_BATCH_SIZE: int = _get_int("NEON_MIRROR_BATCH_SIZE", 100)
MAX_RETRIES: int = _get_int("NEON_MIRROR_MAX_RETRIES", 5)
EMPTY_QUEUE_SLEEP: float = _get_float("NEON_MIRROR_EMPTY_SLEEP", 5.0)
INTER_BATCH_SLEEP: float = _get_float("NEON_MIRROR_BATCH_SLEEP", 0.1)

# Exponential backoff schedule (seconds). Indexed by retry_count.
BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 16.0)


def reload_from_env() -> None:
    """Re-read every value from os.environ. Test helper — production never calls this."""
    global NEON_MIRROR_URL, NEON_MIRROR_BATCH_SIZE, MAX_RETRIES
    global EMPTY_QUEUE_SLEEP, INTER_BATCH_SLEEP
    NEON_MIRROR_URL = os.environ.get("NEON_MIRROR_URL") or None
    NEON_MIRROR_BATCH_SIZE = _get_int("NEON_MIRROR_BATCH_SIZE", 100)
    MAX_RETRIES = _get_int("NEON_MIRROR_MAX_RETRIES", 5)
    EMPTY_QUEUE_SLEEP = _get_float("NEON_MIRROR_EMPTY_SLEEP", 5.0)
    INTER_BATCH_SLEEP = _get_float("NEON_MIRROR_BATCH_SLEEP", 0.1)
