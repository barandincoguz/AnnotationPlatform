"""3-tab shuffle feed service.

Public API:
  list_feed(db, *, user_id, tab, limit, offset, sort, order) -> dict

Returns:
  {"items": list[FeedItem], "total": int}

Tab semantics (mirror of FeedItem.workflow_state):
  new      -> no annotation row AND no (non-empty) draft by caller
              -> workflow_state in {'new'}
  review   -> annotation row exists AND is_completed=0
              OR no annotation row AND caller has draft with ≥1 ref
              -> workflow_state in {'review', 'draft'}
  verified -> annotation row exists AND is_completed=1
              -> workflow_state in {'verified'}

Sort:
  - sort="shuffle": deterministic per-(user_id, tab, UTC date) shuffle so
    one user gets the same order all day, the order rotates daily, and
    different users see different orders.
  - Any other whitelisted sort key: SQL ORDER BY <column> <direction>,
    always followed by `document_id ASC` as a stable tiebreaker so
    paginated fetches never skip or duplicate on equal keys.
  - sort=None: resolves to DEFAULT_SORT_FOR[tab].

Sort whitelist (per-tab availability noted):
  document_id    -> d.document_id    (all tabs; Phase 6 cross-team
                                      coordination key — DEFAULT)
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
from typing import Optional
from datetime import datetime, timezone


VALID_TABS = ("new", "review", "verified")
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# Cross-team coordination (Phase 6): both this annotator team and the
# partner team (Zeynep) work the same özelge corpus. To preserve the
# "annotate in fixed order" contract the document_id (= evrakOid) is the
# canonical ordering key across teams. DESC matches the user's Neon
# preview (DBeaver `evrak_id` DESC against the partner DB). The new tab
# previously defaulted to `tarih DESC` (deterministic but date-only) and
# review/verified to `updated_at DESC` (user-specific edit time — NOT
# deterministic across teams). Phase 6 unifies all three tabs on
# document_id DESC. The legacy keys (tarih, updated_at, …) remain
# available via the explicit `sort=` query param; the frontend SortMenu
# is hidden behind a localStorage dev flag (`a11n.dev_sort=1`) and does
# not surface them to users.
DEFAULT_SORT_FOR = {
    "new": ("document_id", "desc"),
    "review": ("document_id", "desc"),
    "verified": ("document_id", "desc"),
}

# Whitelist of sort keys → (SQL column expression, allowed-tabs).
# The SQL fragment is interpolated literally; never accept caller input
# into the ORDER BY chain bypassing this mapping.
SORT_COLUMNS: dict[str, tuple[str, frozenset[str]]] = {
    # Phase 6 canonical cross-team ordering key (= evrakOid). Available
    # on all tabs. PRIMARY KEY NOT NULL → no NULL-sink branch fires.
    "document_id": ("d.document_id", frozenset({"new", "review", "verified"})),
    "tarih": ("d.tarih", frozenset({"new", "review", "verified"})),
    "created_at": ("d.created_at", frozenset({"new", "review", "verified"})),
    "sayi": ("d.sayi", frozenset({"new", "review", "verified"})),
    "vergi_turu": ("d.vergi_turu", frozenset({"new", "review", "verified"})),
    "konu": ("d.konu", frozenset({"new", "review", "verified"})),
    "difficulty": ("d.estimated_difficulty", frozenset({"new", "review", "verified"})),
    "word_count": ("d.word_count", frozenset({"new", "review", "verified"})),
    # COALESCE so the review tab can rank draft-only rows (a.updated_at
    # NULL) alongside annotation-backed rows by latest activity. The
    # SQL expression is interpolated literally into ORDER BY — bound
    # parameters never reach here, so injection risk stays zero.
    "updated_at": ("COALESCE(a.updated_at, dr.updated_at)", frozenset({"review", "verified"})),
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
    "d.estimated_difficulty, d.word_count, "
    # `dr.references_json IS NOT NULL` distinguishes "no draft row" from
    # "empty draft row" (the click-then-back-out case). Carried through
    # so _row_to_item_new can produce has_draft.
    "dr.references_json AS draft_refs_json"
)
# "Yeni" = no annotation row AND no draft-with-refs by the calling user.
# The drafts filter keeps tabs mutually exclusive once the Devam Eden
# tab also accepts draft-only documents — without it, a doc with only
# a user draft would appear in both Yeni AND Devam Eden simultaneously.
# Same single bound parameter as the review query: the caller's user_id.
_NEW_FROM_WHERE = (
    "FROM documents_meta d "
    "LEFT JOIN annotations a ON a.document_id = d.document_id "
    "LEFT JOIN drafts dr ON dr.document_id = d.document_id AND dr.user_id = ? "
    "WHERE a.document_id IS NULL "
    "  AND (dr.user_id IS NULL "
    "       OR json_array_length(COALESCE(dr.references_json, '[]')) = 0)"
)

_CHAIN_COLUMNS = (
    "d.document_id, d.sayi, d.tarih, d.konu, d.vergi_turu, "
    "d.estimated_difficulty, d.word_count, "
    "a.is_completed, a.last_editor_user_id, u.username AS last_editor_username, "
    "a.edit_count, a.unique_users_count, "
    # Widened so draft-only review-tab rows (annotation NULL) still get
    # a populated updated_at for sort + UI recency. Falls through to
    # the draft's own updated_at when the annotation row is absent.
    "COALESCE(a.updated_at, dr.updated_at) AS updated_at, "
    "dr.references_json AS draft_refs_json"
)
# Review = "Devam Eden". Two populations live here:
#   1. Shared annotations that exist but are not yet completed
#      (the original, multi-user definition).
#   2. Drafts owned by the current caller that point at a document
#      WITHOUT an annotation row yet — i.e. the user has typed at
#      least one reference into the right pane but has not clicked
#      "Kaydet". Without this, a caller's in-flight work is
#      indistinguishable from "Yeni" until they save, which doesn't
#      match the operator's mental model of "Devam Eden".
#
# The query needs ONE bound parameter (?) — the calling user_id — so
# the drafts LEFT JOIN filters to that caller only. `json_array_length`
# guards against the empty-array draft case (a click-then-back-out
# pattern creates a `[]` draft that should NOT count as "in progress").
_REVIEW_FROM_WHERE = (
    "FROM documents_meta d "
    "LEFT JOIN annotations a ON a.document_id = d.document_id "
    "LEFT JOIN users u ON u.id = a.last_editor_user_id "
    "LEFT JOIN drafts dr ON dr.document_id = d.document_id AND dr.user_id = ? "
    "WHERE (a.document_id IS NOT NULL AND a.is_completed = 0) "
    "   OR (a.document_id IS NULL AND dr.user_id IS NOT NULL "
    "       AND json_array_length(COALESCE(dr.references_json, '[]')) > 0)"
)
_VERIFIED_FROM_WHERE = (
    "FROM documents_meta d "
    "INNER JOIN annotations a ON a.document_id = d.document_id "
    "LEFT JOIN users u ON u.id = a.last_editor_user_id "
    # LEFT JOIN drafts here so _CHAIN_COLUMNS' `dr.references_json` and
    # `COALESCE(a.updated_at, dr.updated_at)` resolve uniformly across
    # all three tabs. Drafts should normally be cleared by complete,
    # but the JOIN tolerates stragglers without breaking the SELECT.
    "LEFT JOIN drafts dr ON dr.document_id = d.document_id AND dr.user_id = ? "
    "WHERE a.is_completed = 1"
)

# Legacy default ORDER BY for the shuffle path. The in-memory shuffle
# rewrites the order anyway, but a deterministic base reads better in
# EXPLAIN QUERY PLAN traces and makes the un-shuffled fallback safer
# if the shuffle ever gets disabled.
_SHUFFLE_FALLBACK_ORDER_BY = {
    "new": "ORDER BY d.created_at DESC, d.document_id ASC",
    # COALESCE for the same reason it's in SORT_COLUMNS: draft-only
    # rows have a.updated_at=NULL and would otherwise sink under the
    # shuffle base ordering.
    "review": "ORDER BY COALESCE(a.updated_at, dr.updated_at) DESC, d.document_id ASC",
    "verified": "ORDER BY a.updated_at DESC, d.document_id ASC",
}

_TAB_PARTS = {
    "new": (_NEW_COLUMNS, _NEW_FROM_WHERE),
    "review": (_CHAIN_COLUMNS, _REVIEW_FROM_WHERE),
    "verified": (_CHAIN_COLUMNS, _VERIFIED_FROM_WHERE),
}


def _row_to_item_new(row: sqlite3.Row) -> dict:
    # New-tab WHERE excludes annotation-bearing rows AND non-empty
    # caller drafts. What can still reach this mapper:
    #   - no draft row at all              (draft_refs_json IS NULL)
    #   - empty draft row from click-back  (draft_refs_json = '[]')
    # Both classify as 'new'. has_draft distinguishes them for the UI.
    has_draft = row["draft_refs_json"] is not None
    return {
        "document_id": row["document_id"],
        "sayi": row["sayi"],
        "tarih": row["tarih"],
        "konu": row["konu"],
        "vergi_turu": row["vergi_turu"],
        "estimated_difficulty": row["estimated_difficulty"],
        "word_count": row["word_count"],
        "workflow_state": "new",
        "has_draft": has_draft,
        "has_annotation": False,
        "is_completed": False,
        "last_editor_user_id": None,
        "last_editor_username": None,
        "edit_count": 0,
        "unique_users_count": 0,
        # New tab carries no meaningful "last activity" time. Even when
        # an empty draft exists, the UI treats this as "untouched" — a
        # touched-then-cleared signal lives in has_draft alone.
        "updated_at": None,
    }


def _row_to_item_chain(row: sqlite3.Row) -> dict:
    # Review tab admits two populations (annotation-backed OR
    # draft-only-by-caller); verified tab is annotation-only. Branch
    # on the annotation-row-NULL signal:
    #   annotation NULL              -> 'draft'   (review tab only,
    #                                              guaranteed by WHERE)
    #   annotation present + flag=0  -> 'review'
    #   annotation present + flag=1  -> 'verified'
    has_annotation = row["is_completed"] is not None
    is_completed = bool(row["is_completed"]) if has_annotation else False
    has_draft = row["draft_refs_json"] is not None

    if not has_annotation:
        workflow_state = "draft"
    elif is_completed:
        workflow_state = "verified"
    else:
        workflow_state = "review"

    return {
        "document_id": row["document_id"],
        "sayi": row["sayi"],
        "tarih": row["tarih"],
        "konu": row["konu"],
        "vergi_turu": row["vergi_turu"],
        "estimated_difficulty": row["estimated_difficulty"],
        "word_count": row["word_count"],
        "workflow_state": workflow_state,
        "has_draft": has_draft,
        "has_annotation": has_annotation,
        "is_completed": is_completed,
        "last_editor_user_id": row["last_editor_user_id"],
        "last_editor_username": row["last_editor_username"],
        "edit_count": row["edit_count"] if has_annotation else 0,
        "unique_users_count": row["unique_users_count"] if has_annotation else 0,
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

    # All three tabs' FROM clauses now bind the caller's user_id to
    # scope the drafts LEFT JOIN. Verified joined drafts post-Phase-1
    # for uniform `dr.references_json` + `COALESCE(...)` resolution in
    # _CHAIN_COLUMNS. One parameter, spliced into every query below.
    from_where_params: tuple = (user_id,)

    if resolved_sort == "shuffle":
        sql = f"SELECT {columns} {from_where} {_SHUFFLE_FALLBACK_ORDER_BY[tab]}"
        rows = db.execute(sql, from_where_params).fetchall()
        items = [row_mapper(r) for r in rows]
        total = len(items)
        items = _shuffle(items, user_id=user_id, tab=tab)
        page = items[offset : offset + limit]
        return {"items": page, "total": total}

    order_by = _build_order_by(tab=tab, sort=resolved_sort, order=resolved_order)
    page_sql = f"SELECT {columns} {from_where} {order_by} LIMIT ? OFFSET ?"
    rows = db.execute(page_sql, (*from_where_params, limit, offset)).fetchall()
    items = [row_mapper(r) for r in rows]
    # COUNT(*) over the new-tab anti-join (~17.9k rows, no covering
    # index on `a.document_id IS NULL`) is the single most expensive
    # scan in this service. The frontend's `useInfiniteQuery` only uses
    # `total` from page 0 to drive `getNextPageParam`; subsequent pages
    # don't need it. Returning `None` for offset > 0 collapses N COUNT
    # executions to 1 across a full scroll (worst-case 360 → 1 for the
    # 17.9k-doc new tab). The frontend treats `None` as "use last known
    # total" — see frontend/src/api/queries/feed.ts.
    if offset == 0:
        # COUNT shares from_where so it carries user_id for ALL tabs
        # post-Phase-1 (drafts LEFT JOIN added to verified for uniform
        # column resolution).
        total: Optional[int] = db.execute(
            f"SELECT COUNT(*) {from_where}",
            from_where_params,
        ).fetchone()[0]
    else:
        total = None
    return {"items": items, "total": total}
