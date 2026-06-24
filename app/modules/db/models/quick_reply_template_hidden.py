from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class QuickReplyTemplateHidden(Base):
    __tablename__ = "quick_reply_template_hidden"
    __table_args__ = (UniqueConstraint("template_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("quick_reply_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hidden_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
