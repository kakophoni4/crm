from app.modules.lawyer_registry.tickets_map import merge_unreliable, status_from_company


def test_merge_unreliable_keeps_tax_and_applies_ticket_flags() -> None:
    assert merge_unreliable("Налог", address=True, director=False, founder=False) == "Налог, Адрес"
    assert merge_unreliable("Адрес", address=False, director=True, founder=False) == "Должност.лицо"
    assert merge_unreliable("Налог, Адрес", address=False, director=False, founder=False) == "Налог"
    assert merge_unreliable(None, address=False, director=False, founder=False) is None


def test_status_from_company_liquidation_and_heal() -> None:
    assert status_from_company({"is_liquidated": True}, "Активна") == "Ликвидирована"
    assert status_from_company({"is_liquidating": True}, "Активна") == "В процессе ликвидации"
    assert status_from_company({}, "В процессе ликвидации") == "Активна"
    assert status_from_company({}, "Утиль") == "Утиль"
