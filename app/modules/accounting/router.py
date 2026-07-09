from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.schemas import (
    AccountingAssignmentListResponse,
    AccountingAssignmentItem,
    AccountingAssignmentUpdateRequest,
    AccountingRequirementIngestRequest,
    AccountingRequirementIngestResponse,
    AccountingRequirementListResponse,
    AccountingUnitCategoriesResponse,
    AccountingUnitCreateRequest,
    AccountingUnitListResponse,
    AccountingUnitOrdersResponse,
    AccountingUnitOwnerListResponse,
    AccountingUnitOwnerRow,
    AccountingUnitOwnerUpdateRequest,
    AccountingUnitResponse,
)
from app.modules.accounting.service import AccountingService
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.exceptions import PermissionDenied
from app.shared.security.permissions import requires_permission
from app.shared.settings import settings
from fastapi import APIRouter, File, Form, Query
from urllib.parse import quote

router = APIRouter(prefix="/api/v1/accounting", tags=["accounting"])


def _service(session: Annotated[AsyncSession, Depends(get_db)]) -> AccountingService:
    return AccountingService(session)


async def _require_ingest_token(
    x_accounting_ingest_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = (settings.accounting_ingest_token or "").strip()
    if not expected:
        raise PermissionDenied(message="Ingest token is not configured")
    if (x_accounting_ingest_token or "").strip() != expected:
        raise PermissionDenied(message="Invalid ingest token")


@router.get("/units", response_model=AccountingUnitListResponse)
async def list_accounting_units(
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    service: Annotated[AccountingService, Depends(_service)],
) -> AccountingUnitListResponse:
    return await service.list_units(actor)


@router.get("/units/categories", response_model=AccountingUnitCategoriesResponse)
async def list_accounting_unit_categories(
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    service: Annotated[AccountingService, Depends(_service)],
) -> AccountingUnitCategoriesResponse:
    return service.list_categories()


@router.post("/units", response_model=AccountingUnitResponse)
async def create_accounting_unit(
    body: AccountingUnitCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_MANAGE))],
    service: Annotated[AccountingService, Depends(_service)],
) -> AccountingUnitResponse:
    return await service.create_unit(actor, body)


@router.get("/orders", response_model=AccountingUnitOrdersResponse)
async def list_accounting_orders(
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    service: Annotated[AccountingService, Depends(_service)],
    supplier_inn: Annotated[str | None, Query()] = None,
    manager_user_id: Annotated[int | None, Query()] = None,
    date_from: Annotated[str | None, Query(description="YYYY-MM-DD")] = None,
    date_to: Annotated[str | None, Query(description="YYYY-MM-DD")] = None,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AccountingUnitOrdersResponse:
    from datetime import date as date_cls

    parsed_from = date_cls.fromisoformat(date_from) if date_from else None
    parsed_to = date_cls.fromisoformat(date_to) if date_to else None
    return await service.list_orders_by_units(
        actor,
        supplier_inn=supplier_inn,
        manager_user_id=manager_user_id,
        date_from=parsed_from,
        date_to=parsed_to,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/orders/{order_id}/registry")
async def download_accounting_registry(
    order_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    service: Annotated[AccountingService, Depends(_service)],
) -> Response:
    content, filename = await service.export_registry(actor, order_id)
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


@router.get("/requirements", response_model=AccountingRequirementListResponse)
async def list_accounting_requirements(
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    service: Annotated[AccountingService, Depends(_service)],
    supplier_inn: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AccountingRequirementListResponse:
    return await service.list_requirements(
        actor,
        supplier_inn=supplier_inn,
        status=status,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/requirements/{requirement_id}/pdf")
async def download_requirement_pdf(
    requirement_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    service: Annotated[AccountingService, Depends(_service)],
) -> Response:
    content, content_type, filename = await service.get_requirement_pdf(actor, requirement_id)
    ascii_name = filename.encode("ascii", "ignore").decode() or "requirement.pdf"
    return Response(
        content=content,
        media_type=content_type or "application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
            ),
        },
    )


@router.post(
    "/requirements/ingest",
    response_model=AccountingRequirementIngestResponse,
    dependencies=[Depends(_require_ingest_token)],
)
async def ingest_accounting_requirement_json(
    body: AccountingRequirementIngestRequest,
    service: Annotated[AccountingService, Depends(_service)],
) -> AccountingRequirementIngestResponse:
    return await service.ingest_requirement(body, pdf_bytes=None, pdf_filename=body.pdf_filename)


@router.post(
    "/requirements/ingest/multipart",
    response_model=AccountingRequirementIngestResponse,
    dependencies=[Depends(_require_ingest_token)],
)
async def ingest_accounting_requirement_multipart(
    service: Annotated[AccountingService, Depends(_service)],
    external_id: Annotated[str, Form()],
    supplier_inn: Annotated[str, Form()],
    title: Annotated[str, Form()],
    supplier_kpp: Annotated[str | None, Form()] = None,
    supplier_name: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    status: Annotated[str, Form()] = "new",
    received_at: Annotated[str | None, Form()] = None,
    metadata_json: Annotated[str | None, Form()] = None,
    pdf: Annotated[UploadFile | None, File()] = None,
) -> AccountingRequirementIngestResponse:
    import json
    from datetime import datetime

    metadata: dict[str, object] = {}
    if metadata_json:
        try:
            parsed = json.loads(metadata_json)
            if isinstance(parsed, dict):
                metadata = parsed
        except json.JSONDecodeError as exc:
            from app.shared.exceptions import ValidationError

            raise ValidationError(message="metadata_json must be valid JSON object") from exc

    received: datetime | None = None
    if received_at:
        received = datetime.fromisoformat(received_at.replace("Z", "+00:00"))

    pdf_bytes: bytes | None = None
    pdf_filename: str | None = None
    if pdf is not None:
        pdf_bytes = await pdf.read()
        pdf_filename = pdf.filename

    body = AccountingRequirementIngestRequest(
        external_id=external_id,
        supplier_inn=supplier_inn,
        supplier_kpp=supplier_kpp,
        supplier_name=supplier_name,
        title=title,
        description=description,
        status=status,
        received_at=received,
        metadata=metadata,
    )
    return await service.ingest_requirement(body, pdf_bytes=pdf_bytes, pdf_filename=pdf_filename)


@router.get("/assignments/units", response_model=AccountingUnitOwnerListResponse)
async def list_accounting_unit_owners(
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_MANAGE))],
    service: Annotated[AccountingService, Depends(_service)],
) -> AccountingUnitOwnerListResponse:
    return await service.list_unit_owners(actor)


@router.put("/assignments/units/{unit_id}", response_model=AccountingUnitOwnerRow)
async def assign_accounting_unit_owner(
    unit_id: int,
    body: AccountingUnitOwnerUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_MANAGE))],
    service: Annotated[AccountingService, Depends(_service)],
) -> AccountingUnitOwnerRow:
    return await service.assign_unit_owner(actor, unit_id, body.accountant_user_id)


@router.get("/assignments", response_model=AccountingAssignmentListResponse)
async def list_accounting_assignments(
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_MANAGE))],
    service: Annotated[AccountingService, Depends(_service)],
) -> AccountingAssignmentListResponse:
    return await service.list_assignments(actor)


@router.put("/assignments/{user_id}", response_model=AccountingAssignmentItem)
async def update_accounting_assignments(
    user_id: int,
    body: AccountingAssignmentUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_MANAGE))],
    service: Annotated[AccountingService, Depends(_service)],
) -> AccountingAssignmentItem:
    return await service.update_assignments(actor, user_id, body.unit_ids)
