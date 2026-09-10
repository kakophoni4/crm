from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.accounting.service import AccountingService
from app.modules.db.models.enums import UserRole


async def test_table_fields_use_shared_shop_and_director_in_one_query():
    session = AsyncMock()
    result = MagicMock()
    shop = SimpleNamespace(id=7, inn="1234567890", fns="1234", received_at="2026-09-10",
                           company_status="Работает", unreliable=None, treatment_status=None,
                           comment="Заметка", dirovod="wrong source")
    result.all.return_value = [(shop, "Директор", "Ответственный директора")]
    session.execute.return_value = result
    service = AccountingService(session)
    unit = SimpleNamespace(id=1, inn=shop.inn, name="Лавка", category_code=None,
                           commission_rate_percent=None, volume_limit=None, is_active=True)
    service._repo = SimpleNamespace(
        list_unit_owner_rows=AsyncMock(return_value=[(unit, 10, "Бухгалтер")]),
        list_period_codes_by_inns=AsyncMock(return_value={shop.inn: ["2/26"]}),
    )
    response = await service.list_unit_owners(SimpleNamespace(id=10, role=UserRole.ACCOUNTANT))
    row = response.items[0]
    assert row.shop_fields["dirovod"] == "Ответственный директора"
    assert row.shop_fields["received_at"] == "2026-09-10"
    assert row.shop_fields["fns"] == "1234"
    assert row.shop_fields["comment"] == "Заметка"
    assert row.accountant_full_name == "Бухгалтер"
    assert row.lawyer_director_name == "Директор"
    session.execute.assert_awaited_once()
    service._repo.list_unit_owner_rows.assert_awaited_once_with(accountant_user_id=10)
