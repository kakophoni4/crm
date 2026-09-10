from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Integer, BigInteger, String, Text, Date, DateTime, Numeric, ForeignKey, Boolean, JSON, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class CashDeal(Base):
    __tablename__ = "cash_deals"
    __table_args__ = (CheckConstraint("amount > 0", name="positive_amount"), CheckConstraint("executor_rate >= 0 AND executor_rate <= 100", name="executor_rate_range"), CheckConstraint("client_rate >= 0 AND client_rate <= 100", name="client_rate_range"), CheckConstraint("manager_rate >= 0 AND manager_rate <= 100", name="manager_rate_range"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entered_on: Mapped[date] = mapped_column(Date, index=True)
    due_on: Mapped[date | None] = mapped_column(Date)
    payer: Mapped[str] = mapped_column(String(200))
    receiver: Mapped[str] = mapped_column(String(200))
    payer_inn: Mapped[str] = mapped_column(String(12), default="")
    receiver_inn: Mapped[str] = mapped_column(String(12), default="")
    client: Mapped[str] = mapped_column(String(200), index=True)
    executor: Mapped[str] = mapped_column(String(200), index=True)
    manager: Mapped[str] = mapped_column(String(200), default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    executor_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    client_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    manager_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    comment: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CashAccount(Base):
    __tablename__ = "cash_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class CashMovement(Base):
    __tablename__ = "cash_movements"
    __table_args__ = (CheckConstraint("amount > 0", name="positive_amount"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_key: Mapped[str] = mapped_column(String(36), unique=True)
    deal_id: Mapped[int | None] = mapped_column(ForeignKey("cash_deals.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("cash_accounts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    client: Mapped[str] = mapped_column(String(200), default="")
    manager: Mapped[str] = mapped_column(String(200), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    comment2: Mapped[str] = mapped_column(Text, default="")
    voided: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CashAudit(Base):
    __tablename__ = "cash_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_id: Mapped[int | None] = mapped_column(ForeignKey("cash_deals.id"), index=True)
    movement_id: Mapped[int | None] = mapped_column(ForeignKey("cash_movements.id"))
    actor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40))
    changes: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
