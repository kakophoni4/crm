from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.leads.opt.repository import OptOrderRepository
from app.modules.leads.service_types import SERVICE_TYPE_OPT
from app.shared.exceptions import ValidationError


async def assert_lead_won_payment_allowed(
    session: AsyncSession,
    lead_id: int,
    service_name: str | None,
) -> None:
    if service_name != SERVICE_TYPE_OPT:
        return
    repo = OptOrderRepository(session)
    if await repo.lead_has_unpaid_orders(lead_id):
        raise ValidationError(
            message="Нельзя закрыть сделку ОПТ как успешную: не все заявки оплачены полностью",
        )
