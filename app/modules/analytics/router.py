from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.repository import AnalyticsRepository
from app.modules.analytics.schemas import OperatorAnalyticsResponse
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.rbac.scope import SCOPE_ALL, visible_user_ids
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

_PERIOD_DAYS: dict[str, int | None] = {
    "last_7_days": 7,
    "last_30_days": 30,
    "all": None,
}


@router.get("/operators", response_model=OperatorAnalyticsResponse)
async def operator_analytics(
    actor: Annotated[User, Depends(requires_permission(Permission.ANALYTICS_READ))],
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Literal["last_7_days", "last_30_days", "all"] = "last_7_days",
) -> OperatorAnalyticsResponse:
    ctx = await ScopeLoader(db).load(actor)
    scope_users = visible_user_ids(ctx)
    scoped_ids: set[int] | Literal["ALL"] = (
        SCOPE_ALL if scope_users == SCOPE_ALL else scope_users
    )

    repo = AnalyticsRepository(db)
    operators = await repo.get_operator_stats(scoped_ids, _PERIOD_DAYS[period])
    return OperatorAnalyticsResponse(period=period, operators=operators)
