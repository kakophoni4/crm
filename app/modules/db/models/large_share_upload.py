from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class LargeShareUpload(Base):
    __tablename__ = "large_share_uploads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    s3_upload_id: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("file_vault_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="uploading")
    part_etags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    expires_in_hours: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="72")
    max_downloads: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1")
    file_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    vault_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("file_vault_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    share_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("file_share_links.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
