from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.db.models.base import Base

if TYPE_CHECKING:
    from app.modules.db.models.lead import Lead
    from app.modules.db.models.lead_opt_order_commission_history import (
        LeadOptOrderCommissionHistory,
    )
    from app.modules.db.models.lead_opt_order_payment import LeadOptOrderPayment
    from app.modules.db.models.user import User


class LeadOptOrder(Base):
    __tablename__ = "lead_opt_orders"
    __table_args__ = (
        Index("idx_lead_opt_orders_lead_id", "lead_id"),
        Index("uq_lead_opt_orders_lead_order_no", "lead_id", "order_no", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    crm_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    buyer_inn: Mapped[str] = mapped_column(Text, nullable=False)
    buyer_kpp: Mapped[str | None] = mapped_column(Text, nullable=True)
    buyer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    source_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_attachment_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="unpaid")
    total_volume: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
    commission_due: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
    commission_adjustment: Mapped[float] = mapped_column(
        Numeric(15, 2),
        nullable=False,
        server_default="0",
    )
    amount_paid: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, server_default="0")
    volume_by_category: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    submission_request: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    submission_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    submission_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    submitted_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    lead: Mapped[Lead] = relationship(lazy="selectin")
    lines: Mapped[list[LeadOptOrderLine]] = relationship(
        back_populates="order",
        lazy="selectin",
        order_by="LeadOptOrderLine.line_no",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payments: Mapped[list[LeadOptOrderPayment]] = relationship(
        back_populates="order",
        lazy="selectin",
        order_by="LeadOptOrderPayment.paid_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    commission_history: Mapped[list[LeadOptOrderCommissionHistory]] = relationship(
        back_populates="order",
        lazy="selectin",
        order_by="LeadOptOrderCommissionHistory.created_at.desc()",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LeadOptOrderLine(Base):
    __tablename__ = "lead_opt_order_lines"
    __table_args__ = (Index("idx_lead_opt_order_lines_order_id", "order_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("lead_opt_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    crm_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    supplier_inn: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_kpp: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    vat_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    amount_without_vat: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    document_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    order: Mapped[LeadOptOrder] = relationship(back_populates="lines", lazy="selectin")
