from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

if TYPE_CHECKING:
    from app.modules.db.models.group import Group
    from app.modules.db.models.user import User


class GroupEscalationSettings(Base):
    __tablename__ = "group_escalation_settings"

    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    first_response_timeout_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="15",
    )
    new_contact_reassign_strategy: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="first_responder",
    )
    notify_owner_on_inbound: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    notify_group_on_escalation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
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
