from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, LargeBinary, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

if TYPE_CHECKING:
    from app.modules.db.models.user import User


class NotificationBotSettings(Base):
    """Singleton row (id=1) for the staff notification Telegram bot."""

    __tablename__ = "notification_bot_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    bot_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    bot_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    updater: Mapped[User | None] = relationship(
        foreign_keys=[updated_by],
        primaryjoin="NotificationBotSettings.updated_by == User.id",
        lazy="selectin",
        viewonly=True,
    )
