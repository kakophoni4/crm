from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.tickets.client import smertniki_request
from app.modules.tickets.schemas import CompanyPatchRequest, TicketCreateRequest, TicketsInnsRequest
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


@router.get("/companies")
async def list_companies(
    _actor: Annotated[User, Depends(requires_permission(Permission.TICKETS_READ))],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    return await smertniki_request("GET", "/api/v1/companies")


@router.post("/companies/inns")
async def add_companies_by_inn(
    body: TicketsInnsRequest,
    _actor: Annotated[User, Depends(requires_permission(Permission.TICKETS_READ))],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    return await smertniki_request(
        "POST",
        "/api/v1/companies/inns",
        json=body.model_dump(),
    )


@router.patch("/companies/{company_id}")
async def patch_company(
    company_id: int,
    body: CompanyPatchRequest,
    _actor: Annotated[User, Depends(requires_permission(Permission.TICKETS_READ))],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    return await smertniki_request(
        "PATCH",
        f"/api/v1/companies/{company_id}",
        json=body.model_dump(exclude_unset=True),
    )


@router.post("/companies/{company_id}/check")
async def check_company(
    company_id: int,
    _actor: Annotated[User, Depends(requires_permission(Permission.TICKETS_READ))],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    return await smertniki_request("POST", f"/api/v1/companies/{company_id}/check")


@router.post("/companies/check-all")
async def check_all_companies(
    _actor: Annotated[User, Depends(requires_permission(Permission.TICKETS_READ))],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    return await smertniki_request("POST", "/api/v1/companies/check-all", timeout=30.0)


@router.get("/companies/check-all")
async def check_all_status(
    _actor: Annotated[User, Depends(requires_permission(Permission.TICKETS_READ))],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    return await smertniki_request("GET", "/api/v1/companies/check-all")


@router.get("")
async def list_tickets(
    _actor: Annotated[User, Depends(requires_permission(Permission.TICKETS_READ))],
    _db: Annotated[AsyncSession, Depends(get_db)],
    issue_type: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> Any:
    params: dict[str, str] = {}
    if issue_type:
        params["issue_type"] = issue_type
    if status:
        params["status"] = status
    return await smertniki_request("GET", "/api/v1/tickets", params=params or None)


@router.post("")
async def create_ticket(
    body: TicketCreateRequest,
    _actor: Annotated[User, Depends(requires_permission(Permission.TICKETS_READ))],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    return await smertniki_request("POST", "/api/v1/tickets", json=body.model_dump())


@router.post("/{ticket_id}/heal")
async def heal_ticket(
    ticket_id: int,
    _actor: Annotated[User, Depends(requires_permission(Permission.TICKETS_READ))],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    return await smertniki_request("POST", f"/api/v1/tickets/{ticket_id}/heal")
