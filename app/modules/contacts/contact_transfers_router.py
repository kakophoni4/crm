from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.decorator import AuditedResult, audit
from app.modules.contacts.schemas_transfer import (
    ContactTransferListResponse,
    ContactTransferResponse,
)
from app.modules.contacts.transfers import ContactGroupTransfersService
from app.modules.db.models.enums import AuditAction, TransferStatus
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/contact-transfers", tags=["contact-transfers"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> ContactGroupTransfersService:
    return ContactGroupTransfersService(db)


@router.get("", response_model=ContactTransferListResponse)
async def list_contact_transfers(
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.CHATS_TRANSFER_REQUEST,
                Permission.CHATS_TRANSFER_APPROVE,
            ),
        ),
    ],
    service: Annotated[ContactGroupTransfersService, Depends(_service)],
    state: TransferStatus | None = None,
    group_id: int | None = None,
) -> ContactTransferListResponse:
    rows = await service.list_transfers(actor, state=state, group_id=group_id)
    payloads = await service.to_responses(rows)
    return ContactTransferListResponse(
        items=[ContactTransferResponse(**payload) for payload in payloads],
    )


@router.post("/{transfer_id}/approve", response_model=ContactTransferResponse)
@audit(AuditAction.CHAT_TRANSFER_APPROVE, "contact_group_transfer")
async def approve_contact_transfer(
    transfer_id: int,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_TRANSFER_APPROVE))],
    service: Annotated[ContactGroupTransfersService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    expected_version: int | None = Query(default=None),
) -> AuditedResult[ContactTransferResponse]:
    transfer, payload = await service.approve(
        actor,
        transfer_id,
        expected_version=expected_version,
    )
    return AuditedResult(
        data=ContactTransferResponse(**await service.to_response(transfer)),
        entity_id=transfer.id,
        payload=payload,
    )


@router.post("/{transfer_id}/decline", response_model=ContactTransferResponse)
@audit(AuditAction.CHAT_TRANSFER_DECLINE, "contact_group_transfer")
async def decline_contact_transfer(
    transfer_id: int,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_TRANSFER_APPROVE))],
    service: Annotated[ContactGroupTransfersService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[ContactTransferResponse]:
    transfer, payload = await service.decline(actor, transfer_id)
    return AuditedResult(
        data=ContactTransferResponse(**await service.to_response(transfer)),
        entity_id=transfer.id,
        payload=payload,
    )


@router.post("/{transfer_id}/accept", response_model=ContactTransferResponse)
@audit(AuditAction.CHAT_TRANSFER_ACCEPT, "contact_group_transfer")
async def accept_contact_transfer(
    transfer_id: int,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_WRITE))],
    service: Annotated[ContactGroupTransfersService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    expected_version: int | None = Query(default=None),
) -> AuditedResult[ContactTransferResponse]:
    transfer, payload = await service.accept(
        actor,
        transfer_id,
        expected_version=expected_version,
    )
    return AuditedResult(
        data=ContactTransferResponse(**await service.to_response(transfer)),
        entity_id=transfer.id,
        payload=payload,
    )


@router.post("/{transfer_id}/reject", response_model=ContactTransferResponse)
@audit(AuditAction.CHAT_TRANSFER_DECLINE, "contact_group_transfer")
async def reject_contact_transfer(
    transfer_id: int,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_WRITE))],
    service: Annotated[ContactGroupTransfersService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[ContactTransferResponse]:
    transfer, payload = await service.reject(actor, transfer_id)
    return AuditedResult(
        data=ContactTransferResponse(**await service.to_response(transfer)),
        entity_id=transfer.id,
        payload=payload,
    )


@router.post("/{transfer_id}/cancel", response_model=ContactTransferResponse)
@audit(AuditAction.CHAT_TRANSFER_CANCEL, "contact_group_transfer")
async def cancel_contact_transfer(
    transfer_id: int,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CHATS_TRANSFER_CANCEL))],
    service: Annotated[ContactGroupTransfersService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[ContactTransferResponse]:
    transfer, payload = await service.cancel(actor, transfer_id)
    return AuditedResult(
        data=ContactTransferResponse(**await service.to_response(transfer)),
        entity_id=transfer.id,
        payload=payload,
    )
