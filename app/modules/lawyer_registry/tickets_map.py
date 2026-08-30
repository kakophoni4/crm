"""Map smertniki company/ticket flags onto lawyer-registry shop fields."""

from __future__ import annotations

from typing import Any

_TICKET_UNRELIABLE = frozenset({"адрес", "должност.лицо", "должностное лицо", "учредитель", "дл"})
_LIQUIDATION_STATUSES = frozenset({"ликвидирована", "в процессе ликвидации"})


def payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return [row for row in items if isinstance(row, dict)]
    return []


def merge_unreliable(
    existing: str | None,
    *,
    address: bool,
    director: bool,
    founder: bool,
) -> str | None:
    kept: list[str] = []
    for part in (existing or "").replace(";", ",").split(","):
        token = part.strip()
        if not token:
            continue
        if token.casefold() in _TICKET_UNRELIABLE:
            continue
        if token not in kept:
            kept.append(token)
    if address:
        kept.append("Адрес")
    if director or founder:
        kept.append("Должност.лицо")
    return ", ".join(kept) or None


def status_from_company(company: dict[str, Any], current: str | None) -> str | None:
    if company.get("is_liquidated"):
        return "Ликвидирована"
    if company.get("is_liquidating"):
        return "В процессе ликвидации"
    if (current or "").strip().casefold() in _LIQUIDATION_STATUSES:
        return "Активна"
    return current
