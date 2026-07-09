from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.contact import Contact
from app.modules.db.models.group import Group
from app.modules.db.models.enums import MessageDirection, UserRole
from app.modules.db.models.file_share_link import FileShareLink
from app.modules.db.models.file_vault_item import FileVaultItem
from app.modules.db.models.group_chat_file import GroupChatFile
from app.modules.db.models.uploaded_file import UploadedFile
from app.modules.db.models.user import User
from app.modules.files.service import FilesService
from app.modules.storage.repository import StorageRepository
from app.modules.storage.schemas import (
    AnonymousShareResponse,
    GroupChatFileGroupSummary,
    GroupChatFileGroupsResponse,
    GroupChatFileListResponse,
    GroupChatFileResponse,
    PublicShareInfoResponse,
    ShareLinkCreateRequest,
    ShareLinkResponse,
    VaultFileContentResponse,
    VaultFileListResponse,
    VaultFileResponse,
)
from app.modules.users.memberships import list_user_group_ids
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError
from app.shared.security.passwords import hash_password, verify_password
from app.shared.settings import get_settings
from app.shared.storage import get_file_storage


_EDITABLE_TEXT_EXTENSIONS = frozenset(
    {
        "txt", "md", "markdown", "csv", "tsv", "log", "json", "xml", "yaml", "yml",
        "html", "htm", "css", "scss", "js", "ts", "jsx", "tsx", "vue", "py", "java",
        "c", "cpp", "h", "hpp", "go", "rs", "rb", "php", "sh", "bat", "ps1", "sql",
        "ini", "conf", "cfg", "toml", "env", "rst",
    },
)

_MAX_EDITABLE_BYTES = 1_000_000


def _is_editable_text_file(*, original_name: str, mime_type: str, size_bytes: int) -> bool:
    if size_bytes > _MAX_EDITABLE_BYTES:
        return False
    mime = (mime_type or "").lower()
    if mime.startswith("text/"):
        return True
    editable_mimes = {
        "application/json",
        "application/xml",
        "application/x-yaml",
        "application/javascript",
    }
    if mime in editable_mimes:
        return True
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    return ext in _EDITABLE_TEXT_EXTENSIONS


class StorageService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = StorageRepository(session)
        self._files = FilesService(session)
        self._scope_loader = ScopeLoader(session)

    def _share_url(self, token: str) -> str:
        base = get_settings().app_public_base_url.rstrip("/")
        return f"{base}/share/{token}"

    def _to_share_response(self, row: FileShareLink) -> ShareLinkResponse:
        return ShareLinkResponse(
            id=row.id,
            token=row.token,
            url=self._share_url(row.token),
            has_password=row.password_hash is not None,
            expires_at=row.expires_at,
            max_downloads=row.max_downloads,
            download_count=row.download_count,
            revoked_at=row.revoked_at,
            created_at=row.created_at,
        )

    async def _load_vault_files_map(
        self,
        items: list[FileVaultItem],
    ) -> dict[int, UploadedFile]:
        if not items:
            return {}
        file_ids = [item.file_id for item in items]
        result = await self._session.execute(
            select(UploadedFile).where(UploadedFile.id.in_(file_ids)),
        )
        return {row.id: row for row in result.scalars().all()}

    async def list_vault(
        self,
        actor: User,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> VaultFileListResponse:
        items, total = await self._repo.list_vault_items(actor.id, offset=offset, limit=limit)
        files_map = await self._load_vault_files_map(items)
        file_ids = [item.file_id for item in items]
        shares = await self._repo.list_share_links_for_files(file_ids)
        shares_by_file: dict[int, list[ShareLinkResponse]] = {}
        for share in shares:
            shares_by_file.setdefault(share.file_id, []).append(self._to_share_response(share))

        responses: list[VaultFileResponse] = []
        for item in items:
            uploaded = files_map.get(item.file_id)
            if uploaded is None:
                continue
            responses.append(
                VaultFileResponse(
                    id=item.id,
                    file_id=uploaded.id,
                    original_name=uploaded.original_name,
                    mime_type=uploaded.mime_type,
                    size_bytes=uploaded.size_bytes,
                    created_at=item.created_at,
                    share_links=shares_by_file.get(uploaded.id, []),
                ),
            )
        return VaultFileListResponse(items=responses, total=total)

    async def upload_to_vault(
        self,
        actor: User,
        *,
        data: bytes,
        original_name: str,
        mime_type: str,
    ) -> VaultFileResponse:
        uploaded = await self._files.create_upload(
            uploaded_by=actor.id,
            data=data,
            original_name=original_name,
            mime_type=mime_type,
        )
        vault_item = await self._repo.add_vault_item(file_id=uploaded.id, owner_user_id=actor.id)
        return VaultFileResponse(
            id=vault_item.id,
            file_id=uploaded.id,
            original_name=uploaded.original_name,
            mime_type=uploaded.mime_type,
            size_bytes=uploaded.size_bytes,
            created_at=vault_item.created_at,
            share_links=[],
        )

    async def delete_vault_file(self, actor: User, vault_id: int) -> None:
        item = await self._repo.get_vault_item(vault_id)
        if item is None or item.owner_user_id != actor.id:
            raise NotFound(message="File not found")
        uploaded = await self._repo.get_uploaded_file(item.file_id)
        deleted = await self._repo.delete_vault_item(vault_id, actor.id)
        if not deleted:
            raise NotFound(message="File not found")
        if uploaded is not None:
            try:
                await get_file_storage().delete_object(uploaded.storage_key)
            except Exception:
                pass
            await self._repo.delete_uploaded_file(uploaded.id)

    async def _owned_vault_upload(
        self,
        actor: User,
        vault_id: int,
    ) -> tuple[FileVaultItem, UploadedFile]:
        item = await self._repo.get_vault_item(vault_id)
        if item is None or item.owner_user_id != actor.id:
            raise NotFound(message="File not found")
        uploaded = await self._repo.get_uploaded_file(item.file_id)
        if uploaded is None:
            raise NotFound(message="File not found")
        return item, uploaded

    def _vault_response(self, item: FileVaultItem, uploaded: UploadedFile) -> VaultFileResponse:
        return VaultFileResponse(
            id=item.id,
            file_id=uploaded.id,
            original_name=uploaded.original_name,
            mime_type=uploaded.mime_type,
            size_bytes=uploaded.size_bytes,
            created_at=item.created_at,
            share_links=[],
        )

    async def get_vault_file_bytes(
        self,
        actor: User,
        vault_id: int,
    ) -> tuple[bytes, str, str]:
        _item, uploaded = await self._owned_vault_upload(actor, vault_id)
        data, content_type = await get_file_storage().get_bytes(uploaded.storage_key)
        return data, content_type, uploaded.original_name

    async def get_vault_file_content(
        self,
        actor: User,
        vault_id: int,
    ) -> VaultFileContentResponse:
        item, uploaded = await self._owned_vault_upload(actor, vault_id)
        editable = _is_editable_text_file(
            original_name=uploaded.original_name,
            mime_type=uploaded.mime_type,
            size_bytes=uploaded.size_bytes,
        )
        content = ""
        if editable:
            data, _content_type = await get_file_storage().get_bytes(uploaded.storage_key)
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                editable = False
        return VaultFileContentResponse(
            id=item.id,
            file_id=uploaded.id,
            original_name=uploaded.original_name,
            mime_type=uploaded.mime_type,
            size_bytes=uploaded.size_bytes,
            editable=editable,
            content=content,
        )

    async def rename_vault_file(
        self,
        actor: User,
        vault_id: int,
        *,
        original_name: str,
    ) -> VaultFileResponse:
        item, uploaded = await self._owned_vault_upload(actor, vault_id)
        name = original_name.strip()
        if not name:
            raise ValidationError(message="Имя файла не может быть пустым")
        uploaded = await self._files.rename(uploaded.id, original_name=name)
        return self._vault_response(item, uploaded)

    async def update_vault_file_content(
        self,
        actor: User,
        vault_id: int,
        *,
        data: bytes,
    ) -> VaultFileResponse:
        item, uploaded = await self._owned_vault_upload(actor, vault_id)
        if not _is_editable_text_file(
            original_name=uploaded.original_name,
            mime_type=uploaded.mime_type,
            size_bytes=len(data),
        ):
            raise ValidationError(message="Этот тип файла нельзя редактировать как текст")
        uploaded = await self._files.replace_content(uploaded.id, data=data)
        return self._vault_response(item, uploaded)

    async def create_share_link(
        self,
        actor: User,
        file_id: int,
        body: ShareLinkCreateRequest,
    ) -> ShareLinkResponse:
        vault_item = await self._repo.get_vault_item_by_file(file_id)
        if vault_item is None or vault_item.owner_user_id != actor.id:
            raise NotFound(message="File not found")
        password_hash = hash_password(body.password) if body.password else None
        expires_at = StorageRepository.expires_at_from_hours(body.expires_in_hours)
        share = await self._repo.create_share_link(
            file_id=file_id,
            created_by=None,
            is_anonymous=False,
            password_hash=password_hash,
            expires_at=expires_at,
            max_downloads=body.max_downloads,
        )
        return self._to_share_response(share)

    async def revoke_share_link(self, actor: User, share_id: int) -> None:
        revoked = await self._repo.revoke_share_link(share_id, actor.id)
        if not revoked:
            raise NotFound(message="Share link not found")

    async def create_anonymous_share(
        self,
        *,
        data: bytes,
        original_name: str,
        mime_type: str,
        expires_in_hours: int | None,
        max_downloads: int | None,
        password: str | None,
    ) -> AnonymousShareResponse:
        key = f"anonymous/{uuid4().hex}"
        storage = get_file_storage()
        await storage.upload_bytes(key, data, mime_type or "application/octet-stream")
        uploaded = UploadedFile(
            storage_key=key,
            original_name=original_name or "file",
            mime_type=mime_type or "application/octet-stream",
            size_bytes=len(data),
            uploaded_by=None,
        )
        self._session.add(uploaded)
        await self._session.flush()
        await self._session.refresh(uploaded)

        password_hash = hash_password(password) if password else None
        expires_at = StorageRepository.expires_at_from_hours(expires_in_hours)
        share = await self._repo.create_share_link(
            file_id=uploaded.id,
            created_by=None,
            is_anonymous=True,
            password_hash=password_hash,
            expires_at=expires_at,
            max_downloads=max_downloads,
        )
        return AnonymousShareResponse(
            token=share.token,
            url=self._share_url(share.token),
            original_name=uploaded.original_name,
            mime_type=uploaded.mime_type,
            size_bytes=uploaded.size_bytes,
            expires_at=share.expires_at,
            max_downloads=share.max_downloads,
            has_password=share.password_hash is not None,
        )

    async def get_public_share_info(self, token: str) -> PublicShareInfoResponse:
        share, uploaded = await self._resolve_share(token, check_password=False)
        now = datetime.now(UTC)
        is_expired = share.expires_at is not None and share.expires_at < now
        is_exhausted = (
            share.max_downloads is not None and share.download_count >= share.max_downloads
        )
        return PublicShareInfoResponse(
            original_name=uploaded.original_name,
            mime_type=uploaded.mime_type,
            size_bytes=uploaded.size_bytes,
            has_password=share.password_hash is not None,
            expires_at=share.expires_at,
            max_downloads=share.max_downloads,
            download_count=share.download_count,
            is_expired=is_expired or share.revoked_at is not None,
            is_exhausted=is_exhausted,
        )

    async def download_public_share(
        self,
        token: str,
        *,
        password: str | None,
    ) -> tuple[bytes, str, str]:
        share, uploaded = await self._resolve_share(token, check_password=True, password=password)
        now = datetime.now(UTC)
        if share.expires_at is not None and share.expires_at < now:
            raise ValidationError(message="Ссылка истекла")
        if share.max_downloads is not None and share.download_count >= share.max_downloads:
            raise ValidationError(message="Лимит скачиваний исчерпан")
        data, content_type = await get_file_storage().get_bytes(uploaded.storage_key)
        await self._repo.increment_share_download(share.id)
        return data, content_type, uploaded.original_name

    async def _resolve_share(
        self,
        token: str,
        *,
        check_password: bool,
        password: str | None = None,
    ) -> tuple[FileShareLink, UploadedFile]:
        share = await self._repo.get_share_by_token(token)
        if share is None or share.revoked_at is not None:
            raise NotFound(message="Ссылка не найдена")
        uploaded = await self._repo.get_uploaded_file(share.file_id)
        if uploaded is None:
            raise NotFound(message="Файл не найден")
        if check_password and share.password_hash is not None:
            if not password or not verify_password(password, share.password_hash):
                raise ValidationError(message="Неверный пароль")
        return share, uploaded

    async def _actor_group_ids(self, actor: User) -> frozenset[int]:
        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        if role == UserRole.ADMIN:
            result = await self._session.execute(select(Group.id))
            return frozenset(int(x) for x in result.scalars().all())
        return frozenset(await list_user_group_ids(self._session, actor.id))

    async def list_group_file_groups(self, actor: User) -> GroupChatFileGroupsResponse:
        group_ids = await self._actor_group_ids(actor)
        summaries = await self._repo.list_group_summaries(group_ids)
        return GroupChatFileGroupsResponse(
            items=[
                GroupChatFileGroupSummary(
                    group_id=group_id,
                    group_name=name,
                    file_count=count,
                )
                for group_id, name, count in summaries
            ],
        )

    async def list_group_files(
        self,
        actor: User,
        *,
        group_id: int | None,
        chat_id: int | None,
        offset: int = 0,
        limit: int = 50,
    ) -> GroupChatFileListResponse:
        group_ids = await self._actor_group_ids(actor)
        if group_id is not None and group_id not in group_ids:
            raise PermissionDenied(message="Нет доступа к группе")
        items, total = await self._repo.list_group_files(
            group_ids,
            group_id=group_id,
            chat_id=chat_id,
            offset=offset,
            limit=limit,
        )
        contact_names = await self._load_contact_names_for_chats({row.chat_id for row in items})
        responses = [
            self._to_group_file_response(row, contact_names.get(row.chat_id))
            for row in items
        ]
        return GroupChatFileListResponse(items=responses, total=total)

    async def _load_contact_names_for_chats(
        self,
        chat_ids: set[int],
    ) -> dict[int, str | None]:
        if not chat_ids:
            return {}
        result = await self._session.execute(
            select(Chat.id, Contact.full_name)
            .join(Contact, Contact.id == Chat.contact_id)
            .where(Chat.id.in_(chat_ids)),
        )
        return {int(row[0]): row[1] for row in result.all()}

    def _to_group_file_response(
        self,
        row: GroupChatFile,
        contact_name: str | None,
    ) -> GroupChatFileResponse:
        return GroupChatFileResponse(
            id=row.id,
            group_id=row.group_id,
            chat_id=row.chat_id,
            message_id=row.message_id,
            attachment_index=row.attachment_index,
            file_id=row.file_id,
            original_name=row.original_name,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            direction=row.direction,
            sender_display_name=row.sender_display_name,
            sender_user_id=row.sender_user_id,
            sender_contact_id=row.sender_contact_id,
            created_at=row.created_at,
            download_path=(
                f"chats/{row.chat_id}/messages/{row.message_id}/attachments/{row.attachment_index}"
            ),
            contact_name=contact_name,
        )

    async def get_group_file_bytes(
        self,
        actor: User,
        file_row_id: int,
    ) -> tuple[bytes, str, str]:
        row = await self._repo.get_group_file(file_row_id)
        if row is None:
            raise NotFound(message="File not found")
        group_ids = await self._actor_group_ids(actor)
        if row.group_id not in group_ids:
            raise PermissionDenied(message="Нет доступа к файлу")
        data, content_type = await get_file_storage().get_bytes(row.storage_key)
        return data, content_type, row.original_name

    async def assert_vault_file_owned(self, actor: User, file_id: int) -> None:
        vault_item = await self._repo.get_vault_item_by_file(file_id)
        if vault_item is not None and vault_item.owner_user_id == actor.id:
            return
        uploaded = await self._repo.get_uploaded_file(file_id)
        if uploaded is not None and uploaded.uploaded_by == actor.id:
            return
        raise PermissionDenied(message="Файл недоступен")
