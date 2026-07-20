"""OPT order period_code: normalize + lavka availability checks."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.db.models.opt_unit import OptUnit
from app.modules.db.models.opt_unit_period import OptUnitPeriodAvailability
from app.modules.leads.opt.periods import list_opt_period_codes, normalize_period_code
from app.shared.exceptions import ValidationError


def normalize_requested_period(requested: str) -> str:
    new_code = normalize_period_code(requested)
    if new_code is None or new_code not in set(list_opt_period_codes()):
        raise ValidationError(message="Некорректный период")
    return new_code


async def assert_supplier_inns_allowed_for_period(
    session: AsyncSession,
    *,
    period_code: str,
    supplier_inns: Iterable[str],
) -> None:
    """Reject period change if any order lavka is not allowed for that period."""
    inns = sorted({str(inn).strip() for inn in supplier_inns if str(inn).strip()})
    if not inns:
        return

    result = await session.execute(
        select(OptUnitPeriodAvailability.inn)
        .join(OptUnit, OptUnit.inn == OptUnitPeriodAvailability.inn)
        .where(
            OptUnitPeriodAvailability.period_code == period_code,
            OptUnitPeriodAvailability.inn.in_(inns),
            OptUnit.is_active.is_(True),
        ),
    )
    allowed = {str(inn) for inn in result.scalars().all()}
    blocked = [inn for inn in inns if inn not in allowed]
    if blocked:
        raise ValidationError(
            message=(
                f"Нельзя сменить период на {period_code}: лавки не доступны для этого периода: "
                + ", ".join(blocked)
            ),
            details={"period_code": period_code, "blocked_inns": blocked},
        )
