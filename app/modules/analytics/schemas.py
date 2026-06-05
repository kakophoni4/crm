from __future__ import annotations

from pydantic import BaseModel

from app.modules.db.models.enums import UserPresence


class OperatorStats(BaseModel):
    user_id: int
    full_name: str
    presence: UserPresence
    active_chats_count: int
    closed_chats_count: int
    avg_first_response_minutes: float | None


class OperatorAnalyticsResponse(BaseModel):
    period: str
    operators: list[OperatorStats]
