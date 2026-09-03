from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import structlog
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.modules.contacts.scope_loader import ScopeLoader
from app.modules.db.models.chat import Chat
from app.modules.db.models.chat_message import ChatMessage
from app.modules.db.models.contact import Contact
from app.modules.db.models.group import Group
from app.modules.db.models.enums import MessageDirection, UserRole, UserStatus
from app.modules.db.models.file_share_link import FileShareLink
from app.modules.db.models.file_vault_folder_share import FileVaultFolderShare
from app.modules.db.models.file_vault_item import FileVaultItem
from app.modules.db.models.group_chat_file import GroupChatFile
from app.modules.db.models.large_share_upload import LargeShareUpload
from app.modules.db.models.uploaded_file import UploadedFile
from app.modules.db.models.user import User
from app.modules.files.service import FilesService
from app.modules.rbac.role_checks import is_admin
from app.modules.storage.repository import StorageRepository
from app.modules.storage.schemas import (
    AnonymousShareResponse,
    GroupChatFileGroupSummary,
    GroupChatFileGroupsResponse,
    GroupChatFileListResponse,
    GroupChatFileResponse,
    LargeShareCompleteResponse,
    LargeShareInitResponse,
    PublicShareInfoResponse,
    ShareLinkCreateRequest,
    ShareLinkResponse,
    VaultFileContentResponse,
    VaultFileListResponse,
    VaultFileResponse,
    VaultFolderUserShareListResponse,
    VaultFolderUserShareResponse,
    VaultShareUserListResponse,
    VaultShareUserOption,
)
from app.modules.users.memberships import list_user_group_ids
from app.shared.exceptions import NotFound, PermissionDenied, ValidationError
from app.shared.security.passwords import hash_password, verify_password
from app.shared.settings import get_settings
from app.shared.storage import get_file_storage

logger = structlog.get_logger(__name__)


_EDITABLE_TEXT_EXTENSIONS = frozenset(
    {
        "txt", "md", "markdown", "csv", "tsv", "log", "json", "xml", "yaml", "yml",
        "html", "htm", "css", "scss", "js", "ts", "jsx", "tsx", "vue", "py", "java",
        "c", "cpp", "h", "hpp", "go", "rs", "rb", "php", "sh", "bat", "ps1", "sql",
        "ini", "conf", "cfg", "toml", "env", "rst",
    },
)

_MAX_EDITABLE_BYTES = 1_000_000
ADMIN_LARGE_SHARE_PART_BYTES = 8 * 1024 * 1024
ADMIN_LARGE_SHARE_PART_MAX_BYTES = 16 * 1024 * 1024


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
        file_ids = [item.file_id for item in items if item.file_id is not None]
        if not file_ids:
            return {}
        result = await self._session.execute(
            select(UploadedFile).where(UploadedFile.id.in_(file_ids)),
        )
        return {row.id: row for row in result.scalars().all()}

    async def _assert_vault_parent(
        self,
        actor: User,
        parent_id: int | None,
    ) -> None:
        if parent_id is None:
            return
        parent = await self._repo.get_vault_item(parent_id)
        if parent is None or parent.owner_user_id != actor.id or not parent.is_folder:
            raise ValidationError(message="Папка не найдена")

    async def _resolve_writable_parent(
        self,
        actor: User,
        parent_id: int | None,
    ) -> FileVaultItem | None:
        if parent_id is None:
            return None
        parent = await self._repo.get_vault_item(parent_id)
        if parent is None or not parent.is_folder:
            raise ValidationError(message="Папка не найдена")
        if parent.owner_user_id == actor.id or await self._can_read_vault_item(actor, parent):
            return parent
        raise ValidationError(message="Папка не найдена")

    async def _can_read_vault_item(self, actor: User, item: FileVaultItem) -> bool:
        if item.owner_user_id == actor.id:
            return True
        current: FileVaultItem | None = item
        seen: set[int] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.is_folder:
                share = await self._repo.get_folder_share(current.id, actor.id)
                if share is not None:
                    return True
            if current.parent_id is None:
                return False
            current = await self._repo.get_vault_item(current.parent_id)
        return False

    async def _folder_share_responses(
        self,
        shares: list[FileVaultFolderShare],
    ) -> list[VaultFolderUserShareResponse]:
        user_ids = {share.user_id for share in shares}
        user_ids.update(share.shared_by for share in shares if share.shared_by is not None)
        names = await self._load_user_names(user_ids)
        return [
            VaultFolderUserShareResponse(
                id=share.id,
                folder_id=share.folder_id,
                user_id=share.user_id,
                user_name=names.get(share.user_id) or f"user #{share.user_id}",
                shared_by=share.shared_by,
                shared_by_name=(
                    names.get(share.shared_by) if share.shared_by is not None else None
                ),
                created_at=share.created_at,
            )
            for share in shares
        ]

    def _vault_item_response(
        self,
        item: FileVaultItem,
        uploaded: UploadedFile | None = None,
        *,
        share_links: list[ShareLinkResponse] | None = None,
        access: str = "owned",
        shared_by_name: str | None = None,
        folder_shares: list[VaultFolderUserShareResponse] | None = None,
    ) -> VaultFileResponse:
        extras = {
            "access": access,
            "shared_by_name": shared_by_name,
            "folder_shares": folder_shares or [],
        }
        if item.is_folder:
            return VaultFileResponse(
                id=item.id,
                file_id=None,
                original_name=(item.name or "Папка").strip() or "Папка",
                mime_type="inode/directory",
                size_bytes=0,
                is_folder=True,
                parent_id=item.parent_id,
                created_at=item.created_at,
                share_links=[],
                **extras,
            )
        if uploaded is None:
            raise NotFound(message="File not found")
        return VaultFileResponse(
            id=item.id,
            file_id=uploaded.id,
            original_name=uploaded.original_name,
            mime_type=uploaded.mime_type,
            size_bytes=uploaded.size_bytes,
            is_folder=False,
            parent_id=item.parent_id,
            created_at=item.created_at,
            share_links=share_links or [],
            **extras,
        )

    async def list_vault(
        self,
        actor: User,
        *,
        parent_id: int | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> VaultFileListResponse:
        can_write = True
        can_manage = True
        owner_filter: int | None = actor.id
        access = "owned"
        if parent_id is not None:
            parent = await self._repo.get_vault_item(parent_id)
            if parent is None or not parent.is_folder:
                raise ValidationError(message="Папка не найдена")
            if parent.owner_user_id == actor.id:
                can_write = True
                can_manage = True
            elif await self._can_read_vault_item(actor, parent):
                can_write = True
                can_manage = False
                owner_filter = None
                access = "shared"
            else:
                raise ValidationError(message="Папка не найдена")
        items, total = await self._repo.list_vault_items(
            owner_filter,
            parent_id=parent_id,
            offset=offset,
            limit=limit,
        )
        return await self._vault_list_response(
            items,
            total,
            access=access,
            can_write=can_write,
            can_manage=can_manage,
        )

    async def list_shared_folders(self, actor: User) -> VaultFileListResponse:
        shares = await self._repo.list_shares_for_user(actor.id)
        if not shares:
            return VaultFileListResponse(items=[], total=0, can_write=False, can_manage=False)
        share_responses = await self._folder_share_responses(shares)
        share_by_folder = {row.folder_id: row for row in share_responses}
        loaded = await self._repo.get_vault_items([share.folder_id for share in shares])
        folders = [folder for folder in loaded if folder.is_folder]
        responses = [
            self._vault_item_response(
                folder,
                access="shared",
                shared_by_name=share_by_folder.get(folder.id).shared_by_name
                if share_by_folder.get(folder.id)
                else None,
                folder_shares=[share_by_folder[folder.id]] if folder.id in share_by_folder else [],
            )
            for folder in folders
        ]
        return VaultFileListResponse(items=responses, total=len(responses), can_write=False, can_manage=False)

    async def list_share_users(
        self,
        actor: User,
        *,
        q: str | None = None,
    ) -> VaultShareUserListResponse:
        filters = [
            User.status == UserStatus.ACTIVE,
            User.id != actor.id,
        ]
        needle = (q or "").strip()
        if needle:
            like = f"%{needle}%"
            filters.append(
                or_(
                    User.full_name.ilike(like),
                    User.username.ilike(like),
                    User.email.ilike(like),
                ),
            )
        result = await self._session.execute(
            select(User).where(*filters).order_by(User.full_name).limit(50),
        )
        users = list(result.scalars().all())
        return VaultShareUserListResponse(
            items=[
                VaultShareUserOption(
                    id=user.id,
                    full_name=user.full_name or f"user #{user.id}",
                    username=user.username,
                )
                for user in users
            ],
        )

    async def share_vault_folder(
        self,
        actor: User,
        folder_id: int,
        user_id: int,
    ) -> VaultFolderUserShareResponse:
        folder = await self._repo.get_vault_item(folder_id)
        if folder is None or not folder.is_folder or folder.owner_user_id != actor.id:
            raise NotFound(message="Папка не найдена")
        if user_id == actor.id:
            raise ValidationError(message="Нельзя поделиться папкой с собой")
        target = await self._session.get(User, user_id)
        if target is None:
            raise ValidationError(message="Пользователь не найден")
        status = (
            target.status
            if isinstance(target.status, UserStatus)
            else UserStatus(str(target.status))
        )
        if status != UserStatus.ACTIVE:
            raise ValidationError(message="Пользователь неактивен")
        existing = await self._repo.get_folder_share(folder_id, user_id)
        if existing is not None:
            rows = await self._folder_share_responses([existing])
            return rows[0]
        share = await self._repo.add_folder_share(
            folder_id=folder_id,
            user_id=user_id,
            shared_by=actor.id,
        )
        rows = await self._folder_share_responses([share])
        return rows[0]

    async def list_folder_user_shares(
        self,
        actor: User,
        folder_id: int,
    ) -> VaultFolderUserShareListResponse:
        folder = await self._repo.get_vault_item(folder_id)
        if folder is None or not folder.is_folder or folder.owner_user_id != actor.id:
            raise NotFound(message="Папка не найдена")
        shares = await self._repo.list_shares_for_folder(folder_id)
        return VaultFolderUserShareListResponse(items=await self._folder_share_responses(shares))

    async def revoke_folder_user_share(self, actor: User, share_id: int) -> None:
        share = await self._repo.get_folder_share_by_id(share_id)
        if share is None:
            raise NotFound(message="Доступ не найден")
        folder = await self._repo.get_vault_item(share.folder_id)
        is_owner = folder is not None and folder.owner_user_id == actor.id
        is_recipient = share.user_id == actor.id
        if not is_owner and not is_recipient:
            raise NotFound(message="Доступ не найден")
        await self._repo.delete_folder_share(share_id)

    async def _vault_list_response(
        self,
        items: list[FileVaultItem],
        total: int,
        *,
        access: str,
        can_write: bool,
        can_manage: bool,
    ) -> VaultFileListResponse:
        files_map = await self._load_vault_files_map(items)
        shares_by_file: dict[int, list[ShareLinkResponse]] = {}
        if can_manage:
            file_ids = [item.file_id for item in items if item.file_id is not None]
            shares = await self._repo.list_share_links_for_files(file_ids)
            for share in shares:
                shares_by_file.setdefault(share.file_id, []).append(self._to_share_response(share))
        folder_ids = [item.id for item in items if item.is_folder]
        folder_share_rows = (
            await self._repo.list_shares_for_folders(folder_ids) if can_manage else []
        )
        folder_share_responses = await self._folder_share_responses(folder_share_rows)
        shares_by_folder: dict[int, list[VaultFolderUserShareResponse]] = {}
        for row in folder_share_responses:
            shares_by_folder.setdefault(row.folder_id, []).append(row)

        responses: list[VaultFileResponse] = []
        for item in items:
            if item.is_folder:
                responses.append(
                    self._vault_item_response(
                        item,
                        access=access,
                        folder_shares=shares_by_folder.get(item.id, []),
                    ),
                )
                continue
            if item.file_id is None:
                continue
            uploaded = files_map.get(item.file_id)
            if uploaded is None:
                continue
            responses.append(
                self._vault_item_response(
                    item,
                    uploaded,
                    share_links=shares_by_file.get(uploaded.id, []),
                    access=access,
                ),
            )
        return VaultFileListResponse(
            items=responses,
            total=total,
            can_write=can_write,
            can_manage=can_manage,
        )

    async def create_vault_folder(
        self,
        actor: User,
        *,
        name: str,
        parent_id: int | None = None,
    ) -> VaultFileResponse:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError(message="Имя папки не может быть пустым")
        parent = await self._resolve_writable_parent(actor, parent_id)
        owner_id = parent.owner_user_id if parent is not None else actor.id
        row = await self._repo.add_vault_item(
            file_id=None,
            owner_user_id=owner_id,
            parent_id=parent_id,
            is_folder=True,
            name=cleaned[:255],
        )
        return self._vault_item_response(row)

    async def upload_to_vault(
        self,
        actor: User,
        *,
        data: bytes,
        original_name: str,
        mime_type: str,
        parent_id: int | None = None,
    ) -> VaultFileResponse:
        parent = await self._resolve_writable_parent(actor, parent_id)
        owner_id = parent.owner_user_id if parent is not None else actor.id
        uploaded = await self._files.create_upload(
            uploaded_by=actor.id,
            data=data,
            original_name=original_name,
            mime_type=mime_type,
        )
        vault_item = await self._repo.add_vault_item(
            file_id=uploaded.id,
            owner_user_id=owner_id,
            parent_id=parent_id,
            is_folder=False,
        )
        return self._vault_item_response(vault_item, uploaded)

    async def _delete_vault_tree(self, actor: User, item: FileVaultItem) -> None:
        if item.is_folder:
            children = await self._repo.list_vault_children(item.id)
            for child in children:
                await self._delete_vault_tree(actor, child)
        uploaded = None
        if item.file_id is not None:
            uploaded = await self._repo.get_uploaded_file(item.file_id)
        deleted = await self._repo.delete_vault_item(item.id, actor.id)
        if not deleted:
            return
        if uploaded is not None:
            try:
                await get_file_storage().delete_object(uploaded.storage_key)
            except Exception:
                pass
            await self._repo.delete_uploaded_file(uploaded.id)

    async def delete_vault_file(self, actor: User, vault_id: int) -> None:
        item = await self._repo.get_vault_item(vault_id)
        if item is None or item.owner_user_id != actor.id:
            raise NotFound(message="File not found")
        await self._delete_vault_tree(actor, item)

    async def _owned_vault_upload(
        self,
        actor: User,
        vault_id: int,
    ) -> tuple[FileVaultItem, UploadedFile]:
        item = await self._repo.get_vault_item(vault_id)
        if item is None or item.owner_user_id != actor.id:
            raise NotFound(message="File not found")
        if item.is_folder or item.file_id is None:
            raise ValidationError(message="Это папка, не файл")
        uploaded = await self._repo.get_uploaded_file(item.file_id)
        if uploaded is None:
            raise NotFound(message="File not found")
        return item, uploaded

    async def _accessible_vault_upload(
        self,
        actor: User,
        vault_id: int,
    ) -> tuple[FileVaultItem, UploadedFile]:
        item = await self._repo.get_vault_item(vault_id)
        if item is None or not await self._can_read_vault_item(actor, item):
            raise NotFound(message="File not found")
        if item.is_folder or item.file_id is None:
            raise ValidationError(message="Это папка, не файл")
        uploaded = await self._repo.get_uploaded_file(item.file_id)
        if uploaded is None:
            raise NotFound(message="File not found")
        return item, uploaded

    def _vault_response(self, item: FileVaultItem, uploaded: UploadedFile) -> VaultFileResponse:
        return self._vault_item_response(item, uploaded)

    async def get_vault_file_bytes(
        self,
        actor: User,
        vault_id: int,
    ) -> tuple[bytes, str, str]:
        _item, uploaded = await self._accessible_vault_upload(actor, vault_id)
        data, content_type = await get_file_storage().get_bytes(uploaded.storage_key)
        return data, content_type, uploaded.original_name

    async def get_vault_file_content(
        self,
        actor: User,
        vault_id: int,
    ) -> VaultFileContentResponse:
        item, uploaded = await self._accessible_vault_upload(actor, vault_id)
        editable = item.owner_user_id == actor.id and _is_editable_text_file(
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
        name = original_name.strip()
        if not name:
            raise ValidationError(message="Имя не может быть пустым")
        item = await self._repo.get_vault_item(vault_id)
        if item is None or item.owner_user_id != actor.id:
            raise NotFound(message="File not found")
        if item.is_folder:
            item.name = name[:255]
            await self._session.flush()
            await self._session.refresh(item)
            return self._vault_item_response(item)
        _item, uploaded = await self._owned_vault_upload(actor, vault_id)
        uploaded = await self._files.rename(uploaded.id, original_name=name)
        return self._vault_response(_item, uploaded)

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
    ) -> tuple[str, str, str, int, int]:
        """Return storage key, mime, filename, size, share_id. Count is incremented after a full stream."""
        share, uploaded = await self._resolve_share(token, check_password=True, password=password)
        now = datetime.now(UTC)
        if share.expires_at is not None and share.expires_at < now:
            raise ValidationError(message="Ссылка истекла")
        if share.max_downloads is not None and share.download_count >= share.max_downloads:
            raise ValidationError(message="Лимит скачиваний исчерпан")
        return (
            uploaded.storage_key,
            uploaded.mime_type or "application/octet-stream",
            uploaded.original_name,
            int(uploaded.size_bytes),
            int(share.id),
        )

    async def init_admin_large_share(
        self,
        actor: User,
        *,
        original_name: str,
        mime_type: str,
        size_bytes: int,
        parent_id: int | None,
        expires_in_hours: int,
        max_downloads: int,
    ) -> LargeShareInitResponse:
        self._require_admin(actor)
        settings = get_settings()
        cap = int(settings.max_admin_large_share_bytes)
        if size_bytes > cap:
            raise ValidationError(
                message="Файл слишком большой для исключения",
                details={"max_bytes": cap},
            )
        await self._assert_vault_parent(actor, parent_id)
        name = original_name.strip() or "file"
        mime = (mime_type or "application/octet-stream").strip() or "application/octet-stream"
        key = f"operator/{actor.id}/large/{uuid4().hex}"
        storage = get_file_storage()
        try:
            s3_upload_id = await storage.initiate_multipart(key, mime)
        except (httpx.HTTPError, RuntimeError, TimeoutError) as exc:
            logger.warning("large_share_initiate_failed", error=str(exc))
            raise ValidationError(
                message="Не удалось начать загрузку в хранилище. Проверьте MinIO и повторите.",
            ) from exc
        row = LargeShareUpload(
            owner_user_id=actor.id,
            storage_key=key,
            s3_upload_id=s3_upload_id,
            original_name=name[:512],
            mime_type=mime[:255],
            expected_size_bytes=size_bytes,
            parent_id=parent_id,
            status="uploading",
            part_etags={},
            expires_in_hours=expires_in_hours,
            max_downloads=max_downloads,
        )
        try:
            await self._repo.add_large_share_upload(row)
        except SQLAlchemyError:
            await storage.abort_multipart(key, s3_upload_id)
            logger.warning("large_share_session_insert_failed", exc_info=True)
            raise ValidationError(
                message="Не удалось создать сессию загрузки. На сервере не применена миграция 0107.",
            ) from None
        except Exception:
            await storage.abort_multipart(key, s3_upload_id)
            raise
        return LargeShareInitResponse(
            id=row.id,
            part_size_bytes=ADMIN_LARGE_SHARE_PART_BYTES,
            max_size_bytes=cap,
        )

    async def upload_admin_large_share_part(
        self,
        actor: User,
        upload_id: int,
        part_number: int,
        data: bytes,
    ) -> dict[str, int]:
        row = await self._owned_large_share(actor, upload_id)
        if row.status != "uploading":
            raise ValidationError(message="Эта загрузка уже завершена")
        if part_number < 1 or part_number > 10_000:
            raise ValidationError(message="Некорректный номер части")
        if not data or len(data) > ADMIN_LARGE_SHARE_PART_MAX_BYTES:
            raise ValidationError(
                message="Размер части не подходит",
                details={"max_bytes": ADMIN_LARGE_SHARE_PART_MAX_BYTES},
            )
        try:
            etag = await get_file_storage().upload_part(
                row.storage_key,
                row.s3_upload_id,
                part_number,
                data,
            )
        except (httpx.HTTPError, RuntimeError, TimeoutError) as exc:
            logger.warning("large_share_part_failed", upload_id=upload_id, error=str(exc))
            raise ValidationError(message="Не удалось загрузить часть файла") from exc
        etags = dict(row.part_etags or {})
        etags[str(part_number)] = {"etag": etag, "size": len(data)}
        row.part_etags = etags
        flag_modified(row, "part_etags")
        await self._session.flush()
        uploaded = sum(int(item.get("size") or 0) for item in etags.values())
        return {"part_number": part_number, "uploaded_bytes": uploaded}

    async def complete_admin_large_share(
        self,
        actor: User,
        upload_id: int,
    ) -> LargeShareCompleteResponse:
        row = await self._owned_large_share(actor, upload_id)
        if row.status == "completed" and row.file_id is not None:
            vault = await self._repo.get_vault_item(row.vault_item_id) if row.vault_item_id else None
            uploaded = await self._repo.get_uploaded_file(row.file_id)
            share = await self._session.get(FileShareLink, row.share_id) if row.share_id else None
            if vault is not None and uploaded is not None and share is not None:
                return LargeShareCompleteResponse(
                    vault=self._vault_item_response(
                        vault,
                        uploaded,
                        share_links=[self._to_share_response(share)],
                    ),
                    share=self._to_share_response(share),
                )
        if row.status != "uploading":
            raise ValidationError(message="Эта загрузка уже завершена")
        parts = self._ordered_large_share_parts(row)
        total = sum(size for _num, _etag, size in parts)
        if total != int(row.expected_size_bytes):
            raise ValidationError(
                message="Загружены не все части файла",
                details={"uploaded_bytes": total, "expected_bytes": row.expected_size_bytes},
            )
        storage = get_file_storage()
        try:
            await storage.complete_multipart(
                row.storage_key,
                row.s3_upload_id,
                [(number, etag) for number, etag, _size in parts],
            )
        except (httpx.HTTPError, RuntimeError, TimeoutError) as exc:
            logger.warning("large_share_complete_failed", upload_id=upload_id, error=str(exc))
            raise ValidationError(message="Не удалось собрать файл в хранилище") from exc

        uploaded = UploadedFile(
            storage_key=row.storage_key,
            original_name=row.original_name,
            mime_type=row.mime_type,
            size_bytes=row.expected_size_bytes,
            uploaded_by=actor.id,
        )
        self._session.add(uploaded)
        await self._session.flush()
        await self._session.refresh(uploaded)
        vault_item = await self._repo.add_vault_item(
            file_id=uploaded.id,
            owner_user_id=actor.id,
            parent_id=row.parent_id,
            is_folder=False,
        )
        share = await self._repo.create_share_link(
            file_id=uploaded.id,
            created_by=actor.id,
            is_anonymous=False,
            password_hash=None,
            expires_at=StorageRepository.expires_at_from_hours(int(row.expires_in_hours)),
            max_downloads=int(row.max_downloads),
        )
        row.status = "completed"
        row.file_id = uploaded.id
        row.vault_item_id = vault_item.id
        row.share_id = share.id
        row.completed_at = datetime.now(UTC)
        await self._session.flush()
        return LargeShareCompleteResponse(
            vault=self._vault_item_response(
                vault_item,
                uploaded,
                share_links=[self._to_share_response(share)],
            ),
            share=self._to_share_response(share),
        )

    async def abort_admin_large_share(self, actor: User, upload_id: int) -> None:
        row = await self._owned_large_share(actor, upload_id)
        if row.status == "completed":
            raise ValidationError(message="Готовую загрузку нельзя отменить — удалите файл из хранилища")
        if row.status == "uploading":
            try:
                await get_file_storage().abort_multipart(row.storage_key, row.s3_upload_id)
            except Exception:
                logger.warning("large_share_abort_s3_failed", upload_id=upload_id, exc_info=True)
        row.status = "aborted"
        await self._session.flush()

    def _require_admin(self, actor: User) -> None:
        if not is_admin(actor.role):
            raise PermissionDenied(message="Только администратор")

    async def _owned_large_share(self, actor: User, upload_id: int) -> LargeShareUpload:
        self._require_admin(actor)
        row = await self._repo.get_large_share_upload(upload_id)
        if row is None or row.owner_user_id != actor.id:
            raise NotFound(message="Загрузка не найдена")
        return row

    @staticmethod
    def _ordered_large_share_parts(row: LargeShareUpload) -> list[tuple[int, str, int]]:
        raw = row.part_etags or {}
        if not raw:
            raise ValidationError(message="Нет загруженных частей")
        items: list[tuple[int, str, int]] = []
        for key, value in raw.items():
            try:
                number = int(key)
            except (TypeError, ValueError) as exc:
                raise ValidationError(message="Некорректный список частей") from exc
            if not isinstance(value, dict):
                raise ValidationError(message="Некорректный список частей")
            etag = str(value.get("etag") or "").strip()
            size = int(value.get("size") or 0)
            if not etag or size <= 0:
                raise ValidationError(message="Некорректный список частей")
            items.append((number, etag, size))
        items.sort(key=lambda item: item[0])
        expected = list(range(1, len(items) + 1))
        if [item[0] for item in items] != expected:
            raise ValidationError(message="Пропущены части файла")
        return items

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
        await self._maybe_backfill_group_files()
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

    async def _maybe_backfill_group_files(self) -> None:
        """Catch up inbound files that were downloaded but never indexed."""
        try:
            from app.shared.redis import get_redis
            from app.modules.storage.indexing import backfill_group_chat_files

            redis = get_redis()
            acquired = await redis.set(
                "crm:storage:group-files:backfill-on-read",
                "1",
                nx=True,
                ex=120,
            )
            if not acquired:
                return
            count = await backfill_group_chat_files(self._session, limit=200)
            if count:
                logger.info("group_chat_files_backfill_on_read", indexed_messages=count)
        except Exception:
            logger.warning("group_chat_files_backfill_on_read_failed", exc_info=True)

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
        contact_labels = await self._load_contact_labels_for_chats({row.chat_id for row in items})
        message_meta = await self._load_message_meta({row.message_id for row in items})
        user_names = await self._load_user_names(
            {
                *(row.sender_user_id for row in items if row.sender_user_id is not None),
                *(
                    meta["sender_user_id"]
                    for meta in message_meta.values()
                    if meta.get("sender_user_id") is not None
                ),
            },
        )
        responses = [
            self._to_group_file_response(
                row,
                contact_labels.get(row.chat_id),
                user_names,
                message_meta.get(row.message_id),
            )
            for row in items
        ]
        return GroupChatFileListResponse(items=responses, total=total)

    async def _load_user_names(self, user_ids: set[int]) -> dict[int, str]:
        if not user_ids:
            return {}
        result = await self._session.execute(
            select(User.id, User.full_name).where(User.id.in_(user_ids)),
        )
        return {int(row[0]): str(row[1]) for row in result.all() if row[1]}

    async def _load_message_meta(
        self,
        message_ids: set[int],
    ) -> dict[int, dict[str, Any]]:
        if not message_ids:
            return {}
        result = await self._session.execute(
            select(
                ChatMessage.id,
                ChatMessage.direction,
                ChatMessage.sender_user_id,
            ).where(ChatMessage.id.in_(message_ids)),
        )
        out: dict[int, dict[str, Any]] = {}
        for message_id, direction, sender_user_id in result.all():
            direction_value = (
                direction.value if hasattr(direction, "value") else str(direction or "")
            )
            out[int(message_id)] = {
                "direction": direction_value,
                "sender_user_id": int(sender_user_id) if sender_user_id is not None else None,
            }
        return out

    async def _load_contact_labels_for_chats(
        self,
        chat_ids: set[int],
    ) -> dict[int, str | None]:
        if not chat_ids:
            return {}
        result = await self._session.execute(
            select(
                Chat.id,
                Contact.full_name,
                Contact.telegram_username,
                Contact.phone,
            )
            .join(Contact, Contact.id == Chat.contact_id)
            .where(Chat.id.in_(chat_ids)),
        )
        labels: dict[int, str | None] = {}
        for chat_id, full_name, username, phone in result.all():
            labels[int(chat_id)] = self._contact_label(
                full_name=full_name,
                telegram_username=username,
                phone=phone,
            )
        return labels

    @staticmethod
    def _contact_label(
        *,
        full_name: str | None,
        telegram_username: str | None = None,
        phone: str | None = None,
    ) -> str:
        name = (full_name or "").strip()
        if name and name.casefold() not in {"клиент", "client", "unknown", "без имени"}:
            return name
        if telegram_username:
            handle = str(telegram_username).strip().lstrip("@")
            if handle:
                return f"@{handle}"
        if phone and str(phone).strip():
            return str(phone).strip()
        return name or "Клиент"

    def _to_group_file_response(
        self,
        row: GroupChatFile,
        contact_label: str | None,
        user_names: dict[int, str],
        message_meta: dict[str, Any] | None = None,
    ) -> GroupChatFileResponse:
        direction = row.direction
        sender_user_id = row.sender_user_id
        if message_meta:
            live_direction = str(message_meta.get("direction") or "").strip().lower()
            if live_direction in {"inbound", "outbound"}:
                direction = live_direction
            if message_meta.get("sender_user_id") is not None:
                sender_user_id = int(message_meta["sender_user_id"])

        if direction == "inbound":
            display_name = contact_label or row.sender_display_name or "Клиент"
            if display_name.strip().casefold() in {"оператор", "operator"}:
                display_name = contact_label or "Клиент"
        else:
            sender_user_name = (
                user_names.get(sender_user_id) if sender_user_id is not None else None
            )
            display_name = (
                sender_user_name
                or (row.sender_display_name if row.sender_display_name not in ("Оператор", "") else None)
                or "Оператор"
            )

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
            direction=direction,
            sender_display_name=display_name,
            sender_user_id=sender_user_id,
            sender_contact_id=row.sender_contact_id,
            created_at=row.created_at,
            download_path=(
                f"chats/{row.chat_id}/messages/{row.message_id}/attachments/{row.attachment_index}"
            ),
            contact_name=contact_label,
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

    async def list_receipts_tree(self, actor: User):
        from sqlalchemy import select

        from app.modules.accounting.receipts import (
            OptReceiptRepository,
            visible_receipt_supplier_inns,
        )
        from app.modules.accounting.sales_books import (
            OptSalesBookExtractRepository,
            pairs_for_period_orders,
            visible_sales_book_pairs,
        )
        from app.modules.contacts.scope_loader import ScopeLoader
        from app.modules.db.models.lead import Lead
        from app.modules.db.models.lead_opt_order import LeadOptOrder, LeadOptOrderLine
        from app.modules.rbac.scope import SCOPE_ALL, visible_group_ids
        from app.modules.storage.schemas import (
            StorageReceiptItem,
            StorageReceiptPeriodGroup,
            StorageReceiptTreeResponse,
            StorageSalesBookItem,
        )

        ctx = await ScopeLoader(self._session).load(actor)
        inns = await visible_receipt_supplier_inns(self._session, actor, ctx)
        rows = await OptReceiptRepository(self._session).list_all(supplier_inns=inns)
        by_period: dict[str, list[StorageReceiptItem]] = {}
        for row in rows:
            by_period.setdefault(row.period_code, []).append(
                StorageReceiptItem(
                    id=row.id,
                    supplier_inn=row.supplier_inn,
                    supplier_name=row.supplier_name,
                    period_code=row.period_code,
                    doc_kind=row.doc_kind,
                    is_correction=bool(getattr(row, "is_correction", False)),
                    source_filename=row.source_filename,
                    has_pdf=row.pdf_file_id is not None,
                ),
            )

        sb_pairs = await visible_sales_book_pairs(self._session, actor, ctx)
        from app.modules.db.models.enums import UserRole

        role = actor.role if isinstance(actor.role, UserRole) else UserRole(str(actor.role))
        groups = visible_group_ids(ctx)
        gids: set[int] | None
        if (
            role in {UserRole.ADMIN, UserRole.CHIEF_ACCOUNTANT, UserRole.ACCOUNTANT}
            or groups == SCOPE_ALL
        ):
            # Admin/chief/accountant: no chat-group filter (accountant filtered via pairs).
            gids = None
        elif isinstance(groups, set) and groups:
            gids = set(groups)
        else:
            gids = set()

        period_codes = set(by_period.keys())
        if gids is None or gids:
            period_stmt = select(LeadOptOrder.period_code).join(
                Lead,
                Lead.id == LeadOptOrder.lead_id,
            ).where(
                LeadOptOrder.deleted_at.is_(None),
                LeadOptOrder.period_code.is_not(None),
            )
            if gids is not None:
                period_stmt = period_stmt.where(Lead.group_id.in_(gids))
            period_result = await self._session.execute(period_stmt.distinct())
            for code in period_result.scalars().all():
                if code:
                    period_codes.add(str(code).strip())

        def _period_key_early(code: str) -> tuple[int, int]:
            parts = str(code).strip().split("/")
            if len(parts) != 2:
                return (0, 0)
            try:
                quarter, yy = int(parts[0]), int(parts[1])
            except ValueError:
                return (0, 0)
            return (2000 + yy, quarter)

        sales_period_codes = sorted(period_codes, key=_period_key_early, reverse=True)[:8]

        from app.modules.accounting.sales_books import normalize_inn
        from app.modules.db.models.opt_unit import OptUnit
        from app.modules.storage.schemas import (
            StorageSalesBookOrderGroup,
            StorageSalesBookUnitGroup,
        )

        sales_by_period: dict[str, list[StorageSalesBookItem]] = {}
        units_by_period: dict[str, list[StorageSalesBookUnitGroup]] = {}
        repo = OptSalesBookExtractRepository(self._session)

        units_result = await self._session.execute(select(OptUnit))
        unit_name_by_inn = {
            str(u.inn): (u.name or str(u.inn)) for u in units_result.scalars().all()
        }

        for code in sales_period_codes:
            pairs = await pairs_for_period_orders(
                self._session,
                period_code=code,
                visible_pairs=sb_pairs,
                visible_group_ids_set=gids,
            )
            if not pairs:
                continue
            extracts = await repo.list_for_pairs(pairs)
            if not extracts:
                continue
            sales_by_period[code] = [
                StorageSalesBookItem(
                    id=ex.id,
                    seller_inn=ex.seller_inn,
                    buyer_inn=ex.buyer_inn,
                    seller_name=ex.seller_name or unit_name_by_inn.get(ex.seller_inn),
                    buyer_name=ex.buyer_name,
                    source_filename=ex.source_filename,
                    has_pdf=ex.pdf_file_id is not None,
                )
                for ex in extracts
            ]

            order_stmt = (
                select(
                    LeadOptOrder.id,
                    LeadOptOrder.order_no,
                    LeadOptOrder.lead_id,
                    LeadOptOrder.buyer_inn,
                    LeadOptOrder.buyer_name,
                    LeadOptOrderLine.supplier_inn,
                )
                .join(LeadOptOrderLine, LeadOptOrderLine.order_id == LeadOptOrder.id)
                .join(Lead, Lead.id == LeadOptOrder.lead_id)
                .where(
                    LeadOptOrder.deleted_at.is_(None),
                    LeadOptOrder.period_code == code,
                    LeadOptOrder.buyer_inn.is_not(None),
                    LeadOptOrderLine.supplier_inn.is_not(None),
                )
            )
            if gids is not None:
                order_stmt = order_stmt.where(Lead.group_id.in_(gids))
            order_rows = await self._session.execute(order_stmt)

            # seller -> order_id -> meta + pairs
            by_seller: dict[str, dict[int, dict]] = {}
            buyer_name_by_inn: dict[str, str] = {}
            for (
                order_id,
                order_no,
                lead_id,
                buyer_raw,
                buyer_name_raw,
                seller_raw,
            ) in order_rows.all():
                seller = normalize_inn(str(seller_raw) if seller_raw else None)
                buyer = normalize_inn(str(buyer_raw) if buyer_raw else None)
                if not seller or not buyer:
                    continue
                if sb_pairs is not None and (seller, buyer) not in sb_pairs:
                    continue
                if buyer_name_raw and buyer not in buyer_name_by_inn:
                    buyer_name_by_inn[buyer] = str(buyer_name_raw).strip()
                by_seller.setdefault(seller, {})
                bucket = by_seller[seller].setdefault(
                    int(order_id),
                    {
                        "order_no": int(order_no),
                        "lead_id": int(lead_id),
                        "buyer_inn": buyer,
                        "buyer_name": (str(buyer_name_raw).strip() if buyer_name_raw else None),
                        "pairs": set(),
                    },
                )
                if buyer_name_raw and not bucket.get("buyer_name"):
                    bucket["buyer_name"] = str(buyer_name_raw).strip()
                bucket["pairs"].add((seller, buyer))

            extract_map = {(e.seller_inn, e.buyer_inn): e for e in extracts}
            # Enrich flat list buyer_name from extracts or orders.
            for item in sales_by_period[code]:
                if not item.buyer_name:
                    item.buyer_name = buyer_name_by_inn.get(item.buyer_inn)
            unit_groups: list[StorageSalesBookUnitGroup] = []
            for seller, orders_map in sorted(
                by_seller.items(),
                key=lambda kv: unit_name_by_inn.get(kv[0], kv[0]).casefold(),
            ):
                order_groups: list[StorageSalesBookOrderGroup] = []
                for oid, meta in sorted(orders_map.items(), key=lambda kv: kv[1]["order_no"]):
                    items: list[StorageSalesBookItem] = []
                    for pair in meta["pairs"]:
                        ex = extract_map.get(pair)
                        if ex is None:
                            continue
                        items.append(
                            StorageSalesBookItem(
                                id=ex.id,
                                seller_inn=ex.seller_inn,
                                buyer_inn=ex.buyer_inn,
                                seller_name=ex.seller_name
                                or unit_name_by_inn.get(ex.seller_inn),
                                buyer_name=ex.buyer_name
                                or meta.get("buyer_name")
                                or buyer_name_by_inn.get(ex.buyer_inn),
                                source_filename=ex.source_filename,
                                has_pdf=ex.pdf_file_id is not None,
                            ),
                        )
                    if not items:
                        continue
                    order_groups.append(
                        StorageSalesBookOrderGroup(
                            order_id=oid,
                            order_no=meta["order_no"],
                            lead_id=meta["lead_id"],
                            buyer_inn=meta["buyer_inn"],
                            buyer_name=meta.get("buyer_name")
                            or next((i.buyer_name for i in items if i.buyer_name), None),
                            items=items,
                        ),
                    )
                if not order_groups:
                    continue
                unit_groups.append(
                    StorageSalesBookUnitGroup(
                        seller_inn=seller,
                        seller_name=unit_name_by_inn.get(seller) or seller,
                        orders=order_groups,
                    ),
                )
            if unit_groups:
                units_by_period[code] = unit_groups

        def _period_key(code: str) -> tuple[int, int]:
            # "2/26" → (2026, 2) — newest year/quarter first
            parts = str(code).strip().split("/")
            if len(parts) != 2:
                return (0, 0)
            try:
                quarter, yy = int(parts[0]), int(parts[1])
            except ValueError:
                return (0, 0)
            return (2000 + yy, quarter)

        def _item_key(item: StorageReceiptItem) -> tuple:
            name = (item.supplier_name or item.supplier_inn or "").casefold()
            # notice before receipt within the same lavka
            kind = 0 if item.doc_kind == "notice" else 1
            return (name, item.supplier_inn, kind, item.source_filename or "")

        all_codes = set(by_period.keys()) | set(sales_by_period.keys()) | set(units_by_period.keys())
        periods = []
        for code in sorted(all_codes, key=_period_key, reverse=True):
            items_sorted = sorted(by_period.get(code, []), key=_item_key)
            sales = sales_by_period.get(code, [])
            sales_sorted = sorted(
                sales,
                key=lambda s: (
                    (s.seller_name or s.seller_inn).casefold(),
                    s.buyer_inn,
                    s.source_filename or "",
                ),
            )
            periods.append(
                StorageReceiptPeriodGroup(
                    period_code=code,
                    items=items_sorted,
                    sales_books=sales_sorted,
                    sales_book_units=units_by_period.get(code, []),
                ),
            )
        return StorageReceiptTreeResponse(periods=periods)

    async def get_receipt_bytes(self, actor: User, receipt_id: int) -> tuple[bytes, str]:
        from app.modules.accounting.receipts import (
            OptReceiptRepository,
            load_receipt_pdf_bytes,
            visible_receipt_supplier_inns,
        )
        from app.modules.contacts.scope_loader import ScopeLoader

        ctx = await ScopeLoader(self._session).load(actor)
        inns = await visible_receipt_supplier_inns(self._session, actor, ctx)
        row = await OptReceiptRepository(self._session).get_by_id(receipt_id)
        if row is None:
            raise NotFound(message="Квитанция не найдена")
        if inns is not None and row.supplier_inn not in inns:
            raise PermissionDenied(message="Нет доступа к квитанции")
        content = await load_receipt_pdf_bytes(self._session, row)
        return content, row.source_filename or f"receipt-{row.id}.pdf"

    async def get_sales_book_bytes(self, actor: User, extract_id: int) -> tuple[bytes, str]:
        from app.modules.accounting.sales_books import (
            OptSalesBookExtractRepository,
            load_sales_book_pdf_bytes,
            sales_book_download_name,
            visible_sales_book_pairs,
        )
        from app.modules.contacts.scope_loader import ScopeLoader

        ctx = await ScopeLoader(self._session).load(actor)
        pairs = await visible_sales_book_pairs(self._session, actor, ctx)
        row = await OptSalesBookExtractRepository(self._session).get(extract_id)
        if row is None:
            raise NotFound(message="Выписка книги продаж не найдена")
        if pairs is not None and (row.seller_inn, row.buyer_inn) not in pairs:
            raise PermissionDenied(message="Нет доступа к книге продаж")
        content = await load_sales_book_pdf_bytes(self._session, row)
        return content, sales_book_download_name(row)
