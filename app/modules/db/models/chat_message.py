from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Computed, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base
from app.modules.db.models.enums import (
    MessageDirection,
    MessageKind,
    message_direction_pg,
    message_kind_pg,
)

if TYPE_CHECKING:
    from app.modules.db.models.chat import Chat
    from app.modules.db.models.user import User


class ChatMessage(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_chat_id_id", "chat_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    direction: Mapped[MessageDirection] = mapped_column(message_direction_pg, nullable=False)
    kind: Mapped[MessageKind] = mapped_column(message_kind_pg, nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_vector: Mapped[object | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('russian', coalesce(text, ''))", persisted=True),
        nullable=True,
    )
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    sender_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    external_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_event_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_to_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)

    chat: Mapped[Chat] = relationship(back_populates="messages", lazy="selectin")
    sender: Mapped[User | None] = relationship(
        foreign_keys=[sender_user_id],
        lazy="selectin",
    )
