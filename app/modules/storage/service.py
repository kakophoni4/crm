from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog
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

    def _vault_item_response(
        self,
        item: FileVaultItem,
        uploaded: UploadedFile | None = None,
        *,
        share_links: list[ShareLinkResponse] | None = None,
    ) -> VaultFileResponse:
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
        )

    async def list_vault(
        self,
        actor: User,
        *,
        parent_id: int | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> VaultFileListResponse:
        await self._assert_vault_parent(actor, parent_id)
        items, total = await self._repo.list_vault_items(
            actor.id,
            parent_id=parent_id,
            offset=offset,
            limit=limit,
        )
        files_map = await self._load_vault_files_map(items)
        file_ids = [item.file_id for item in items if item.file_id is not None]
        shares = await self._repo.list_share_links_for_files(file_ids)
        shares_by_file: dict[int, list[ShareLinkResponse]] = {}
        for share in shares:
            shares_by_file.setdefault(share.file_id, []).append(self._to_share_response(share))

        responses: list[VaultFileResponse] = []
        for item in items:
            if item.is_folder:
                responses.append(self._vault_item_response(item))
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
                ),
            )
        return VaultFileListResponse(items=responses, total=total)

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
        await self._assert_vault_parent(actor, parent_id)
        row = await self._repo.add_vault_item(
            file_id=None,
            owner_user_id=actor.id,
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
        await self._assert_vault_parent(actor, parent_id)
        uploaded = await self._files.create_upload(
            uploaded_by=actor.id,
            data=data,
            original_name=original_name,
            mime_type=mime_type,
        )
        vault_item = await self._repo.add_vault_item(
            file_id=uploaded.id,
            owner_user_id=actor.id,
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

    def _vault_response(self, item: FileVaultItem, uploaded: UploadedFile) -> VaultFileResponse:
        return self._vault_item_response(item, uploaded)

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

        for code in period_codes:
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
