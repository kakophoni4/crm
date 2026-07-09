from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.chat import Chat
from app.modules.db.models.enums import ChatStatus
from app.modules.db.models.user import User
from app.modules.leads.repository import LeadRepository
from app.modules.leads.service import LeadService
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, visible_group_ids
from app.modules.users.memberships import list_user_group_ids
from app.shared.exceptions import PermissionDenied, ValidationError


@dataclass(frozen=True)
class ContactWorkspaceResult:
    chat_id: int
    lead_id: int
    group_id: int
    created_chat: bool
    created_lead: bool


def _department_fallback_group_id(ctx: ScopeContext) -> int | None:
    dept_groups = set(ctx.department_group_ids)
    if dept_groups:
        return min(dept_groups)
    return None


async def resolve_workspace_group_id(
    session: AsyncSession,
    *,
    actor: User,
    ctx: ScopeContext,
    requested_group_id: int | None,
) -> int:
    scope_groups = visible_group_ids(ctx)

    if requested_group_id is not None:
        if scope_groups != SCOPE_ALL and (
            not isinstance(scope_groups, set) or requested_group_id not in scope_groups
        ):
            raise PermissionDenied(message="Cannot create lead in this group")
        return requested_group_id

    actor_groups = await list_user_group_ids(session, actor.id)
    if actor.group_id is not None:
        actor_groups = sorted(set(actor_groups) | {int(actor.group_id)})

    if scope_groups == SCOPE_ALL:
        if actor_groups:
            return actor_groups[0]
        dept_group = _department_fallback_group_id(ctx)
        if dept_group is not None:
            return dept_group
        raise ValidationError(message="Укажите группу для создания диалога")

    if isinstance(scope_groups, set) and scope_groups:
        preferred = [gid for gid in actor_groups if gid in scope_groups]
        if preferred:
            return preferred[0]
        return min(scope_groups)

    if actor_groups:
        return actor_groups[0]

    dept_group = _department_fallback_group_id(ctx)
    if dept_group is not None:
        return dept_group

    raise ValidationError(
        message="Нет назначенной группы — обратитесь к руководителю или администратору",
    )


async def ensure_offline_workspace(
    session: AsyncSession,
    *,
    actor: User,
    ctx: ScopeContext,
    contact_id: int,
    group_id: int | None = None,
) -> ContactWorkspaceResult:
    """Create or reuse manual chat + open lead for contacts outside Telegram."""
    resolved_group_id = await resolve_workspace_group_id(
        session,
        actor=actor,
        ctx=ctx,
        requested_group_id=group_id,
    )

    existing_chat = (
        await session.execute(
            select(Chat).where(
                Chat.contact_id == contact_id,
                Chat.bot_id.is_(None),
                Chat.assigned_group_id == resolved_group_id,
                Chat.status != ChatStatus.ARCHIVED,
            ),
        )
    ).scalar_one_or_none()

    created_chat = False
    if existing_chat is None:
        chat = Chat(
            contact_id=contact_id,
            bot_id=None,
            assigned_user_id=actor.id,
            assigned_group_id=resolved_group_id,
            assigned_department_id=actor.department_id,
            status=ChatStatus.OPEN,
        )
        session.add(chat)
        await session.flush()
        await session.refresh(chat)
        created_chat = True
        chat_id = int(chat.id)
    else:
        chat_id = int(existing_chat.id)

    lead_service = LeadService(session)
    lead_repo = LeadRepository(session)
    existing_lead = await lead_repo.get_open(contact_id, resolved_group_id)
    created_lead = existing_lead is None
    lead = await lead_service.ensure_open_lead(
        contact_id=contact_id,
        group_id=resolved_group_id,
        bot_id=None,
        chat_id=chat_id,
        source="manual",
    )

    return ContactWorkspaceResult(
        chat_id=chat_id,
        lead_id=int(lead.id),
        group_id=resolved_group_id,
        created_chat=created_chat,
        created_lead=created_lead,
    )
