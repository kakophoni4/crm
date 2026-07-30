from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounting.schemas import (
    AccountingAssignmentListResponse,
    AccountingAssignmentItem,
    AccountingAssignmentUpdateRequest,
    AccountingOrderPeriodUpdateRequest,
    AccountingOrderPeriodUpdateResponse,
    AccountingReceiptIngestResponse,
    AccountingReceiptPullClaimResponse,
    AccountingReceiptSyncResponse,
    AccountingRequirementIngestRequest,
    AccountingRequirementIngestResponse,
    AccountingRequirementListResponse,
    AccountingRequirementPullClaimResponse,
    AccountingRequirementResponse,
    AccountingRequirementStatusUpdateRequest,
    AccountingRequirementSyncResponse,
    AccountingRequirementWebhookPayload,
    AccountingUnitCategoriesResponse,
    AccountingUnitCreateRequest,
    AccountingUnitListResponse,
    AccountingUnitOrdersResponse,
    AccountingUnitOwnerListResponse,
    AccountingUnitOwnerRow,
    AccountingUnitOwnerUpdateRequest,
    AccountingUnitPatchRequest,
    AccountingUnitResponse,
)
from app.modules.accounting.service import AccountingService
from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.exceptions import PermissionDenied
from app.shared.security.permissions import requires_permission
from app.shared.settings import settings
from fastapi import APIRouter, File, Form, Query, Request
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


async def _require_sbis_webhook_token(request: Request) -> None:
    expected = (settings.sbis_norm_webhook_token or "").strip()
    if not expected:
        # Fall back to API token if webhook token not set separately
        expected = (settings.sbis_norm_api_token or "").strip()
    if not expected:
        raise PermissionDenied(message="Webhook token is not configured")

    api_key = (request.headers.get("X-API-Key") or "").strip()
    auth = (request.headers.get("Authorization") or "").strip()
    bearer = ""
    if auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
    provided = api_key or bearer
    if provided != expected:
        raise PermissionDenied(message="Invalid webhook token")


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


@router.patch("/units/{unit_id}", response_model=AccountingUnitResponse)
async def patch_accounting_unit(
    unit_id: int,
    body: AccountingUnitPatchRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_MANAGE))],
    service: Annotated[AccountingService, Depends(_service)],
) -> AccountingUnitResponse:
    return await service.update_unit(actor, unit_id, body)


@router.delete("/units/{unit_id}", status_code=204)
async def delete_accounting_unit(
    unit_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_MANAGE))],
    service: Annotated[AccountingService, Depends(_service)],
) -> None:
    await service.delete_unit(actor, unit_id)


@router.get("/orders", response_model=AccountingUnitOrdersResponse)
async def list_accounting_orders(
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    service: Annotated[AccountingService, Depends(_service)],
    supplier_inn: Annotated[str | None, Query()] = None,
    manager_user_id: Annotated[int | None, Query()] = None,
    date_from: Annotated[str | None, Query(description="YYYY-MM-DD")] = None,
    date_to: Annotated[str | None, Query(description="YYYY-MM-DD")] = None,
    q: Annotated[str | None, Query()] = None,
    period_code: Annotated[str | None, Query(description="OPT period, e.g. 2/26")] = None,
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
        period_code=(period_code or "").strip() or None,
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


@router.patch(
    "/orders/{order_id}/period",
    response_model=AccountingOrderPeriodUpdateResponse,
)
async def patch_accounting_order_period(
    order_id: int,
    body: AccountingOrderPeriodUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    service: Annotated[AccountingService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccountingOrderPeriodUpdateResponse:
    order_id_out, period_code = await service.update_order_period(
        actor,
        order_id,
        body.period_code,
    )
    await db.commit()
    return AccountingOrderPeriodUpdateResponse(order_id=order_id_out, period_code=period_code)


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
    "/requirements/sync",
    response_model=AccountingRequirementSyncResponse,
)
async def sync_accounting_requirements(
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
) -> AccountingRequirementSyncResponse:
    """Request pull. In agent mode kali pull-agent claims and pushes ingest."""
    del actor
    from app.workers.jobs.sbis_norm_sync import schedule_sbis_norm_sync_if_due
    from app.shared.settings import get_settings

    await schedule_sbis_norm_sync_if_due(force=True)
    mode = (get_settings().sbis_norm_sync_mode or "agent").strip().lower()
    return AccountingRequirementSyncResponse(
        fetched=0,
        created=0,
        existing=0,
        failed=0,
        marked_synced=0,
        skipped_non_pdf=0,
        queued=True,
        mode=mode,
        errors=[],
    )


@router.post(
    "/requirements/pull-claim",
    response_model=AccountingRequirementPullClaimResponse,
    dependencies=[Depends(_require_ingest_token)],
)
async def claim_accounting_requirements_pull() -> AccountingRequirementPullClaimResponse:
    """Kali pull-agent: claim a UI/schedule pull request (no CRM→sbis download)."""
    from app.workers.jobs.sbis_norm_sync import claim_sbis_norm_pull

    claimed = await claim_sbis_norm_pull()
    return AccountingRequirementPullClaimResponse(claimed=claimed)


@router.patch(
    "/requirements/{requirement_id}",
    response_model=AccountingRequirementResponse,
)
async def patch_accounting_requirement(
    requirement_id: int,
    body: AccountingRequirementStatusUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
    service: Annotated[AccountingService, Depends(_service)],
) -> AccountingRequirementResponse:
    return await service.update_requirement_status(actor, requirement_id, body.status)


@router.post(
    "/requirements/webhook",
    response_model=AccountingRequirementSyncResponse,
    dependencies=[Depends(_require_sbis_webhook_token)],
)
async def sbis_norm_requirements_webhook(
    body: AccountingRequirementWebhookPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccountingRequirementSyncResponse:
    """Push from sbis-norm after scanner save (meta only → CRM pulls file)."""
    from app.modules.accounting.sbis_norm_sync import sync_requirement_by_id

    result = await sync_requirement_by_id(db, body.id, mark=True)
    await db.commit()
    return AccountingRequirementSyncResponse(
        fetched=result.fetched,
        created=result.created,
        existing=result.existing,
        failed=result.failed,
        marked_synced=result.marked_synced,
        skipped_non_pdf=result.skipped_non_pdf,
        errors=result.errors[:20],
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


@router.post(
    "/receipts/sync",
    response_model=AccountingReceiptSyncResponse,
)
async def sync_accounting_receipts(
    actor: Annotated[User, Depends(requires_permission(Permission.ACCOUNTING_READ))],
) -> AccountingReceiptSyncResponse:
    del actor
    from app.workers.jobs.sbis_norm_sync import request_sbis_receipts_pull

    await request_sbis_receipts_pull(reason="manual")
    return AccountingReceiptSyncResponse(queued=True, mode="agent")


@router.post(
    "/receipts/pull-claim",
    response_model=AccountingReceiptPullClaimResponse,
    dependencies=[Depends(_require_ingest_token)],
)
async def claim_accounting_receipts_pull() -> AccountingReceiptPullClaimResponse:
    from app.workers.jobs.sbis_norm_sync import claim_sbis_receipts_pull

    claimed = await claim_sbis_receipts_pull()
    return AccountingReceiptPullClaimResponse(claimed=claimed)


@router.post(
    "/receipts/ingest/multipart",
    response_model=AccountingReceiptIngestResponse,
    dependencies=[Depends(_require_ingest_token)],
)
async def ingest_accounting_receipt_multipart(
    db: Annotated[AsyncSession, Depends(get_db)],
    external_id: Annotated[str, Form()],
    pdf: Annotated[UploadFile, File()],
    supplier_inn: Annotated[str | None, Form()] = None,
    supplier_kpp: Annotated[str | None, Form()] = None,
    supplier_name: Annotated[str | None, Form()] = None,
    period_code: Annotated[str | None, Form()] = None,
    doc_kind: Annotated[str | None, Form()] = None,
    source_filename: Annotated[str | None, Form()] = None,
    metadata_json: Annotated[str | None, Form()] = None,
) -> AccountingReceiptIngestResponse:
    import json

    from app.modules.accounting.receipts import ingest_receipt_pdf

    metadata: dict[str, object] = {}
    if metadata_json:
        try:
            parsed = json.loads(metadata_json)
            if isinstance(parsed, dict):
                metadata = parsed
        except json.JSONDecodeError as exc:
            from app.shared.exceptions import ValidationError

            raise ValidationError(message="Некорректный metadata_json") from exc

    pdf_bytes = await pdf.read()
    filename = (source_filename or pdf.filename or "receipt.pdf").strip()
    row, created = await ingest_receipt_pdf(
        db,
        external_id=external_id,
        pdf_bytes=pdf_bytes,
        source_filename=filename,
        supplier_inn=supplier_inn,
        supplier_kpp=supplier_kpp,
        supplier_name=supplier_name,
        period_code=period_code,
        doc_kind=doc_kind,
        metadata=metadata,
    )
    await db.commit()
    return AccountingReceiptIngestResponse(
        id=row.id,
        external_id=row.external_id,
        supplier_inn=row.supplier_inn,
        period_code=row.period_code,
        doc_kind=row.doc_kind,
        created=created,
    )


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
