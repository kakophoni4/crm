from __future__ import annotations

from pydantic import BaseModel, Field


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int = Field(default=60, ge=1)
