"""Pre-submit quality audit: vendored DQCheck engine + AP-facing services."""

from typing import Any

__all__ = ("router",)


def __getattr__(name: str) -> Any:
    """Keep the historical router export without importing FastAPI eagerly.

    Migration discovery imports ``backend.quality.provenance`` in the minimal
    Docker smoke-test host, where only pytest is installed. Importing the
    package must not pull in the HTTP stack unless a caller actually requests
    the legacy ``backend.quality.router`` export.
    """
    if name == "router":
        from backend.quality.routes import router

        return router
    raise AttributeError(name)
