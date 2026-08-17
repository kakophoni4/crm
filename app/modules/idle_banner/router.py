from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import UserStatus
from app.modules.db.models.idle_banner_settings import IdleBannerSettings
from app.modules.db.models.user import User
from app.modules.idle_banner.schemas import (
    IdleBannerPatchRequest,
    IdleBannerSendRequest,
    IdleBannerSendResponse,
    IdleBannerStatus,
)
from app.modules.rbac.role_checks import is_admin
from app.realtime.events import publish
from app.realtime.topics import IDLE_BANNER_SETTINGS, IDLE_BANNER_SHOW
from app.shared.db import get_db
from app.shared.exceptions import PermissionDenied, ValidationError
from app.shared.security.deps import current_user

router = APIRouter(prefix="/api/v1/idle-banner", tags=["idle-banner"])

_SETTINGS_ID = 1


async def _get_or_create(db: AsyncSession) -> IdleBannerSettings:
    row = await db.get(IdleBannerSettings, _SETTINGS_ID)
    if row is not None:
        return row
    row = IdleBannerSettings(id=_SETTINGS_ID, is_enabled=False)
    db.add(row)
    await db.flush()
    return row


def _require_admin(actor: User) -> None:
    if not is_admin(actor.role):
        raise PermissionDenied(message="Только администратор")


@router.get("", response_model=IdleBannerStatus)
async def get_idle_banner(
    _actor: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IdleBannerStatus:
    row = await _get_or_create(db)
    return IdleBannerStatus(is_enabled=row.is_enabled)


@router.patch("", response_model=IdleBannerStatus)
async def patch_idle_banner(
    body: IdleBannerPatchRequest,
    actor: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IdleBannerStatus:
    _require_admin(actor)
    row = await _get_or_create(db)
    row.is_enabled = body.is_enabled
    row.updated_by = actor.id
    row.updated_at = datetime.now(UTC)
    await db.commit()
    await publish(IDLE_BANNER_SETTINGS, {"is_enabled": row.is_enabled})
    return IdleBannerStatus(is_enabled=row.is_enabled)


@router.post("/send", response_model=IdleBannerSendResponse)
async def send_idle_banner(
    body: IdleBannerSendRequest,
    actor: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IdleBannerSendResponse:
    _require_admin(actor)
    ids = sorted({int(uid) for uid in body.user_ids if int(uid) > 0})
    if not ids:
        raise ValidationError(message="Выберите пользователей")
    result = await db.execute(
        select(User.id).where(
            User.id.in_(ids),
            User.status == UserStatus.ACTIVE,
        ),
    )
    active_ids = [int(uid) for uid in result.scalars().all()]
    if not active_ids:
        raise ValidationError(message="Нет активных пользователей в списке")
    for uid in active_ids:
        await publish(IDLE_BANNER_SHOW, {"user_id": uid}, scope={"user_id": uid})
    return IdleBannerSendResponse(sent=len(active_ids))
