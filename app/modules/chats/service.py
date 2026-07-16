from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.chats_bridge import upsert_chat_for_bot, upsert_contact_from_telegram
from app.modules.bots.repository import BotRepository
from app.modules.bots.routing import resolve_bot_routing
from app.modules.chats.filters import ChatListSort
from app.modules.chats.needs_reply import chat_list_needs_reply
from app.modules.chats.repository import ChatRepository
from app.modules.chats.schemas import (
    ChatCreateRequest,
    ChatListResponse,
    ChatStatusPatchRequest,
    WhatsappOutreachRequest,
    WhatsappOutreachResponse,
)
from app.modules.chats.scope import can_view_chat_async, resolve_chats_read_permission
from app.modules.chats.serialization import to_chat_detail, to_chat_list_item
from app.modules.contacts.repository import ContactRepository
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.bot import Bot
from app.modules.db.models.chat import Chat
from app.modules.db.models.enums import BotChannel, BotOwnerType, ChatStatus, StatusKind
from app.modules.db.models.user import User
from app.modules.leads.access import actor_can_access_lead
from app.modules.leads.department_inbox import get_department_inbox_group_id
from app.modules.rbac.scope import (
    SCOPE_ALL,
    visible_department_ids,
    visible_group_ids,
    visible_user_ids,
)
from app.modules.statuses.validation import ensure_status_kind
from app.realtime.events import publish
from app.shared.exceptions import Conflict, NotFound, PermissionDenied, ValidationError


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
            [chat.id for chat, *_ in rows],
            actor.id,
        )
        bot_ids = {chat.bot_id for chat, *_ in rows if chat.bot_id is not None}
        bot_names: dict[int, str] = {}
        if bot_ids:
            bot_rows = await self._session.execute(
                select(Bot.id, Bot.name).where(Bot.id.in_(bot_ids)),
            )
            bot_names = {int(bid): str(name) for bid, name in bot_rows.all()}
        items = []
        for (
            chat,
            owner_user_id,
            owner_full_name,
            pending_inbound_at,
            escalated_at,
            last_direction,
        ) in rows:
            lead_in_scope = chat.current_lead is None or await actor_can_access_lead(
                self._session,
                ctx,
                chat.current_lead,
            )
            item = to_chat_list_item(
                chat,
                unread_for_me=unread_map.get(chat.id, False),
                lead_in_scope=lead_in_scope,
                bot_name=bot_names.get(chat.bot_id) if chat.bot_id is not None else None,
            )
            item.pending_inbound_at = pending_inbound_at
            item.escalated_at = escalated_at
            item.needs_reply = chat_list_needs_reply(
                escalated_at=escalated_at,
                last_direction=last_direction,
            )
            owner_group_id = chat.assigned_group_id
            if owner_group_id is None and chat.assigned_department_id is not None:
                owner_group_id = await get_department_inbox_group_id(
                    self._session,
                    chat.assigned_department_id,
                )
            if owner_group_id is None and chat.current_lead is not None:
                owner_group_id = chat.current_lead.group_id
            if owner_group_id is not None:
                item.card_owner_group_id = owner_group_id
            if owner_user_id is not None and owner_group_id is not None:
                item.card_owner_user_id = owner_user_id
                item.card_owner_name = owner_full_name
                item.card_owner_full_name = owner_full_name
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
        lead_in_scope = chat.current_lead is None or await actor_can_access_lead(
            self._session,
            ctx,
            chat.current_lead,
        )
        bot_name: str | None = None
        if chat.bot_id is not None:
            bot_row = await self._session.execute(
                select(Bot.name).where(Bot.id == chat.bot_id),
            )
            bot_name = bot_row.scalar_one_or_none()
        payload = to_chat_detail(chat, lead_in_scope=lead_in_scope, bot_name=bot_name)
        owner_group_id = chat.assigned_group_id
        if owner_group_id is None and chat.assigned_department_id is not None:
            owner_group_id = await get_department_inbox_group_id(
                self._session,
                chat.assigned_department_id,
            )
        if owner_group_id is None:
            return payload
        owner_map = await self._repo.get_card_owner_map(
            {(chat.contact_id, owner_group_id)},
        )
        owner_user_id, owner_name = owner_map.get(
            (chat.contact_id, owner_group_id),
            (None, None),
        )
        payload["card_owner_user_id"] = owner_user_id
        payload["card_owner_name"] = owner_name
        payload["card_owner_full_name"] = owner_name
        payload["card_owner_group_id"] = owner_group_id
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

        default_group_id: int | None = body.assigned_group_id
        if default_group_id is None:
            scope_groups = visible_group_ids(ctx)
            if isinstance(scope_groups, set) and len(scope_groups) == 1:
                default_group_id = next(iter(scope_groups))

        chat = Chat(
            contact_id=body.contact_id,
            bot_id=body.bot_id,
            assigned_user_id=body.assigned_user_id or actor.id,
            assigned_group_id=default_group_id,
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

    async def start_whatsapp_outreach(
        self,
        actor: User,
        body: WhatsappOutreachRequest,
    ) -> WhatsappOutreachResponse:
        from app.modules.db.models.contact import Contact

        ctx = await self._scope_loader.load(actor)
        digits = "".join(ch for ch in body.phone if ch.isdigit())
        if len(digits) < 10:
            raise ValidationError(
                message=(
                    "Укажите номер WhatsApp в международном формате "
                    "(только цифры, с кодом страны)"  # noqa: RUF001
                ),
            )
        phone_int = int(digits)

        bot_repo = BotRepository(self._session)
        bot = await bot_repo.get_by_id(body.bot_id)
        if bot is None or not bot.is_active:
            raise NotFound(message="Bot not found")
        channel = (
            bot.channel
            if isinstance(bot.channel, BotChannel)
            else BotChannel(str(bot.channel))
        )
        if channel != BotChannel.WHATSAPP:
            raise ValidationError(message="Выбранный бот не является WhatsApp")

        scope_depts = visible_department_ids(ctx)
        if scope_depts != SCOPE_ALL and bot.department_id not in set(scope_depts):
            raise NotFound(message="Bot not found")

        routing = await resolve_bot_routing(self._session, bot)
        if routing.owner_type == BotOwnerType.GROUP:
            scope_groups = visible_group_ids(ctx)
            if scope_groups != SCOPE_ALL and routing.owner_id not in set(scope_groups):
                raise PermissionDenied(message="Нет доступа к группе этого бота")
        elif routing.lead_group_id is not None:
            scope_groups = visible_group_ids(ctx)
            if scope_groups != SCOPE_ALL and routing.lead_group_id not in set(scope_groups):
                raise PermissionDenied(message="Нет доступа к группе этого бота")

        contact_existing = (
            await self._session.execute(
                select(Contact).where(Contact.telegram_user_id == phone_int),
            )
        ).scalar_one_or_none()

        created_chat = False
        if contact_existing is not None:
            contact_id = contact_existing.id
            if not contact_existing.phone:
                contact_existing.phone = f"+{digits}"
            name = body.full_name.strip()
            if name and (
                contact_existing.full_name.startswith("TG ")
                or contact_existing.full_name.startswith("WA ")
            ):
                contact_existing.full_name = name
        else:
            contact_id = await upsert_contact_from_telegram(
                self._session,
                telegram_user_id=phone_int,
                telegram_username=None,
                first_name=body.full_name.strip(),
                last_name=None,
                created_by=actor.id,
            )
            contact = await self._contacts.get_by_id(contact_id)
            if contact is not None and not contact.phone:
                contact.phone = f"+{digits}"

        active = await self._session.execute(
            select(Chat).where(
                Chat.contact_id == contact_id,
                Chat.bot_id == bot.id,
                Chat.status != ChatStatus.ARCHIVED,
            ),
        )
        chat = active.scalar_one_or_none()
        if chat is None:
            chat_result = await upsert_chat_for_bot(
                self._session,
                contact_id=contact_id,
                bot_id=bot.id,
                owner_type=routing.owner_type,
                owner_id=routing.owner_id,
                candidate_group_ids=routing.candidate_group_ids,
            )
            chat_id = chat_result.chat_id
            chat = await self._repo.get_by_id(chat_id)
            created_chat = True
        else:
            chat_id = int(chat.id)

        if chat is None or not await can_view_chat_async(self._session, ctx, chat):
            raise NotFound(message="Chat not found")

        await self._session.commit()
        return WhatsappOutreachResponse(
            chat_id=chat_id,
            contact_id=contact_id,
            created_chat=created_chat,
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
