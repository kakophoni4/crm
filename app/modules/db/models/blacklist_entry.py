from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class BlacklistEntry(Base):
    __tablename__ = "blacklist_entries"
    __table_args__ = (UniqueConstraint("kind", "value", name="uq_blacklist_entries_kind_value"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # telegram_username | buyer_inn
    value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
