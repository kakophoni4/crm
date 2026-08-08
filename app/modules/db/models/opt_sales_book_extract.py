"""Short SBIS sales-book extracts (seller × buyer). Never store _full.pdf."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base
from app.modules.db.models.uploaded_file import UploadedFile


class OptSalesBookExtract(Base):
    __tablename__ = "opt_sales_book_extracts"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_opt_sales_book_extracts_external_id"),
        Index("idx_opt_sbe_seller_buyer", "seller_inn", "buyer_inn"),
        Index("idx_opt_sbe_buyer", "buyer_inn"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    seller_inn: Mapped[str] = mapped_column(Text, nullable=False)
    buyer_inn: Mapped[str] = mapped_column(Text, nullable=False)
    seller_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_filename: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_file_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
    )
    received_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    pdf_file: Mapped[UploadedFile | None] = relationship(lazy="selectin")
