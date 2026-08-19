"""OPT deal period codes (quarter/year) and helpers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

# UI / storage format: "{quarter}/{yy}" e.g. 2/26 = Q2 2026
_PERIOD_RE = re.compile(r"^([1-4])/(\d{2})$")

# Years shown in the period picker (relative to business need: 2025–2026).
OPT_PERIOD_YEARS = (2025, 2026)

# Park companies — available for 2Q 2026.
PARK_2Q26_INNS: tuple[str, ...] = (
    "7708721010",  # Рысь
    "9729097741",  # Континент
    "9731112362",  # Глория
    "9718148521",  # Лифт Комплекс
    "7743359603",  # К-Пласт
    "7724774530",  # Лорриплюс
    "9731112429",  # Пионер
    "7734474261",  # Кохер
    "9731112323",  # Афина
    "9729355449",  # Паром
    "5011036907",  # ТЭК
    "9718078916",  # Илиона
    "9719029573",  # Дир Партс
)

# Special rearrangements for other quarters.
PERIOD_SPECIAL_INNS: dict[str, tuple[tuple[str, str], ...]] = {
    "3/25": (
        ("7733419099", "Привет"),
        ("7733428671", "Иволга"),
    ),
    "4/25": (
        ("7733418909", "Спектр"),
        ("7733430705", "Орион"),
    ),
}


def period_label(code: str) -> str:
    match = _PERIOD_RE.match(code.strip())
    if match is None:
        return code
    quarter, yy = match.groups()
    return f"{quarter} кв. 20{yy}"


def list_opt_period_codes(*, years: tuple[int, ...] = OPT_PERIOD_YEARS) -> list[str]:
    codes: list[str] = []
    for year in years:
        yy = year % 100
        for quarter in (1, 2, 3, 4):
            codes.append(f"{quarter}/{yy:02d}")
    return codes


def normalize_period_code(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    # Accept "2/26", "2-26", "2.26"
    text = text.replace("-", "/").replace(".", "/")
    match = _PERIOD_RE.match(text)
    if match is None:
        return None
    quarter, yy = match.groups()
    return f"{int(quarter)}/{yy}"


def period_code_to_mole_iso(code: str) -> str | None:
    """Map CRM period ``2/26`` → Mole filter ISO date at quarter start ``2026-04-01``."""
    normalized = normalize_period_code(code)
    if normalized is None:
        return None
    quarter_s, yy_s = normalized.split("/", 1)
    quarter = int(quarter_s)
    year = 2000 + int(yy_s)
    month = (quarter - 1) * 3 + 1
    return f"{year:04d}-{month:02d}-01"


def mole_iso_to_period_code(value: object) -> str | None:
    """Map Mole period ISO ``2026-04-01`` (or datetime) → CRM ``2/26``."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Accept date or datetime prefixes.
    date_part = text[:10]
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_part)
    if match is None:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    if month < 1 or month > 12:
        return None
    quarter = (month - 1) // 3 + 1
    return f"{quarter}/{year % 100:02d}"


def period_code_from_date(value: date) -> str:
    """Map a document date to CRM period ``2/26``."""
    quarter = (value.month - 1) // 3 + 1
    return f"{quarter}/{value.year % 100:02d}"


def _format_ru_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


@dataclass(frozen=True)
class ApplicationPeriodResolution:
    period_code: str
    outlier_dates: tuple[tuple[date, str], ...] = ()


def resolve_application_period(
    dates: Sequence[date],
    *,
    requested_period: str | None = None,
) -> ApplicationPeriodResolution:
    """Infer the application quarter from document dates.

    Majority period wins. Mixed quarters or a mismatch with the selected
    deal period are errors — the application must not be accepted.
    """
    from app.shared.exceptions import ValidationError

    if not dates:
        raise ValidationError(message="В заявке нет дат документов")

    counts: dict[str, int] = {}
    by_period: dict[str, list[date]] = {}
    for value in dates:
        code = period_code_from_date(value)
        counts[code] = counts.get(code, 0) + 1
        by_period.setdefault(code, []).append(value)

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    top_code, top_count = ranked[0]
    tied = any(code != top_code and count == top_count for code, count in ranked)
    if tied:
        parts = [f"{period_label(code)} — {count} шт." for code, count in ranked]
        raise ValidationError(
            message=(
                "Нельзя определить квартал заявки: даты документов из разных "
                "кварталов поровну (" + "; ".join(parts) + "). "
                "Исправьте датирование и загрузите заявку заново."
            ),
            details={"periods": dict(counts)},
        )

    outliers: list[tuple[date, str]] = []
    for code, values in by_period.items():
        if code == top_code:
            continue
        for value in values:
            outliers.append((value, code))
    if outliers:
        outliers.sort(key=lambda item: item[0])
        listed = ", ".join(
            f"{_format_ru_date(value)} ({period_label(code)})" for value, code in outliers
        )
        raise ValidationError(
            message=(
                f"Даты документов не сходятся с кварталом заявки. "
                f"Большинство строк — {period_label(top_code)}, но есть даты другого квартала: "
                f"{listed}. Заявка не принята. Исправьте датирование."
            ),
            details={
                "majority_period": top_code,
                "outlier_dates": [
                    {"date": value.isoformat(), "period_code": code} for value, code in outliers
                ],
            },
        )

    if top_code not in set(list_opt_period_codes()):
        raise ValidationError(
            message=(
                f"Квартал {period_label(top_code)} по датам заявки сейчас нельзя принять "
                "(доступны 2025–2026)."
            ),
            details={"period_code": top_code},
        )

    requested = normalize_period_code(requested_period) if requested_period else None
    if requested and requested != top_code:
        raise ValidationError(
            message=(
                f"Даты документов относятся к {period_label(top_code)}, "
                f"а выбран период {period_label(requested)}. "
                "Исправьте даты или период сделки."
            ),
            details={"inferred_period": top_code, "requested_period": requested},
        )

    return ApplicationPeriodResolution(period_code=top_code, outlier_dates=tuple(outliers))


def read_lead_opt_period(custom_fields: dict | None) -> str | None:
    if not isinstance(custom_fields, dict):
        return None
    order = custom_fields.get("order")
    if not isinstance(order, dict):
        return None
    return normalize_period_code(order.get("period"))
