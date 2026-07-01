from __future__ import annotations

from app.modules.leads.opt.buyer_lookup import lookup_buyer_by_inn


def test_lookup_navel_buyer() -> None:
    kpp, name = lookup_buyer_by_inn("5507266215")
    assert kpp == "550701001"
    assert name == "НАВЕЛ КО ООО"


def test_lookup_unknown_buyer() -> None:
    kpp, name = lookup_buyer_by_inn("1234567890")
    assert kpp is None
    assert name is None
