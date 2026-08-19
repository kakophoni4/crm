from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.modules.leads.opt.periods import normalize_period_code

ALLOWED_OPT_VAT_RATES = (Decimal("20"), Decimal("22"))
VAT_RATE_BEFORE_2026 = Decimal("20")
VAT_RATE_FROM_2026 = Decimal("22")


def vat_rate_for_period_code(period_code: str | None) -> Decimal:
    """20% through 2025, 22% from Q1 2026 onwards."""
    normalized = normalize_period_code(period_code)
    if normalized is None:
        return VAT_RATE_FROM_2026
    _quarter, yy = normalized.split("/", 1)
    year = 2000 + int(yy)
    if year < 2026:
        return VAT_RATE_BEFORE_2026
    return VAT_RATE_FROM_2026


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
