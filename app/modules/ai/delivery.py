"""Last-minute validity gate for persisted AI outbox operations."""

from typing import Any

from sqlalchemy import select

from app.modules.db.models.ai import AIChatState, AIRequest
from app.modules.db.models.blacklist_entry import BlacklistEntry
from app.modules.db.models.chat import Chat
from app.modules.db.models.contact import Contact
from app.shared.settings import settings


async def allowed(db: Any, chat: Any) -> bool:
    if not chat or str(chat.status) in ("closed", "archived"):
        return False
    contact = await db.get(Contact, chat.contact_id)
    if (
        not contact
        or contact.archived_at
        or str(contact.status) in ("disabled", "merged", "archived")
    ):
        return False
    if contact.telegram_username:
        blocked = await db.scalar(
            select(BlacklistEntry.id)
            .where(
                BlacklistEntry.kind == "telegram_username",
                BlacklistEntry.value == contact.telegram_username.lstrip("@").lower(),
            )
            .limit(1)
        )
        if blocked:
            return False
    return True


async def validate_outbox(db: Any, row: Any) -> bool:
    if not row.request_id.startswith("crm-chat-"):
        return True
    from app.modules.db.models.enums import BotOutboundStatus

    request = await db.get(AIRequest, row.request_id)
    state = (
        await db.scalar(
            select(AIChatState).where(AIChatState.chat_id == request.chat_id).with_for_update()
        )
        if request
        else None
    )
    chat = await db.get(Chat, request.chat_id) if request else None
    from sqlalchemy import func, or_

    from app.modules.db.models.chat_message import ChatMessage

    latest = (
        await db.scalar(
            select(func.max(ChatMessage.id)).where(
                ChatMessage.chat_id == request.chat_id,
                ChatMessage.kind != "system",
                or_(ChatMessage.direction == "inbound", ChatMessage.sender_user_id.is_not(None)),
            )
        )
        if request
        else None
    )
    valid = bool(
        request
        and state
        and settings.ai_auto_replies_enabled
        and state.mode != "OFF"
        and state.revision == request.meta["revision"]
        and latest == request.meta["trigger_message_id"]
        and await allowed(db, chat)
    )
    if not valid or row.attempts:
        row.status = BotOutboundStatus.FAILED
        row.last_error = (
            "AI result obsolete"
            if not valid
            else "AI delivery uncertain; manual verification required"
        )
        if request:
            request.status = "obsolete" if not valid else "delivery_uncertain"
        if state and request and request.body.get("mode") == "fallback" and not row.attempts:
            state.data = {**state.data, "fallback_done": False}
        await db.commit()
        return False
    return True
