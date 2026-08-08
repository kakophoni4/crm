from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class FileVaultItem(Base):
    __tablename__ = "file_vault_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("uploaded_files.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_folder: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("file_vault_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
