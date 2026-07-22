from __future__ import annotations

from app.modules.leads.opt.periods import mole_iso_to_period_code, period_code_to_mole_iso
from app.modules.leads.opt.sync_diff import plan_sync_actions, registries_match


def test_period_code_to_mole_iso_q2_2026() -> None:
    assert period_code_to_mole_iso("2/26") == "2026-04-01"
    assert period_code_to_mole_iso("1/25") == "2025-01-01"
    assert period_code_to_mole_iso("4/26") == "2026-10-01"
    assert period_code_to_mole_iso("bad") is None


def test_mole_iso_to_period_code_roundtrip() -> None:
    assert mole_iso_to_period_code("2026-04-01") == "2/26"
    assert mole_iso_to_period_code("2026-04-01T00:00:00") == "2/26"
    assert mole_iso_to_period_code("2025-01-15") == "1/25"
    for code in ("1/25", "2/26", "3/26", "4/25"):
        iso = period_code_to_mole_iso(code)
        assert iso is not None
        assert mole_iso_to_period_code(iso) == code


def _payload(*, line_amount: float = 100.0) -> dict:
    return {
        "CRMid": "crm-order-1",
        "Покупатель": {"ИНН": "564200586550", "КПП": "", "Наименование": "ИП"},
        "Реестр": [
            {
                "CRMid": "crm-line-1",
                "Поставщик": {"ИНН": "9731112362", "КПП": "773101001", "Наименование": "ГЛОРИЯ"},
                "ДатаДокумента": "2026-05-25",
                "Сумма": line_amount,
                "СуммаНДС": 18.03,
                "СуммаБезНДС": 81.97,
            },
        ],
    }


def test_registries_match_tolerates_float_noise() -> None:
    expected = _payload(line_amount=100.0)
    actual = _payload(line_amount=100.005)
    assert registries_match(expected, actual)


def test_registries_match_detects_amount_change() -> None:
    expected = _payload(line_amount=100.0)
    actual = _payload(line_amount=200.0)
    assert not registries_match(expected, actual)


def test_plan_sync_update_restore_delete() -> None:
    local_payloads = {
        "crm-order-1": _payload(),
        "crm-order-2": _payload(),
    }
    local_payloads["crm-order-2"]["CRMid"] = "crm-order-2"
    local_payloads["crm-order-2"]["Реестр"][0]["CRMid"] = "crm-line-2"

    mole_orders = [
        {
            "CRMid": "crm-order-1",
            "Удален": False,
            "Покупатель": {"ИНН": "564200586550"},
            "Реестр": local_payloads["crm-order-1"]["Реестр"],
        },
        {
            "CRMid": "crm-order-2",
            "Удален": True,
            "Реестр": [],
        },
        {
            "CRMid": "crm-order-extra",
            "Удален": False,
            "Реестр": [],
        },
    ]
    # Make order-1 differ so it needs update
    mole_orders[0]["Реестр"] = [
        {
            **local_payloads["crm-order-1"]["Реестр"][0],
            "Сумма": 999.0,
        },
    ]

    actions = {
        crm_id: kind
        for kind, crm_id in plan_sync_actions(
            local_crm_ids=set(local_payloads),
            local_payloads=local_payloads,
            mole_orders=mole_orders,
        )
    }
    assert actions["crm-order-1"] == "update"
    assert actions["crm-order-2"] == "restore"
    assert actions["crm-order-extra"] == "delete_extra"


def test_plan_sync_unchanged() -> None:
    payload = _payload()
    mole = {
        "CRMid": "crm-order-1",
        "Удален": False,
        "Покупатель": {"ИНН": "564200586550"},
        "Реестр": payload["Реестр"],
    }
    actions = plan_sync_actions(
        local_crm_ids={"crm-order-1"},
        local_payloads={"crm-order-1": payload},
        mole_orders=[mole],
    )
    assert actions == [("unchanged", "crm-order-1")]
