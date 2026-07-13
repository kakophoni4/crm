from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.decorator import AuditedResult, audit
from app.modules.chats.filters import ChatListSort
from app.modules.chats.messages import ChatMessagesService
from app.modules.chats.quick_replies import QuickReplyTemplateService
from app.modules.chats.rate_limit import check_chat_message_rate_limit
from app.modules.chats.read_state import ChatReadStateService
from app.modules.chats.schemas import (
    ChatCreateRequest,
    ChatListResponse,
    ChatMarkReadRequest,
    ChatMarkReadResponse,
    ChatMessageSearchResponse,
    ChatStatusIdPatchRequest,
    ChatStatusPatchRequest,
    MessageListResponse,
    MessageResponse,
    OutboundMessageRequest,
    QuickReplyTemplateCreateRequest,
    QuickReplyTemplateListResponse,
    QuickReplyTemplateResponse,
    QuickReplyTemplateUpdateRequest,
    TakeoverRequestBody,
    TakeoverResponse,
    WhatsappOutreachRequest,
    WhatsappOutreachResponse,
)
from app.modules.chats.search import ChatSearchService
from app.modules.chats.search_scope import ChatSearchScope
from app.modules.chats.serialization import to_message_response
from app.modules.chats.service import ChatService
from app.modules.chats.takeovers import ChatTakeoversService
from app.modules.db.models.enums import AuditAction, ChatStatus
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/chats", tags=["chats"])


def _chat_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ChatService:
    return ChatService(db)


def _read_state_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ChatReadStateService:
    return ChatReadStateService(db)


def _messages_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ChatMessagesService:
    return ChatMessagesService(db)


def _takeovers_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ChatTakeoversService:
    return ChatTakeoversService(db)


def _search_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ChatSearchService:
    return ChatSearchService(db)


def _quick_replies_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QuickReplyTemplateService:
    return QuickReplyTemplateService(db)


@router.get("", response_model=ChatListResponse)
async def list_chats(
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.CHATS_READ_OWN,
                Permission.CHATS_READ_GROUP,
                Permission.CHATS_READ_DEPARTMENT,
                Permission.CHATS_READ_ALL,
            ),
        ),
    ],
    service: Annotated[ChatService, Depends(_chat_service)],
    status: ChatStatus | None = None,
    status_id: int | None = None,
    assigned_user_id: int | None = None,
    contact_id: int | None = None,
    bot_id: int | None = None,
    unread_only: bool = False,
    needs_reply: bool = False,
    card_owner_user_id: int | None = None,
    assigned_group_id: int | None = None,
    lead_status_id: int | None = None,
    lead_open_only: bool | None = None,
    q: str | None = None,
    sort: ChatListSort = ChatListSort.LAST_MESSAGE_AT_DESC,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> ChatListResponse:
    return await service.list_chats(
        actor,
        status=status,
        status_id=status_id,
        assigned_user_id=assigned_user_id,
        contact_id=contact_id,
        bot_id=bot_id,
        unread_only=unread_only,
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


@router.get("/quick-replies", response_model=QuickReplyTemplateListResponse)
async def list_quick_replies(
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_WRITE))],
    service: Annotated[QuickReplyTemplateService, Depends(_quick_replies_service)],
    q: str | None = None,
    department_id: int | None = None,
    group_id: int | None = None,
    include_inactive: bool = False,
    limit: int = Query(default=20, ge=1, le=50),
) -> QuickReplyTemplateListResponse:
    return await service.list_templates(
        actor,
        q=q,
        department_id=department_id,
        group_id=group_id,
        include_inactive=include_inactive,
        limit=limit,
    )


@router.post("/quick-replies", response_model=QuickReplyTemplateResponse, status_code=201)
async def create_quick_reply(
    body: QuickReplyTemplateCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_WRITE))],
    service: Annotated[QuickReplyTemplateService, Depends(_quick_replies_service)],
) -> QuickReplyTemplateResponse:
    return await service.create_template(actor, body)


@router.patch("/quick-replies/{template_id}", response_model=QuickReplyTemplateResponse)
async def update_quick_reply(
    template_id: int,
    body: QuickReplyTemplateUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_WRITE))],
    service: Annotated[QuickReplyTemplateService, Depends(_quick_replies_service)],
) -> QuickReplyTemplateResponse:
    return await service.update_template(actor, template_id, body)


@router.delete("/quick-replies/{template_id}", response_model=QuickReplyTemplateResponse)
async def delete_quick_reply(
    template_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_WRITE))],
    service: Annotated[QuickReplyTemplateService, Depends(_quick_replies_service)],
) -> QuickReplyTemplateResponse:
    return await service.delete_template(actor, template_id)


@router.post("/quick-replies/{template_id}/hide", response_model=QuickReplyTemplateResponse)
async def hide_quick_reply(
    template_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_WRITE))],
    service: Annotated[QuickReplyTemplateService, Depends(_quick_replies_service)],
) -> QuickReplyTemplateResponse:
    return await service.hide_template(actor, template_id)


@router.post("/quick-replies/{template_id}/use", response_model=QuickReplyTemplateResponse)
async def use_quick_reply(
    template_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_WRITE))],
    service: Annotated[QuickReplyTemplateService, Depends(_quick_replies_service)],
) -> QuickReplyTemplateResponse:
    return await service.track_use(actor, template_id)


@router.get("/search", response_model=ChatMessageSearchResponse)
async def search_chats_messages(
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.CHATS_READ_OWN,
                Permission.CHATS_READ_GROUP,
                Permission.CHATS_READ_DEPARTMENT,
                Permission.CHATS_READ_ALL,
            ),
        ),
    ],
    service: Annotated[ChatSearchService, Depends(_search_service)],
    q: str = Query(min_length=2),
    scope: ChatSearchScope | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    highlight: bool = True,
) -> ChatMessageSearchResponse:
    return await service.search_messages(
        actor,
        q=q,
        scope=scope,
        cursor=cursor,
        limit=limit,
        highlight=highlight,
    )


@router.get("/{chat_id}")
async def get_chat(
    chat_id: int,
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.CHATS_READ_OWN,
                Permission.CHATS_READ_GROUP,
                Permission.CHATS_READ_DEPARTMENT,
                Permission.CHATS_READ_ALL,
            ),
        ),
    ],
    service: Annotated[ChatService, Depends(_chat_service)],
) -> dict[str, object]:
    return await service.get_chat(actor, chat_id)


@router.post("/{chat_id}/read", response_model=ChatMarkReadResponse)
async def mark_chat_read(
    chat_id: int,
    body: ChatMarkReadRequest,
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.CHATS_READ_OWN,
                Permission.CHATS_READ_GROUP,
                Permission.CHATS_READ_DEPARTMENT,
                Permission.CHATS_READ_ALL,
            ),
        ),
    ],
    service: Annotated[ChatReadStateService, Depends(_read_state_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChatMarkReadResponse:
    payload = await service.mark_read(
        actor,
        chat_id,
        last_read_message_id=body.last_read_message_id,
    )
    return ChatMarkReadResponse.model_validate(payload)


@router.post("", status_code=201)
@audit(AuditAction.CHAT_CREATE, "chat")
async def create_chat(
    body: ChatCreateRequest,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_WRITE))],
    service: Annotated[ChatService, Depends(_chat_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[dict[str, object]]:
    from app.modules.chats.serialization import to_chat_detail

    result = await service.create_chat(actor, body)
    return AuditedResult(
        data=to_chat_detail(result.chat),
        entity_id=result.chat.id,
        payload=result.audit_payload,
    )


@router.post("/whatsapp-outreach", response_model=WhatsappOutreachResponse)
async def start_whatsapp_outreach(
    body: WhatsappOutreachRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_WRITE))],
    service: Annotated[ChatService, Depends(_chat_service)],
) -> WhatsappOutreachResponse:
    return await service.start_whatsapp_outreach(actor, body)


@router.patch("/{chat_id}/status")
@audit(AuditAction.CHAT_STATUS_UPDATE, "chat")
async def patch_chat_status(
    chat_id: int,
    body: ChatStatusPatchRequest,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_STATUS_UPDATE))],
    service: Annotated[ChatService, Depends(_chat_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[dict[str, object]]:
    from app.modules.chats.serialization import to_chat_detail

    result = await service.update_status(actor, chat_id, body)
    return AuditedResult(
        data=to_chat_detail(result.chat),
        entity_id=result.chat.id,
        payload=result.audit_payload,
    )


@router.patch("/{chat_id}/status_id")
@audit(AuditAction.CHAT_STATUS_UPDATE, "chat")
async def patch_chat_status_id(
    chat_id: int,
    body: ChatStatusIdPatchRequest,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_STATUS_UPDATE))],
    service: Annotated[ChatService, Depends(_chat_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[dict[str, object]]:
    from app.modules.chats.serialization import to_chat_detail

    result = await service.update_status_id(actor, chat_id, body.status_id)
    return AuditedResult(
        data=to_chat_detail(result.chat),
        entity_id=result.chat.id,
        payload=result.audit_payload,
    )


@router.post("/{chat_id}/archive")
@audit(AuditAction.CHAT_ARCHIVE, "chat")
async def archive_chat(
    chat_id: int,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_ARCHIVE))],
    service: Annotated[ChatService, Depends(_chat_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[dict[str, object]]:
    from app.modules.chats.serialization import to_chat_detail

    result = await service.archive_chat(actor, chat_id)
    return AuditedResult(
        data=to_chat_detail(result.chat),
        entity_id=result.chat.id,
        payload=result.audit_payload,
    )


@router.get("/{chat_id}/messages", response_model=MessageListResponse)
async def list_messages(
    chat_id: int,
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.CHATS_READ_OWN,
                Permission.CHATS_READ_GROUP,
                Permission.CHATS_READ_DEPARTMENT,
                Permission.CHATS_READ_ALL,
            ),
        ),
    ],
    service: Annotated[ChatMessagesService, Depends(_messages_service)],
    lead_id: int | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> MessageListResponse:
    payload = await service.list_messages(
        actor,
        chat_id,
        lead_id=lead_id,
        cursor=cursor,
        limit=limit,
    )
    return MessageListResponse(**payload)


@router.get("/{chat_id}/messages/{message_id}/attachments/{attachment_index}")
async def download_message_attachment(
    chat_id: int,
    message_id: int,
    attachment_index: int,
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.CHATS_READ_OWN,
                Permission.CHATS_READ_GROUP,
                Permission.CHATS_READ_DEPARTMENT,
                Permission.CHATS_READ_ALL,
            ),
        ),
    ],
    service: Annotated[ChatMessagesService, Depends(_messages_service)],
) -> Response:
    data, content_type, filename = await service.get_attachment(
        actor,
        chat_id,
        message_id,
        attachment_index,
    )
    headers: dict[str, str] = {}
    if filename:
        ascii_name = filename.encode("ascii", "ignore").decode() or "file"
        headers["Content-Disposition"] = (
            f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
        )
    return Response(content=data, media_type=content_type, headers=headers)


@router.post("/{chat_id}/messages", status_code=202, response_model=MessageResponse)
@audit(AuditAction.CHAT_MESSAGE_SEND, "message")
async def send_message(
    chat_id: int,
    body: OutboundMessageRequest,
    request: Request,
    actor: Annotated[User, Depends(check_chat_message_rate_limit)],
    service: Annotated[ChatMessagesService, Depends(_messages_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
) -> AuditedResult[MessageResponse]:
    message, audit_payload, owner_fields = await service.send_outbound(actor, chat_id, body)
    card_owner_user_id, card_owner_name, card_owner_group_id = owner_fields
    response.status_code = 202
    return AuditedResult(
        data=to_message_response(
            message,
            card_owner_user_id=card_owner_user_id,
            card_owner_name=card_owner_name,
            card_owner_group_id=card_owner_group_id,
            sender_username=actor.username or actor.full_name,
        ),
        entity_id=message.id,
        payload=audit_payload,
    )


@router.post("/{chat_id}/takeover", response_model=TakeoverResponse)
@audit(AuditAction.CHAT_TAKEOVER, "chat_takeover")
async def start_takeover(
    chat_id: int,
    request: Request,
    body: TakeoverRequestBody,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_TAKEOVER))],
    service: Annotated[ChatTakeoversService, Depends(_takeovers_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[TakeoverResponse]:
    takeover, payload = await service.start(actor, chat_id, reason=body.reason)
    return AuditedResult(
        data=TakeoverResponse(**service.to_response(takeover)),
        entity_id=takeover.id,
        payload=payload,
    )


@router.post("/{chat_id}/takeover/release", response_model=TakeoverResponse)
@audit(AuditAction.CHAT_TAKEOVER_RELEASE, "chat_takeover")
async def release_takeover(
    chat_id: int,
    request: Request,
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.CHATS_TAKEOVER_RELEASE,
                Permission.CHATS_TAKEOVER,
            ),
        ),
    ],
    service: Annotated[ChatTakeoversService, Depends(_takeovers_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[TakeoverResponse]:
    takeover, payload = await service.release(actor, chat_id)
    return AuditedResult(
        data=TakeoverResponse(**service.to_response(takeover)),
        entity_id=takeover.id,
        payload=payload,
    )
