from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VaultFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: int
    original_name: str
    mime_type: str
    size_bytes: int
    created_at: datetime
    share_links: list["ShareLinkResponse"] = Field(default_factory=list)


class VaultFileListResponse(BaseModel):
    items: list[VaultFileResponse]
    total: int


class VaultFileRenameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_name: str = Field(min_length=1, max_length=512)


class VaultFileContentResponse(BaseModel):
    id: int
    file_id: int
    original_name: str
    mime_type: str
    size_bytes: int
    editable: bool
    content: str


class VaultFileContentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(max_length=1_000_000)


class ShareLinkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_in_hours: int | None = Field(default=None, ge=1, le=8760)
    max_downloads: int | None = Field(default=None, ge=1, le=10000)
    password: str | None = Field(default=None, min_length=1, max_length=128)


class ShareLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    token: str
    url: str
    has_password: bool
    expires_at: datetime | None
    max_downloads: int | None
    download_count: int
    revoked_at: datetime | None
    created_at: datetime


class AnonymousShareCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_in_hours: int | None = Field(default=168, ge=1, le=8760)
    max_downloads: int | None = Field(default=None, ge=1, le=10000)
    password: str | None = Field(default=None, min_length=1, max_length=128)


class AnonymousShareResponse(BaseModel):
    token: str
    url: str
    original_name: str
    mime_type: str
    size_bytes: int
    expires_at: datetime | None
    max_downloads: int | None
    has_password: bool


class PublicShareInfoResponse(BaseModel):
    original_name: str
    mime_type: str
    size_bytes: int
    has_password: bool
    expires_at: datetime | None
    max_downloads: int | None
    download_count: int
    is_expired: bool
    is_exhausted: bool


class PublicShareDownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str | None = Field(default=None, max_length=128)


class GroupChatFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    chat_id: int
    message_id: int
    attachment_index: int
    file_id: int | None
    original_name: str
    mime_type: str
    size_bytes: int
    direction: str
    sender_display_name: str
    sender_user_id: int | None
    sender_contact_id: int | None
    created_at: datetime
    download_path: str
    contact_name: str | None = None


class GroupChatFileListResponse(BaseModel):
    items: list[GroupChatFileResponse]
    total: int


class GroupChatFileGroupSummary(BaseModel):
    group_id: int
    group_name: str
    file_count: int


class GroupChatFileGroupsResponse(BaseModel):
    items: list[GroupChatFileGroupSummary]


class StorageReceiptItem(BaseModel):
    id: int
    supplier_inn: str
    supplier_name: str | None = None
    period_code: str
    doc_kind: str
    is_correction: bool = False
    source_filename: str
    has_pdf: bool


class StorageSalesBookItem(BaseModel):
    id: int
    seller_inn: str
    buyer_inn: str
    seller_name: str | None = None
    buyer_name: str | None = None
    source_filename: str
    has_pdf: bool


class StorageReceiptPeriodGroup(BaseModel):
    period_code: str
    items: list[StorageReceiptItem] = Field(default_factory=list)
    sales_books: list[StorageSalesBookItem] = Field(default_factory=list)


class StorageReceiptTreeResponse(BaseModel):
    periods: list[StorageReceiptPeriodGroup] = Field(default_factory=list)
