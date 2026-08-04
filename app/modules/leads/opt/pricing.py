from __future__ import annotations

from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.modules.db.models.opt_unit import OptUnit
from app.modules.leads.opt.tariffs import (
    CATEGORY_LABELS,
    normalize_category_code,
    rate_percent_for_unit,
)

# Commission and payments are whole rubles (no kopecks).
RUBLE = Decimal("1")


def round_rubles(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(RUBLE, rounding=ROUND_HALF_UP)


def compute_order_pricing(
    lines: list[Any],
    units_by_inn: dict[str, OptUnit],
) -> tuple[Decimal, Decimal, dict[str, dict[str, float]]]:
    """Commission is per supplier rate, not one rate for the whole category.

    Previously volume was summed by category and the *first* unit's rate was applied
    to the whole bucket — so Кохер @2.8% inside L/Абсолют was billed at 3.5% if
    another L-supplier appeared first.
    """
    volume_by_cat_rate: dict[tuple[str, Decimal], Decimal] = defaultdict(lambda: Decimal("0"))

    for line in lines:
        inn = str(line.supplier_inn)
        unit = units_by_inn.get(inn)
        category = normalize_category_code(unit.category_code if unit else None)
        rate = rate_percent_for_unit(unit, category_code=category)
        volume_by_cat_rate[(category, rate)] += Decimal(str(line.amount))

    cat_rate_counts = Counter(category for category, _rate in volume_by_cat_rate)

    total_volume = Decimal("0")
    total_commission = Decimal("0")
    breakdown: dict[str, dict[str, float]] = {}

    for (category, rate), volume in sorted(
        volume_by_cat_rate.items(),
        key=lambda item: (item[0][0], item[0][1]),
    ):
        commission = round_rubles(volume * rate / Decimal("100"))
        total_volume += volume
        total_commission += commission
        base_label = CATEGORY_LABELS.get(category, category)
        if cat_rate_counts[category] > 1:
            # Same category, different custom rates — show separately.
            key = f"{category}@{rate}"
            label = f"{base_label} · {rate}%"
        else:
            key = category
            label = base_label
        breakdown[key] = {
            "label": label,
            "volume": float(volume),
            "rate_percent": float(rate),
            "commission": float(commission),
        }

    return total_volume, round_rubles(total_commission), breakdown


def payment_status(amount_paid: Decimal, commission_due: Decimal) -> str:
    """Paid when remainder is under 1 ₽ (kopeck tails count as paid)."""
    due = Decimal(str(commission_due or 0))
    paid = Decimal(str(amount_paid or 0))
    if due <= 0:
        return "paid"
    if paid <= 0:
        return "unpaid"
    if paid + Decimal("0.999") >= due:
        return "paid"
    return "partial"


def commission_base_from_breakdown(breakdown: dict[str, object] | None) -> Decimal:
    total = Decimal("0")
    if not isinstance(breakdown, dict):
        return total
    for row in breakdown.values():
        if isinstance(row, dict):
            total += Decimal(str(row.get("commission", 0)))
    return round_rubles(total)
