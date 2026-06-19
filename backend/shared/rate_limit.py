"""In-memory sliding-window rate limiter.

Designed for the single-process uvicorn deployment: a per-key deque of
recent hit timestamps, capped to N hits in W seconds. No cross-worker
state, no Redis dependency — adding one would exceed polish-phase scope.

Use it via the FastAPI dependency factory `rate_limit(...)` that returns
a parameterized dependency. Each dependency instance owns one bucket
namespace (e.g. "login", "register"); buckets are keyed off the client
IP so multiple users behind the same NAT only burn their own quota.

The IP is read via `backend.users.deps.get_request_ip`, which honors
the `TRUST_FORWARDED_FOR` env var. Without that env, the source IP is
the immediate peer (`request.client.host`), so XFF-spoof cannot evade
the limit on a direct-to-uvicorn deployment.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from fastapi import Request




# Per-namespace state. Each value is {ip: deque[float_ts]}.
_BUCKETS: dict[str, dict[str, deque[float]]] = {}
_LOCK = threading.Lock()


def _bucket(namespace: str) -> dict[str, deque[float]]:
    """Get-or-create the IP→timestamps map for a namespace."""
    bucket = _BUCKETS.get(namespace)
    if bucket is None:
        with _LOCK:
            bucket = _BUCKETS.setdefault(namespace, {})
    return bucket


def reset_for_tests() -> None:
    """Drain every bucket's entries. Called from test fixtures to isolate
    runs. Note: this clears each per-namespace dict in place rather than
    replacing it, because the `rate_limit` dependency captures a
    reference to the namespace dict at module load (so swapping the
    outer `_BUCKETS` entry would leave stale references alive). Draining
    in place keeps the reference identity valid while emptying state."""
    with _LOCK:
        for ns_bucket in _BUCKETS.values():
            ns_bucket.clear()


class FailureRateLimiter:
    """Sliding-window limiter that records only explicit failures.

    Authentication uses this instead of a pre-request dependency so valid
    logins never consume the brute-force budget. This matters for offices
    where many legitimate users share one public NAT address.
    """

    def __init__(self, *, namespace: str, max_hits: int, window_seconds: int):
        self.max_hits = max_hits
        self.window_seconds = window_seconds
        self.bucket = _bucket(namespace)

    def _evict_stale(self, key: str, now: float) -> deque[float]:
        cutoff = now - self.window_seconds
        dq = self.bucket.get(key)
        if dq is None:
            dq = deque(maxlen=self.max_hits)
            self.bucket[key] = dq
        while dq and dq[0] < cutoff:
            dq.popleft()
        return dq

    def check(self, key: str) -> None:
        """Raise 429 when the key has exhausted its failure budget."""
        from fastapi import HTTPException

        now = time.monotonic()
        with _LOCK:
            dq = self._evict_stale(key, now)
            if len(dq) < self.max_hits:
                return
            retry_after = max(
                1,
                int(dq[0] + self.window_seconds - now + 0.999),
            )
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limited",
                "message": f"too many requests; retry in ~{retry_after}s",
            },
            headers={"Retry-After": str(retry_after)},
        )

    def record_failure(self, key: str) -> None:
        """Consume one slot after an authentication failure."""
        now = time.monotonic()
        with _LOCK:
            self._evict_stale(key, now).append(now)


def rate_limit(
    *,
    namespace: str,
    max_hits: int,
    window_seconds: int,
    key_fn: Optional[Callable[[Request], str]] = None,
) -> Callable:
    """Build a FastAPI dependency that throttles based on a sliding window.

    Args:
        namespace: bucket identifier (e.g. "login").
        max_hits: maximum permitted hits within `window_seconds`.
        window_seconds: rolling window length.
        key_fn: optional function (Request) -> str for the bucket key.
            Defaults to the client IP (via get_request_ip).

    The returned callable is suitable as a FastAPI `Depends(...)` value.

    Behaviour:
        - Each request appends `time.monotonic()` to the per-key deque.
        - Stale entries (older than `window_seconds`) are evicted on
          every call so the deque never grows beyond `max_hits + 1`.
        - When the post-eviction count exceeds `max_hits`, the
          dependency raises HTTPException(429) with the remaining
          window in `Retry-After`.
    """
    global Request
    from fastapi import Request

    from backend.users.deps import get_request_ip  # local import: avoid cycle

    def _key_default(req: Request) -> str:
        ip = get_request_ip(req)
        return ip or "unknown"

    extract_key = key_fn or _key_default
    bucket = _bucket(namespace)

    def dependency(request: Request) -> None:
        from fastapi import HTTPException

        now = time.monotonic()
        cutoff = now - window_seconds
        key = extract_key(request)

        with _LOCK:
            dq = bucket.get(key)
            if dq is None:
                dq = deque(maxlen=max_hits + 1)
                bucket[key] = dq
            # Evict stale hits (left side of deque).
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= max_hits:
                # Oldest still-valid hit defines when the next slot
                # opens. Retry-After is integer seconds, rounded up.
                retry_after = max(1, int(dq[0] + window_seconds - now + 0.999))
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limited",
                        "message": (
                            f"too many requests; retry in ~{retry_after}s"
                        ),
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            dq.append(now)

    return dependency
