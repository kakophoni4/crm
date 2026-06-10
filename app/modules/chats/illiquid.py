"""Archive / restore chats for illiquid (disabled) contacts."""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.chat import Chat
from app.modules.db.models.enums import ChatStatus


async def archive_contact_chats(session: AsyncSession, contact_id: int) -> int:
    result = await session.execute(
        update(Chat)
        .where(
            Chat.contact_id == contact_id,
            Chat.status != ChatStatus.ARCHIVED,
        )
        .values(status=ChatStatus.ARCHIVED)
    )
    return int(result.rowcount or 0)


async def restore_chat_on_inbound(session: AsyncSession, chat_id: int) -> bool:
    chat = await session.get(Chat, chat_id)
    if chat is None or chat.status != ChatStatus.ARCHIVED:
        return False
    chat.status = ChatStatus.OPEN
    return True
