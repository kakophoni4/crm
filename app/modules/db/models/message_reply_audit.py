from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

if TYPE_CHECKING:
    from app.modules.db.models.chat import Chat
    from app.modules.db.models.chat_message import ChatMessage
    from app.modules.db.models.contact import Contact
    from app.modules.db.models.group import Group
    from app.modules.db.models.user import User


class MessageReplyAudit(Base):
    __tablename__ = "message_reply_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
    )
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
    card_owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    author_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_on_behalf: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    message: Mapped[ChatMessage] = relationship(lazy="select")
    chat: Mapped[Chat] = relationship(lazy="select")
    contact: Mapped[Contact] = relationship(lazy="select")
    group: Mapped[Group] = relationship(lazy="select")
    card_owner: Mapped[User] = relationship(
        foreign_keys=[card_owner_user_id],
        lazy="select",
    )
    author: Mapped[User] = relationship(
        foreign_keys=[author_user_id],
        lazy="select",
    )
