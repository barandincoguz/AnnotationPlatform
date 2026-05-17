"""Pydantic response models for the shuffle feed."""
from typing import Optional
from pydantic import BaseModel


class FeedItem(BaseModel):
    document_id: str
    sayi: Optional[int]
    tarih: Optional[str]
    konu: Optional[str]
    vergi_turu: Optional[str]
    estimated_difficulty: str
    word_count: int

    has_annotation: bool
    is_completed: bool
    last_editor_user_id: Optional[int]
    last_editor_username: Optional[str]
    edit_count: int
    unique_users_count: int
    updated_at: Optional[str]


class FeedResponse(BaseModel):
    items: list[FeedItem]
    # Total is returned ONLY on page 0 (offset=0). Page 1+ omits it
    # because COUNT(*) over the new-tab anti-join is the most expensive
    # scan in this service and the frontend's `useInfiniteQuery` only
    # consults page 0's total via getNextPageParam. Optional[int] keeps
    # the OpenAPI contract honest about the new shape.
    total: Optional[int] = None
