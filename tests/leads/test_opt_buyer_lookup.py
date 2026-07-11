from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.leads.opt import buyer_lookup
from app.modules.leads.opt.buyer_lookup import lookup_buyer_by_inn


def test_lookup_example_buyer(monkeypatch: pytest.MonkeyPatch) -> None:
    example = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "leads"
        / "opt"
        / "data"
        / "opt-known-buyers.example.json"
    )
    monkeypatch.setattr(buyer_lookup, "_BUYERS_PATH", example)
    buyer_lookup._load_known_buyers.cache_clear()

    kpp, name = lookup_buyer_by_inn("7700000100")
    assert kpp == "770001001"
    assert name == 'ООО "Тестовый покупатель"'


def test_lookup_unknown_buyer(monkeypatch: pytest.MonkeyPatch) -> None:
    example = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "leads"
        / "opt"
        / "data"
        / "opt-known-buyers.example.json"
    )
    monkeypatch.setattr(buyer_lookup, "_BUYERS_PATH", example)
    buyer_lookup._load_known_buyers.cache_clear()

    kpp, name = lookup_buyer_by_inn("1234567890")
    assert kpp is None
    assert name is None
