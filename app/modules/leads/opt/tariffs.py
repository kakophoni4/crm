from __future__ import annotations

from decimal import Decimal

OPT_CATEGORY_TECH = "TECH"
OPT_CATEGORY_ELITE = "L"
OPT_CATEGORY_EXCLUSIVE = "E"
OPT_CATEGORY_PREMIUM = "F"
OPT_CATEGORY_A = "A"
OPT_CATEGORY_T = "T"
OPT_CATEGORY_OPTIMA = "O"

ALL_CATEGORY_CODES: tuple[str, ...] = (
    OPT_CATEGORY_ELITE,
    OPT_CATEGORY_EXCLUSIVE,
    OPT_CATEGORY_PREMIUM,
    OPT_CATEGORY_A,
    OPT_CATEGORY_T,
    OPT_CATEGORY_OPTIMA,
    OPT_CATEGORY_TECH,
)

CATEGORY_LABELS: dict[str, str] = {
    OPT_CATEGORY_ELITE: "Абсолют (L)",
    OPT_CATEGORY_EXCLUSIVE: "Эксклюзив (E)",
    OPT_CATEGORY_PREMIUM: "Премиум (F)",
    OPT_CATEGORY_A: "1 категория (A)",
    OPT_CATEGORY_T: "Категория (T)",
    OPT_CATEGORY_OPTIMA: "Оптима",
    OPT_CATEGORY_TECH: "Техничка",
}

# Base rate per category (%). Tiered L/E thresholds apply to quarterly volume in 1C later.
CATEGORY_BASE_RATE_PERCENT: dict[str, Decimal] = {
    OPT_CATEGORY_ELITE: Decimal("3.5"),
    OPT_CATEGORY_EXCLUSIVE: Decimal("3.4"),
    OPT_CATEGORY_PREMIUM: Decimal("3.0"),
    OPT_CATEGORY_A: Decimal("2.7"),
    OPT_CATEGORY_T: Decimal("2.7"),
    OPT_CATEGORY_OPTIMA: Decimal("2.8"),
    OPT_CATEGORY_TECH: Decimal("1.3"),
}

PARK_CATEGORY_LABEL_TO_CODE: dict[str, str] = {
    "абсолют": OPT_CATEGORY_ELITE,
    "оптима": OPT_CATEGORY_OPTIMA,
    "техничка": OPT_CATEGORY_TECH,
}


def normalize_category_code(value: str | None) -> str:
    code = (value or OPT_CATEGORY_TECH).strip().upper()
    if code not in CATEGORY_BASE_RATE_PERCENT:
        return OPT_CATEGORY_TECH
    return code


def rate_percent_for_category(category_code: str) -> Decimal:
    return CATEGORY_BASE_RATE_PERCENT[normalize_category_code(category_code)]


def rate_percent_for_unit(unit: object | None, *, category_code: str) -> Decimal:
    if unit is not None:
        custom = getattr(unit, "commission_rate_percent", None)
        if custom is not None:
            return Decimal(str(custom))
    return rate_percent_for_category(category_code)
