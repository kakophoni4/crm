from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base
from app.modules.db.models.enums import TransferStatus, transfer_status_pg

if TYPE_CHECKING:
    from app.modules.db.models.contact import Contact
    from app.modules.db.models.group import Group
    from app.modules.db.models.user import User


class ContactGroupTransfer(Base):
    __tablename__ = "contact_group_transfers"

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
    from_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    to_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    state: Mapped[TransferStatus] = mapped_column(transfer_status_pg, nullable=False)
    senior_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    senior_decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    recipient_decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    force_assigned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    contact: Mapped[Contact] = relationship(lazy="selectin")
    group: Mapped[Group] = relationship(lazy="selectin")
    from_user: Mapped[User] = relationship(foreign_keys=[from_user_id], lazy="selectin")
    to_user: Mapped[User] = relationship(foreign_keys=[to_user_id], lazy="selectin")
    requester: Mapped[User] = relationship(foreign_keys=[requested_by], lazy="selectin")
    senior_user: Mapped[User | None] = relationship(
        foreign_keys=[senior_user_id],
        lazy="selectin",
    )
