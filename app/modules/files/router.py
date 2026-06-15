from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.hmac_util import verify_outbound
from app.modules.bots.repository import BotRepository
from app.modules.db.models.user import User
from app.modules.files.service import FilesService
from app.modules.rbac.permissions import Permission
from app.shared.db import get_db
from app.shared.exceptions import AppError, AuthenticationRequired, NotFound
from app.shared.security.permissions import requires_permission
from app.shared.settings import get_settings
from app.shared.upload_limits import max_upload_bytes_for

router = APIRouter(prefix="/api/v1/files", tags=["files"])


def _files_service(db: Annotated[AsyncSession, Depends(get_db)]) -> FilesService:
    return FilesService(db)


@router.post("")
async def upload_file(
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_UPLOAD))],
    service: Annotated[FilesService, Depends(_files_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
) -> dict[str, int | str]:
    settings = get_settings()
    content = await file.read()
    mime = file.content_type or "application/octet-stream"
    max_bytes = max_upload_bytes_for(
        mime=mime,
        max_photo_bytes=settings.max_upload_photo_bytes,
        max_file_bytes=settings.max_upload_file_bytes,
    )
    if len(content) > max_bytes:
        raise AppError(
            code="payload_too_large",
            message="File too large",
            status=413,
            details={"max_bytes": max_bytes},
        )
    name = file.filename or "file"
    row = await service.create_upload(
        uploaded_by=actor.id,
        data=content,
        original_name=name,
        mime_type=mime,
    )
    await db.commit()
    return {"id": row.id, "name": row.original_name, "mime": row.mime_type, "size": row.size_bytes}


@router.get("/{file_id}")
async def download_file(
    file_id: int,
    _actor: Annotated[User, Depends(requires_permission(Permission.FILES_DOWNLOAD))],
    service: Annotated[FilesService, Depends(_files_service)],
) -> Response:
    data, content_type, filename = await service.get_bytes(file_id)
    from urllib.parse import quote

    ascii_name = filename.encode("ascii", "ignore").decode() or "file"
    headers = {
        "Content-Disposition": (
            f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
        ),
    }
    return Response(content=data, media_type=content_type, headers=headers)


bot_outbound_router = APIRouter(prefix="/api/v1/bot-outbound", tags=["bot-outbound"])


@bot_outbound_router.get("/files/{file_id}")
async def bot_outbound_download_file(
    file_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_bot_code: Annotated[str, Header(alias="X-Bot-Code")],
    x_crm_timestamp: Annotated[str, Header(alias="X-CRM-Timestamp")],
    x_crm_signature: Annotated[str, Header(alias="X-CRM-Signature")],
) -> Response:
    bot_repo = BotRepository(db)
    bot = await bot_repo.get_by_code(x_bot_code.strip())
    if bot is None or not bot.is_active:
        raise AuthenticationRequired(message="Invalid bot")

    path = f"/api/v1/bot-outbound/files/{file_id}"
    secret = await bot_repo.decrypt_outbound_secret(bot)
    if not verify_outbound("GET", path, x_crm_timestamp, b"", secret, x_crm_signature):
        raise AuthenticationRequired(message="Invalid signature")

    service = FilesService(db)
    try:
        data, content_type, filename = await service.get_bytes(file_id)
    except NotFound as exc:
        raise NotFound(message="File not found") from exc

    from urllib.parse import quote

    ascii_name = filename.encode("ascii", "ignore").decode() or "file"
    headers = {
        "Content-Disposition": (
            f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
        ),
    }
    return Response(content=data, media_type=content_type, headers=headers)
