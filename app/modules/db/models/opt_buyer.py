from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class OptBuyer(Base):
    """OPT client (покупатель) directory for 1C payloads."""

    __tablename__ = "opt_buyers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    inn: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    kpp: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
