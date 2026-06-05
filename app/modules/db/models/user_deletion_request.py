from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base
from app.modules.db.models.enums import UserDeletionRequestState

if TYPE_CHECKING:
    from app.modules.db.models.user import User


class UserDeletionRequest(Base):
    __tablename__ = "user_deletion_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    target_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state: Mapped[UserDeletionRequestState] = mapped_column(
        SAEnum(
            UserDeletionRequestState,
            native_enum=False,
            values_callable=lambda cls: [m.value for m in cls],
        ),
        nullable=False,
        server_default=UserDeletionRequestState.PENDING.value,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decided_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    target_user: Mapped[User] = relationship(foreign_keys=[target_user_id], lazy="selectin")
    requested_by: Mapped[User] = relationship(foreign_keys=[requested_by_user_id], lazy="selectin")
    decided_by: Mapped[User | None] = relationship(
        foreign_keys=[decided_by_user_id],
        lazy="selectin",
    )
