from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

if TYPE_CHECKING:
    from app.modules.db.models.opt_unit import OptUnit
    from app.modules.db.models.user import User


class OptAccountantUnitAssignment(Base):
    """Maps accountant users to lavki (opt_units) they can access."""

    __tablename__ = "opt_accountant_unit_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "unit_id", name="uq_opt_accountant_unit"),
        Index("idx_opt_accountant_unit_user_id", "user_id"),
        Index("idx_opt_accountant_unit_unit_id", "unit_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    unit_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("opt_units.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="selectin")
    unit: Mapped[OptUnit] = relationship(lazy="selectin")
