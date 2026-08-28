from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.timeutil import to_naive_utc
from app.modules.db.models.file_share_link import FileShareLink
from app.modules.db.models.file_vault_item import FileVaultItem
from app.modules.db.models.group import Group
from app.modules.db.models.group_chat_file import GroupChatFile
from app.modules.db.models.large_share_upload import LargeShareUpload
from app.modules.db.models.uploaded_file import UploadedFile


class StorageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_vault_item(
        self,
        *,
        file_id: int | None,
        owner_user_id: int,
        parent_id: int | None = None,
        is_folder: bool = False,
        name: str | None = None,
    ) -> FileVaultItem:
        row = FileVaultItem(
            file_id=file_id,
            owner_user_id=owner_user_id,
            parent_id=parent_id,
            is_folder=is_folder,
            name=name,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_vault_item(self, vault_id: int) -> FileVaultItem | None:
        return await self._session.get(FileVaultItem, vault_id)

    async def get_vault_item_by_file(self, file_id: int) -> FileVaultItem | None:
        result = await self._session.execute(
            select(FileVaultItem).where(FileVaultItem.file_id == file_id),
        )
        return result.scalar_one_or_none()

    async def list_vault_items(
        self,
        owner_user_id: int,
        *,
        parent_id: int | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[FileVaultItem], int]:
        base = select(FileVaultItem).where(FileVaultItem.owner_user_id == owner_user_id)
        if parent_id is None:
            base = base.where(FileVaultItem.parent_id.is_(None))
        else:
            base = base.where(FileVaultItem.parent_id == parent_id)
        # Folders first, then newest.
        base = base.order_by(
            FileVaultItem.is_folder.desc(),
            FileVaultItem.created_at.desc(),
        )
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery()),
        )
        total = int(count_result.scalar_one())
        result = await self._session.execute(
            base.offset(offset).limit(limit),
        )
        return list(result.scalars().all()), total

    async def list_vault_children(self, parent_id: int) -> list[FileVaultItem]:
        result = await self._session.execute(
            select(FileVaultItem).where(FileVaultItem.parent_id == parent_id),
        )
        return list(result.scalars().all())

    async def delete_vault_item(self, vault_id: int, owner_user_id: int) -> bool:
        result = await self._session.execute(
            delete(FileVaultItem).where(
                FileVaultItem.id == vault_id,
                FileVaultItem.owner_user_id == owner_user_id,
            ),
        )
        return result.rowcount > 0

    async def create_share_link(
        self,
        *,
        file_id: int,
        created_by: int | None,
        is_anonymous: bool,
        password_hash: str | None,
        expires_at: datetime | None,
        max_downloads: int | None,
    ) -> FileShareLink:
        row = FileShareLink(
            token=secrets.token_urlsafe(32),
            file_id=file_id,
            created_by=created_by,
            is_anonymous=is_anonymous,
            password_hash=password_hash,
            expires_at=expires_at,
            max_downloads=max_downloads,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_share_links_for_files(self, file_ids: list[int]) -> list[FileShareLink]:
        if not file_ids:
            return []
        result = await self._session.execute(
            select(FileShareLink)
            .where(
                FileShareLink.file_id.in_(file_ids),
                FileShareLink.revoked_at.is_(None),
            )
            .order_by(FileShareLink.created_at.desc()),
        )
        return list(result.scalars().all())

    async def get_share_by_token(self, token: str) -> FileShareLink | None:
        result = await self._session.execute(
            select(FileShareLink).where(FileShareLink.token == token),
        )
        return result.scalar_one_or_none()

    async def revoke_share_link(self, share_id: int, owner_user_id: int) -> bool:
        result = await self._session.execute(
            update(FileShareLink)
            .where(
                FileShareLink.id == share_id,
                FileShareLink.revoked_at.is_(None),
                FileShareLink.file_id.in_(
                    select(FileVaultItem.file_id).where(
                        FileVaultItem.owner_user_id == owner_user_id,
                    ),
                ),
            )
            .values(revoked_at=datetime.now(UTC)),
        )
        return result.rowcount > 0

    async def increment_share_download(self, share_id: int) -> None:
        await self._session.execute(
            update(FileShareLink)
            .where(FileShareLink.id == share_id)
            .values(download_count=FileShareLink.download_count + 1),
        )

    async def add_large_share_upload(self, row: LargeShareUpload) -> LargeShareUpload:
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_large_share_upload(self, upload_id: int) -> LargeShareUpload | None:
        return await self._session.get(LargeShareUpload, upload_id)

    async def upsert_group_chat_file(
        self,
        *,
        group_id: int,
        chat_id: int,
        message_id: int,
        attachment_index: int,
        file_id: int | None,
        storage_key: str,
        original_name: str,
        mime_type: str,
        size_bytes: int,
        direction: str,
        sender_user_id: int | None,
        sender_contact_id: int | None,
        sender_display_name: str,
        created_at: datetime | None = None,
    ) -> GroupChatFile:
        existing = await self._session.execute(
            select(GroupChatFile).where(
                GroupChatFile.message_id == message_id,
                GroupChatFile.attachment_index == attachment_index,
            ),
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            row.storage_key = storage_key
            row.original_name = original_name
            row.mime_type = mime_type
            row.size_bytes = size_bytes
            row.file_id = file_id
            row.direction = direction
            row.sender_user_id = sender_user_id
            row.sender_contact_id = sender_contact_id
            row.sender_display_name = sender_display_name
            if created_at is not None:
                row.created_at = to_naive_utc(created_at)
            await self._session.flush()
            return row

        row = GroupChatFile(
            group_id=group_id,
            chat_id=chat_id,
            message_id=message_id,
            attachment_index=attachment_index,
            file_id=file_id,
            storage_key=storage_key,
            original_name=original_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            direction=direction,
            sender_user_id=sender_user_id,
            sender_contact_id=sender_contact_id,
            sender_display_name=sender_display_name,
        )
        if created_at is not None:
            row.created_at = to_naive_utc(created_at)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_group_files(
        self,
        group_ids: frozenset[int],
        *,
        group_id: int | None,
        chat_id: int | None,
        offset: int,
        limit: int,
    ) -> tuple[list[GroupChatFile], int]:
        if not group_ids:
            return [], 0
        filters: list[Any] = [GroupChatFile.group_id.in_(group_ids)]
        if group_id is not None:
            filters.append(GroupChatFile.group_id == group_id)
        if chat_id is not None:
            filters.append(GroupChatFile.chat_id == chat_id)
        base = select(GroupChatFile).where(*filters).order_by(GroupChatFile.created_at.desc())
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery()),
        )
        total = int(count_result.scalar_one())
        result = await self._session.execute(base.offset(offset).limit(limit))
        return list(result.scalars().all()), total

    async def list_group_summaries(
        self,
        group_ids: frozenset[int],
    ) -> list[tuple[int, str, int]]:
        if not group_ids:
            return []
        result = await self._session.execute(
            select(
                GroupChatFile.group_id,
                Group.name,
                func.count(GroupChatFile.id),
            )
            .join(Group, Group.id == GroupChatFile.group_id)
            .where(GroupChatFile.group_id.in_(group_ids))
            .group_by(GroupChatFile.group_id, Group.name)
            .order_by(Group.name),
        )
        return [(int(r[0]), str(r[1]), int(r[2])) for r in result.all()]

    async def get_group_file(self, file_row_id: int) -> GroupChatFile | None:
        return await self._session.get(GroupChatFile, file_row_id)

    async def get_uploaded_file(self, file_id: int) -> UploadedFile | None:
        return await self._session.get(UploadedFile, file_id)

    async def delete_uploaded_file(self, file_id: int) -> UploadedFile | None:
        row = await self.get_uploaded_file(file_id)
        if row is None:
            return None
        await self._session.delete(row)
        return row

    async def purge_expired_shares(self, now: datetime) -> list[int]:
        result = await self._session.execute(
            select(FileShareLink.file_id)
            .where(
                FileShareLink.revoked_at.is_(None),
                FileShareLink.expires_at.is_not(None),
                FileShareLink.expires_at < now,
            )
            .distinct(),
        )
        file_ids = [int(x) for x in result.scalars().all()]
        await self._session.execute(
            update(FileShareLink)
            .where(
                FileShareLink.revoked_at.is_(None),
                FileShareLink.expires_at.is_not(None),
                FileShareLink.expires_at < now,
            )
            .values(revoked_at=now),
        )
        return file_ids

    @staticmethod
    def expires_at_from_hours(hours: int | None) -> datetime | None:
        if hours is None:
            return None
        return datetime.now(UTC) + timedelta(hours=hours)


async def increment_share_download_standalone(share_id: int) -> None:
    from app.shared.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            update(FileShareLink)
            .where(FileShareLink.id == share_id)
            .values(download_count=FileShareLink.download_count + 1),
        )
        await session.commit()
