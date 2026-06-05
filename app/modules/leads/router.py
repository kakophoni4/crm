from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.decorator import AuditedResult, audit
from app.modules.db.models.enums import AuditAction
from app.modules.db.models.user import User
from app.modules.leads.api_service import LeadApiService, LeadMutationResult
from app.modules.leads.rate_limit import (
    enforce_leads_create_rate_limit,
    enforce_leads_list_rate_limit,
)
from app.modules.leads.schemas import (
    CrmDashboardSummaryResponse,
    LeadCloseRequest,
    LeadCreateRequest,
    LeadDetailResponse,
    LeadListResponse,
    LeadPatchRequest,
)
from app.modules.leads.serialization import to_lead_detail
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1", tags=["leads"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> LeadApiService:
    return LeadApiService(db)


@router.get("/crm-summary", response_model=CrmDashboardSummaryResponse)
async def get_crm_dashboard_summary(
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
    service: Annotated[LeadApiService, Depends(_service)],
) -> CrmDashboardSummaryResponse:
    return await service.get_dashboard_crm_summary(actor)


@router.get("/contacts/{contact_id}/leads", response_model=LeadListResponse)
async def list_contact_leads(
    contact_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
    service: Annotated[LeadApiService, Depends(_service)],
    group_id: int | None = None,
    status_id: int | None = None,
    open_only: bool | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> LeadListResponse:
    await enforce_leads_list_rate_limit(actor.id)
    return await service.list_contact_leads(
        actor,
        contact_id,
        group_id=group_id,
        status_id=status_id,
        open_only=open_only,
        cursor=cursor,
        limit=limit,
    )


@router.post("/contacts/{contact_id}/leads", status_code=201, response_model=LeadDetailResponse)
@audit(AuditAction.LEAD_CREATE, "lead")
async def create_contact_lead(
    contact_id: int,
    body: LeadCreateRequest,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    service: Annotated[LeadApiService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[LeadDetailResponse]:
    await enforce_leads_create_rate_limit(actor.id)
    result = await service.create_manual_lead(actor, contact_id, body)
    return AuditedResult(
        data=to_lead_detail(result.lead, in_scope=True),
        entity_id=result.lead.id,
        payload=result.audit_payload,
    )


@router.get("/leads/{lead_id}", response_model=LeadDetailResponse)
async def get_lead(
    lead_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_READ))],
    service: Annotated[LeadApiService, Depends(_service)],
) -> LeadDetailResponse:
    return await service.get_lead(actor, lead_id)


@router.patch("/leads/{lead_id}", response_model=LeadDetailResponse)
@audit(AuditAction.LEAD_STATUS_UPDATE, "lead")
async def patch_lead(
    lead_id: int,
    body: LeadPatchRequest,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    service: Annotated[LeadApiService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[LeadDetailResponse]:
    result: LeadMutationResult = await service.patch_lead(actor, lead_id, body)
    detail = await service.get_lead(actor, result.lead.id)
    return AuditedResult(
        data=detail,
        entity_id=result.lead.id,
        payload=result.audit_payload,
        action=result.audit_action,
        skip=result.skip_audit,
    )


@router.post("/leads/{lead_id}/close", response_model=LeadDetailResponse)
@audit(AuditAction.LEAD_CLOSE, "lead")
async def close_lead(
    lead_id: int,
    body: LeadCloseRequest,
    request: Request,
    actor: Annotated[User, Depends(requires_permission(Permission.CONTACTS_UPDATE))],
    service: Annotated[LeadApiService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuditedResult[LeadDetailResponse]:
    closed = await service.close_lead(actor, lead_id, body)
    detail = await service.get_lead(actor, closed.id)
    return AuditedResult(
        data=detail,
        entity_id=closed.id,
        payload={
            "lead_id": closed.id,
            "contact_id": closed.contact_id,
            "group_id": closed.group_id,
            "chat_id": closed.chat_id,
            "closed_at": closed.closed_at.isoformat() if closed.closed_at else None,
            "closed_by_user_id": actor.id,
        },
    )
