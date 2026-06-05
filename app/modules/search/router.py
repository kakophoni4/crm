from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.search.rate_limit import enforce_search_rate_limit
from app.modules.search.schemas import GlobalSearchResponse
from app.modules.search.service import GlobalSearchService
from app.modules.search.types import parse_search_types
from app.shared.db import get_db
from app.shared.security.deps import current_user

router = APIRouter(prefix="/api/v1/search", tags=["search"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> GlobalSearchService:
    return GlobalSearchService(db)


async def _actor_with_search_rate_limit(
    actor: Annotated[User, Depends(current_user)],
) -> User:
    await enforce_search_rate_limit(actor.id)
    return actor


@router.get("", response_model=GlobalSearchResponse)
async def global_search(
    actor: Annotated[User, Depends(_actor_with_search_rate_limit)],
    service: Annotated[GlobalSearchService, Depends(_service)],
    q: str = Query(min_length=2),
    types: str | None = None,
    limit_per_type: int = Query(default=10, ge=1, le=25),
    contacts_cursor: str | None = None,
    messages_cursor: str | None = None,
    chats_cursor: str | None = None,
) -> GlobalSearchResponse:
    return await service.search(
        actor,
        q=q,
        types=parse_search_types(types),
        limit_per_type=limit_per_type,
        contacts_cursor=contacts_cursor,
        messages_cursor=messages_cursor,
        chats_cursor=chats_cursor,
    )
