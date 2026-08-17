from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class IdleBannerSettings(Base):
    """Singleton row (id=1) for the idle contract banner."""

    __tablename__ = "idle_banner_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    image_file_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("uploaded_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
