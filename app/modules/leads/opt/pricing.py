from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from app.modules.db.models.opt_unit import OptUnit
from app.modules.leads.opt.tariffs import (
    CATEGORY_LABELS,
    normalize_category_code,
    rate_percent_for_category,
)


def compute_order_pricing(
    lines: list[Any],
    units_by_inn: dict[str, OptUnit],
) -> tuple[Decimal, Decimal, dict[str, dict[str, float]]]:
    volume_by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for line in lines:
        inn = str(line.supplier_inn)
        unit = units_by_inn.get(inn)
        category = normalize_category_code(unit.category_code if unit else None)
        volume_by_category[category] += Decimal(str(line.amount))

    total_volume = Decimal("0")
    total_commission = Decimal("0")
    breakdown: dict[str, dict[str, float]] = {}

    for category, volume in sorted(volume_by_category.items()):
        rate = rate_percent_for_category(category)
        commission = (volume * rate / Decimal("100")).quantize(Decimal("0.01"))
        total_volume += volume
        total_commission += commission
        breakdown[category] = {
            "label": CATEGORY_LABELS.get(category, category),
            "volume": float(volume),
            "rate_percent": float(rate),
            "commission": float(commission),
        }

    return total_volume, total_commission, breakdown


def payment_status(amount_paid: Decimal, commission_due: Decimal) -> str:
    if commission_due <= 0:
        return "paid"
    if amount_paid <= 0:
        return "unpaid"
    if amount_paid + Decimal("0.01") >= commission_due:
        return "paid"
    return "partial"
