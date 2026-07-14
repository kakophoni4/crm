from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

if TYPE_CHECKING:
    from app.modules.db.models.chat import Chat
    from app.modules.db.models.contact import Contact
    from app.modules.db.models.department import Department
    from app.modules.db.models.group import Group
    from app.modules.db.models.user import User


class StaffNotificationKind(str, enum.Enum):
    INBOUND_MESSAGE = "inbound_message"
    NEW_CARD = "new_card"
    ESCALATION_GROUP_SENIOR = "escalation_group_senior"
    ESCALATION_DEPT_SENIOR = "escalation_dept_senior"
    ESCALATION_ADMIN = "escalation_admin"


class StaffNotificationStatus(str, enum.Enum):
    SENT = "sent"
    ACKED = "acked"
    CANCELLED = "cancelled"
    FAILED = "failed"


staff_notification_kind_pg = Enum(
    StaffNotificationKind,
    name="staff_notification_kind",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)
staff_notification_status_pg = Enum(
    StaffNotificationStatus,
    name="staff_notification_status",
    create_type=False,
    values_callable=lambda x: [e.value for e in x],
)


class StaffNotificationEvent(Base):
    __tablename__ = "staff_notification_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[StaffNotificationKind] = mapped_column(
        staff_notification_kind_pg,
        nullable=False,
    )
    status: Mapped[StaffNotificationStatus] = mapped_column(
        staff_notification_status_pg,
        nullable=False,
        server_default=StaffNotificationStatus.SENT.value,
    )
    contact_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="SET NULL"),
        nullable=True,
    )
    group_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    department_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pending_key: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    acked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)

    contact: Mapped[Contact | None] = relationship(lazy="selectin")
    chat: Mapped[Chat | None] = relationship(lazy="selectin")
    group: Mapped[Group | None] = relationship(lazy="selectin")
    department: Mapped[Department | None] = relationship(lazy="selectin")
    target_user: Mapped[User | None] = relationship(
        foreign_keys=[target_user_id],
        lazy="selectin",
    )
