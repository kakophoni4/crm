from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def split_vat_included(total: Decimal, *, rate_percent: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Return (total, vat, without_vat) when total includes VAT."""
    divisor = Decimal("1") + (rate_percent / Decimal("100"))
    without_vat = (total / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    vat = (total - without_vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), vat, without_vat
