"""3-tab shuffle feed service.

Public API:
  list_feed(db, *, user_id, tab, limit, offset, sort, order) -> dict

Returns:
  {"items": list[FeedItem], "total": int}

Tab semantics:
  new      -> no annotation row exists for the document
  review   -> annotation row exists AND is_completed=0
  verified -> annotation row exists AND is_completed=1

Sort:
  - sort="shuffle": deterministic per-(user_id, tab, UTC date) shuffle so
    one user gets the same order all day, the order rotates daily, and
    different users see different orders.
  - Any other whitelisted sort key: SQL ORDER BY <column> <direction>,
    always followed by `document_id ASC` as a stable tiebreaker so
    paginated fetches never skip or duplicate on equal keys.
  - sort=None: resolves to DEFAULT_SORT_FOR[tab].

Sort whitelist (per-tab availability noted):
  shuffle        -> Python shuffle (no SQL ORDER BY chosen)
  tarih          -> d.tarih          (all tabs; NULLs sink to the end)
  created_at     -> d.created_at     (all tabs)
  sayi           -> d.sayi           (all tabs)
  vergi_turu     -> d.vergi_turu     (all tabs; NULLs sink to the end)
  konu           -> d.konu           (all tabs; NULLs sink to the end)
  difficulty     -> d.estimated_difficulty (all tabs)
  word_count     -> d.word_count     (all tabs)
  updated_at     -> a.updated_at     (review + verified only)
  editors_count  -> a.unique_users_count (review + verified only)

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

DEFAULT_SORT_FOR = {
    "new": ("tarih", "desc"),
    "review": ("updated_at", "desc"),
    "verified": ("updated_at", "desc"),
}

# Whitelist of sort keys → (SQL column expression, allowed-tabs).
# The SQL fragment is interpolated literally; never accept caller input
# into the ORDER BY chain bypassing this mapping.
SORT_COLUMNS: dict[str, tuple[str, frozenset[str]]] = {
    "tarih": ("d.tarih", frozenset({"new", "review", "verified"})),
    "created_at": ("d.created_at", frozenset({"new", "review", "verified"})),
    "sayi": ("d.sayi", frozenset({"new", "review", "verified"})),
    "vergi_turu": ("d.vergi_turu", frozenset({"new", "review", "verified"})),
    "konu": ("d.konu", frozenset({"new", "review", "verified"})),
    "difficulty": ("d.estimated_difficulty", frozenset({"new", "review", "verified"})),
    "word_count": ("d.word_count", frozenset({"new", "review", "verified"})),
    "updated_at": ("a.updated_at", frozenset({"review", "verified"})),
    "editors_count": ("a.unique_users_count", frozenset({"review", "verified"})),
}

VALID_ORDERS = ("asc", "desc")


class ShuffleServiceError(Exception):
    """Base."""


class InvalidTab(ShuffleServiceError):
    pass


class InvalidSort(ShuffleServiceError):
    """Sort key or order is malformed, or the key is not valid on the
    current tab (e.g. updated_at on the 'new' tab)."""


def _seed_str(*, user_id: int, tab: str) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return f"{user_id}|{tab}|{today}"


def _shuffle(items: list[dict], *, user_id: int, tab: str) -> list[dict]:
    rng = random.Random(_seed_str(user_id=user_id, tab=tab))
    rng.shuffle(items)
    return items


def _build_order_by(*, tab: str, sort: str, order: str) -> str:
    """ORDER BY clause for a non-shuffle sort. Stable tiebreaker on
    document_id ASC; NULLs sink to the end regardless of direction."""
    if sort not in SORT_COLUMNS:
        raise InvalidSort(f"unknown sort key: {sort!r}")
    if order not in VALID_ORDERS:
        raise InvalidSort(f"unknown order: {order!r}")
    column, allowed_tabs = SORT_COLUMNS[sort]
    if tab not in allowed_tabs:
        raise InvalidSort(f"sort key {sort!r} is not valid on tab {tab!r}")
    direction = "DESC" if order == "desc" else "ASC"
    # `<col> IS NULL` evaluates to 1 for NULLs and 0 otherwise; ordering
    # on that ASC pushes nulls past everything else, then we sort by the
    # column itself, then the tiebreaker.
    return f"ORDER BY ({column} IS NULL), {column} {direction}, d.document_id ASC"


# Per-tab (column_list, from_where) pair. column_list is the SELECT
# projection used to build items; from_where is the shared FROM/JOIN/WHERE
# tail used by both the page query AND the COUNT(*) query.
_NEW_COLUMNS = (
    "d.document_id, d.sayi, d.tarih, d.konu, d.vergi_turu, "
    "d.estimated_difficulty, d.word_count"
)
_NEW_FROM_WHERE = (
    "FROM documents_meta d "
    "LEFT JOIN annotations a ON a.document_id = d.document_id "
    "WHERE a.document_id IS NULL"
)

_CHAIN_COLUMNS = (
    "d.document_id, d.sayi, d.tarih, d.konu, d.vergi_turu, "
    "d.estimated_difficulty, d.word_count, "
    "a.is_completed, a.last_editor_user_id, u.username AS last_editor_username, "
    "a.edit_count, a.unique_users_count, a.updated_at"
)
_REVIEW_FROM_WHERE = (
    "FROM documents_meta d "
    "INNER JOIN annotations a ON a.document_id = d.document_id "
    "LEFT JOIN users u ON u.id = a.last_editor_user_id "
    "WHERE a.is_completed = 0"
)
_VERIFIED_FROM_WHERE = (
    "FROM documents_meta d "
    "INNER JOIN annotations a ON a.document_id = d.document_id "
    "LEFT JOIN users u ON u.id = a.last_editor_user_id "
    "WHERE a.is_completed = 1"
)

# Legacy default ORDER BY for the shuffle path. The in-memory shuffle
# rewrites the order anyway, but a deterministic base reads better in
# EXPLAIN QUERY PLAN traces and makes the un-shuffled fallback safer
# if the shuffle ever gets disabled.
_SHUFFLE_FALLBACK_ORDER_BY = {
    "new": "ORDER BY d.created_at DESC, d.document_id ASC",
    "review": "ORDER BY a.updated_at DESC, d.document_id ASC",
    "verified": "ORDER BY a.updated_at DESC, d.document_id ASC",
}

_TAB_PARTS = {
    "new": (_NEW_COLUMNS, _NEW_FROM_WHERE),
    "review": (_CHAIN_COLUMNS, _REVIEW_FROM_WHERE),
    "verified": (_CHAIN_COLUMNS, _VERIFIED_FROM_WHERE),
}


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
    sort: str | None = None,
    order: str | None = None,
) -> dict:
    """Return paginated feed items for a tab, ordered per `sort`.

    sort=None resolves to DEFAULT_SORT_FOR[tab] (a real sort, not shuffle).

    Raises:
      InvalidTab on unknown tab.
      InvalidSort on unknown sort key, unknown order, or a sort key not
        valid on the requested tab.
      ValueError on negative limit/offset.
    """
    if tab not in VALID_TABS:
        raise InvalidTab(f"unknown tab: {tab!r} (valid: {VALID_TABS})")
    if limit < 0:
        raise ValueError("limit must be >= 0")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    limit = min(limit, MAX_LIMIT)

    resolved_sort = sort if sort is not None else DEFAULT_SORT_FOR[tab][0]
    resolved_order = order if order is not None else (
        DEFAULT_SORT_FOR[tab][1] if sort is None else "desc"
    )

    columns, from_where = _TAB_PARTS[tab]
    row_mapper = _row_to_item_new if tab == "new" else _row_to_item_chain

    if resolved_sort == "shuffle":
        sql = f"SELECT {columns} {from_where} {_SHUFFLE_FALLBACK_ORDER_BY[tab]}"
        rows = db.execute(sql).fetchall()
        items = [row_mapper(r) for r in rows]
        total = len(items)
        items = _shuffle(items, user_id=user_id, tab=tab)
        page = items[offset : offset + limit]
        return {"items": page, "total": total}

    order_by = _build_order_by(tab=tab, sort=resolved_sort, order=resolved_order)
    page_sql = f"SELECT {columns} {from_where} {order_by} LIMIT ? OFFSET ?"
    count_sql = f"SELECT COUNT(*) {from_where}"
    rows = db.execute(page_sql, (limit, offset)).fetchall()
    total = db.execute(count_sql).fetchone()[0]
    items = [row_mapper(r) for r in rows]
    return {"items": items, "total": total}
