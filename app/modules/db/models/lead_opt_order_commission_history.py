from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

if TYPE_CHECKING:
    from app.modules.db.models.lead_opt_order import LeadOptOrder
    from app.modules.db.models.user import User


class LeadOptOrderCommissionHistory(Base):
    __tablename__ = "lead_opt_order_commission_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("lead_opt_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_commission_due: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    new_commission_due: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    delta: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    order: Mapped[LeadOptOrder] = relationship(back_populates="commission_history", lazy="selectin")
    changer: Mapped[User] = relationship(lazy="selectin")
