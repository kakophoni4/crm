from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.escalation import (
    STRATEGY_FIRST_RESPONDER,
    STRATEGY_RANDOM_AVAILABLE,
    get_group_settings,
)
from app.modules.contacts.schemas_transfer import (
    EscalationSettingsPatchRequest,
    EscalationSettingsResponse,
)
from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.group import Group
from app.modules.db.models.user import User
from app.modules.groups.schemas import (
    GroupCreateRequest,
    GroupListResponse,
    GroupOut,
    GroupUpdateRequest,
)
from app.modules.groups.service import GroupOrgService
from app.modules.rbac.permissions import Permission
from app.modules.rbac.scope import SCOPE_ALL, visible_group_ids
from app.shared.db import get_db
from app.shared.exceptions import NotFound, ValidationError
from app.shared.security.permissions import requires_permission

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])

_VALID_STRATEGIES = frozenset({STRATEGY_FIRST_RESPONDER, STRATEGY_RANDOM_AVAILABLE})


def _org_service(db: Annotated[AsyncSession, Depends(get_db)]) -> GroupOrgService:
    return GroupOrgService(db)


@router.get("", response_model=GroupListResponse)
async def list_groups(
    actor: Annotated[User, Depends(requires_permission(Permission.GROUPS_READ))],
    service: Annotated[GroupOrgService, Depends(_org_service)],
    department_id: int | None = Query(default=None),
) -> GroupListResponse:
    return await service.list_groups(actor, department_id=department_id)


@router.post("", response_model=GroupOut, status_code=201)
async def create_group(
    body: GroupCreateRequest,
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.GROUPS_CREATE,
                Permission.GROUPS_CREATE_IN_DEP,
            ),
        ),
    ],
    service: Annotated[GroupOrgService, Depends(_org_service)],
) -> GroupOut:
    return await service.create_group(actor, body)


@router.patch("/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: int,
    body: GroupUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.GROUPS_UPDATE))],
    service: Annotated[GroupOrgService, Depends(_org_service)],
) -> GroupOut:
    return await service.update_group(actor, group_id, body)


@router.delete("/{group_id}", response_model=GroupOut)
async def delete_group(
    group_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.GROUPS_DELETE))],
    service: Annotated[GroupOrgService, Depends(_org_service)],
) -> GroupOut:
    return await service.delete_group(actor, group_id)


@router.get("/{group_id}/escalation-settings", response_model=EscalationSettingsResponse)
async def get_escalation_settings(
    group_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.GROUPS_UPDATE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EscalationSettingsResponse:
    await _ensure_group_manageable(db, actor, group_id)
    settings = await get_group_settings(db, group_id)
    return EscalationSettingsResponse(
        group_id=settings.group_id,
        first_response_timeout_minutes=settings.first_response_timeout_minutes,
        new_contact_reassign_strategy=settings.new_contact_reassign_strategy,
        notify_owner_on_inbound=settings.notify_owner_on_inbound,
        notify_group_on_escalation=settings.notify_group_on_escalation,
        updated_at=settings.updated_at,
    )


@router.patch("/{group_id}/escalation-settings", response_model=EscalationSettingsResponse)
async def patch_escalation_settings(
    group_id: int,
    body: EscalationSettingsPatchRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.GROUPS_UPDATE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EscalationSettingsResponse:
    await _ensure_group_manageable(db, actor, group_id)
    settings = await get_group_settings(db, group_id)
    if body.first_response_timeout_minutes is not None:
        settings.first_response_timeout_minutes = body.first_response_timeout_minutes
    if body.new_contact_reassign_strategy is not None:
        if body.new_contact_reassign_strategy not in _VALID_STRATEGIES:
            raise ValidationError(
                message="new_contact_reassign_strategy must be first_responder or random_available",
            )
        settings.new_contact_reassign_strategy = body.new_contact_reassign_strategy
    if body.notify_owner_on_inbound is not None:
        settings.notify_owner_on_inbound = body.notify_owner_on_inbound
    if body.notify_group_on_escalation is not None:
        settings.notify_group_on_escalation = body.notify_group_on_escalation
    settings.updated_by = actor.id
    await db.flush()
    await db.refresh(settings)
    return EscalationSettingsResponse(
        group_id=settings.group_id,
        first_response_timeout_minutes=settings.first_response_timeout_minutes,
        new_contact_reassign_strategy=settings.new_contact_reassign_strategy,
        notify_owner_on_inbound=settings.notify_owner_on_inbound,
        notify_group_on_escalation=settings.notify_group_on_escalation,
        updated_at=settings.updated_at,
    )


async def _ensure_group_manageable(
    session: AsyncSession,
    actor: User,
    group_id: int,
) -> Group:
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise NotFound(message="Group not found")
    ctx = await ScopeLoader(session).load(actor)
    visible = visible_group_ids(ctx)
    if visible != SCOPE_ALL and (not isinstance(visible, set) or group_id not in visible):
        raise NotFound(message="Group not found")
    return group


__all__ = ["router"]
