from datetime import datetime
from sqlalchemy import BigInteger, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.modules.db.models.base import Base

class SalesSeason(Base):
    __tablename__ = 'sales_seasons'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
