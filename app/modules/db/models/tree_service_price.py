from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class TreeServicePrice(Base):
    __tablename__ = "tree_service_prices"

    type_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
