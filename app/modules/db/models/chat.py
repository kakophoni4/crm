from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base
from app.modules.db.models.enums import ChatStatus, chat_status_pg

if TYPE_CHECKING:
    from app.modules.db.models.chat_message import ChatMessage
    from app.modules.db.models.contact import Contact
    from app.modules.db.models.department import Department
    from app.modules.db.models.group import Group
    from app.modules.db.models.lead import Lead
    from app.modules.db.models.status import Status
    from app.modules.db.models.user import User


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("contacts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bot_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # DEPRECATED as card owner — use contact_group_assignments.owner_user_id.
    # Maps to DB column last_handled_by_user_id (who last wrote/opened, not ownership).
    assigned_user_id: Mapped[int | None] = mapped_column(
        "last_handled_by_user_id",
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_group_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_department_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[ChatStatus] = mapped_column(
        chat_status_pg,
        nullable=False,
        server_default=ChatStatus.OPEN.value,
    )
    status_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("statuses.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_lead_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_message_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    contact: Mapped[Contact] = relationship(lazy="selectin")
    assigned_user: Mapped[User | None] = relationship(
        foreign_keys=[assigned_user_id],
        lazy="select",
    )
    assigned_group: Mapped[Group | None] = relationship(
        foreign_keys=[assigned_group_id],
        lazy="selectin",
    )
    assigned_department: Mapped[Department | None] = relationship(
        foreign_keys=[assigned_department_id],
        lazy="select",
    )
    business_status: Mapped[Status | None] = relationship(
        foreign_keys=[status_id],
        lazy="selectin",
    )
    current_lead: Mapped[Lead | None] = relationship(
        foreign_keys=[current_lead_id],
        lazy="selectin",
    )
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="chat",
        lazy="select",
    )
