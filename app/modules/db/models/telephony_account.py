from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.db.models.base import Base


class TelephonyAccount(Base):
    __tablename__ = "telephony_accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="bitcall")
    department_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    group_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sip_host: Mapped[str] = mapped_column(Text, nullable=False)
    sip_port: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5060")
    sip_transport: Mapped[str] = mapped_column(Text, nullable=False, server_default="udp")
    sip_username: Mapped[str] = mapped_column(Text, nullable=False)
    sip_password_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    outbound_caller_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    pbx_extension_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    webrtc_ws_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
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
