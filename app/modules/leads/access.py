from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.scope import can_view_chat_async
from app.modules.db.models.chat import Chat
from app.modules.db.models.enums import UserRole
from app.modules.db.models.group import Group
from app.modules.db.models.lead import Lead
from app.modules.rbac.scope import (
    SCOPE_ALL,
    ScopeContext,
    visible_department_ids,
    visible_group_ids,
)


async def get_group_department_id(session: AsyncSession, group_id: int) -> int | None:
    result = await session.execute(
        select(Group.department_id).where(Group.id == group_id),
    )
    return result.scalar_one_or_none()


async def actor_can_access_lead(
    session: AsyncSession,
    ctx: ScopeContext,
    lead: Lead,
) -> bool:
    """Whether actor may read or mutate this lead (independent of card ownership)."""
    groups = visible_group_ids(ctx)
    if groups == SCOPE_ALL:
        return True
    if isinstance(groups, set) and lead.group_id in groups:
        return True

    actor = ctx.actor
    role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))

    if role == UserRole.SENIOR:
        dept_ids = visible_department_ids(ctx)
        if isinstance(dept_ids, set) and dept_ids:
            group_dept = await get_group_department_id(session, lead.group_id)
            if group_dept is not None and group_dept in dept_ids:
                return True
        if actor.group_id is not None and lead.group_id == actor.group_id:
            return True
        actor_groups = ctx.actor_group_ids
        if actor_groups and lead.group_id in actor_groups:
            return True

    # Any deal on a chat the actor can view (not only current_lead) —
    # side panel lets managers open/close older deals on the same chat.
    if lead.chat_id is not None:
        chat = await session.get(Chat, lead.chat_id)
        if chat is not None and await can_view_chat_async(session, ctx, chat):
            return True

    return False
