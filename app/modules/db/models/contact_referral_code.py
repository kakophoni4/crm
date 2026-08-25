from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class ContactReferralCode(Base):
    __tablename__ = "contact_referral_codes"
    __table_args__ = (
        UniqueConstraint("contact_id", "bot_id", name="uq_contact_referral_codes_contact_bot"),
        UniqueConstraint("code", name="uq_contact_referral_codes_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    bot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
