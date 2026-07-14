from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

if TYPE_CHECKING:
    from app.modules.db.models.group import Group
    from app.modules.db.models.user import User


DEFAULT_WORKING_HOURS: dict[str, list[list[str]]] = {
    "mon": [["09:00", "18:00"]],
    "tue": [["09:00", "18:00"]],
    "wed": [["09:00", "18:00"]],
    "thu": [["09:00", "18:00"]],
    "fri": [["09:00", "18:00"]],
    "sat": [],
    "sun": [],
}


class GroupAfterHoursSettings(Base):
    __tablename__ = "group_after_hours_settings"

    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    reply_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="15")
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Europe/Moscow")
    working_hours: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="120")
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    group: Mapped[Group] = relationship(lazy="selectin")
    updater: Mapped[User | None] = relationship(
        foreign_keys=[updated_by],
        lazy="selectin",
    )
