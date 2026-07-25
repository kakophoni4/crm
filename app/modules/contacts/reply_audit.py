from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.contacts.repository import ContactRepository
from app.modules.contacts.schemas_transfer import ReplyAuditItem, ReplyAuditListResponse
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.message_reply_audit import MessageReplyAudit
from app.modules.db.models.user import User
from app.modules.rbac.scope import SCOPE_ALL, ScopeContext, visible_group_ids
from app.shared.exceptions import NotFound


class ContactReplyAuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._contacts = ContactRepository(session)
        self._scope_loader = ScopeLoader(session)

    async def _ctx(self, actor: User) -> ScopeContext:
        return await self._scope_loader.load(actor)

    def _ensure_group_visible(self, ctx: ScopeContext, group_id: int) -> None:
        visible = visible_group_ids(ctx)
        if visible == SCOPE_ALL:
            return
        if not isinstance(visible, set) or group_id not in visible:
            raise NotFound(message="Group not found")

    async def list_reply_audit(
        self,
        actor: User,
        contact_id: int,
        group_id: int,
        *,
        limit: int,
    ) -> ReplyAuditListResponse:
        ctx = await self._ctx(actor)
        if not await self._contacts.is_contact_visible(ctx, contact_id):
            raise NotFound(message="Contact not found")
        self._ensure_group_visible(ctx, group_id)

        author_user = aliased(User)
        card_owner_user = aliased(User)
        result = await self._session.execute(
            select(
                MessageReplyAudit.message_id,
                MessageReplyAudit.chat_id,
                MessageReplyAudit.author_user_id,
                author_user.username.label("author_username"),
                author_user.full_name.label("author_full_name"),
                MessageReplyAudit.card_owner_user_id,
                card_owner_user.full_name.label("card_owner_full_name"),
                MessageReplyAudit.is_on_behalf,
                MessageReplyAudit.created_at,
            )
            .select_from(MessageReplyAudit)
            .join(author_user, author_user.id == MessageReplyAudit.author_user_id)
            .join(card_owner_user, card_owner_user.id == MessageReplyAudit.card_owner_user_id)
            .where(
                MessageReplyAudit.contact_id == contact_id,
                MessageReplyAudit.group_id == group_id,
            )
            .order_by(MessageReplyAudit.created_at.desc(), MessageReplyAudit.id.desc())
            .limit(limit),
        )
        items = [
            ReplyAuditItem(
                message_id=row.message_id,
                chat_id=row.chat_id,
                author_user_id=row.author_user_id,
                author_username=row.author_username,
                author_full_name=row.author_full_name,
                card_owner_user_id=row.card_owner_user_id,
                card_owner_full_name=row.card_owner_full_name,
                is_on_behalf=row.is_on_behalf,
                created_at=row.created_at,
            )
            for row in result.all()
        ]
        return ReplyAuditListResponse(items=items)
