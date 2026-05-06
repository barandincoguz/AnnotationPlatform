"""Pydantic schemas for admin endpoints."""
from typing import Any

from pydantic import BaseModel


class SettingUpdateRequest(BaseModel):
    value: Any


class SettingUpdateResponse(BaseModel):
    key: str
    value: Any
