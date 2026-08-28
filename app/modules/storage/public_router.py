from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.storage.schemas import (
    AnonymousShareResponse,
    PublicShareDownloadRequest,
    PublicShareInfoResponse,
)
from app.modules.storage.service import StorageService
from app.modules.storage.streaming import stream_stored_file
from app.shared.db import get_db
from app.shared.exceptions import AppError
from app.shared.settings import get_settings
from app.shared.upload_limits import max_upload_bytes_for

router = APIRouter(prefix="/api/v1/public/storage", tags=["public-storage"])


def _service(db: Annotated[AsyncSession, Depends(get_db)]) -> StorageService:
    return StorageService(db)


def _check_upload_size(content: bytes, mime: str) -> None:
    settings = get_settings()
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


def _stream_share(
    storage_key: str,
    content_type: str,
    filename: str,
    size_bytes: int,
    share_id: int,
) -> StreamingResponse:
    return stream_stored_file(
        storage_key=storage_key,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        share_id=share_id,
    )


@router.post("/share", status_code=201, response_model=AnonymousShareResponse)
async def create_anonymous_share(
    service: Annotated[StorageService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
    expires_in_hours: Annotated[int | None, Form()] = 168,
    max_downloads: Annotated[int | None, Form()] = None,
    password: Annotated[str | None, Form()] = None,
) -> AnonymousShareResponse:
    content = await file.read()
    mime = file.content_type or "application/octet-stream"
    _check_upload_size(content, mime)
    result = await service.create_anonymous_share(
        data=content,
        original_name=file.filename or "file",
        mime_type=mime,
        expires_in_hours=expires_in_hours,
        max_downloads=max_downloads,
        password=password or None,
    )
    await db.commit()
    return result


@router.get("/shares/{token}", response_model=PublicShareInfoResponse)
async def get_public_share_info(
    token: str,
    service: Annotated[StorageService, Depends(_service)],
) -> PublicShareInfoResponse:
    return await service.get_public_share_info(token)


@router.get("/shares/{token}/file")
async def download_public_share_file(
    token: str,
    service: Annotated[StorageService, Depends(_service)],
) -> StreamingResponse:
    storage_key, content_type, filename, size_bytes, share_id = await service.download_public_share(
        token,
        password=None,
    )
    return _stream_share(storage_key, content_type, filename, size_bytes, share_id)


@router.post("/shares/{token}/download")
async def download_public_share(
    token: str,
    body: PublicShareDownloadRequest,
    service: Annotated[StorageService, Depends(_service)],
) -> StreamingResponse:
    storage_key, content_type, filename, size_bytes, share_id = await service.download_public_share(
        token,
        password=body.password,
    )
    return _stream_share(storage_key, content_type, filename, size_bytes, share_id)
