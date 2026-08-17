from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.enums import UserStatus
from app.modules.db.models.idle_banner_settings import IdleBannerSettings
from app.modules.db.models.user import User
from app.modules.files.service import FilesService
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
from app.shared.exceptions import AppError, NotFound, PermissionDenied, ValidationError
from app.shared.security.deps import current_user
from app.shared.settings import get_settings
from app.shared.upload_limits import is_photo_mime, max_upload_bytes_for

router = APIRouter(prefix="/api/v1/idle-banner", tags=["idle-banner"])

_SETTINGS_ID = 1
_ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


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


def _image_version(row: IdleBannerSettings) -> int:
    ts = row.updated_at
    if ts is None:
        return 0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return int(ts.timestamp())


def _status(row: IdleBannerSettings) -> IdleBannerStatus:
    return IdleBannerStatus(
        is_enabled=row.is_enabled,
        has_image=row.image_file_id is not None,
        image_version=_image_version(row),
    )


def _settings_payload(row: IdleBannerSettings) -> dict[str, bool | int]:
    return {
        "is_enabled": row.is_enabled,
        "has_image": row.image_file_id is not None,
        "image_version": _image_version(row),
    }


@router.get("", response_model=IdleBannerStatus)
async def get_idle_banner(
    _actor: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IdleBannerStatus:
    return _status(await _get_or_create(db))


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
    await publish(IDLE_BANNER_SETTINGS, _settings_payload(row))
    return _status(row)


@router.get("/image")
async def get_idle_banner_image(
    _actor: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    row = await _get_or_create(db)
    if row.image_file_id is None:
        raise NotFound(message="Нет загруженного баннера")
    data, content_type, filename = await FilesService(db).get_bytes(row.image_file_id)
    ascii_name = filename.encode("ascii", "ignore").decode() or "banner"
    return Response(
        content=data,
        media_type=content_type or "image/jpeg",
        headers={
            "Cache-Control": "private, max-age=60",
            "Content-Disposition": (
                f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
            ),
        },
    )


@router.post("/image", response_model=IdleBannerStatus)
async def upload_idle_banner_image(
    actor: Annotated[User, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
) -> IdleBannerStatus:
    _require_admin(actor)
    content = await file.read()
    mime = (file.content_type or "").lower()
    name = file.filename or "banner.jpg"
    if not is_photo_mime(mime) and not name.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        raise ValidationError(message="Нужна картинка: JPG, PNG, WEBP или GIF")
    if mime not in _ALLOWED_IMAGE_TYPES and mime != "image/jpg":
        if not name.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            raise ValidationError(message="Нужна картинка: JPG, PNG, WEBP или GIF")
        mime = "image/jpeg" if name.lower().endswith((".jpg", ".jpeg")) else mime or "image/png"
    settings = get_settings()
    max_bytes = max_upload_bytes_for(
        mime=mime if is_photo_mime(mime) else "image/jpeg",
        max_photo_bytes=settings.max_upload_photo_bytes,
        max_file_bytes=settings.max_upload_file_bytes,
    )
    if len(content) > max_bytes:
        raise AppError(
            code="payload_too_large",
            message="Файл слишком большой",
            status=413,
            details={"max_bytes": max_bytes},
        )
    uploaded = await FilesService(db).create_upload(
        uploaded_by=actor.id,
        data=content,
        original_name=name,
        mime_type=mime if is_photo_mime(mime) else "image/jpeg",
    )
    row = await _get_or_create(db)
    row.image_file_id = uploaded.id
    row.updated_by = actor.id
    row.updated_at = datetime.now(UTC)
    await db.commit()
    await publish(IDLE_BANNER_SETTINGS, _settings_payload(row))
    return _status(row)


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
