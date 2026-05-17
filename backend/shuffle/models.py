"""Pydantic response models for the shuffle feed."""
from typing import Literal, Optional
from pydantic import BaseModel


class FeedItem(BaseModel):
    document_id: str
    sayi: Optional[int]
    tarih: Optional[str]
    konu: Optional[str]
    vergi_turu: Optional[str]
    estimated_difficulty: str
    word_count: int

    # Canonical 4-state workflow classification — single source of truth
    # for status branding. Computed server-side from the (annotation,
    # is_completed, caller-draft-refs) tuple so the frontend stops
    # juggling has_annotation && !is_completed && hasDraft ternaries:
    #   'new'      no annotation row AND no (non-empty) draft by caller
    #   'draft'    no annotation row AND caller has draft with ≥1 ref
    #   'review'   annotation row exists, is_completed=False
    #   'verified' annotation row exists, is_completed=True
    workflow_state: Literal["new", "draft", "review", "verified"]

    # True if the caller owns ANY draft row on this document (incl. an
    # empty `[]`). Surfaces "you've opened this" hints in the UI even
    # when the user backed out without typing.
    has_draft: bool

    # Legacy flags retained for backward compat. Phase 3 will migrate
    # the frontend to consume `workflow_state` exclusively and these
    # may be removed afterwards. Derivable today:
    #   has_annotation = workflow_state in ('review', 'verified')
    #   is_completed   = workflow_state == 'verified'
    has_annotation: bool
    is_completed: bool

    last_editor_user_id: Optional[int]
    last_editor_username: Optional[str]
    edit_count: int
    unique_users_count: int
    # COALESCE(annotation.updated_at, caller-draft.updated_at). Lets
    # the review tab sort draft-only rows alongside in-flight annotations
    # by latest activity instead of dumping NULL-bearing rows to the
    # end of the list.
    updated_at: Optional[str]


class FeedResponse(BaseModel):
    items: list[FeedItem]
    # Total is returned ONLY on page 0 (offset=0). Page 1+ omits it
    # because COUNT(*) over the new-tab anti-join is the most expensive
    # scan in this service and the frontend's `useInfiniteQuery` only
    # consults page 0's total via getNextPageParam. Optional[int] keeps
    # the OpenAPI contract honest about the new shape.
    total: Optional[int] = None
