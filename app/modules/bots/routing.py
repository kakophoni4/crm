from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.repository import BotRepository
from app.modules.db.models.bot import Bot
from app.modules.db.models.enums import BotOwnerType


@dataclass(frozen=True)
class BotRoutingTarget:
    owner_type: BotOwnerType
    owner_id: int
    department_id: int
    lead_group_id: int | None
    candidate_group_ids: list[int]


async def resolve_bot_routing(session: AsyncSession, bot: Bot) -> BotRoutingTarget:
    repo = BotRepository(session)
    group_ids = await repo.list_assigned_group_ids(bot.id)
    department_id = bot.department_id

    if len(group_ids) == 1:
        group_id = group_ids[0]
        return BotRoutingTarget(
            owner_type=BotOwnerType.GROUP,
            owner_id=group_id,
            department_id=department_id,
            lead_group_id=group_id,
            candidate_group_ids=group_ids,
        )

    return BotRoutingTarget(
        owner_type=BotOwnerType.DEPARTMENT,
        owner_id=department_id,
        department_id=department_id,
        lead_group_id=None,
        candidate_group_ids=group_ids,
    )
