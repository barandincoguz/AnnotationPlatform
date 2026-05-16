"""Coverage test: every /api/admin/* route must depend on require_admin.

Catches regressions where a new admin route is added but the
require_admin guard is forgotten. Walks the FastAPI route table at
collection time and inspects each route's resolved dependency graph.
"""
from typing import Iterable

import pytest


def _collect_dependants(dep_tree, out):
    """Recursively traverse a fastapi.dependencies.models.Dependant tree
    collecting every nested Dependant + its call target name."""
    if dep_tree is None:
        return
    out.append(dep_tree)
    for sub in getattr(dep_tree, "dependencies", []):
        _collect_dependants(sub, out)


def _route_uses_require_admin(route) -> bool:
    """True if any node in the route's dependency graph is the function
    `require_admin` (matched by __name__)."""
    nodes: list = []
    _collect_dependants(getattr(route, "dependant", None), nodes)
    for node in nodes:
        call = getattr(node, "call", None)
        if call is not None and getattr(call, "__name__", "") == "require_admin":
            return True
    return False


def test_every_admin_route_requires_admin():
    """No /api/admin/* route should be reachable without require_admin guard."""
    import os
    os.environ.setdefault("DISABLE_SPA_MOUNT", "1")
    os.environ.setdefault("ENVIRONMENT", "test")
    from backend.main import app

    bad: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        # Skip non-HTTP routes (e.g. WebSocketRoute, Mount). Only APIRoute
        # has a dependant attribute.
        if not hasattr(route, "dependant"):
            continue
        if not path.startswith("/api/admin"):
            continue
        if not _route_uses_require_admin(route):
            methods = ",".join(sorted(getattr(route, "methods", set())))
            bad.append(f"{methods} {path}")

    assert bad == [], (
        f"{len(bad)} admin route(s) missing require_admin guard:\n  "
        + "\n  ".join(bad)
    )
