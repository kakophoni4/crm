from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.modules.db.models.contact import Contact

_INN_RE = re.compile(r"^\d{10}(\d{2})?$")


def normalize_inn(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        text = str(int(value))
    elif isinstance(value, int):
        text = str(value)
    else:
        text = str(value).strip().replace(" ", "")
        if text.endswith(".0"):
            text = text[:-2]
    if not text or not _INN_RE.match(text):
        return None
    return text


def parse_excel_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except Exception:
        return None


def buyer_from_contact(contact: Contact) -> tuple[str | None, str | None, str | None]:
    """Legacy helper — OPT buyer INN is taken from the uploaded заявка, not the contact."""
    fields = contact.custom_fields or {}
    inn = normalize_inn(
        fields.get("company_inn") or fields.get("inn") or fields.get("buyer_inn"),
    )
    kpp_raw = fields.get("company_kpp") or fields.get("kpp") or fields.get("buyer_kpp")
    kpp = str(kpp_raw).strip() if kpp_raw not in (None, "") else None
    name_raw = (
        fields.get("company_legal_name")
        or fields.get("company_name")
        or fields.get("legal_name")
        or contact.full_name
    )
    name = str(name_raw).strip() if name_raw else contact.full_name
    return inn, kpp, name
