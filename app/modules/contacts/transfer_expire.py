from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chats.timeutil import utc_now
from app.modules.db.models.contact_group_transfer import ContactGroupTransfer
from app.modules.db.models.enums import CONTACT_TRANSFER_ACTIVE_STATES, TransferStatus
from app.realtime.events import publish

logger = structlog.get_logger(__name__)


@dataclass
class TransferExpireResult:
    expired: int = 0


async def expire_stale_transfers(session: AsyncSession) -> TransferExpireResult:
    now = utc_now()
    result = await session.execute(
        select(ContactGroupTransfer)
        .where(
            ContactGroupTransfer.state.in_(CONTACT_TRANSFER_ACTIVE_STATES),
            ContactGroupTransfer.expires_at <= now,
        )
        .with_for_update(skip_locked=True),
    )
    rows = list(result.scalars().all())
    expired = 0
    for transfer in rows:
        transfer.state = TransferStatus.EXPIRED
        expired += 1
        await publish(
            "transfer.expired",
            {"transfer_id": transfer.id},
            scope={"group_id": transfer.group_id},
        )
        await publish(
            "contact.transfer.expired",
            {
                "transfer_id": transfer.id,
                "contact_id": transfer.contact_id,
                "group_id": transfer.group_id,
                "state": TransferStatus.EXPIRED.value,
            },
            scope={"group_id": transfer.group_id},
        )
        logger.info(
            "transfer_expired",
            transfer_id=transfer.id,
            contact_id=transfer.contact_id,
            group_id=transfer.group_id,
        )
    return TransferExpireResult(expired=expired)
