from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.modules.leads.opt.contact_buyer import normalize_inn

_BUYERS_PATH = Path(__file__).resolve().parent / "data" / "opt-known-buyers.json"


@lru_cache(maxsize=1)
def _load_known_buyers() -> dict[str, dict[str, str]]:
    if not _BUYERS_PATH.is_file():
        return {}
    try:
        raw = json.loads(_BUYERS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    known: dict[str, dict[str, str]] = {}
    for inn, row in raw.items():
        if not isinstance(row, dict):
            continue
        normalized = normalize_inn(inn)
        if normalized is None:
            continue
        kpp = str(row.get("kpp", "")).strip() or None
        name = str(row.get("name", "")).strip() or None
        if kpp or name:
            known[normalized] = {"kpp": kpp or "", "name": name or ""}
    return known


def lookup_buyer_by_inn(inn: str) -> tuple[str | None, str | None]:
    row = _load_known_buyers().get(inn)
    if not row:
        return None, None
    kpp = row.get("kpp") or None
    name = row.get("name") or None
    return kpp, name
