from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.workflow_status import on_inbound_from_client
from app.modules.contacts.escalation import get_group_settings
from app.modules.contacts.ownership import (
    ensure_assignment,
    ownership_v2_enabled,
    set_pending_inbound,
)
from app.modules.contacts.realtime_payloads import contact_group_context, user_full_name
from app.realtime.events import publish


async def handle_inbound_ownership(
    session: AsyncSession,
    *,
    contact_id: int,
    group_id: int,
    chat_id: int,
) -> int | None:
    if not ownership_v2_enabled():
        return None

    result = await ensure_assignment(session, contact_id, group_id)
    await set_pending_inbound(session, contact_id, group_id)
    await on_inbound_from_client(session, chat_id)

    owner_id = result.owner_user_id
    if owner_id is None:
        return None

    settings = await get_group_settings(session, group_id)
    ctx = await contact_group_context(
        session,
        contact_id,
        group_id,
        include_chat_id=False,
    )
    ctx["chat_id"] = chat_id

    if result.created:
        owner_name = await user_full_name(session, owner_id)
        await publish(
            "contact.ownership.assigned",
            {
                **ctx,
                "owner_user_id": owner_id,
                "owner_full_name": owner_name,
                "source": result.assignment.assignment_source,
            },
            scope={"group_id": group_id},
        )

    if settings.notify_owner_on_inbound:
        owner_name = await user_full_name(session, owner_id)
        await publish(
            "contact.escalation.owner_notify",
            {
                **ctx,
                "owner_user_id": owner_id,
                "owner_full_name": owner_name,
            },
            scope={"user_id": owner_id},
        )

    return owner_id
