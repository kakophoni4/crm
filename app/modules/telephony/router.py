from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.telephony.schemas import (
    TelephonyAccountCreateRequest,
    TelephonyAccountListResponse,
    TelephonyAccountResponse,
    TelephonyAccountUpdateRequest,
    TelephonyWebrtcConfigResponse,
)
from app.modules.telephony.service import TelephonyService
from app.shared.db import get_db
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/telephony", tags=["telephony"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> TelephonyService:
    return TelephonyService(db)


@router.get("/accounts", response_model=TelephonyAccountListResponse)
async def list_accounts(
    actor: Annotated[User, Depends(requires_permission(Permission.TELEPHONY_READ))],
    service: Annotated[TelephonyService, Depends(_service)],
) -> TelephonyAccountListResponse:
    return await service.list_accounts(actor)


@router.post("/accounts", response_model=TelephonyAccountResponse, status_code=201)
async def create_account(
    body: TelephonyAccountCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.TELEPHONY_MANAGE))],
    service: Annotated[TelephonyService, Depends(_service)],
) -> TelephonyAccountResponse:
    return await service.create_account(actor, body)


@router.get("/accounts/{account_id}", response_model=TelephonyAccountResponse)
async def get_account(
    account_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.TELEPHONY_READ))],
    service: Annotated[TelephonyService, Depends(_service)],
) -> TelephonyAccountResponse:
    return await service.get_account(account_id, actor)


@router.patch("/accounts/{account_id}", response_model=TelephonyAccountResponse)
async def update_account(
    account_id: int,
    body: TelephonyAccountUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.TELEPHONY_MANAGE))],
    service: Annotated[TelephonyService, Depends(_service)],
) -> TelephonyAccountResponse:
    return await service.update_account(account_id, actor, body)


@router.delete("/accounts/{account_id}", response_model=TelephonyAccountResponse)
async def deactivate_account(
    account_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.TELEPHONY_MANAGE))],
    service: Annotated[TelephonyService, Depends(_service)],
) -> TelephonyAccountResponse:
    return await service.deactivate_account(account_id, actor)


@router.post(
    "/accounts/{account_id}/webrtc-config",
    response_model=TelephonyWebrtcConfigResponse,
)
async def get_webrtc_config(
    account_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.TELEPHONY_CALL))],
    service: Annotated[TelephonyService, Depends(_service)],
) -> TelephonyWebrtcConfigResponse:
    return await service.get_webrtc_config(account_id, actor)
