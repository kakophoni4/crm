from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class LavokParserLot(Base):
    """Daily lavok listing snapshot from Parser lavok.xlsx (one row per INN+sheet date)."""

    __tablename__ = "lavok_parser_lots"
    __table_args__ = (
        UniqueConstraint("inn", "sheet_date", name="uq_lavok_parser_lots_inn_sheet_date"),
        Index("idx_lavok_parser_lots_sheet_date", "sheet_date"),
        Index("idx_lavok_parser_lots_is_deleted", "is_deleted"),
        Index("idx_lavok_parser_lots_inn", "inn"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    inn: Mapped[str] = mapped_column(Text, nullable=False)
    sheet_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_director: Mapped[str | None] = mapped_column(Text, nullable=True)
    courts: Mapped[str | None] = mapped_column(Text, nullable=True)
    debts: Mapped[str | None] = mapped_column(Text, nullable=True)
    egrul_reliability: Mapped[str | None] = mapped_column(Text, nullable=True)
    bankruptcy: Mapped[str | None] = mapped_column(Text, nullable=True)
    turnover: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporting: Mapped[str | None] = mapped_column(Text, nullable=True)
    leasing: Mapped[str | None] = mapped_column(Text, nullable=True)
    zsk: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen: Mapped[str | None] = mapped_column(Text, nullable=True)
    seller: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    companium: Mapped[str | None] = mapped_column(Text, nullable=True)
    egrul_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    mark: Mapped[str] = mapped_column(Text, nullable=False, server_default="new")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
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
