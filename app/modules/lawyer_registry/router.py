from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.lawyer_registry.schemas import (
    LawyerAlertListResponse,
    LawyerAlertReadRequest,
    LawyerDirectorCreateRequest,
    LawyerDirectorListResponse,
    LawyerDirectorOut,
    LawyerDirectorPatchRequest,
    LawyerImportResponse,
    LawyerPaymentCreateRequest,
    LawyerPaymentOut,
    LawyerShopCreateRequest,
    LawyerShopOut,
    LawyerShopPatchRequest,
)
from app.modules.lawyer_registry.service import LawyerRegistryService
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.exceptions import NotFound, ValidationError
from app.shared.security.permissions import has_permission, requires_permission

router = APIRouter(prefix="/api/v1/lawyer-registry", tags=["lawyer-registry"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> LawyerRegistryService:
    return LawyerRegistryService(db)


@router.get("", response_model=LawyerDirectorListResponse)
async def list_registry(
    actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ, Permission.ACCOUNTING_READ))],
    service: Annotated[LawyerRegistryService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    kind: Annotated[str | None, Query(max_length=32)] = None,
    company_status: Annotated[str | None, Query(max_length=64)] = None,
    unreliable: Annotated[str | None, Query(max_length=64)] = None,
    zsk: Annotated[str | None, Query(max_length=64)] = None,
    ecsp_status: Annotated[str | None, Query(max_length=64)] = None,
    manager: Annotated[str | None, Query(max_length=128)] = None,
    dirovod: Annotated[str | None, Query(max_length=128)] = None,
    include_hidden: bool = False,
) -> LawyerDirectorListResponse:
    if not has_permission(actor.role, Permission.PARSER_READ):
        return await service.accountant_tree(
            actor, q=q, kind=kind, company_status=company_status,
            unreliable=unreliable, zsk=zsk, ecsp_status=ecsp_status,
            manager=manager, dirovod=dirovod, include_hidden=include_hidden,
        )
    return await service.list_tree(
        q=q,
        kind=kind,
        company_status=company_status,
        unreliable=unreliable,
        zsk=zsk,
        ecsp_status=ecsp_status,
        manager=manager,
        dirovod=dirovod,
        include_hidden=include_hidden,
    )


@router.get("/alerts", response_model=LawyerAlertListResponse)
async def list_alerts(
    actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ, Permission.ACCOUNTING_READ))],
    service: Annotated[LawyerRegistryService, Depends(_service)],
) -> LawyerAlertListResponse:
    if not has_permission(actor.role, Permission.PARSER_READ):
        return LawyerAlertListResponse(items=[], unread=0)
    return await service.list_alerts()


@router.post("/alerts/read")
async def mark_alerts_read(
    actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ))],
    service: Annotated[LawyerRegistryService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    body: LawyerAlertReadRequest | None = None,
) -> dict[str, bool]:
    _ = actor
    await service.mark_alerts_read(body.ids if body else None)
    await db.commit()
    return {"ok": True}


@router.post("/import", response_model=LawyerImportResponse)
async def import_svodnaya(
    actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ))],
    service: Annotated[LawyerRegistryService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
) -> LawyerImportResponse:
    name = (file.filename or "").lower()
    if not name.endswith(".xlsx"):
        raise ValidationError(message="Нужен файл .xlsx")
    content = await file.read()
    result = await service.import_svodnaya(actor, content)
    await db.commit()
    return result


@router.post("/directors", status_code=201, response_model=LawyerDirectorOut)
async def create_director(
    body: LawyerDirectorCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ))],
    service: Annotated[LawyerRegistryService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LawyerDirectorOut:
    result = await service.create_director(actor, body)
    await db.commit()
    return result


@router.get("/directors/{director_id}", response_model=LawyerDirectorOut)
async def get_director(
    director_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ, Permission.ACCOUNTING_READ))],
    service: Annotated[LawyerRegistryService, Depends(_service)],
) -> LawyerDirectorOut:
    if not has_permission(actor.role, Permission.PARSER_READ):
        tree = await service.accountant_tree(actor, director_id=director_id, include_hidden=True)
        if not tree.items:
            raise NotFound(message="Директор не найден среди назначенных вам лавок")
        return tree.items[0]
    return await service.get_director(director_id)


@router.patch("/directors/{director_id}", response_model=LawyerDirectorOut)
async def patch_director(
    director_id: int,
    body: LawyerDirectorPatchRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ))],
    service: Annotated[LawyerRegistryService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LawyerDirectorOut:
    result = await service.patch_director(actor, director_id, body)
    await db.commit()
    return result


@router.post(
    "/directors/{director_id}/payments",
    status_code=201,
    response_model=LawyerPaymentOut,
)
async def add_payment(
    director_id: int,
    body: LawyerPaymentCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ))],
    service: Annotated[LawyerRegistryService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LawyerPaymentOut:
    result = await service.add_payment(actor, director_id, body)
    await db.commit()
    return result


@router.delete("/payments/{payment_id}")
async def delete_payment(
    payment_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ))],
    service: Annotated[LawyerRegistryService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    _ = actor
    await service.delete_payment(payment_id)
    await db.commit()
    return {"deleted": True}


@router.post("/shops", status_code=201, response_model=LawyerShopOut)
async def create_shop(
    body: LawyerShopCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ))],
    service: Annotated[LawyerRegistryService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LawyerShopOut:
    result = await service.create_shop(actor, body)
    await db.commit()
    return result


@router.patch("/shops/{shop_id}", response_model=LawyerShopOut)
async def patch_shop(
    shop_id: int,
    body: LawyerShopPatchRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.PARSER_READ))],
    service: Annotated[LawyerRegistryService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LawyerShopOut:
    accounting_fields = {"received_at", "company_status", "treatment_status", "unreliable", "zsk", "ecsp_status", "banks", "accounts_status", "registered_at", "fns", "sbis", "edo_id", "edo_until", "purchased_at", "failed_at", "failure_reason", "accountant"}
    if body.model_fields_set & accounting_fields:
        raise ValidationError(message="Эти поля заполняются в разделе «Бухгалтерия → Лавки»")
    result = await service.patch_shop(actor, shop_id, body)
    await db.commit()
    return result
