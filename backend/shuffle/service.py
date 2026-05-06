"""3-tab shuffle feed service.

Public API:
  list_feed(db, *, user_id, tab, limit, offset) -> dict

Returns:
  {"items": list[FeedItem], "total": int}

Tab semantics:
  new      -> no annotation row exists for the document
  review   -> annotation row exists AND is_completed=0
  verified -> annotation row exists AND is_completed=1

Shuffle is deterministic per-(user_id, tab, UTC date) so:
  - The same user gets the same order all day -> pagination is stable.
  - The order rotates daily.
  - Different users see different orders.

The feed item is a flat denormalized record optimized for the left-column
list. pdf_text is intentionally excluded -- frontend reads full doc content
via GET /api/documents/{id}.
"""
import random
import sqlite3
from datetime import datetime, timezone


VALID_TABS = ("new", "review", "verified")
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class ShuffleServiceError(Exception):
    """Base."""


class InvalidTab(ShuffleServiceError):
    pass


def _seed_str(*, user_id: int, tab: str) -> str:
    """Public helper (also used by tests) -- UTC date-based per-day rotation."""
    today = datetime.now(timezone.utc).date().isoformat()
    return f"{user_id}|{tab}|{today}"


def _shuffle(items: list[dict], *, user_id: int, tab: str) -> list[dict]:
    """Deterministic shuffle in place; returns the same list."""
    rng = random.Random(_seed_str(user_id=user_id, tab=tab))
    rng.shuffle(items)
    return items


_NEW_QUERY = """
SELECT
    d.document_id, d.sayi, d.tarih, d.konu, d.vergi_turu,
    d.estimated_difficulty, d.word_count
FROM documents_meta d
LEFT JOIN annotations a ON a.document_id = d.document_id
WHERE a.document_id IS NULL
ORDER BY d.created_at DESC, d.document_id ASC
"""

_REVIEW_QUERY = """
SELECT
    d.document_id, d.sayi, d.tarih, d.konu, d.vergi_turu,
    d.estimated_difficulty, d.word_count,
    a.is_completed, a.last_editor_user_id, u.username AS last_editor_username,
    a.edit_count, a.unique_users_count, a.updated_at
FROM documents_meta d
INNER JOIN annotations a ON a.document_id = d.document_id
LEFT JOIN users u ON u.id = a.last_editor_user_id
WHERE a.is_completed = 0
ORDER BY a.updated_at DESC, d.document_id ASC
"""

_VERIFIED_QUERY = """
SELECT
    d.document_id, d.sayi, d.tarih, d.konu, d.vergi_turu,
    d.estimated_difficulty, d.word_count,
    a.is_completed, a.last_editor_user_id, u.username AS last_editor_username,
    a.edit_count, a.unique_users_count, a.updated_at
FROM documents_meta d
INNER JOIN annotations a ON a.document_id = d.document_id
LEFT JOIN users u ON u.id = a.last_editor_user_id
WHERE a.is_completed = 1
ORDER BY a.updated_at DESC, d.document_id ASC
"""


def _empty_chain_fields() -> dict:
    return {
        "has_annotation": False,
        "is_completed": False,
        "last_editor_user_id": None,
        "last_editor_username": None,
        "edit_count": 0,
        "unique_users_count": 0,
        "updated_at": None,
    }


def _row_to_item_new(row: sqlite3.Row) -> dict:
    return {
        "document_id": row["document_id"],
        "sayi": row["sayi"],
        "tarih": row["tarih"],
        "konu": row["konu"],
        "vergi_turu": row["vergi_turu"],
        "estimated_difficulty": row["estimated_difficulty"],
        "word_count": row["word_count"],
        **_empty_chain_fields(),
    }


def _row_to_item_chain(row: sqlite3.Row) -> dict:
    return {
        "document_id": row["document_id"],
        "sayi": row["sayi"],
        "tarih": row["tarih"],
        "konu": row["konu"],
        "vergi_turu": row["vergi_turu"],
        "estimated_difficulty": row["estimated_difficulty"],
        "word_count": row["word_count"],
        "has_annotation": True,
        "is_completed": bool(row["is_completed"]),
        "last_editor_user_id": row["last_editor_user_id"],
        "last_editor_username": row["last_editor_username"],
        "edit_count": row["edit_count"],
        "unique_users_count": row["unique_users_count"],
        "updated_at": row["updated_at"],
    }


def list_feed(
    db: sqlite3.Connection,
    *,
    user_id: int,
    tab: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    """Return paginated, deterministically-shuffled feed items for a tab.

    Raises InvalidTab on unknown tab; ValueError on negative limit/offset.
    """
    if tab not in VALID_TABS:
        raise InvalidTab(f"unknown tab: {tab!r} (valid: {VALID_TABS})")
    if limit < 0:
        raise ValueError("limit must be >= 0")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    limit = min(limit, MAX_LIMIT)

    if tab == "new":
        rows = db.execute(_NEW_QUERY).fetchall()
        items = [_row_to_item_new(r) for r in rows]
    elif tab == "review":
        rows = db.execute(_REVIEW_QUERY).fetchall()
        items = [_row_to_item_chain(r) for r in rows]
    else:  # verified
        rows = db.execute(_VERIFIED_QUERY).fetchall()
        items = [_row_to_item_chain(r) for r in rows]

    total = len(items)
    items = _shuffle(items, user_id=user_id, tab=tab)
    page = items[offset : offset + limit]
    return {"items": page, "total": total}
