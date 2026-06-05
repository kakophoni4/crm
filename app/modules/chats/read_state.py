from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.repository import ChatRepository
from app.modules.chats.scope import can_view_chat_async
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.chat_read_state import ChatReadState
from app.modules.db.models.user import User
from app.realtime.events import publish
from app.shared.exceptions import NotFound, ValidationError


async def upsert_read_state(
    session: AsyncSession,
    *,
    user_id: int,
    chat_id: int,
    last_read_message_id: int | None,
) -> None:
    """Update per-user read cursor without committing (caller owns transaction)."""
    now = datetime.now(UTC)
    stmt = insert(ChatReadState).values(
        user_id=user_id,
        chat_id=chat_id,
        last_read_message_id=last_read_message_id,
        read_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "chat_id"],
        set_={
            "last_read_message_id": last_read_message_id,
            "read_at": now,
        },
    )
    await session.execute(stmt)


class ChatReadStateService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ChatRepository(session)
        self._scope_loader = ScopeLoader(session)

    async def _latest_message_id(self, chat_id: int) -> int | None:
        result = await self._session.execute(
            select(func.max(ChatMessage.id)).where(ChatMessage.chat_id == chat_id),
        )
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None

    async def mark_read(
        self,
        actor: User,
        chat_id: int,
        *,
        last_read_message_id: int | None,
    ) -> dict[str, int | str | None]:
        ctx = await self._scope_loader.load(actor)
        chat = await self._repo.get_by_id(chat_id)
        if chat is None or not await can_view_chat_async(self._session, ctx, chat):
            raise NotFound(message="Chat not found")

        latest_id = await self._latest_message_id(chat_id)
        target_id = last_read_message_id if last_read_message_id is not None else latest_id

        if target_id is not None:
            msg = await self._session.execute(
                select(ChatMessage.id).where(
                    ChatMessage.id == target_id,
                    ChatMessage.chat_id == chat_id,
                ),
            )
            if msg.scalar_one_or_none() is None:
                raise ValidationError(message="last_read_message_id not found in chat")

        now = datetime.now(UTC)
        stmt = insert(ChatReadState).values(
            user_id=actor.id,
            chat_id=chat_id,
            last_read_message_id=target_id,
            read_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "chat_id"],
            set_={
                "last_read_message_id": target_id,
                "read_at": now,
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()

        await publish(
            "chat.read",
            {"chat_id": chat_id, "user_id": actor.id, "last_read_message_id": target_id},
        )
        await self._session.commit()

        return {
            "chat_id": chat_id,
            "user_id": actor.id,
            "last_read_message_id": target_id,
            "read_at": now.isoformat(),
        }
