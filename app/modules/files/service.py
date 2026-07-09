from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.uploaded_file import UploadedFile
from app.shared.exceptions import NotFound
from app.shared.storage import get_file_storage


class FilesService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_upload(
        self,
        *,
        uploaded_by: int,
        data: bytes,
        original_name: str,
        mime_type: str,
    ) -> UploadedFile:
        key = f"operator/{uploaded_by}/{uuid4().hex}"
        storage = get_file_storage()
        await storage.upload_bytes(key, data, mime_type or "application/octet-stream")
        row = UploadedFile(
            storage_key=key,
            original_name=original_name or "file",
            mime_type=mime_type or "application/octet-stream",
            size_bytes=len(data),
            uploaded_by=uploaded_by,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_by_id(self, file_id: int) -> UploadedFile | None:
        return await self._session.get(UploadedFile, file_id)

    async def get_bytes(self, file_id: int) -> tuple[bytes, str, str]:
        row = await self.get_by_id(file_id)
        if row is None:
            raise NotFound(message="File not found")
        data, content_type = await get_file_storage().get_bytes(row.storage_key)
        return data, content_type, row.original_name

    async def rename(self, file_id: int, *, original_name: str) -> UploadedFile:
        row = await self.get_by_id(file_id)
        if row is None:
            raise NotFound(message="File not found")
        row.original_name = original_name
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def replace_content(
        self,
        file_id: int,
        *,
        data: bytes,
        mime_type: str | None = None,
    ) -> UploadedFile:
        row = await self.get_by_id(file_id)
        if row is None:
            raise NotFound(message="File not found")
        content_type = mime_type or row.mime_type or "application/octet-stream"
        await get_file_storage().upload_bytes(row.storage_key, data, content_type)
        row.size_bytes = len(data)
        if mime_type:
            row.mime_type = mime_type
        await self._session.flush()
        await self._session.refresh(row)
        return row
