from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

if TYPE_CHECKING:
    from app.modules.db.models.chat import Chat
    from app.modules.db.models.chat_message import ChatMessage
    from app.modules.db.models.user import User


class ChatReadState(Base):
    __tablename__ = "chat_read_state"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_read_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(lazy="selectin")
    chat: Mapped[Chat] = relationship(lazy="selectin")
    last_read_message: Mapped[ChatMessage | None] = relationship(
        foreign_keys=[last_read_message_id],
        lazy="selectin",
    )
