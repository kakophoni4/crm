from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, func, nulls_last, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.chats.cursor import CursorError, decode_chat_cursor, decode_message_cursor
from app.modules.chats.filters import ChatListSort, chat_list_order_by
from app.modules.chats.scope import chat_visibility_clause
from app.modules.chats.search_scope import ChatSearchScope, search_scope_clause
from app.modules.chats.unread import (
    latest_message_subquery,
    unread_for_actor_expression,
    unread_for_me_map,
)
from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.chat_read_state import ChatReadState
from app.modules.db.models.chat_takeover import ChatTakeover
from app.modules.db.models.contact import Contact
from app.modules.db.models.contact_group_assignment import ContactGroupAssignment
from app.modules.db.models.enums import ChatStatus, MessageDirection
from app.modules.db.models.group import Group
from app.modules.db.models.lead import Lead
from app.modules.db.models.message_reply_audit import MessageReplyAudit
from app.modules.db.models.user import User
from app.modules.leads.department_inbox import DEPT_INBOX_GROUP_NAME
from app.modules.rbac.permissions import Permission
from app.modules.rbac.scope import ScopeContext
from app.modules.search.trgm import trgm_or_ilike, trgm_search_indexes_available

_HEADLINE_OPTS = "StartSel=<mark>, StopSel=</mark>, MaxWords=25, MinWords=3"


@dataclass(frozen=True)
class MessageSearchHit:
    chat_id: int
    contact_id: int
    message_id: int
    snippet: str
    matched_at: datetime
    lead_id: int | None
    assigned_group_id: int | None
    card_owner_user_id: int | None


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _scoped[T: tuple[Any, ...]](
        self,
        stmt: Select[T],
        ctx: ScopeContext,
        read_perm: Permission,
    ) -> Select[T]:
        clause = chat_visibility_clause(ctx, read_perm)
        if clause is not None:
            stmt = stmt.where(clause)
        return stmt

    async def get_by_id(self, chat_id: int) -> Chat | None:
        result = await self._session.execute(select(Chat).where(Chat.id == chat_id))
        return result.scalar_one_or_none()

    async def get_by_id_scoped(
        self,
        chat_id: int,
        ctx: ScopeContext,
        read_perm: Permission,
    ) -> Chat | None:
        stmt = self._scoped(select(Chat).where(Chat.id == chat_id), ctx, read_perm)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_chats(
        self,
        *,
        ctx: ScopeContext,
        read_perm: Permission,
        status: ChatStatus | None,
        status_id: int | None,
        assigned_user_id: int | None,
        contact_id: int | None,
        bot_id: int | None,
        unread_only: bool,
        actor_user_id: int | None,
        needs_reply: bool,
        card_owner_user_id: int | None,
        assigned_group_id: int | None,
        lead_status_id: int | None,
        lead_open_only: bool | None,
        q: str | None,
        sort: ChatListSort,
        cursor: str | None,
        limit: int,
    ) -> tuple[
        list[
            tuple[
                Chat,
                int | None,
                str | None,
                datetime | None,
                datetime | None,
                MessageDirection | None,
            ]
        ],
        str | None,
    ]:
        from app.modules.chats.cursor import encode_chat_cursor

        latest_msg = latest_message_subquery()
        read_state = aliased(ChatReadState)
        use_actor_unread = actor_user_id is not None
        order_by: list[Any]
        if sort == ChatListSort.UNREAD_FIRST and use_actor_unread:
            unread_expr = unread_for_actor_expression(latest_msg, read_state)
            order_by = [
                unread_expr.desc(),
                nulls_last(Chat.last_message_at.desc()),
                Chat.id.desc(),
            ]
        else:
            order_by = chat_list_order_by(sort)
        # Card owner lives in contact_group_assignments for (contact, owner_group),
        # not in chats.last_handled_by_user_id. Department bots use synthetic inbox group.
        card_owner_cga = aliased(ContactGroupAssignment)
        card_owner_user = aliased(User)
        inbox_group = aliased(Group)
        latest_message = aliased(ChatMessage)
        stmt = (
            select(
                Chat,
                card_owner_cga.owner_user_id,
                card_owner_user.full_name,
                card_owner_cga.pending_inbound_at,
                card_owner_cga.escalated_to_group_at,
                latest_message.direction,
            )
            .outerjoin(
                inbox_group,
                and_(
                    Chat.assigned_group_id.is_(None),
                    Chat.assigned_department_id.isnot(None),
                    inbox_group.department_id == Chat.assigned_department_id,
                    inbox_group.name == DEPT_INBOX_GROUP_NAME,
                ),
            )
            .outerjoin(
                card_owner_cga,
                and_(
                    card_owner_cga.contact_id == Chat.contact_id,
                    card_owner_cga.group_id
                    == func.coalesce(Chat.assigned_group_id, inbox_group.id),
                ),
            )
            .outerjoin(card_owner_user, card_owner_user.id == card_owner_cga.owner_user_id)
            .outerjoin(latest_msg, latest_msg.c.chat_id == Chat.id)
            .outerjoin(
                latest_message,
                latest_message.id == latest_msg.c.max_message_id,
            )
            .order_by(*order_by)
            .limit(limit + 1)
        )
        stmt = self._scoped(stmt, ctx, read_perm)
        if status is None:
            stmt = stmt.where(Chat.status != ChatStatus.ARCHIVED)
        if use_actor_unread and (
            unread_only or sort == ChatListSort.UNREAD_FIRST
        ):
            stmt = stmt.outerjoin(
                read_state,
                and_(
                    read_state.chat_id == Chat.id,
                    read_state.user_id == actor_user_id,
                ),
            )

        if status is not None:
            stmt = stmt.where(Chat.status == status)
        if status_id is not None:
            stmt = stmt.where(Chat.status_id == status_id)
        if assigned_user_id is not None:
            stmt = stmt.where(Chat.assigned_user_id == assigned_user_id)
        if contact_id is not None:
            stmt = stmt.where(Chat.contact_id == contact_id)
        if bot_id is not None:
            stmt = stmt.where(Chat.bot_id == bot_id)
        if unread_only and actor_user_id is not None:
            stmt = stmt.where(unread_for_actor_expression(latest_msg, read_state))
        elif unread_only:
            stmt = stmt.where(latest_msg.c.max_message_id.isnot(None))
        if needs_reply:
            needs_owner = aliased(ContactGroupAssignment)
            needs_inbox = aliased(Group)
            stmt = stmt.outerjoin(
                needs_inbox,
                and_(
                    Chat.assigned_group_id.is_(None),
                    Chat.assigned_department_id.isnot(None),
                    needs_inbox.department_id == Chat.assigned_department_id,
                    needs_inbox.name == DEPT_INBOX_GROUP_NAME,
                ),
            ).join(
                needs_owner,
                and_(
                    needs_owner.contact_id == Chat.contact_id,
                    needs_owner.group_id
                    == func.coalesce(Chat.assigned_group_id, needs_inbox.id),
                ),
            ).where(
                or_(
                    needs_owner.escalated_to_group_at.isnot(None),
                    latest_message.direction == MessageDirection.INBOUND,
                ),
            )
        if assigned_group_id is not None:
            stmt = stmt.where(Chat.assigned_group_id == assigned_group_id)
        if lead_status_id is not None or lead_open_only is not None:
            current_lead = aliased(Lead)
            if lead_open_only is True:
                stmt = stmt.where(Chat.current_lead_id.isnot(None))
                stmt = stmt.join(current_lead, current_lead.id == Chat.current_lead_id)
                stmt = stmt.where(current_lead.closed_at.is_(None))
            else:
                stmt = stmt.outerjoin(current_lead, current_lead.id == Chat.current_lead_id)
                if lead_open_only is False:
                    stmt = stmt.where(
                        or_(
                            current_lead.closed_at.is_not(None),
                            Chat.current_lead_id.is_(None),
                        ),
                    )
            if lead_status_id is not None:
                stmt = stmt.where(current_lead.status_id == lead_status_id)
        if card_owner_user_id is not None:
            stmt = stmt.where(card_owner_cga.owner_user_id == card_owner_user_id)
        if q:
            pattern = f"%{q}%"
            normalized_lead_id = q.strip().lstrip("#№").strip()
            search_clauses = [
                select(Contact.id)
                .where(
                    Contact.id == Chat.contact_id,
                    Contact.full_name.ilike(pattern),
                )
                .exists(),
            ]
            if normalized_lead_id.isdigit():
                search_clauses.append(
                    select(Lead.id)
                    .where(
                        Lead.chat_id == Chat.id,
                        Lead.id == int(normalized_lead_id),
                    )
                    .exists(),
                )
            stmt = stmt.where(
                or_(*search_clauses),
            )
        if cursor is not None and sort == ChatListSort.LAST_MESSAGE_AT_DESC:
            try:
                cursor_at, cursor_id = decode_chat_cursor(cursor)
            except CursorError:
                cursor_at, cursor_id = datetime.min.replace(tzinfo=None), -1
            stmt = stmt.where(
                or_(
                    Chat.last_message_at < cursor_at,
                    and_(
                        Chat.last_message_at == cursor_at,
                        Chat.id < cursor_id,
                    ),
                    Chat.last_message_at.is_(None),
                ),
            )
        elif cursor is not None and sort == ChatListSort.CREATED_AT_DESC:
            try:
                cursor_at, cursor_id = decode_chat_cursor(cursor)
            except CursorError:
                cursor_at, cursor_id = datetime.min.replace(tzinfo=None), -1
            stmt = stmt.where(
                or_(
                    Chat.created_at < cursor_at,
                    and_(
                        Chat.created_at == cursor_at,
                        Chat.id < cursor_id,
                    ),
                ),
            )

        result = await self._session.execute(stmt)
        rows = [(row[0], row[1], row[2], row[3], row[4], row[5]) for row in result.all()]
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last_chat = rows[-1][0]
            if sort == ChatListSort.CREATED_AT_DESC:
                next_cursor = encode_chat_cursor(last_chat.created_at, last_chat.id)
            elif (
                sort == ChatListSort.LAST_MESSAGE_AT_DESC
                and last_chat.last_message_at is not None
            ):
                next_cursor = encode_chat_cursor(last_chat.last_message_at, last_chat.id)

        return rows, next_cursor

    async def get_unread_for_me_map(
        self,
        chat_ids: list[int],
        actor_user_id: int,
    ) -> dict[int, bool]:
        return await unread_for_me_map(self._session, chat_ids, actor_user_id)

    async def search_chats(
        self,
        *,
        ctx: ScopeContext,
        read_perm: Permission,
        q: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Chat], str | None]:
        from app.modules.chats.cursor import encode_chat_cursor

        pattern = f"%{q}%"
        use_trgm = len(q) >= 2 and await trgm_search_indexes_available(self._session)
        stmt = (
            select(Chat)
            .join(Contact, Contact.id == Chat.contact_id)
            .where(
                trgm_or_ilike(
                    Chat.last_message_preview,
                    Contact.full_name,
                    pattern=pattern,
                ),
            )
        )
        if use_trgm:
            rank = func.greatest(
                func.word_similarity(q, func.coalesce(Chat.last_message_preview, "")),
                func.word_similarity(q, func.coalesce(Contact.full_name, "")),
            )
            stmt = stmt.order_by(
                rank.desc(),
                Chat.last_message_at.desc().nulls_last(),
                Chat.id.desc(),
            )
        else:
            stmt = stmt.order_by(
                Chat.last_message_at.desc().nulls_last(),
                Chat.id.desc(),
            )
        stmt = stmt.limit(limit + 1)
        stmt = self._scoped(stmt, ctx, read_perm)

        if cursor is not None:
            try:
                cursor_at, cursor_id = decode_chat_cursor(cursor)
            except CursorError:
                cursor_at, cursor_id = datetime.min.replace(tzinfo=None), -1
            stmt = stmt.where(
                or_(
                    Chat.last_message_at < cursor_at,
                    and_(
                        Chat.last_message_at == cursor_at,
                        Chat.id < cursor_id,
                    ),
                    Chat.last_message_at.is_(None),
                ),
            )

        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            if last.last_message_at is not None:
                next_cursor = encode_chat_cursor(last.last_message_at, last.id)
        return rows, next_cursor

    async def add(self, chat: Chat) -> Chat:
        self._session.add(chat)
        await self._session.flush()
        await self._session.refresh(chat)
        return chat

    async def save(self, chat: Chat) -> None:
        await self._session.flush()

    async def get_active_takeover(self, chat_id: int) -> ChatTakeover | None:
        result = await self._session.execute(
            select(ChatTakeover).where(
                ChatTakeover.chat_id == chat_id,
                ChatTakeover.released_at.is_(None),
            ),
        )
        return result.scalar_one_or_none()

    async def add_takeover(self, takeover: ChatTakeover) -> ChatTakeover:
        self._session.add(takeover)
        await self._session.flush()
        await self._session.refresh(takeover)
        return takeover

    async def list_messages(
        self,
        chat_id: int,
        *,
        lead_id: int | None = None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[tuple[ChatMessage, int | None, str | None, int | None, str | None]], str | None]:
        from app.modules.chats.cursor import encode_message_cursor

        owner_user = aliased(User)
        sender_user = aliased(User)
        author_user = aliased(User)
        # Prefer message.sender_user_id; fall back to reply-audit author
        # (covers older rows / phone-synced outbound that still have an audit).
        sender_label = func.nullif(
            func.trim(
                func.coalesce(
                    sender_user.username,
                    author_user.username,
                    sender_user.full_name,
                    author_user.full_name,
                )
            ),
            "",
        )
        stmt = (
            select(
                ChatMessage,
                MessageReplyAudit.card_owner_user_id,
                owner_user.full_name,
                MessageReplyAudit.group_id,
                sender_label.label("sender_username"),
            )
            .select_from(ChatMessage)
            .outerjoin(
                MessageReplyAudit,
                MessageReplyAudit.message_id == ChatMessage.id,
            )
            .outerjoin(owner_user, owner_user.id == MessageReplyAudit.card_owner_user_id)
            .outerjoin(sender_user, sender_user.id == ChatMessage.sender_user_id)
            .outerjoin(author_user, author_user.id == MessageReplyAudit.author_user_id)
            .where(ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit + 1)
        )
        if lead_id is not None:
            stmt = stmt.where(ChatMessage.lead_id == lead_id)
        if cursor is not None:
            try:
                cursor_at, cursor_id = decode_message_cursor(cursor)
            except CursorError:
                cursor_at, cursor_id = datetime.min.replace(tzinfo=None), -1
            stmt = stmt.where(
                or_(
                    ChatMessage.created_at < cursor_at,
                    and_(
                        ChatMessage.created_at == cursor_at,
                        ChatMessage.id < cursor_id,
                    ),
                ),
            )

        result = await self._session.execute(stmt)
        rows = [
            (row[0], row[1], row[2], row[3], row[4])
            for row in result.all()
        ]
        next_cursor: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1][0]
            next_cursor = encode_message_cursor(last.created_at, last.id)
        return rows, next_cursor

    async def get_message_by_idempotency(self, key: str) -> ChatMessage | None:
        result = await self._session.execute(
            select(ChatMessage).where(ChatMessage.idempotency_key == key),
        )
        return result.scalar_one_or_none()

    async def get_message_in_chat(self, chat_id: int, message_id: int) -> ChatMessage | None:
        result = await self._session.execute(
            select(ChatMessage).where(
                ChatMessage.chat_id == chat_id,
                ChatMessage.id == message_id,
            ),
        )
        return result.scalar_one_or_none()

    async def get_message_owner_fields(
        self,
        message_id: int,
    ) -> tuple[int | None, str | None, int | None]:
        owner_user = aliased(User)
        result = await self._session.execute(
            select(
                MessageReplyAudit.card_owner_user_id,
                owner_user.full_name,
                MessageReplyAudit.group_id,
            )
            .select_from(MessageReplyAudit)
            .outerjoin(owner_user, owner_user.id == MessageReplyAudit.card_owner_user_id)
            .where(MessageReplyAudit.message_id == message_id),
        )
        row = result.one_or_none()
        if row is None:
            return None, None, None
        return row[0], row[1], row[2]

    async def get_card_owner_map(
        self,
        pairs: set[tuple[int, int]],
    ) -> dict[tuple[int, int], tuple[int | None, str | None]]:
        if not pairs:
            return {}
        owner_user = aliased(User)
        result = await self._session.execute(
            select(
                ContactGroupAssignment.contact_id,
                ContactGroupAssignment.group_id,
                ContactGroupAssignment.owner_user_id,
                owner_user.full_name,
            )
            .select_from(ContactGroupAssignment)
            .outerjoin(owner_user, owner_user.id == ContactGroupAssignment.owner_user_id)
            .where(
                tuple_(
                    ContactGroupAssignment.contact_id,
                    ContactGroupAssignment.group_id,
                ).in_(pairs),
            ),
        )
        owner_map: dict[tuple[int, int], tuple[int | None, str | None]] = {}
        for contact_id, group_id, owner_user_id, owner_name in result.all():
            owner_map[(contact_id, group_id)] = (owner_user_id, owner_name)
        return owner_map

    async def add_message(self, message: ChatMessage) -> ChatMessage:
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message)
        return message

    async def search_messages(
        self,
        *,
        ctx: ScopeContext,
        read_perm: Permission,
        scope: ChatSearchScope,
        q: str,
        cursor: str | None,
        limit: int,
        highlight: bool = True,
    ) -> list[MessageSearchHit]:
        # Uses GIN idx_messages_search_vector; EXPLAIN on 10k rows should show Bitmap Index Scan
        # and stay under ~200ms when scope filters chats before messages.
        ts_query = func.plainto_tsquery("russian", q)
        visibility = chat_visibility_clause(ctx, read_perm)
        scope_filter = search_scope_clause(ctx, scope)

        if highlight:
            snippet_expr = func.ts_headline(
                "russian",
                func.coalesce(ChatMessage.text, ""),
                ts_query,
                _HEADLINE_OPTS,
            )
        else:
            snippet_expr = func.left(func.coalesce(ChatMessage.text, ""), 200)

        owner_subq = (
            select(ContactGroupAssignment.owner_user_id)
            .where(
                ContactGroupAssignment.contact_id == Chat.contact_id,
                ContactGroupAssignment.group_id == Chat.assigned_group_id,
            )
            .correlate(Chat)
            .scalar_subquery()
        )

        stmt = (
            select(
                Chat.id,
                Chat.contact_id,
                ChatMessage.id,
                snippet_expr,
                ChatMessage.created_at,
                ChatMessage.lead_id,
                Chat.assigned_group_id,
                owner_subq,
            )
            .select_from(ChatMessage)
            .join(Chat, Chat.id == ChatMessage.chat_id)
            .where(
                ChatMessage.search_vector.op("@@")(ts_query),
                ChatMessage.text.isnot(None),
            )
            .order_by(
                ChatMessage.created_at.desc(),
                ChatMessage.id.desc(),
            )
            .limit(limit + 1)
        )

        if visibility is not None:
            stmt = stmt.where(visibility)
        if scope_filter is not None:
            stmt = stmt.where(scope_filter)

        if cursor is not None:
            try:
                cursor_at, cursor_id = decode_message_cursor(cursor)
            except CursorError:
                cursor_at, cursor_id = datetime.min.replace(tzinfo=None), -1
            stmt = stmt.where(
                or_(
                    ChatMessage.created_at < cursor_at,
                    and_(
                        ChatMessage.created_at == cursor_at,
                        ChatMessage.id < cursor_id,
                    ),
                ),
            )

        result = await self._session.execute(stmt)
        return [
            MessageSearchHit(
                chat_id=int(row[0]),
                contact_id=int(row[1]),
                message_id=int(row[2]),
                snippet=str(row[3] or ""),
                matched_at=row[4],
                lead_id=int(row[5]) if row[5] is not None else None,
                assigned_group_id=row[6],
                card_owner_user_id=row[7],
            )
            for row in result.all()
        ]
