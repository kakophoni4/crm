from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base
from app.modules.db.models.uploaded_file import UploadedFile


class OptReceipt(Base):
    """SBIS KV/IV receipt or notice PDF tied to a lavka + OPT period."""

    __tablename__ = "opt_receipts"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_opt_receipts_external_id"),
        Index("idx_opt_receipts_supplier_period", "supplier_inn", "period_code"),
        Index("idx_opt_receipts_period", "period_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_inn: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_kpp: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_code: Mapped[str] = mapped_column(Text, nullable=False)
    doc_kind: Mapped[str] = mapped_column(Text, nullable=False)  # receipt | notice
    is_correction: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    source_filename: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_name: Mapped[str | None] = mapped_column(Text, nullable=True)
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
