"""OPT lavka availability by business period (quarter/year)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class OptUnitPeriodAvailability(Base):
    """Which supplier INNs are allowed for a given OPT period code (e.g. 2/26)."""

    __tablename__ = "opt_unit_period_availability"
    __table_args__ = (
        UniqueConstraint("inn", "period_code", name="uq_opt_unit_period_inn_code"),
        Index("idx_opt_unit_period_code", "period_code"),
        Index("idx_opt_unit_period_inn", "inn"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    inn: Mapped[str] = mapped_column(Text, nullable=False)
    period_code: Mapped[str] = mapped_column(Text, nullable=False)
    unit_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("opt_units.id", ondelete="SET NULL"),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
