from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base
from app.modules.db.models.uploaded_file import UploadedFile


class OptRequirement(Base):
    """Tax/authority requirement document tied to a lavka (supplier)."""

    __tablename__ = "opt_requirements"
    __table_args__ = (
        Index("idx_opt_requirements_supplier_inn", "supplier_inn"),
        Index("idx_opt_requirements_received_at", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    supplier_inn: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_kpp: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="new")
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

    pdf_file: Mapped[UploadedFile | None] = relationship(lazy="selectin")
