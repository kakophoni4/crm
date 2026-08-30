from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class LawyerDirector(Base):
    __tablename__ = "lawyer_directors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    salary_plan: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    dirovod: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    companies_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    ecsp_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    ecsp_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    banks: Mapped[str | None] = mapped_column(Text, nullable=True)
    accounts_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram: Mapped[str | None] = mapped_column(Text, nullable=True)
    passport: Mapped[str | None] = mapped_column(Text, nullable=True)
    inn_personal: Mapped[str | None] = mapped_column(Text, nullable=True)
    snils: Mapped[str | None] = mapped_column(Text, nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    in_touch: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class LawyerShop(Base):
    __tablename__ = "lawyer_shops"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    inn: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    director_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("lawyer_directors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="priority")
    registered_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_payout: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    company_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    sale_priority: Mapped[str | None] = mapped_column(Text, nullable=True)
    unreliable: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    ecsp_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    ecsp_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    zsk: Mapped[str | None] = mapped_column(Text, nullable=True)
    banks: Mapped[str | None] = mapped_column(Text, nullable=True)
    accounts_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram: Mapped[str | None] = mapped_column(Text, nullable=True)
    accountant: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual")
    last_parser_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class LawyerDirectorPayment(Base):
    __tablename__ = "lawyer_director_payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    director_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("lawyer_directors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shop_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("lawyer_shops.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    period_ym: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class LawyerParserAlert(Base):
    __tablename__ = "lawyer_parser_alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shop_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("lawyer_shops.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    inn: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
