from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.user import User
from app.modules.rbac.permissions import Permission
from app.modules.storage.schemas import (
    GroupChatFileGroupsResponse,
    GroupChatFileListResponse,
    ShareLinkCreateRequest,
    ShareLinkResponse,
    StorageReceiptTreeResponse,
    VaultFileContentResponse,
    VaultFileContentUpdateRequest,
    VaultFileListResponse,
    VaultFileRenameRequest,
    VaultFileResponse,
)
from app.modules.storage.service import StorageService
from app.shared.db import get_db
from app.shared.exceptions import AppError
from app.shared.security.permissions import requires_permission
from app.shared.settings import get_settings
from app.shared.upload_limits import max_upload_bytes_for

router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


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


@router.get("/vault", response_model=VaultFileListResponse)
async def list_vault_files(
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_DOWNLOAD))],
    service: Annotated[StorageService, Depends(_service)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> VaultFileListResponse:
    return await service.list_vault(actor, offset=offset, limit=limit)


@router.post("/vault", status_code=201, response_model=VaultFileResponse)
async def upload_vault_file(
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_UPLOAD))],
    service: Annotated[StorageService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
) -> VaultFileResponse:
    content = await file.read()
    mime = file.content_type or "application/octet-stream"
    _check_upload_size(content, mime)
    result = await service.upload_to_vault(
        actor,
        data=content,
        original_name=file.filename or "file",
        mime_type=mime,
    )
    await db.commit()
    return result


@router.get("/vault/{vault_id}/download")
async def download_vault_file(
    vault_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_DOWNLOAD))],
    service: Annotated[StorageService, Depends(_service)],
) -> Response:
    data, content_type, filename = await service.get_vault_file_bytes(actor, vault_id)
    ascii_name = filename.encode("ascii", "ignore").decode() or "file"
    headers = {
        "Content-Disposition": (
            f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
        ),
    }
    return Response(content=data, media_type=content_type, headers=headers)


@router.get("/vault/{vault_id}/content", response_model=VaultFileContentResponse)
async def get_vault_file_content(
    vault_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_DOWNLOAD))],
    service: Annotated[StorageService, Depends(_service)],
) -> VaultFileContentResponse:
    return await service.get_vault_file_content(actor, vault_id)


@router.put("/vault/{vault_id}/content", response_model=VaultFileResponse)
async def update_vault_file_content(
    vault_id: int,
    body: VaultFileContentUpdateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_UPLOAD))],
    service: Annotated[StorageService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VaultFileResponse:
    result = await service.update_vault_file_content(
        actor,
        vault_id,
        data=body.content.encode("utf-8"),
    )
    await db.commit()
    return result


@router.patch("/vault/{vault_id}", response_model=VaultFileResponse)
async def rename_vault_file(
    vault_id: int,
    body: VaultFileRenameRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_UPLOAD))],
    service: Annotated[StorageService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VaultFileResponse:
    result = await service.rename_vault_file(actor, vault_id, original_name=body.original_name)
    await db.commit()
    return result


@router.delete("/vault/{vault_id}")
async def delete_vault_file(
    vault_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_DELETE))],
    service: Annotated[StorageService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    await service.delete_vault_file(actor, vault_id)
    await db.commit()
    return {"deleted": True}


@router.post(
    "/vault/{file_id}/shares",
    status_code=201,
    response_model=ShareLinkResponse,
)
async def create_vault_share_link(
    file_id: int,
    body: ShareLinkCreateRequest,
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_UPLOAD))],
    service: Annotated[StorageService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ShareLinkResponse:
    result = await service.create_share_link(actor, file_id, body)
    await db.commit()
    return result


@router.delete("/shares/{share_id}")
async def revoke_share_link(
    share_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_UPLOAD))],
    service: Annotated[StorageService, Depends(_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    await service.revoke_share_link(actor, share_id)
    await db.commit()
    return {"revoked": True}


@router.get("/group-files/groups", response_model=GroupChatFileGroupsResponse)
async def list_group_file_groups(
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.CHATS_READ_OWN,
                Permission.CHATS_READ_GROUP,
                Permission.CHATS_READ_DEPARTMENT,
                Permission.CHATS_READ_ALL,
            ),
        ),
    ],
    service: Annotated[StorageService, Depends(_service)],
) -> GroupChatFileGroupsResponse:
    return await service.list_group_file_groups(actor)


@router.get("/group-files", response_model=GroupChatFileListResponse)
async def list_group_files(
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.CHATS_READ_OWN,
                Permission.CHATS_READ_GROUP,
                Permission.CHATS_READ_DEPARTMENT,
                Permission.CHATS_READ_ALL,
            ),
        ),
    ],
    service: Annotated[StorageService, Depends(_service)],
    group_id: int | None = Query(default=None),
    chat_id: int | None = Query(default=None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> GroupChatFileListResponse:
    return await service.list_group_files(
        actor,
        group_id=group_id,
        chat_id=chat_id,
        offset=offset,
        limit=limit,
    )


@router.get("/group-files/{file_row_id}/download")
async def download_group_file(
    file_row_id: int,
    actor: Annotated[
        User,
        Depends(
            requires_permission(
                Permission.CHATS_READ_OWN,
                Permission.CHATS_READ_GROUP,
                Permission.CHATS_READ_DEPARTMENT,
                Permission.CHATS_READ_ALL,
            ),
        ),
    ],
    service: Annotated[StorageService, Depends(_service)],
) -> Response:
    data, content_type, filename = await service.get_group_file_bytes(actor, file_row_id)
    ascii_name = filename.encode("ascii", "ignore").decode() or "file"
    headers = {
        "Content-Disposition": (
            f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
        ),
    }
    return Response(content=data, media_type=content_type, headers=headers)


@router.get("/receipts/tree", response_model=StorageReceiptTreeResponse)
async def list_storage_receipts_tree(
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_DOWNLOAD))],
    service: Annotated[StorageService, Depends(_service)],
) -> StorageReceiptTreeResponse:
    return await service.list_receipts_tree(actor)


@router.get("/receipts/{receipt_id}/download")
async def download_storage_receipt(
    receipt_id: int,
    actor: Annotated[User, Depends(requires_permission(Permission.FILES_DOWNLOAD))],
    service: Annotated[StorageService, Depends(_service)],
) -> Response:
    data, filename = await service.get_receipt_bytes(actor, receipt_id)
    ascii_name = filename.encode("ascii", "ignore").decode() or "receipt.pdf"
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'
        ),
    }
    return Response(content=data, media_type="application/pdf", headers=headers)
