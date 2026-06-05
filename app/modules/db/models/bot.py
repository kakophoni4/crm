from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, LargeBinary, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, INET
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base
from app.modules.db.models.enums import BotOwnerType, bot_owner_type_pg


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    owner_type: Mapped[BotOwnerType] = mapped_column(bot_owner_type_pg, nullable=False)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    department_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    inbound_secret_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    outbound_secret_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    outbound_url: Mapped[str] = mapped_column(Text, nullable=False)
    health_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_allowlist: Mapped[list[Any] | None] = mapped_column(ARRAY(INET), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_health_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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
