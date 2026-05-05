"""Help content discovery and parsing.

Markdown files in `content/` are loaded at request time (not cached) — small
file count (~9), small bodies, fine for our scale.
"""
from pathlib import Path
from typing import Optional

CONTENT_DIR = Path(__file__).parent / "content"


def _parse_title(body: str, fallback: str) -> str:
    """First '# ' H1 line, else fallback."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def _parse_order(stem: str) -> Optional[int]:
    """Extract leading numeric prefix (e.g. '01-welcome' → 1)."""
    head = stem.split("-", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def list_help_sections() -> list[dict]:
    """Return all help sections sorted by leading numeric prefix."""
    if not CONTENT_DIR.exists():
        return []
    out = []
    for path in sorted(CONTENT_DIR.glob("*.md")):
        body = path.read_text(encoding="utf-8")
        order = _parse_order(path.stem)
        if order is None:
            continue  # skip files without numeric prefix
        title = _parse_title(body, path.stem)
        out.append({
            "id": path.stem,
            "order": order,
            "title": title,
            "body": body,
        })
    out.sort(key=lambda s: s["order"])
    return out
