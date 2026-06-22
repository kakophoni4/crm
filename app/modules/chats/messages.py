from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import AuditService
from app.modules.chats.read_state import upsert_read_state
from app.modules.chats.repository import ChatRepository
from app.modules.chats.schemas import AttachmentInput, OutboundMessageRequest
from app.modules.chats.scope import can_view_chat_async
from app.modules.chats.serialization import to_message_response
from app.modules.chats.timeutil import utc_now
from app.modules.chats.workflow_status import on_outbound_reply_to_client
from app.modules.contacts.ownership import get_owner, ownership_v2_enabled, record_owner_outbound
from app.modules.contacts.realtime_payloads import contact_group_context
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.contact import Contact
from app.modules.db.models.enums import AuditAction, MessageDirection, MessageKind
from app.modules.db.models.message_reply_audit import MessageReplyAudit
from app.modules.db.models.user import User
from app.modules.files.service import FilesService
from app.modules.leads.repository import LeadRepository
from app.realtime.events import publish
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError
from app.workers.bots.dispatch_outbound import enqueue_outbound

logger = structlog.get_logger(__name__)


def _preview_text(text: str | None, limit: int = 200) -> str | None:
    if text is None:
        return None
    trimmed = text.strip()
    if not trimmed:
        return None
    return trimmed[:limit]


def _queued_attachments(attachments: list[AttachmentInput]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in attachments:
        payload: dict[str, Any] = {
            "status": "queued",
        }
        if item.file_id is not None:
            payload["file_id"] = item.file_id
        if item.name is not None:
            payload["name"] = item.name
        if item.mime is not None:
            payload["mime"] = item.mime
        if item.size is not None:
            payload["size"] = item.size
        if item.url is not None:
            payload["url"] = item.url
        result.append(payload)
    return result


async def _materialize_attachments(
    session: AsyncSession,
    attachments: list[AttachmentInput],
) -> list[dict[str, Any]]:
    if not attachments:
        return []
    files = FilesService(session)
    result: list[dict[str, Any]] = []
    for item in attachments:
        if item.file_id is not None:
            if item.file_id <= 0:
                raise ValidationError(message="Invalid file_id")
            row = await files.get_by_id(item.file_id)
            if row is None:
                raise ValidationError(message="Attachment file not found")
            att_type = "photo" if row.mime_type.startswith("image/") else "document"
            result.append(
                {
                    "file_id": row.id,
                    "type": att_type,
                    "mime": row.mime_type,
                    "filename": row.original_name,
                    "name": row.original_name,
                    "size_bytes": row.size_bytes,
                    "storage_key": row.storage_key,
                    "status": "ready",
                },
            )
            continue
        queued = _queued_attachments([item])
        if queued:
            result.append(queued[0])
    return result


def _message_kind_for_attachments(attachments: list[dict[str, Any]]) -> MessageKind:
    if not attachments:
        return MessageKind.TEXT
    first_type = str(attachments[0].get("type", "document"))
    if first_type == "photo":
        return MessageKind.IMAGE
    if first_type == "voice":
        return MessageKind.VOICE
    return MessageKind.DOCUMENT


class ChatMessagesService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ChatRepository(session)
        self._scope_loader = ScopeLoader(session)

    async def list_messages(
        self,
        actor: User,
        chat_id: int,
        *,
        lead_id: int | None = None,
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        ctx = await self._scope_loader.load(actor)
        chat = await self._repo.get_by_id(chat_id)
        if chat is None or not await can_view_chat_async(self._session, ctx, chat):
            raise NotFound(message="Chat not found")
        if lead_id is not None:
            lead = await LeadRepository(self._session).get_by_id(lead_id)
            if (
                lead is None
                or lead.contact_id != chat.contact_id
                or lead.group_id != chat.assigned_group_id
            ):
                raise NotFound(message="Lead not found")
        rows, next_cursor = await self._repo.list_messages(
            chat_id,
            lead_id=lead_id,
            cursor=cursor,
            limit=limit,
        )
        items: list[dict[str, Any]] = []
        for message, card_owner_user_id, card_owner_name, card_owner_group_id in rows:
            payload = to_message_response(
                message,
                card_owner_user_id=card_owner_user_id,
                card_owner_name=card_owner_name,
                card_owner_group_id=card_owner_group_id,
            ).model_dump()
            items.append(payload)
        return {
            "items": items,
            "next_cursor": next_cursor,
        }

    async def send_outbound(
        self,
        actor: User,
        chat_id: int,
        body: OutboundMessageRequest,
    ) -> tuple[ChatMessage, dict[str, Any], tuple[int | None, str | None, int | None]]:
        if body.idempotency_key:
            existing = await self._repo.get_message_by_idempotency(body.idempotency_key)
            if existing is not None:
                await upsert_read_state(
                    self._session,
                    user_id=actor.id,
                    chat_id=chat_id,
                    last_read_message_id=existing.id,
                )
                owner_fields = await self._repo.get_message_owner_fields(existing.id)
                return existing, {"idempotent": True}, owner_fields

        ctx = await self._scope_loader.load(actor)
        chat = await self._repo.get_by_id(chat_id)
        if chat is None or not await can_view_chat_async(self._session, ctx, chat):
            raise NotFound(message="Chat not found")

        takeover = await self._repo.get_active_takeover(chat_id)
        if takeover is not None and takeover.senior_user_id != actor.id:
            raise PermissionDenied(message="Chat is under senior takeover")

        reply_to_external_id: str | None = None
        if body.reply_to_message_id is not None:
            parent = await self._repo.get_message_in_chat(chat_id, body.reply_to_message_id)
            if parent is None:
                raise ValidationError(message="reply_to_message_id not found in chat")
            reply_to_external_id = parent.external_message_id

        lead_id: int | None = chat.current_lead_id
        group_id_for_lead = chat.assigned_group_id
        if lead_id is None and group_id_for_lead is not None:
            open_lead = await LeadRepository(self._session).get_open(
                chat.contact_id,
                group_id_for_lead,
            )
            if open_lead is not None:
                lead_id = open_lead.id
                chat.current_lead_id = lead_id
        # New deals are opened on inbound from the client only — not when operator sends files/text.

        attachments = await _materialize_attachments(self._session, body.attachments)
        has_text = bool(body.text and body.text.strip())
        if not has_text and not attachments:
            raise ValidationError(message="text or attachments required")

        message_kind = _message_kind_for_attachments(attachments) if attachments else body.kind
        if not attachments and message_kind == MessageKind.TEXT and not has_text:
            raise ValidationError(message="text is required for text messages")

        now = utc_now()
        message = ChatMessage(
            chat_id=chat_id,
            lead_id=lead_id,
            direction=MessageDirection.OUTBOUND,
            kind=message_kind,
            text=body.text,
            attachments=attachments,
            sender_user_id=actor.id,
            reply_to_message_id=body.reply_to_message_id,
            idempotency_key=body.idempotency_key,
        )
        message = await self._repo.add_message(message)

        await upsert_read_state(
            self._session,
            user_id=actor.id,
            chat_id=chat_id,
            last_read_message_id=message.id,
        )

        chat.last_message_at = now
        chat.last_message_preview = _preview_text(body.text) or (
            attachments[0].get("filename") if attachments else None
        )
        chat.assigned_user_id = actor.id
        await self._repo.save(chat)
        await on_outbound_reply_to_client(self._session, chat_id)

        group_id = chat.assigned_group_id
        card_owner_id = actor.id
        is_on_behalf = False
        if ownership_v2_enabled() and group_id is not None:
            owner_id = await get_owner(self._session, chat.contact_id, group_id)
            if owner_id is not None:
                card_owner_id = owner_id
                is_on_behalf = actor.id != owner_id
                self._session.add(
                    MessageReplyAudit(
                        message_id=message.id,
                        chat_id=chat_id,
                        contact_id=chat.contact_id,
                        group_id=group_id,
                        card_owner_user_id=card_owner_id,
                        author_user_id=actor.id,
                        is_on_behalf=is_on_behalf,
                    ),
                )
                if not is_on_behalf:
                    await record_owner_outbound(
                        self._session,
                        chat.contact_id,
                        group_id,
                        actor.id,
                        at=now,
                    )
                elif owner_id is not None:
                    preview = _preview_text(body.text, limit=220) or ""
                    group_ctx = await contact_group_context(
                        self._session,
                        chat.contact_id,
                        group_id,
                        include_chat_id=False,
                    )
                    group_ctx["chat_id"] = chat_id
                    await publish(
                        "message.replied.on_behalf",
                        {
                            **group_ctx,
                            "message_id": message.id,
                            "card_owner_user_id": card_owner_id,
                            "author_user_id": actor.id,
                            "author_full_name": actor.full_name,
                            "text_preview": preview,
                        },
                        scope={"user_id": owner_id},
                    )
                await AuditService(self._session).write(
                    actor_id=actor.id,
                    action=AuditAction.CHAT_MESSAGE_SEND,
                    entity_type="message",
                    entity_id=message.id,
                    payload={
                        "action": "message.replied",
                        "chat_id": chat_id,
                        "contact_id": chat.contact_id,
                        "group_id": group_id,
                        "card_owner_user_id": card_owner_id,
                        "author_user_id": actor.id,
                        "is_on_behalf": is_on_behalf,
                    },
                )

        scope: dict[str, Any] = {}
        if chat.assigned_department_id is not None:
            scope["department_id"] = chat.assigned_department_id
        if group_id is not None:
            scope["group_id"] = group_id
        elif chat.assigned_user_id is not None:
            scope["user_id"] = chat.assigned_user_id

        await publish(
            "chat.message.outbound.requested",
            {
                "chat_id": chat_id,
                "message_id": message.id,
                "sender_user_id": actor.id,
            },
            scope=scope,
        )

        audit_payload = {
            "chat_id": chat_id,
            "message_id": message.id,
            "kind": body.kind.value,
            "idempotency_key": body.idempotency_key,
            "card_owner_user_id": card_owner_id,
            "author_user_id": actor.id,
            "is_on_behalf": is_on_behalf,
        }
        if chat.bot_id is not None:
            contact = await self._session.get(Contact, chat.contact_id)
            telegram_user_id = contact.telegram_user_id if contact is not None else None
            if telegram_user_id is None:
                logger.warning(
                    "outbound_enqueue_skipped_missing_telegram_user_id",
                    chat_id=chat_id,
                    message_id=message.id,
                    contact_id=chat.contact_id,
                    bot_id=chat.bot_id,
                )
            else:
                outbound_attachments = [
                    {
                        "file_id": int(a["file_id"]),
                        "type": a.get("type", "document"),
                        "mime": a.get("mime"),
                        "filename": a.get("filename") or a.get("name"),
                    }
                    for a in attachments
                    if a.get("file_id") is not None
                ]
                outbound_payload = {
                    "internal_id": message.id,
                    "contact": {"telegram_user_id": telegram_user_id},
                    "message": {"text": message.text or ""},
                    "attachments": outbound_attachments,
                    "reply_to_external_id": reply_to_external_id,
                }
                try:
                    await enqueue_outbound(
                        bot_id=chat.bot_id,
                        command="send_message",
                        payload=outbound_payload,
                    )
                except Exception:
                    logger.exception(
                        "outbound_enqueue_failed",
                        chat_id=chat_id,
                        message_id=message.id,
                        bot_id=chat.bot_id,
                    )
        owner_fields = await self._repo.get_message_owner_fields(message.id)
        return message, audit_payload, owner_fields

    async def get_attachment(
        self,
        actor: User,
        chat_id: int,
        message_id: int,
        attachment_index: int,
    ) -> tuple[bytes, str, str | None]:
        from app.shared.storage import get_file_storage

        ctx = await self._scope_loader.load(actor)
        chat = await self._repo.get_by_id(chat_id)
        if chat is None or not await can_view_chat_async(self._session, ctx, chat):
            raise NotFound(message="Chat not found")

        message = await self._repo.get_message_in_chat(chat_id, message_id)
        if message is None:
            raise NotFound(message="Message not found")

        attachments = message.attachments or []
        if attachment_index < 0 or attachment_index >= len(attachments):
            raise NotFound(message="Attachment not found")

        att = dict(attachments[attachment_index])
        if att.get("status") != "ready":
            raise NotFound(message="Attachment not ready")

        storage_key = att.get("storage_key")
        if not storage_key:
            raise NotFound(message="Attachment not available")

        data, content_type = await get_file_storage().get_bytes(str(storage_key))
        filename = att.get("filename") or att.get("name")
        if filename is not None:
            filename = str(filename)
        return data, content_type, filename
