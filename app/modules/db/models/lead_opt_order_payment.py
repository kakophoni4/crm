from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

PAYMENT_TYPE_CARD = "card"
PAYMENT_TYPE_CRYPTO = "crypto"
PAYMENT_TYPE_WIRE = "wire"
PAYMENT_TYPE_CASH = "cash"

PAYMENT_RECIPIENT_ORANGE = "orange"
PAYMENT_RECIPIENT_BENEFICIARY = "beneficiary"


class LeadOptOrderPayment(Base):
    __tablename__ = "lead_opt_order_payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("lead_opt_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payment_type: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    document_file_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_file_ids: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    order: Mapped["LeadOptOrder"] = relationship(back_populates="payments", lazy="selectin")
