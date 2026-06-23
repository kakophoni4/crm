from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class TelephonyAccountGroupAssignment(Base):
    __tablename__ = "telephony_account_group_assignments"

    account_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("telephony_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
