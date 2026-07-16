from __future__ import annotations

from typing import Any

from app.modules.chats.schemas import (
    ChatLabelSnippet,
    ChatListItemResponse,
    CurrentLeadSnippet,
    MessageResponse,
    TakeoverResponse,
)
from app.modules.chats.workflow_status import read_contact_client_label_code
from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.chat_takeover import ChatTakeover
from app.modules.db.models.enums import ChatStatus, ContactStatus, MessageDirection, MessageKind


def _sanitize_attachments(message: ChatMessage) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for idx, raw in enumerate(message.attachments or []):
        att = dict(raw)
        status = att.get("status")
        if status == "pending":
            att.pop("url", None)
        elif status == "ready":
            storage_key = att.get("storage_key")
            url = att.get("url")
            if not storage_key and isinstance(url, str) and "/crm-files/" in url:
                storage_key = url.split("/crm-files/", 1)[-1].split("?", 1)[0]
                if storage_key:
                    att["storage_key"] = storage_key
            if storage_key:
                att.pop("url", None)
                att["download_path"] = (
                    f"chats/{message.chat_id}/messages/{message.id}/attachments/{idx}"
                )
            elif att.get("file_id") and status == "ready":
                att.pop("url", None)
                att["download_path"] = f"files/{att['file_id']}"
        sanitized.append(att)
    return sanitized

_CLIENT_LABEL_DISPLAY = {
    "new": "Новый клиент",
    "returning": "Постоянный",
}


def _contact_client_label(chat: Chat) -> str | None:
    if chat.contact is None:
        return None
    code = read_contact_client_label_code(chat.contact.custom_fields)
    if code is None:
        return None
    return _CLIENT_LABEL_DISPLAY.get(code)


def _contact_illiquid(chat: Chat) -> bool:
    if chat.contact is None:
        return False
    status = chat.contact.status
    if isinstance(status, ContactStatus):
        return status == ContactStatus.DISABLED
    return str(status) == ContactStatus.DISABLED.value


def _chat_label_snippet(chat: Chat) -> ChatLabelSnippet | None:
    label_status = chat.business_status
    if label_status is None:
        return None
    return ChatLabelSnippet(
        status_id=label_status.id,
        code=label_status.code,
        label=label_status.label,
    )


def _current_lead_snippet(chat: Chat, *, lead_in_scope: bool) -> CurrentLeadSnippet | None:
    lead = chat.current_lead
    if lead is None:
        return None
    if not lead_in_scope:
        return CurrentLeadSnippet(
            id=lead.id,
            status_id=lead.status_id,
            label="",
            comment=None,
            closed_at=lead.closed_at,
        )
    pipeline = lead.pipeline_status
    return CurrentLeadSnippet(
        id=lead.id,
        status_id=lead.status_id,
        label=pipeline.label if pipeline is not None else "",
        comment=lead.comment,
        closed_at=lead.closed_at,
    )


def to_chat_list_item(
    chat: Chat,
    *,
    unread_for_me: bool = False,
    lead_in_scope: bool = True,
    bot_name: str | None = None,
) -> ChatListItemResponse:
    contact_name = chat.contact.full_name if chat.contact else ""
    group_name = chat.assigned_group.name if chat.assigned_group is not None else None
    status = chat.status if isinstance(chat.status, ChatStatus) else ChatStatus(str(chat.status))
    return ChatListItemResponse(
        id=chat.id,
        contact_id=chat.contact_id,
        contact_name=contact_name,
        bot_id=chat.bot_id,
        bot_name=bot_name,
        assigned_user_id=chat.assigned_user_id,
        assigned_group_id=chat.assigned_group_id,
        assigned_group_name=group_name,
        assigned_department_id=chat.assigned_department_id,
        card_owner_user_id=None,
        card_owner_name=None,
        card_owner_full_name=None,
        card_owner_group_id=None,
        status=status,
        status_id=chat.status_id,
        chat_label=_chat_label_snippet(chat),
        contact_client_label=_contact_client_label(chat),
        contact_illiquid=_contact_illiquid(chat),
        current_lead=_current_lead_snippet(chat, lead_in_scope=lead_in_scope),
        last_message_at=chat.last_message_at,
        last_message_preview=chat.last_message_preview,
        unread_for_me=unread_for_me,
    )


def to_chat_detail(
    chat: Chat,
    *,
    lead_in_scope: bool = True,
    bot_name: str | None = None,
) -> dict[str, Any]:
    item = to_chat_list_item(chat, lead_in_scope=lead_in_scope, bot_name=bot_name)
    return item.model_dump()


def to_message_response(
    message: ChatMessage,
    *,
    card_owner_user_id: int | None = None,
    card_owner_name: str | None = None,
    card_owner_group_id: int | None = None,
    sender_username: str | None = None,
) -> MessageResponse:
    direction = (
        message.direction
        if isinstance(message.direction, MessageDirection)
        else MessageDirection(str(message.direction))
    )
    kind = (
        message.kind if isinstance(message.kind, MessageKind) else MessageKind(str(message.kind))
    )
    return MessageResponse(
        id=message.id,
        chat_id=message.chat_id,
        lead_id=message.lead_id,
        direction=direction.value,
        kind=kind.value,
        text=message.text,
        attachments=_sanitize_attachments(message),
        sender_user_id=message.sender_user_id,
        sender_username=sender_username,
        external_message_id=message.external_message_id,
        external_event_id=message.external_event_id,
        reply_to_message_id=message.reply_to_message_id,
        created_at=message.created_at,
        idempotency_key=message.idempotency_key,
        card_owner_user_id=card_owner_user_id,
        card_owner_name=card_owner_name,
        card_owner_group_id=card_owner_group_id,
    )


def to_takeover_response(takeover: ChatTakeover) -> TakeoverResponse:
    return TakeoverResponse(
        id=takeover.id,
        chat_id=takeover.chat_id,
        senior_user_id=takeover.senior_user_id,
        started_at=takeover.started_at,
        released_at=takeover.released_at,
        reason=takeover.reason,
    )
