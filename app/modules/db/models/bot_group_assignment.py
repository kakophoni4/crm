from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class BotGroupAssignment(Base):
    __tablename__ = "bot_group_assignments"

    bot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
