from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

if TYPE_CHECKING:
    from app.modules.db.models.contact import Contact
    from app.modules.db.models.group import Group
    from app.modules.db.models.user import User


class ContactGroupAssignment(Base):
    __tablename__ = "contact_group_assignments"
    __table_args__ = (UniqueConstraint("contact_id", "group_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    assignment_source: Mapped[str] = mapped_column(Text, nullable=False)
    last_owner_response_at: Mapped[datetime | None] = mapped_column(nullable=True)
    pending_inbound_at: Mapped[datetime | None] = mapped_column(nullable=True)
    escalated_to_group_at: Mapped[datetime | None] = mapped_column(nullable=True)
    after_hours_auto_replied_at: Mapped[datetime | None] = mapped_column(nullable=True)
    staff_notify_acked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    staff_notify_acked_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    staff_notify_group_senior_at: Mapped[datetime | None] = mapped_column(nullable=True)
    staff_notify_dept_senior_at: Mapped[datetime | None] = mapped_column(nullable=True)
    staff_notify_admin_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    contact: Mapped[Contact] = relationship(lazy="selectin")
    group: Mapped[Group] = relationship(lazy="selectin")
    owner_user: Mapped[User | None] = relationship(
        foreign_keys=[owner_user_id],
        lazy="selectin",
    )
