from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class FileVaultFolderShare(Base):
    __tablename__ = "file_vault_folder_shares"
    __table_args__ = (
        UniqueConstraint("folder_id", "user_id", name="uq_file_vault_folder_shares_folder_user"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    folder_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("file_vault_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shared_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
