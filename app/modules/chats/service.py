from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.filters import ChatListSort
from app.modules.chats.repository import ChatRepository
from app.modules.chats.schemas import ChatCreateRequest, ChatListResponse, ChatStatusPatchRequest
from app.modules.chats.scope import can_view_chat_async, resolve_chats_read_permission
from app.modules.chats.serialization import to_chat_detail, to_chat_list_item
from app.modules.contacts.repository import ContactRepository
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.chat import Chat
from app.modules.db.models.enums import ChatStatus, StatusKind
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL, visible_group_ids, visible_user_ids
from app.modules.statuses.validation import ensure_status_kind
from app.realtime.events import publish
from app.shared.exceptions import Conflict, NotFound, PermissionDenied


@dataclass(frozen=True)
class ChatMutationResult:
    chat: Chat
    audit_payload: dict[str, Any]


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ChatRepository(session)
        self._contacts = ContactRepository(session)
        self._scope_loader = ScopeLoader(session)

    async def list_chats(
        self,
        actor: User,
        *,
        status: ChatStatus | None,
        status_id: int | None,
        assigned_user_id: int | None,
        contact_id: int | None,
        bot_id: int | None,
        unread_only: bool,
        needs_reply: bool,
        card_owner_user_id: int | None,
        assigned_group_id: int | None,
        lead_status_id: int | None,
        lead_open_only: bool | None,
        q: str | None,
        sort: ChatListSort,
        cursor: str | None,
        limit: int,
    ) -> ChatListResponse:
        ctx = await self._scope_loader.load(actor)
        read_perm = resolve_chats_read_permission(actor)
        if assigned_user_id is not None:
            scope_users = visible_user_ids(ctx)
            if scope_users != SCOPE_ALL and (
                not isinstance(scope_users, set) or assigned_user_id not in scope_users
            ):
                raise PermissionDenied(message="Assigned user filter outside scope")
        if card_owner_user_id is not None:
            scope_users = visible_user_ids(ctx)
            if scope_users != SCOPE_ALL and (
                not isinstance(scope_users, set) or card_owner_user_id not in scope_users
            ):
                raise PermissionDenied(message="Card owner filter outside scope")
        if assigned_group_id is not None:
            scope_groups = visible_group_ids(ctx)
            if scope_groups != SCOPE_ALL and (
                not isinstance(scope_groups, set) or assigned_group_id not in scope_groups
            ):
                raise PermissionDenied(message="Group filter outside scope")

        if status_id is not None:
            await self._ensure_status(status_id)

        rows, next_cursor = await self._repo.list_chats(
            ctx=ctx,
            read_perm=read_perm,
            status=status,
            status_id=status_id,
            assigned_user_id=assigned_user_id,
            contact_id=contact_id,
            bot_id=bot_id,
            unread_only=unread_only,
            actor_user_id=actor.id,
            needs_reply=needs_reply,
            card_owner_user_id=card_owner_user_id,
            assigned_group_id=assigned_group_id,
            lead_status_id=lead_status_id,
            lead_open_only=lead_open_only,
            q=q,
            sort=sort,
            cursor=cursor,
            limit=limit,
        )
        unread_map = await self._repo.get_unread_for_me_map(
            [chat.id for chat, _, _ in rows],
            actor.id,
        )
        scope_groups = visible_group_ids(ctx)
        items = []
        for chat, owner_user_id, owner_full_name in rows:
            lead_in_scope = chat.current_lead is None or scope_groups == SCOPE_ALL or (
                isinstance(scope_groups, set) and chat.current_lead.group_id in scope_groups
            )
            item = to_chat_list_item(
                chat,
                unread_for_me=unread_map.get(chat.id, False),
                lead_in_scope=lead_in_scope,
            )
            if chat.assigned_group_id is not None:
                item.card_owner_user_id = owner_user_id
                item.card_owner_name = owner_full_name
                item.card_owner_full_name = owner_full_name
                item.card_owner_group_id = chat.assigned_group_id
            items.append(item)
        return ChatListResponse(
            items=items,
            next_cursor=next_cursor,
        )

    async def get_chat(self, actor: User, chat_id: int) -> dict[str, Any]:
        ctx = await self._scope_loader.load(actor)
        read_perm = resolve_chats_read_permission(actor)
        chat = await self._repo.get_by_id_scoped(chat_id, ctx, read_perm)
        if chat is None:
            raise NotFound(message="Chat not found")
        scope_groups = visible_group_ids(ctx)
        lead_in_scope = scope_groups == SCOPE_ALL or (
            chat.current_lead is None
            or (
                isinstance(scope_groups, set)
                and chat.current_lead.group_id in scope_groups
            )
        )
        payload = to_chat_detail(chat, lead_in_scope=lead_in_scope)
        if chat.assigned_group_id is None:
            return payload
        owner_map = await self._repo.get_card_owner_map(
            {(chat.contact_id, chat.assigned_group_id)},
        )
        owner_user_id, owner_name = owner_map.get(
            (chat.contact_id, chat.assigned_group_id),
            (None, None),
        )
        payload["card_owner_user_id"] = owner_user_id
        payload["card_owner_name"] = owner_name
        payload["card_owner_full_name"] = owner_name
        payload["card_owner_group_id"] = chat.assigned_group_id
        return payload

    async def create_chat(self, actor: User, body: ChatCreateRequest) -> ChatMutationResult:
        ctx = await self._scope_loader.load(actor)
        if not await self._contacts.is_contact_visible(ctx, body.contact_id):
            raise NotFound(message="Contact not found")

        existing = await self._session.execute(
            select(Chat).where(
                Chat.contact_id == body.contact_id,
                Chat.bot_id == body.bot_id,
                Chat.status != ChatStatus.ARCHIVED,
            ),
        )
        if existing.scalar_one_or_none() is not None:
            raise Conflict(message="Active chat already exists for this contact and bot")

        chat = Chat(
            contact_id=body.contact_id,
            bot_id=body.bot_id,
            assigned_user_id=body.assigned_user_id or actor.id,
            assigned_group_id=body.assigned_group_id or actor.group_id,
            assigned_department_id=body.assigned_department_id or actor.department_id,
            status=ChatStatus.OPEN,
            status_id=body.status_id,
        )
        if body.status_id is not None:
            await self._ensure_status(body.status_id)

        chat = await self._repo.add(chat)
        return ChatMutationResult(
            chat=chat,
            audit_payload={"contact_id": body.contact_id, "chat_id": chat.id},
        )

    async def _ensure_status(self, status_id: int) -> None:
        await ensure_status_kind(self._session, status_id, StatusKind.CHAT_LABEL)

    async def _get_mutable_chat(self, actor: User, chat_id: int) -> Chat:
        ctx = await self._scope_loader.load(actor)
        chat = await self._repo.get_by_id(chat_id)
        if chat is None or not await can_view_chat_async(self._session, ctx, chat):
            raise NotFound(message="Chat not found")
        return chat

    async def update_status(
        self,
        actor: User,
        chat_id: int,
        body: ChatStatusPatchRequest,
    ) -> ChatMutationResult:
        chat = await self._get_mutable_chat(actor, chat_id)
        old_status = chat.status
        chat.status = ChatStatus(body.status)
        await self._repo.save(chat)
        await publish(
            "chat.status_changed",
            {
                "chat_id": chat_id,
                "from_status": str(old_status),
                "to_status": body.status,
            },
        )
        return ChatMutationResult(
            chat=chat,
            audit_payload={"from": str(old_status), "to": body.status},
        )

    async def update_status_id(
        self,
        actor: User,
        chat_id: int,
        status_id: int,
    ) -> ChatMutationResult:
        from app.shared.exceptions import PermissionDenied

        raise PermissionDenied(message="Chat workflow status is updated automatically")

    async def archive_chat(self, actor: User, chat_id: int) -> ChatMutationResult:
        chat = await self._get_mutable_chat(actor, chat_id)
        if chat.status == ChatStatus.ARCHIVED:
            raise Conflict(message="Chat is already archived")
        chat.status = ChatStatus.ARCHIVED
        await self._repo.save(chat)
        return ChatMutationResult(chat=chat, audit_payload={"archived": True})
