"""Pydantic schemas for user feedback endpoints."""
from typing import Literal
from pydantic import BaseModel


FeedbackType = Literal["complaint", "suggestion"]


class FeedbackCreateRequest(BaseModel):
    type: FeedbackType
    message: str


class FeedbackRow(BaseModel):
    id: int
    user_id: int
    username: str
    type: FeedbackType
    message: str
    created_at: str
