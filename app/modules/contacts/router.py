from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.decorator import AuditedResult, audit
from app.modules.contacts.rate_limit import check_contact_update_rate_limit
from app.modules.contacts.reply_audit import ContactReplyAuditService
from app.modules.contacts.schemas import (
    ContactActivityResponse,
    ContactAuditResponse,
    ContactCreateRequest,
    ContactListResponse,
    ContactUpdateRequest,
)
from app.modules.contacts.schemas_transfer import (
    ContactTransferRequestBody,
    ContactTransferResponse,
    ReplyAuditListResponse,
)
from app.modules.contacts.serialization import to_contact_response
from app.modules.contacts.service import ContactService
from app.modules.contacts.transfers import ContactGroupTransfersService
from app.modules.db.models.enums import AuditAction, ContactStatus
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])

_CUSTOM_FIELD_RE = re.compile(r"^custom_field\[(.+)\]$")


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> ContactService:
    return ContactService(db)


def _transfers_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContactGroupTransfersService:
    return ContactGroupTransfersService(db)


def _reply_audit_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContactReplyAuditService:
    return ContactReplyAuditService(db)


def _parse_custom_field_filters(request: Request) -> dict[str, str]:
    filters: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        match = _CUSTOM_FIELD_RE.match(key)
        if match:
            filters[match.group(1)] = value
    return filters


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
    service: Annotated[ContactService, Depends(_service)],
    q: str | None = None,
    status: ContactStatus | None = None,
    assigned_user_id: int | None = None,
    telegram_username: str | None = None,
    cursor: str | None = None,
    offset: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    include_total: bool = Query(default=False),
) -> ContactListResponse:
    return await service.list_contacts(
        actor,
        q=q,
        status=status,
        assigned_user_id=assigned_user_id,
        telegram_username=telegram_username,
        custom_field_filters=_parse_custom_field_filters(request),
        cursor=cursor,
        offset=offset,
        limit=limit,
        include_total=include_total,
    )


@router.post("", status_code=201)
@audit(AuditAction.CONTACT_CREATE, "contact")
async def create_contact(
    body: ContactCreateRequest,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_CREATE))],
    service: Annotated[ContactService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[dict[str, object]]:
    result = await service.create_contact(actor, body)
    payload = to_contact_response(result.contact, actor=actor)
    if result.workspace is not None:
        payload["workspace"] = {
            "chat_id": result.workspace.chat_id,
            "lead_id": result.workspace.lead_id,
            "group_id": result.workspace.group_id,
            "created_chat": result.workspace.created_chat,
            "created_lead": result.workspace.created_lead,
        }
    return AuditedResult(
        data=payload,
        entity_id=result.contact.id,
        payload=result.audit_payload,
    )


@router.get("/{contact_id}")
async def get_contact(
    contact_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
    service: Annotated[ContactService, Depends(_service)],
    embed_leads: bool = False,
) -> dict[str, object]:
    return await service.get_contact(actor, contact_id, embed_leads=embed_leads)


@router.patch("/{contact_id}")
@audit(AuditAction.CONTACT_UPDATE, "contact")
async def update_contact(
    contact_id: int,
    body: ContactUpdateRequest,
    request: Request,
    actor: Annotated[User, Depends(check_contact_update_rate_limit)],
    service: Annotated[ContactService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[dict[str, object]]:
    result = await service.update_contact(actor, contact_id, body)
    return AuditedResult(
        data=to_contact_response(result.contact, actor=actor),
        entity_id=result.contact.id,
        payload=result.audit_payload,
    )


@router.delete("/{contact_id}")
@audit(AuditAction.CONTACT_DELETE, "contact")
async def delete_contact(
    contact_id: int,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_DELETE))],
    service: Annotated[ContactService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[dict[str, object]]:
    result = await service.delete_contact(actor, contact_id)
    return AuditedResult(
        data=to_contact_response(result.contact, actor=actor),
        entity_id=result.contact.id,
        payload=result.audit_payload,
    )


@router.get("/{contact_id}/history", response_model=ContactActivityResponse)
async def contact_activity_history(
    contact_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
    service: Annotated[ContactService, Depends(_service)],
    limit: int = Query(default=100, ge=1, le=500),
) -> ContactActivityResponse:
    return await service.activity_history(actor, contact_id, limit=limit)


@router.get("/{contact_id}/audit", response_model=ContactAuditResponse)
async def contact_audit_log(
    contact_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_AUDIT_READ))],
    service: Annotated[ContactService, Depends(_service)],
    limit: int = Query(default=100, ge=1, le=500),
) -> ContactAuditResponse:
    return await service.entity_audit(actor, contact_id, limit=limit)


@router.post(
    "/{contact_id}/groups/{group_id}/transfers",
    response_model=ContactTransferResponse,
    status_code=201,
)
@audit(AuditAction.CHAT_TRANSFER_REQUEST, "contact_group_transfer")
async def request_contact_group_transfer(
    contact_id: int,
    group_id: int,
    body: ContactTransferRequestBody,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_TRANSFER_REQUEST))],
    service: Annotated[ContactGroupTransfersService, Depends(_transfers_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[ContactTransferResponse]:
    transfer, payload = await service.request_transfer(
        actor,
        contact_id,
        group_id,
        to_user_id=body.to_user_id,
        target_group_id=body.target_group_id,
        comment=body.comment,
        force=body.force,
    )
    return AuditedResult(
        data=ContactTransferResponse(**await service.to_response(transfer)),
        entity_id=transfer.id,
        payload=payload,
    )


@router.get(
    "/{contact_id}/groups/{group_id}/reply-audit",
    response_model=ReplyAuditListResponse,
)
async def contact_group_reply_audit(
    contact_id: int,
    group_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_AUDIT_READ))],
    service: Annotated[ContactReplyAuditService, Depends(_reply_audit_service)],
    limit: int = Query(default=100, ge=1, le=500),
) -> ReplyAuditListResponse:
    return await service.list_reply_audit(actor, contact_id, group_id, limit=limit)
