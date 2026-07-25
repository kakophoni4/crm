from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.scope import can_view_chat
from app.modules.db.models.bot_group_assignment import BotGroupAssignment
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


async def get_group_department_ids_map(
    session: AsyncSession,
    group_ids: set[int],
) -> dict[int, int | None]:
    if not group_ids:
        return {}
    result = await session.execute(
        select(Group.id, Group.department_id).where(Group.id.in_(group_ids)),
    )
    return {int(gid): dept_id for gid, dept_id in result.all()}


async def _bot_assigned_groups_map(
    session: AsyncSession,
    bot_ids: set[int],
) -> dict[int, set[int]]:
    if not bot_ids:
        return {}
    result = await session.execute(
        select(BotGroupAssignment.bot_id, BotGroupAssignment.group_id).where(
            BotGroupAssignment.bot_id.in_(bot_ids),
        ),
    )
    out: dict[int, set[int]] = {}
    for bot_id, group_id in result.all():
        out.setdefault(int(bot_id), set()).add(int(group_id))
    return out


def _can_view_chat_via_bot_groups(
    ctx: ScopeContext,
    chat: Chat,
    bot_groups: set[int],
) -> bool:
    if can_view_chat(ctx, chat):
        return True
    if chat.bot_id is None:
        return False
    group_ids = visible_group_ids(ctx)
    if group_ids == SCOPE_ALL:
        return True
    if not isinstance(group_ids, set) or not group_ids:
        return False
    return bool(bot_groups & group_ids)


def _senior_grants_lead(
    ctx: ScopeContext,
    lead: Lead,
    *,
    dept_ids: set[int] | str,
    group_dept: int | None,
) -> bool:
    actor = ctx.actor
    if isinstance(dept_ids, set) and dept_ids:
        if group_dept is not None and group_dept in dept_ids:
            return True
    if actor.group_id is not None and lead.group_id == actor.group_id:
        return True
    actor_groups = ctx.actor_group_ids
    return bool(actor_groups and lead.group_id in actor_groups)


async def actor_can_access_leads_map(
    session: AsyncSession,
    ctx: ScopeContext,
    leads: list[Lead],
) -> dict[int, bool]:
    """Batch version of actor_can_access_lead for list endpoints."""
    if not leads:
        return {}

    groups = visible_group_ids(ctx)
    if groups == SCOPE_ALL:
        return {lead.id: True for lead in leads}

    result: dict[int, bool] = {}
    pending: list[Lead] = []
    if isinstance(groups, set):
        for lead in leads:
            if lead.group_id in groups:
                result[lead.id] = True
            else:
                pending.append(lead)
    else:
        pending = list(leads)

    if not pending:
        return result

    actor = ctx.actor
    role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))

    if role == UserRole.SENIOR:
        dept_ids = visible_department_ids(ctx)
        group_dept_map: dict[int, int | None] = {}
        if isinstance(dept_ids, set) and dept_ids:
            group_dept_map = await get_group_department_ids_map(
                session,
                {lead.group_id for lead in pending},
            )
        still_pending: list[Lead] = []
        for lead in pending:
            if _senior_grants_lead(
                ctx,
                lead,
                dept_ids=dept_ids if isinstance(dept_ids, set) else set(),
                group_dept=group_dept_map.get(lead.group_id),
            ):
                result[lead.id] = True
            else:
                still_pending.append(lead)
        pending = still_pending

    if pending:
        chat_ids = {lead.chat_id for lead in pending if lead.chat_id is not None}
        chats_by_id: dict[int, Chat] = {}
        if chat_ids:
            chat_rows = await session.execute(select(Chat).where(Chat.id.in_(chat_ids)))
            chats_by_id = {int(chat.id): chat for chat in chat_rows.scalars().all()}

        bot_ids = {
            chat.bot_id
            for chat in chats_by_id.values()
            if chat.bot_id is not None
        }
        bot_groups_map = await _bot_assigned_groups_map(session, bot_ids)

        for lead in pending:
            granted = False
            if lead.chat_id is not None:
                chat = chats_by_id.get(lead.chat_id)
                if chat is not None:
                    bot_groups = bot_groups_map.get(chat.bot_id or -1, set())
                    granted = _can_view_chat_via_bot_groups(ctx, chat, bot_groups)
            result[lead.id] = granted

    return result


async def actor_can_access_lead(
    session: AsyncSession,
    ctx: ScopeContext,
    lead: Lead,
) -> bool:
    """Whether actor may read or mutate this lead (independent of card ownership)."""
    return (await actor_can_access_leads_map(session, ctx, [lead])).get(lead.id, False)
