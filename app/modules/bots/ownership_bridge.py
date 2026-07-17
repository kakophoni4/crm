from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.escalation import get_group_settings
from app.modules.contacts.ownership import (
    drop_department_inbox_assignment,
    ensure_assignment,
    get_owner,
    ownership_v2_enabled,
    set_pending_inbound,
)
from app.modules.contacts.realtime_payloads import contact_group_context, user_full_name
from app.modules.db.models.bot import Bot
from app.modules.db.models.chat import Chat
from app.modules.db.models.group import Group
from app.modules.leads.department_inbox import DEPT_INBOX_GROUP_NAME
from app.realtime.events import publish


async def handle_inbound_ownership(
    session: AsyncSession,
    *,
    contact_id: int,
    group_id: int,
    chat_id: int,
    message_preview: str | None = None,
) -> int | None:
    if not ownership_v2_enabled():
        return None

    preferred_owner_id: int | None = None
    chat = await session.get(Chat, chat_id)
    if chat is not None and chat.bot_id is not None:
        bot = await session.get(Bot, chat.bot_id)
        if bot is not None and bot.default_owner_user_id is not None:
            preferred_owner_id = int(bot.default_owner_user_id)

    previous_owner_id = await get_owner(session, contact_id, group_id)
    result = await ensure_assignment(
        session,
        contact_id,
        group_id,
        preferred_owner_user_id=preferred_owner_id,
    )
    await set_pending_inbound(session, contact_id, group_id)

    owner_id = result.owner_user_id
    group = await session.get(Group, group_id)
    if (
        owner_id is not None
        and group is not None
        and group.name != DEPT_INBOX_GROUP_NAME
        and group.department_id is not None
    ):
        await drop_department_inbox_assignment(
            session,
            contact_id=contact_id,
            department_id=int(group.department_id),
        )

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

    owner_changed = previous_owner_id != owner_id
    if result.created or owner_changed:
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
        if result.created:
            try:
                from app.modules.notifications.service import notify_new_card

                await notify_new_card(
                    session,
                    contact_id=contact_id,
                    group_id=group_id,
                    chat_id=chat_id,
                    owner_user_id=owner_id,
                )
            except Exception:
                import structlog

                structlog.get_logger(__name__).exception(
                    "staff_notify_new_card_failed",
                    contact_id=contact_id,
                    owner_user_id=owner_id,
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
        try:
            from app.modules.notifications.service import notify_owner_inbound

            pending_at = result.assignment.pending_inbound_at
            if pending_at is not None:
                await notify_owner_inbound(
                    session,
                    contact_id=contact_id,
                    group_id=group_id,
                    chat_id=chat_id,
                    owner_user_id=owner_id,
                    pending_at=pending_at,
                    message_preview=message_preview,
                )
        except Exception:
            import structlog

            structlog.get_logger(__name__).exception(
                "staff_notify_owner_inbound_failed",
                contact_id=contact_id,
                owner_user_id=owner_id,
            )

    return owner_id
