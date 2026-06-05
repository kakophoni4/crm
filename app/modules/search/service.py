from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.repository import ChatRepository
from app.modules.chats.schemas import ChatListItemResponse, ChatMessageSearchItem
from app.modules.chats.scope import resolve_chats_read_permission
from app.modules.chats.search import ChatSearchService
from app.modules.chats.serialization import to_chat_list_item
from app.modules.contacts.repository import ContactRepository
from app.modules.contacts.schemas import ContactResponse
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.contacts.serialization import to_contact_response
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.rbac.role_map import has_any_permission, has_permission
from app.modules.search.schemas import (
    GlobalSearchResponse,
    SearchResultSection,
    SearchType,
)
from app.shared.exceptions import PermissionDenied


class GlobalSearchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._contacts = ContactRepository(session)
        self._chats = ChatRepository(session)
        self._messages = ChatSearchService(session)
        self._scope_loader = ScopeLoader(session)

    def _ensure_type_permissions(self, actor: User, types: set[SearchType]) -> None:
        role = actor.role
        if SearchType.CONTACTS in types and not has_permission(role, Permission.CONTACTS_READ):
            raise PermissionDenied(message="Missing permission for contact search")

        chat_types = {SearchType.MESSAGES, SearchType.CHATS} & types
        if chat_types and not has_any_permission(
            role,
            (
                Permission.CHATS_READ_OWN,
                Permission.CHATS_READ_GROUP,
                Permission.CHATS_READ_DEPARTMENT,
                Permission.CHATS_READ_ALL,
            ),
        ):
            raise PermissionDenied(message="Missing permission for chat/message search")

    async def search(
        self,
        actor: User,
        *,
        q: str,
        types: set[SearchType],
        limit_per_type: int,
        contacts_cursor: str | None,
        messages_cursor: str | None,
        chats_cursor: str | None,
    ) -> GlobalSearchResponse:
        self._ensure_type_permissions(actor, types)
        ctx = await self._scope_loader.load(actor)
        read_perm = resolve_chats_read_permission(actor)

        contacts_section: SearchResultSection[ContactResponse] = SearchResultSection()
        messages_section: SearchResultSection[ChatMessageSearchItem] = SearchResultSection()
        chats_section: SearchResultSection[ChatListItemResponse] = SearchResultSection()

        if SearchType.CONTACTS in types:
            rows, next_cursor = await self._contacts.search_contacts(
                ctx=ctx,
                q=q,
                cursor=contacts_cursor,
                limit=limit_per_type,
            )
            contacts_section = SearchResultSection(
                items=[
                    ContactResponse.model_validate(to_contact_response(row, actor=actor))
                    for row in rows
                ],
                next_cursor=next_cursor,
            )

        if SearchType.MESSAGES in types:
            msg_result = await self._messages.search_messages(
                actor,
                q=q,
                scope=None,
                cursor=messages_cursor,
                limit=limit_per_type,
                highlight=True,
            )
            messages_section = SearchResultSection(
                items=msg_result.items,
                next_cursor=msg_result.next_cursor,
            )

        if SearchType.CHATS in types:
            chat_rows, next_cursor = await self._chats.search_chats(
                ctx=ctx,
                read_perm=read_perm,
                q=q,
                cursor=chats_cursor,
                limit=limit_per_type,
            )
            owner_pairs = {
                (row.contact_id, row.assigned_group_id)
                for row in chat_rows
                if row.assigned_group_id is not None
            }
            owner_map = await self._chats.get_card_owner_map(owner_pairs)
            chat_items = []
            for row in chat_rows:
                item = to_chat_list_item(row)
                if row.assigned_group_id is not None:
                    owner_user_id, owner_name = owner_map.get(
                        (row.contact_id, row.assigned_group_id),
                        (None, None),
                    )
                    item.card_owner_user_id = owner_user_id
                    item.card_owner_name = owner_name
                    item.card_owner_group_id = row.assigned_group_id
                chat_items.append(item)
            chats_section = SearchResultSection(items=chat_items, next_cursor=next_cursor)

        return GlobalSearchResponse(
            contacts=contacts_section,
            messages=messages_section,
            chats=chats_section,
        )
