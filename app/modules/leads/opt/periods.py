"""OPT deal period codes (quarter/year) and helpers."""

from __future__ import annotations

import re

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


def read_lead_opt_period(custom_fields: dict | None) -> str | None:
    if not isinstance(custom_fields, dict):
        return None
    order = custom_fields.get("order")
    if not isinstance(order, dict):
        return None
    return normalize_period_code(order.get("period"))
