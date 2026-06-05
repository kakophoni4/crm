from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base
from app.modules.db.models.enums import ContactStatus, contact_status_pg

if TYPE_CHECKING:
    from app.modules.db.models.contact_field_change import ContactFieldChange
    from app.modules.db.models.department import Department
    from app.modules.db.models.user import User


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(CITEXT, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    status: Mapped[ContactStatus] = mapped_column(
        contact_status_pg,
        nullable=False,
        server_default=ContactStatus.NEW.value,
        index=True,
    )
    custom_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    assigned_department_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    assigned_department: Mapped[Department | None] = relationship(
        foreign_keys=[assigned_department_id],
        lazy="selectin",
    )
    creator: Mapped[User] = relationship(
        foreign_keys=[created_by],
        lazy="selectin",
    )
    field_changes: Mapped[list[ContactFieldChange]] = relationship(
        back_populates="contact",
        lazy="selectin",
    )
