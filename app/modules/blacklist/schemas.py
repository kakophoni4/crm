from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

BlacklistKind = Literal["telegram_username", "buyer_inn"]


class BlacklistCreateRequest(BaseModel):
    kind: BlacklistKind
    value: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2000)


class BlacklistEntryResponse(BaseModel):
    id: int
    kind: BlacklistKind
    value: str
    reason: str
    created_by: int
    created_at: datetime


class BlacklistListResponse(BaseModel):
    items: list[BlacklistEntryResponse]
