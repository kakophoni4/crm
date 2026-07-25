from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.cursor import encode_message_cursor
from app.modules.chats.repository import ChatRepository
from app.modules.chats.schemas import ChatMessageSearchItem, ChatMessageSearchResponse
from app.modules.chats.scope import resolve_chats_read_permission
from app.modules.chats.search_scope import ChatSearchScope, default_search_scope
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.user import User


class ChatSearchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ChatRepository(session)
        self._scope_loader = ScopeLoader(session)

    async def search_messages(
        self,
        actor: User,
        *,
        q: str,
        scope: ChatSearchScope | None,
        cursor: str | None,
        limit: int,
        highlight: bool = True,
    ) -> ChatMessageSearchResponse:
        effective_scope = scope if scope is not None else default_search_scope(actor)
        ctx = await self._scope_loader.load(actor)
        read_perm = resolve_chats_read_permission(actor)

        rows = await self._repo.search_messages(
            ctx=ctx,
            read_perm=read_perm,
            scope=effective_scope,
            q=q,
            cursor=cursor,
            limit=limit,
            highlight=highlight,
        )

        owner_pairs = {
            (row.contact_id, row.assigned_group_id)
            for row in rows
            if row.assigned_group_id is not None
        }
        owner_map = await self._repo.get_card_owner_map(owner_pairs)

        items: list[ChatMessageSearchItem] = []
        for row in rows[:limit]:
            card_owner_user_id: int | None = None
            if row.assigned_group_id is not None:
                card_owner_user_id, _ = owner_map.get(
                    (row.contact_id, row.assigned_group_id),
                    (None, None),
                )
            items.append(
                ChatMessageSearchItem(
                    chat_id=row.chat_id,
                    contact_id=row.contact_id,
                    message_id=row.message_id,
                    snippet=row.snippet,
                    matched_at=row.matched_at,
                    lead_id=row.lead_id,
                    card_owner_user_id=card_owner_user_id,
                ),
            )

        next_cursor: str | None = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = encode_message_cursor(last.matched_at, last.message_id)

        return ChatMessageSearchResponse(items=items, next_cursor=next_cursor)
