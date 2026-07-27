from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class OptUnit(Base):
    """Supplier shop (лавка) directory for OPT registry."""

    __tablename__ = "opt_units"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    inn: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    kpp: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category_code: Mapped[str] = mapped_column(Text, nullable=False, server_default="TECH")
    commission_rate_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    volume_limit: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
