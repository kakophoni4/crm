from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

ALLOWED_OPT_VAT_RATES = (Decimal("20"), Decimal("22"))


def normalize_opt_vat_rate(rate: Decimal | float | int | str | None) -> Decimal:
    """Accept only 20 or 22 percent for OPT applications."""
    if rate is None:
        return Decimal("22")
    value = Decimal(str(rate)).quantize(Decimal("1"))
    if value not in ALLOWED_OPT_VAT_RATES:
        raise ValueError("VAT rate must be 20 or 22")
    return value


def split_vat_included(total: Decimal, *, rate_percent: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Return (total, vat, without_vat) when total includes VAT."""
    divisor = Decimal("1") + (rate_percent / Decimal("100"))
    without_vat = (total / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    vat = (total - without_vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), vat, without_vat
