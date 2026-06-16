from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.schemas_transfer import ContactBotLink
from app.modules.db.models.bot import Bot
from app.modules.db.models.chat import Chat
from app.modules.db.models.enums import ChatStatus


def _resolve_chat_status(status: object) -> ChatStatus:
    if isinstance(status, ChatStatus):
        return status
    return ChatStatus(str(status))


async def load_contact_linked_bots(
    session: AsyncSession,
    contact_id: int,
) -> list[ContactBotLink]:
    result = await session.execute(
        select(Chat, Bot)
        .join(Bot, Bot.id == Chat.bot_id)
        .where(
            Chat.contact_id == contact_id,
            Chat.bot_id.isnot(None),
        )
        .order_by(Chat.bot_id, Chat.id.desc()),
    )
    by_bot: dict[int, tuple[Chat, Bot]] = {}
    for chat, bot in result.all():
        bot_id = int(chat.bot_id)
        prev = by_bot.get(bot_id)
        if prev is None:
            by_bot[bot_id] = (chat, bot)
            continue
        prev_chat = prev[0]
        prev_archived = _resolve_chat_status(prev_chat.status) == ChatStatus.ARCHIVED
        chat_archived = _resolve_chat_status(chat.status) == ChatStatus.ARCHIVED
        if prev_archived and not chat_archived:
            by_bot[bot_id] = (chat, bot)
    items = [
        ContactBotLink(
            bot_id=int(bot.id),
            bot_code=bot.code,
            bot_name=bot.name,
            chat_id=int(chat.id),
            chat_status=_resolve_chat_status(chat.status),
        )
        for chat, bot in by_bot.values()
    ]
    return sorted(items, key=lambda row: row.bot_name.casefold())
