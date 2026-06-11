from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base
from app.modules.db.models.enums import (
    UserAvailability,
    UserPresence,
    UserRole,
    UserStatus,
    user_availability_pg,
    user_presence_pg,
    user_role_pg,
    user_status_pg,
)

if TYPE_CHECKING:
    from app.modules.db.models.department import Department
    from app.modules.db.models.group import Group
    from app.modules.db.models.refresh_token import RefreshToken
    from app.modules.db.models.user_group_membership import UserGroupMembership


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    username: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(user_role_pg, nullable=False, index=True)
    department_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    group_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[UserStatus] = mapped_column(
        user_status_pg,
        nullable=False,
        server_default=UserStatus.ACTIVE.value,
    )
    presence: Mapped[UserPresence] = mapped_column(
        user_presence_pg,
        nullable=False,
        server_default=UserPresence.OFFLINE.value,
    )
    availability: Mapped[UserAvailability] = mapped_column(
        user_availability_pg,
        nullable=False,
        server_default=UserAvailability.AVAILABLE.value,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    department: Mapped[Department | None] = relationship(
        back_populates="users",
        foreign_keys=[department_id],
    )
    group: Mapped[Group | None] = relationship(
        back_populates="users",
        foreign_keys=[group_id],
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user")
    group_memberships: Mapped[list[UserGroupMembership]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
