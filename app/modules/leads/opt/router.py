from __future__ import annotations

from typing import Annotated

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.leads.opt.schemas import (
    OptAttachmentProbeRequest,
    OptAttachmentProbeResponse,
    OptCommissionAdjustRequest,
    OptOrderListResponse,
    OptOrderPaymentCreateRequest,
    OptOrderRegistryListResponse,
    OptOrderResponse,
    OptSendRegistryResponse,
    OptUploadFromAttachmentRequest,
)
from app.modules.leads.opt.service import OptOrderService
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1", tags=["leads-opt"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> OptOrderService:
    return OptOrderService(db)


@router.get("/opt-orders", response_model=OptOrderRegistryListResponse)
async def list_opt_orders_registry(
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
    service: Annotated[OptOrderService, Depends(_service)],
    department_id: int | None = None,
    group_id: int | None = None,
    payment_status: str | None = None,
    open_only: bool = False,
    offset: int = 0,
    limit: int = 50,
) -> OptOrderRegistryListResponse:
    return await service.list_registry(
        actor,
        department_id=department_id,
        group_id=group_id,
        payment_status=payment_status,
        open_only=open_only,
        offset=max(0, offset),
        limit=min(max(1, limit), 100),
    )


@router.get("/leads/{lead_id}/opt-orders", response_model=OptOrderListResponse)
async def list_opt_orders(
    lead_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
    service: Annotated[OptOrderService, Depends(_service)],
) -> OptOrderListResponse:
    return await service.list_orders(actor, lead_id)


@router.post(
    "/leads/{lead_id}/opt-orders/probe-attachment",
    response_model=OptAttachmentProbeResponse,
)
async def probe_opt_chat_attachment(
    lead_id: int,
    body: OptAttachmentProbeRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
    service: Annotated[OptOrderService, Depends(_service)],
) -> OptAttachmentProbeResponse:
    return await service.probe_chat_attachment(
        actor,
        lead_id,
        chat_id=body.chat_id,
        message_id=body.message_id,
        attachment_index=body.attachment_index,
    )


@router.post(
    "/leads/{lead_id}/opt-orders/upload-from-attachment",
    status_code=201,
    response_model=OptOrderResponse,
)
async def upload_opt_from_chat_attachment(
    lead_id: int,
    body: OptUploadFromAttachmentRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    service: Annotated[OptOrderService, Depends(_service)],
) -> OptOrderResponse:
    return await service.upload_from_chat_attachment(
        actor,
        lead_id,
        chat_id=body.chat_id,
        message_id=body.message_id,
        attachment_index=body.attachment_index,
    )


@router.post(
    "/leads/{lead_id}/opt-orders/upload",
    status_code=201,
    response_model=OptOrderResponse,
)
async def upload_opt_application(
    lead_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    service: Annotated[OptOrderService, Depends(_service)],
    file: Annotated[UploadFile, File()],
) -> OptOrderResponse:
    content = await file.read()
    filename = file.filename or "application.xlsx"
    return await service.upload_application(
        actor,
        lead_id,
        filename=filename,
        content=content,
    )


@router.post(
    "/leads/{lead_id}/opt-orders/{order_id}/payments",
    status_code=201,
    response_model=OptOrderResponse,
)
async def add_opt_order_payment(
    lead_id: int,
    order_id: int,
    body: OptOrderPaymentCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    service: Annotated[OptOrderService, Depends(_service)],
) -> OptOrderResponse:
    return await service.add_payment(actor, lead_id, order_id, body)


@router.get("/leads/{lead_id}/opt-orders/{order_id}/payments/{payment_id}/document")
async def download_opt_payment_document(
    lead_id: int,
    order_id: int,
    payment_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
    service: Annotated[OptOrderService, Depends(_service)],
) -> Response:
    content, content_type, filename = await service.get_payment_document(
        actor,
        lead_id,
        order_id,
        payment_id,
    )
    ascii_name = filename.encode("ascii", "ignore").decode() or "payment-document"
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
            ),
        },
    )


@router.delete(
    "/leads/{lead_id}/opt-orders/{order_id}/lines/{line_id}",
    response_model=OptOrderResponse,
)
async def delete_opt_order_line(
    lead_id: int,
    order_id: int,
    line_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    service: Annotated[OptOrderService, Depends(_service)],
) -> OptOrderResponse:
    return await service.delete_line(actor, lead_id, order_id, line_id)


@router.patch(
    "/leads/{lead_id}/opt-orders/{order_id}/commission",
    response_model=OptOrderResponse,
)
async def adjust_opt_order_commission(
    lead_id: int,
    order_id: int,
    body: OptCommissionAdjustRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    service: Annotated[OptOrderService, Depends(_service)],
) -> OptOrderResponse:
    return await service.adjust_commission(actor, lead_id, order_id, body)


@router.delete("/leads/{lead_id}/opt-orders/{order_id}")
async def delete_opt_order(
    lead_id: int,
    order_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    service: Annotated[OptOrderService, Depends(_service)],
) -> dict[str, bool]:
    await service.delete_order(actor, lead_id, order_id)
    return {"deleted": True}


@router.post(
    "/leads/{lead_id}/opt-orders/{order_id}/send-registry",
    response_model=OptSendRegistryResponse,
)
async def send_opt_registry_to_client(
    lead_id: int,
    order_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    service: Annotated[OptOrderService, Depends(_service)],
) -> OptSendRegistryResponse:
    result = await service.send_registry_to_client(actor, lead_id, order_id)
    return OptSendRegistryResponse(**result)


@router.get("/leads/{lead_id}/opt-orders/{order_id}/registry")
async def download_opt_registry(
    lead_id: int,
    order_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
    service: Annotated[OptOrderService, Depends(_service)],
) -> Response:
    content, filename = await service.export_registry(actor, lead_id, order_id)
    ascii_name = filename.encode("ascii", "ignore").decode() or "registry.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
            ),
        },
    )
