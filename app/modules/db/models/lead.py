from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, ForeignKey, Index, Text, desc, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

if TYPE_CHECKING:
    from app.modules.db.models.bot import Bot
    from app.modules.db.models.chat import Chat
    from app.modules.db.models.contact import Contact
    from app.modules.db.models.group import Group
    from app.modules.db.models.lead_comment import LeadComment
    from app.modules.db.models.status import Status


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index(
            "uq_leads_open_contact_group",
            "contact_id",
            "group_id",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
        ),
        Index("idx_leads_contact_closed", "contact_id", "closed_at"),
        Index("idx_leads_group_created", "group_id", desc("created_at")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("contacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bot_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("bots.id", ondelete="SET NULL"),
        nullable=True,
    )
    chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("chats.id", ondelete="SET NULL"),
        nullable=True,
    )
    status_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("statuses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    retention_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    contact: Mapped[Contact] = relationship(lazy="selectin")
    group: Mapped[Group] = relationship(lazy="selectin")
    bot: Mapped[Bot | None] = relationship(foreign_keys=[bot_id], lazy="selectin")
    chat: Mapped[Chat | None] = relationship(
        foreign_keys=[chat_id],
        lazy="selectin",
    )
    pipeline_status: Mapped[Status] = relationship(
        foreign_keys=[status_id],
        lazy="selectin",
    )
    comments: Mapped[list[LeadComment]] = relationship(
        back_populates="lead",
        lazy="selectin",
        order_by="LeadComment.created_at",
    )
